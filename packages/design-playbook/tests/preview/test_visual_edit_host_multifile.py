"""HOST-owned multi-file candidates; real browser handoff/HTTP, no model claim."""
from __future__ import annotations

import hashlib
import io
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from .test_visual_edit_host_e2e import FIXTURE, create_server, host_cli, stage_review
from .test_visual_edit_host_failures import file_hashes

import applier  # noqa: E402


@pytest.fixture
def host_case(tmp_path: Path, request):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("index.html", "styles.css"):
        shutil.copyfile(FIXTURE / name, root / name)
    if getattr(request, "param", False):
        for name in ("assets.json", "palette.json"):
            shutil.copyfile(FIXTURE / name, root / name)
    # Exact restoration must preserve CRLF, not merely equivalent decoded text.
    for path in root.iterdir():
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    server = create_server(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    route = f"http://127.0.0.1:{server.server_port}/"
    run = tmp_path / "run"
    try:
        result, observation = stage_review(root, run / "preview", route)
        assert result["confirmed"] is True
        assert observation["pluginSourceWrites"] == []
        handoff = Path(result["confirm_record_path"])
        assert json.loads(handoff.read_bytes())["visual_handoff"]["writesSource"] is False
        authority = file_hashes(run)
        candidate = tmp_path / "candidate"
        candidate.mkdir()
        contents = {"index.html": before["index.html"] + b"\r\n<!-- agent candidate -->\r\n",
                    "styles.css": before["styles.css"] + b"\r\n#next-read { padding: 24px; }\r\n"}
        for name, content in contents.items():
            (candidate / name).write_bytes(content)
        yield SimpleNamespace(root=root, candidate=candidate, route=route, handoff=handoff,
                              before=before, contents=contents, server=server, thread=thread)
        assert file_hashes(run) == authority
        print("BOUNDARY pluginWritesSource=false; plugin authority byte-identical")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def read_source(case) -> dict[str, bytes]:
    return {path.relative_to(case.root).as_posix(): path.read_bytes()
            for path in case.root.rglob("*") if path.is_file()}


def test_multifile_apply_records_every_file_hash(host_case) -> None:
    case = host_case
    reviewed = host_cli("review", case.root, case.handoff, case.candidate, case.route)
    print("REVIEW", reviewed.returncode, reviewed.stdout, reviewed.stderr)
    assert reviewed.returncode == 0
    proposal = json.loads(reviewed.stdout)
    assert set(proposal["files"]) == {"index.html", "styles.css"}
    for name in case.before:
        assert f"--- a/{name}" in proposal["diff"]
        assert f"+++ b/{name}" in proposal["diff"]
        assert proposal["files"][name] == {
            "beforeHash": hashlib.sha256(case.before[name]).hexdigest(),
            "afterHash": hashlib.sha256(case.contents[name]).hexdigest(),
        }
    result = host_cli("apply", case.root, case.handoff, case.candidate, case.route,
                      proposal["confirmation"] + "\n")
    print("APPLY", result.returncode, result.stdout, result.stderr)
    assert result.returncode == 0
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt["outcome"] == "applied"
    assert receipt["files"] == proposal["files"]
    assert receipt["pluginWritesSource"] is False
    assert receipt["beforeHostSourceHash"] != receipt["afterHostSourceHash"]
    assert receipt["beforeSourceHash"] != receipt["afterSourceHash"]
    assert read_source(case) == case.contents
    assert not (case.root.parent / ("." + case.root.name + ".applier.lock")).exists()


def apply_in_process(case, confirmation=None):
    proposal, _ = applier.review(case.root, case.handoff, case.candidate, case.route)
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = ["applier.py", "apply", "--root", str(case.root), "--handoff", str(case.handoff),
            "--candidate", str(case.candidate), "--route-url", case.route]
    with patch.object(sys, "argv", argv), patch.object(sys, "stdin") as stdin, \
            redirect_stdout(stdout), redirect_stderr(stderr):
        stdin.readline.side_effect = confirmation or (lambda: proposal["confirmation"] + "\n")
        code = applier.main()
    print("CLI", code, "STDOUT", stdout.getvalue(), "STDERR", stderr.getvalue())
    if code:
        assert not any(line.startswith("{") for line in stdout.getvalue().splitlines())
        errors = [line.removeprefix("REFUSED: ") for line in stderr.getvalue().splitlines()
                  if line.startswith("REFUSED: ")]
        assert len(errors) == 1
        diagnostic = json.loads(errors[0])
        assert diagnostic["status"] == "error"
        assert diagnostic["pluginWritesSource"] is False
        return code, diagnostic
    return code, json.loads(stdout.getvalue().splitlines()[-1])


def test_multifile_partial_commit_failure_restores_all_files(host_case) -> None:
    case = host_case
    real_replace = applier.os.replace
    committed = []
    staged_at_commit = []

    def replace(source, target):
        if not committed:
            staged_at_commit.extend(path.read_bytes() for path in case.root.iterdir()
                                    if path.name not in case.before)
        if Path(target).name == "styles.css":
            raise PermissionError("injected second-file commit failure")
        real_replace(source, target)
        committed.append(Path(target).name)

    with patch.object(applier.os, "replace", side_effect=replace):
        code, diagnostic = apply_in_process(case)
    assert code == 2
    assert read_source(case) == case.before
    assert all(content in staged_at_commit for content in case.contents.values())
    assert committed == ["index.html", "index.html"]  # Initial commit plus restoration.
    assert diagnostic["outcome"] == "failed"
    assert diagnostic["phase"] == "commit"
    assert diagnostic["reason"] == "injected second-file commit failure"
    assert diagnostic["committedFiles"] == ["index.html"]
    assert diagnostic["rollbackAttempted"] is True
    assert diagnostic["rolledBack"] is True
    assert diagnostic["rollbackErrors"] == {}
    print("ALL-OR-NOTHING", json.dumps(file_hashes(case.root), sort_keys=True))


@pytest.mark.parametrize("restore_failure", [False, True], ids=["restored", "restore-failed"])
def test_multifile_observation_failure_restores_every_file(host_case, restore_failure) -> None:
    case = host_case
    real_replace = applier.os.replace
    attempts = []

    def replace(source, target):
        name = Path(target).name
        attempts.append(name)
        if restore_failure and len(attempts) == 3:
            assert name == "index.html"
            raise PermissionError("injected index restore failure")
        real_replace(source, target)
        if len(attempts) == 2:
            assert read_source(case) == case.contents
            case.server.shutdown()
            case.server.server_close()
            case.thread.join(timeout=5)
            assert not case.thread.is_alive()

    with patch.object(applier.os, "replace", side_effect=replace):
        code, diagnostic = apply_in_process(case)
    assert code == 2
    expected = dict(case.before)
    if restore_failure:
        expected["index.html"] = case.contents["index.html"]
    assert read_source(case) == expected
    assert attempts == ["index.html", "styles.css", "index.html", "styles.css"]
    assert diagnostic["outcome"] == "failed"
    assert diagnostic["phase"] == "observation"
    assert diagnostic["writeApplied"] is True
    assert diagnostic["committedFiles"] == ["index.html", "styles.css"]
    assert diagnostic["rollbackAttempted"] is True
    assert diagnostic["observationFailed"] is True
    assert "live route observation failed" in diagnostic["observationError"]
    assert diagnostic["rolledBack"] is (not restore_failure)
    assert diagnostic["rollbackErrors"] == (
        {"index.html": "injected index restore failure"} if restore_failure else {})
    print("ROLLBACK", json.dumps({"before": {name: hashlib.sha256(data).hexdigest()
          for name, data in case.before.items()}, "after": file_hashes(case.root),
          "rolledBack": diagnostic["rolledBack"]}, sort_keys=True))


def test_later_concurrent_applier_refuses_while_first_completes(host_case) -> None:
    case = host_case
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    argv = [sys.executable, "-X", "utf8", str(FIXTURE / "applier.py"), "apply",
            "--root", str(case.root), "--handoff", str(case.handoff),
            "--candidate", str(case.candidate), "--route-url", case.route]
    lines = []
    output = queue.Queue()
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr:
        first = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=stderr, text=True, encoding="utf-8")

        def read_stdout():
            for line in first.stdout:
                lines.append(line)
                output.put(line)
            output.put(None)

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        try:
            while True:
                line = output.get(timeout=20)
                assert line is not None, "first applier exited before confirmation"
                if line.startswith("Type exactly: "):
                    confirmation = line.removeprefix("Type exactly: ")
                    break
            marker = lock.read_bytes() if lock.exists() else None
            later = host_cli("apply", case.root, case.handoff, case.candidate,
                             case.route, confirmation)
            while_first_waits = read_source(case)
            assert first.poll() is None
            marker_after = lock.read_bytes() if lock.exists() else None
            first.stdin.write(confirmation)
            first.stdin.flush()
            first.stdin.close()
            code = first.wait(timeout=20)
            reader.join(timeout=5)
            assert not reader.is_alive()
            stderr.seek(0)
            print("FIRST", code, "".join(lines), stderr.read())
            print("LATER", later.returncode, later.stdout, later.stderr)
            assert later.returncode == 2
            diagnostic = json.loads(later.stderr.removeprefix("REFUSED: "))
            assert diagnostic["reason"] == "applier-lock-exists"
            assert diagnostic["phase"] == "lock"
            assert diagnostic["outcome"] == "failed"
            assert diagnostic["lockOwner"]["pid"] == first.pid
            assert diagnostic["lockOwner"]["owner"] == "host-applier"
            assert diagnostic["lockOwner"]["nonce"]
            assert "stale locks require explicit inspection and removal" in diagnostic["error"]
            assert marker is not None and marker_after == marker
            assert while_first_waits == case.before
            assert code == 0
            receipt = json.loads(lines[-1])
            assert receipt["outcome"] == "applied"
            assert read_source(case) == case.contents
            assert not lock.exists()
        finally:
            if first.poll() is None:
                first.kill()
                first.wait(timeout=5)
            reader.join(timeout=5)
            first.stdout.close()
            if not first.stdin.closed:
                first.stdin.close()


def test_stale_lock_is_refused_until_explicit_removal(host_case) -> None:
    case = host_case
    exited = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True, timeout=5)
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    marker = json.dumps({"owner": "host-applier", "pid": int(exited.stdout),
                         "nonce": "exited-test-owner", "sourceRoot": str(case.root)}).encode()
    lock.write_bytes(marker)
    reviewed = host_cli("review", case.root, case.handoff, case.candidate, case.route)
    assert reviewed.returncode == 0
    phrase = json.loads(reviewed.stdout)["confirmation"] + "\n"
    refused = host_cli("apply", case.root, case.handoff, case.candidate, case.route, phrase)
    print("STALE LOCK", refused.returncode, refused.stdout, refused.stderr)
    assert refused.returncode == 2
    diagnostic = json.loads(refused.stderr.removeprefix("REFUSED: "))
    assert diagnostic["reason"] == "applier-lock-exists"
    assert diagnostic["lockOwner"]["pid"] == int(exited.stdout)
    assert "stale locks require explicit inspection and removal" in diagnostic["error"]
    assert lock.read_bytes() == marker  # No time-based guess or PID-based lock stealing.
    assert read_source(case) == case.before
    lock.unlink()  # Explicit test-operator recovery, not automatic applier recovery.
    applied = host_cli("apply", case.root, case.handoff, case.candidate, case.route, phrase)
    print("AFTER EXPLICIT REMOVAL", applied.returncode, applied.stdout, applied.stderr)
    assert applied.returncode == 0
    assert read_source(case) == case.contents
    assert not lock.exists()


@pytest.mark.parametrize("name", ["index.html", "styles.css", "remove-member"])
def test_multifile_confirmation_rejects_changed_member(host_case, name) -> None:
    case = host_case
    proposal, _ = applier.review(case.root, case.handoff, case.candidate, case.route)

    def confirm():
        if name == "remove-member":
            (case.candidate / "styles.css").unlink()
        else:
            path = case.candidate / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        return proposal["confirmation"] + "\n"

    code, diagnostic = apply_in_process(case, confirm)
    assert code == 2
    assert "review changed while awaiting confirmation" in diagnostic["error"]
    assert read_source(case) == case.before
    assert not (case.root.parent / ("." + case.root.name + ".applier.lock")).exists()


def test_staging_failure_leaves_no_partial_state(host_case) -> None:
    case = host_case
    real_temporary_file = applier.tempfile.NamedTemporaryFile
    calls = []

    def stage(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise PermissionError("injected staging failure")
        return real_temporary_file(*args, **kwargs)

    with patch.object(applier.tempfile, "NamedTemporaryFile", side_effect=stage):
        code, diagnostic = apply_in_process(case)
    assert code == 2
    assert read_source(case) == case.before
    assert diagnostic["phase"] == "stage"
    assert diagnostic["reason"] == "injected staging failure"
    assert diagnostic["writeApplied"] is False
    assert diagnostic["committedFiles"] == []
    assert diagnostic["rollbackAttempted"] is False
    assert diagnostic["rolledBack"] is True


def test_partial_commit_restore_failure_is_reported_honestly(host_case) -> None:
    case = host_case
    real_replace = applier.os.replace
    attempts = []

    def replace(source, target):
        attempts.append(Path(target).name)
        if len(attempts) == 2:
            raise PermissionError("injected commit failure")
        if len(attempts) == 3:
            raise PermissionError("injected restore failure")
        real_replace(source, target)

    with patch.object(applier.os, "replace", side_effect=replace):
        code, diagnostic = apply_in_process(case)
    assert code == 2
    assert attempts == ["index.html", "styles.css", "index.html"]
    assert diagnostic["phase"] == "commit"
    assert diagnostic["reason"] == "injected commit failure"
    assert diagnostic["rolledBack"] is False
    assert diagnostic["rollbackErrors"] == {"index.html": "injected restore failure"}
    assert read_source(case) == {"index.html": case.contents["index.html"],
                                 "styles.css": case.before["styles.css"]}


@pytest.mark.parametrize("marker", [b"", b"[]"])
def test_incomplete_or_invalid_lock_is_not_stolen(host_case, marker) -> None:
    case = host_case
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    lock.write_bytes(marker)
    code, diagnostic = apply_in_process(case)
    assert code == 2
    assert diagnostic["reason"] == "applier-lock-exists"
    assert diagnostic["lockOwnerError"]
    assert lock.read_bytes() == marker
    assert read_source(case) == case.before


@contextmanager
def waiting_applier(argv):
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8")
    output = queue.Queue()
    lines = []

    def read():
        for line in process.stdout:
            lines.append(line)
            output.put(line)
        output.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while True:
            line = output.get(timeout=20)
            assert line is not None, "first applier exited before confirmation"
            if line.startswith("Type exactly: "):
                yield process, line.removeprefix("Type exactly: ")
                break
    finally:
        if process.poll() is None:
            process.stdin.close()  # EOF withdraws approval and releases only its own marker.
            process.wait(timeout=10)
        reader.join(timeout=5)
        assert not reader.is_alive()
        print("FIRST", process.returncode, "".join(lines), process.stderr.read())
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()


def test_named_applier_conflict_then_owner_disconnect_allows_apply(host_case):
    case = host_case
    argv = [sys.executable, "-X", "utf8", str(FIXTURE / "applier.py"), "apply",
            "--root", str(case.root), "--handoff", str(case.handoff),
            "--candidate", str(case.candidate), "--route-url", case.route, "--user-id"]
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    with waiting_applier([*argv, "alice"]) as (first, confirmation):
        marker = lock.read_bytes()
        owner = json.loads(marker)
        assert owner["userId"] == "alice"
        assert owner["pid"] == first.pid
        assert owner["selectors"] == ["#next-read", "#queue-title"]
        second = subprocess.run([*argv, "bob"], input=confirmation, capture_output=True,
                                text=True, encoding="utf-8", timeout=20)
        print("CONFLICT", second.returncode, second.stdout, second.stderr)
        assert second.returncode == 2
        error = json.loads(second.stderr.removeprefix("REFUSED: "))
        assert error["phase"] == "lock"
        assert error["requestedBy"] == "bob"
        assert error["lockOwner"] == owner
        assert error["pluginWritesSource"] is False
        assert error["conflicts"] == owner["pendingEdits"]
        assert any(e["locator"] == "#next-read" and e["property"] == "padding"
                   and e["newValue"] == "24px" for e in error["conflicts"])
        assert all(text in error["error"] for text in ("alice", "pending edits", "#next-read", "padding", "24px"))
        assert lock.read_bytes() == marker
        assert read_source(case) == case.before
        assert first.poll() is None
    assert first.returncode == 2
    assert not lock.exists()
    survivor = subprocess.run([*argv, "bob"], input=confirmation, capture_output=True,
                              text=True, encoding="utf-8", timeout=20)
    print("SURVIVOR APPLY", survivor.returncode, survivor.stdout, survivor.stderr)
    assert survivor.returncode == 0
    assert json.loads(survivor.stdout.splitlines()[-1])["pluginWritesSource"] is False
    assert read_source(case) == case.contents
    assert not lock.exists()
