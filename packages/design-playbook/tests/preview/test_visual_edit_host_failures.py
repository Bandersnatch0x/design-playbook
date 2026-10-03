"""HOST fault injection against real HTTP and durable plugin review artifacts.

The candidate is deterministic test input, not a model invocation. Patches are
only at the host CLI stdin/OS boundaries; plugin decisions and HTTP are real.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from .test_visual_edit_host_e2e import FIXTURE, PACKAGE, create_server, stage_review

import applier  # noqa: E402


def file_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.mark.parametrize(("fault", "diagnostic"), [
    ("source_drift", "stale"),
    ("candidate_changed", "review changed while awaiting confirmation"),
    ("replace_failure", "injected locked styles.css"),
    ("post_write_observation", "post-write observation failed; styles.css was replaced; rollback succeeded"),
    ("restore_failure", "post-write observation failed; styles.css was replaced; rollback failed: injected restore failure"),
    ("wrong_confirmation", "explicit hash-bound host confirmation required"),
])
def test_host_failure_preserves_plugin_authority(tmp_path: Path, fault: str, diagnostic: str) -> None:
    root = tmp_path / "host-source"
    root.mkdir()
    for name in ("index.html", "styles.css"):
        shutil.copyfile(FIXTURE / name, root / name)
    before_source = {p.name: p.read_bytes() for p in root.iterdir()}
    server = create_server(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    route = f"http://127.0.0.1:{server.server_port}/"
    run = tmp_path / "run"
    preview = run / "preview"
    audit = {"active": True, "pluginSourceWrites": []}

    def protect_plugin_source(event, args):
        if not audit["active"]:
            return
        paths = []
        if event == "open" and isinstance(args[0], (str, bytes)) and args[2] & (os.O_WRONLY | os.O_RDWR):
            paths = [args[0]]
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename"):
            paths = args[:2] if event == "os.rename" else args[:1]
        for raw in paths:
            if not Path(os.fsdecode(raw)).resolve().is_relative_to(root):
                continue
            frame = sys._getframe()
            while frame is not None:
                if Path(frame.f_code.co_filename).resolve().is_relative_to(PACKAGE / "mcp"):
                    audit["pluginSourceWrites"].append(str(raw))
                    raise AssertionError(f"Plugin source write during HOST failure: {event} {raw}")
                frame = frame.f_back

    # Remains active during apply too: imported plugin observation/validation
    # cannot transiently write-and-restore source while final hashes stay equal.
    sys.addaudithook(protect_plugin_source)
    try:
        result, observation = stage_review(root, preview, route)
        assert result["confirmed"] is True  # Preview approval only, not source approval.
        assert observation["pluginSourceWrites"] == []
        assert before_source == {p.name: p.read_bytes() for p in root.iterdir()}
        handoff = Path(result["confirm_record_path"])
        record = json.loads(handoff.read_bytes())
        assert record["visual_handoff"]["status"] == "pending-review"
        assert record["visual_handoff"]["writesSource"] is False
        # An explicitly test-owned, pre-existing evidence sentinel is not a
        # fabricated capture/verdict; it makes the no-pollution check non-vacuous.
        evidence = run / "evidence"
        evidence.mkdir()
        (evidence / "existing-test-artifact.bin").write_bytes(b"pre-existing test artifact\x00\xff")
        before_authority = file_hashes(run)
        for pattern in ("preview/decision-round-*.json", "preview/confirm-round-*.json",
                        "preview/log.md", "preview/ledger/*", "evidence/*"):
            assert list(run.glob(pattern)), pattern
        candidate = tmp_path / "agent-candidate.css"
        candidate_bytes = before_source["styles.css"] + b"\n#next-read { padding: 24px; }\n"
        candidate.write_bytes(candidate_bytes)
        proposal, _ = applier.review(root, handoff, candidate, route)
        assert proposal["pluginWritesSource"] is False
        expected_source = dict(before_source)
        replacements = []
        real_replace = applier.os.replace
        stdout, stderr = io.StringIO(), io.StringIO()

        def confirmation() -> str:
            # Inject AFTER apply prints its own proposal, before it re-reviews.
            assert "Type exactly: " + proposal["confirmation"] in stdout.getvalue()
            if fault == "source_drift":
                expected_source["styles.css"] += b"/* external writer during confirmation */\n"
                (root / "styles.css").write_bytes(expected_source["styles.css"])
            elif fault == "candidate_changed":
                candidate.write_bytes(candidate_bytes + b"/* swapped after review */\n")
            return ("APPLY wrong-hash" if fault == "wrong_confirmation" else proposal["confirmation"]) + "\n"

        def replace(source, target) -> None:
            assert Path(target) == root / "styles.css"
            replacements.append(str(target))
            if fault == "replace_failure":
                raise PermissionError("injected locked styles.css")
            assert Path(source).read_bytes() == (
                candidate_bytes if len(replacements) == 1 else before_source["styles.css"])
            if fault == "restore_failure" and len(replacements) == 2:
                raise PermissionError("injected restore failure")
            real_replace(source, target)
            assert (root / "styles.css").read_bytes() == (
                candidate_bytes if len(replacements) == 1 else before_source["styles.css"])
            if fault in ("post_write_observation", "restore_failure") and len(replacements) == 1:
                # Real replacement, then the real HTTP listener disappears.
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                assert not thread.is_alive()
                if fault == "restore_failure":
                    expected_source["styles.css"] = candidate_bytes

        argv = ["applier.py", "apply", "--root", str(root), "--handoff", str(handoff),
                "--candidate", str(candidate), "--route-url", route]
        with patch.object(sys, "argv", argv), patch.object(sys, "stdin") as stdin, \
                patch.object(applier.os, "replace", side_effect=replace), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            stdin.readline.side_effect = confirmation
            exit_code = applier.main()
        print(f"FAULT {fault} exit={exit_code}\nSTDOUT\n{stdout.getvalue()}STDERR\n{stderr.getvalue()}")
        after_authority = file_hashes(run)
        print("AUTHORITY " + json.dumps({"before": before_authority, "after": after_authority}, sort_keys=True))
        assert after_authority == before_authority  # Bytes AND artifact set unchanged.
        assert json.loads(handoff.read_bytes())["visual_handoff"] == record["visual_handoff"]
        assert observation["pluginSourceWrites"] == []
        assert audit["pluginSourceWrites"] == []
        assert expected_source == {p.name: p.read_bytes() for p in root.iterdir()}
        assert len(replacements) == {"replace_failure": 1, "post_write_observation": 2,
                                     "restore_failure": 2}.get(fault, 0)
        assert exit_code == 2
        assert diagnostic in stderr.getvalue()
        assert "REFUSED:" in stderr.getvalue()
        assert not any(line.startswith("{") for line in stdout.getvalue().splitlines())
        # Failure has no success receipt; the *existing* Preview confirmation
        # stays pending and must not become source-applied/source-confirmed.
        errors = [line.removeprefix("REFUSED: ") for line in stderr.getvalue().splitlines()
                  if line.startswith("REFUSED: ")]
        assert len(errors) == 1
        error = json.loads(errors[0])
        assert error["status"] == "error"
        assert error["owner"] == "host-applier"
        assert error["pluginWritesSource"] is False
        assert diagnostic in error["error"]
        assert not ({"applied", "confirmed", "afterSourceHash"} & error.keys())
        if fault in ("post_write_observation", "restore_failure"):
            assert error["writeApplied"] is True
            assert error["observationFailed"] is True
            assert error["rollbackAttempted"] is True
            assert "live route observation failed" in error["observationError"]
            before_hash = hashlib.sha256(before_source["styles.css"]).hexdigest()
            after_hash = hashlib.sha256((root / "styles.css").read_bytes()).hexdigest()
            if fault == "post_write_observation":
                assert error["rolledBack"] is True
                assert "rollbackError" not in error
                assert after_hash == before_hash
            else:
                assert error["rolledBack"] is False
                assert error["rollbackError"] == "injected restore failure"
                assert after_hash == hashlib.sha256(candidate_bytes).hexdigest()
                assert after_hash != before_hash
            print("ROLLBACK " + json.dumps({"beforeStylesHash": before_hash,
                  "afterStylesHash": after_hash, "rolledBack": error["rolledBack"]}))
        print("BOUNDARY pluginWritesSource=false; pluginSourceWrites=[]; authority byte-identical; status=error; no success receipt")
    finally:
        audit["active"] = False
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
