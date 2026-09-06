"""Black-box tests for the additive run-status open-console continuation."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from design_playbook.scripts import run_status as run_status_mod  # noqa: E402
from design_playbook.scripts.run_continuation import (  # noqa: E402
    continuation_for_run,
    inspect_console_inventory,
)
from design_playbook.scripts.status_projection import project_next_action  # noqa: E402

RUN_STATUS = PKG / "scripts" / "run_status.py"
RUN_CONSOLE = PKG / "scripts" / "run_console.py"
EXISTING_JSON_KEYS = frozenset(
    {
        "run_root",
        "stages",
        "next",
        "verdict",
        "audited",
        "audit_marker_state",
        "run_profile",
        "shaping",
        "six_block_report",
        "invalidated_evidence",
        "repair",
    }
)


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(RUN_STATUS), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def _tree_digest(root: Path) -> tuple[tuple[str, int, str], ...]:
    items: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            items.append((rel, path.stat().st_size, digest))
        else:
            items.append((rel, -1, ""))
    return tuple(items)


def _write_run(root: Path, name: str, files: dict[str, str]) -> Path:
    run_root = root / name
    run_root.mkdir(parents=True)
    for relative, contents in files.items():
        target = run_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    return run_root


def _fake_package(
    root: Path,
    *,
    runtime: bool = True,
    tests: bool = False,
    trial_status: str | None = None,
) -> Path:
    package = root / "pkg"
    if runtime:
        scripts = package / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "run_console.py").write_text("# inventory stub\n", encoding="utf-8")
        runtime_dir = package / "mcp" / "run_console"
        runtime_dir.mkdir(parents=True)
        for name in ("session.py", "http_server.py", "snapshot_builder.py"):
            (runtime_dir / name).write_text("# inventory stub\n", encoding="utf-8")
        if tests:
            (runtime_dir / "test_session.py").write_text(
                "def test_stub() -> None:\n    return None\n",
                encoding="utf-8",
            )
        if trial_status is not None:
            (runtime_dir / "test_read_only_trial.py").write_text(
                f'TRIAL_STATUS = "{trial_status}"\n',
                encoding="utf-8",
            )
    else:
        package.mkdir(parents=True)
    return package


def _payload_from_render(run_root: Path) -> dict:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = run_status_mod.render(run_root, as_json=True)
    assert code == 0, buffer.getvalue()
    return json.loads(buffer.getvalue())


class RunStatusContinuationTests(unittest.TestCase):
    def test_existing_json_keys_and_next_string_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-spec",
                {"spec.md": "# L1\n"},
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(EXISTING_JSON_KEYS.issubset(payload))
            self.assertIsInstance(payload["next"], str)
            self.assertIn("Resume", payload["next"])
            continuation = payload["continuation"]
            self.assertEqual(continuation["next_action"]["label"], payload["next"])

    def test_explicit_run_command_names_that_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            chosen = _write_run(scratch, "chosen-run", {"spec.md": "# chosen\n"})
            other = _write_run(scratch, "other-run", {"spec.md": "# other\n"})
            os.utime(chosen, (1, 1))
            os.utime(other, (9, 9))
            result = _run(str(chosen), "--scratch", str(scratch), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            open_console = payload["continuation"]["open_console"]
            self.assertTrue(open_console["eligible"])
            self.assertEqual(open_console["action"], "open-console")
            selected = Path(payload["continuation"]["selected_run"]).resolve()
            self.assertEqual(selected, chosen.resolve())
            argv = open_console["argv"]
            self.assertEqual(Path(argv[0]).name, Path(sys.executable).name)
            self.assertEqual(Path(argv[1]).resolve(), RUN_CONSOLE.resolve())
            self.assertEqual(Path(argv[2]).resolve(), chosen.resolve())
            self.assertIn("run_console.py", open_console["command"])
            self.assertNotIn(str(other.resolve()), argv)

    def test_discovered_run_command_names_the_resolved_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            older = _write_run(scratch, "older-run", {"spec.md": "# old\n"})
            newer = _write_run(scratch, "newer-run", {"spec.md": "# new\n"})
            os.utime(older, (1, 1))
            os.utime(newer, (9, 9))
            result = _run("--scratch", str(scratch), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            selected = Path(payload["continuation"]["selected_run"]).resolve()
            self.assertEqual(selected, newer.resolve())
            argv = payload["continuation"]["open_console"]["argv"]
            self.assertEqual(Path(argv[-1]).resolve(), newer.resolve())
            self.assertIn("newer-run", payload["continuation"]["open_console"]["command"])

    def test_list_mode_does_not_emit_open_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch"
            _write_run(scratch, "listed-run", {"spec.md": "# list\n"})
            result = _run("--scratch", str(scratch), "--list")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("listed-run", result.stdout)
            self.assertNotIn("open-console", result.stdout)
            self.assertNotIn("run_console.py", result.stdout)

    def test_render_has_no_server_or_artifact_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(Path(tmp), "run-plain", {"spec.md": "# L1\n"})
            before = _tree_digest(run_root)
            with (
                patch("socket.socket.bind", side_effect=AssertionError("bind")),
                patch(
                    "http.server.HTTPServer.__init__",
                    side_effect=AssertionError("http"),
                ),
                patch("subprocess.Popen", side_effect=AssertionError("popen")),
            ):
                payload = _payload_from_render(run_root)
            self.assertEqual(_tree_digest(run_root), before)
            self.assertTrue(payload["continuation"]["open_console"]["eligible"])
            self.assertIn("run_console.py", payload["continuation"]["open_console"]["command"])

    def test_missing_prerequisites_omit_command_and_name_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(Path(tmp), "run-plain", {"spec.md": "# L1\n"})
            package = _fake_package(Path(tmp), runtime=False)
            continuation = continuation_for_run(run_root, package)
            payload = continuation.to_dict()
            open_console = payload["open_console"]
            self.assertFalse(open_console["eligible"])
            self.assertNotIn("command", open_console)
            self.assertNotIn("argv", open_console)
            self.assertNotIn("action", open_console)
            self.assertIn("missing Console runtime prerequisites", open_console["reason"])
            self.assertIn("scripts/run_console.py", open_console["reason"])
            self.assertIn("run-status JSON", open_console["fallback"])
            self.assertEqual(payload["capability"]["status"]["implementation"], "absent")
            self.assertEqual(payload["capability"]["status"]["publicClaim"], "not-shipped")
            with patch.object(run_status_mod, "_PKG_ROOT", package):
                rendered = _payload_from_render(run_root)
            self.assertNotIn("command", rendered["continuation"]["open_console"])
            self.assertFalse(rendered["continuation"]["open_console"]["eligible"])

    def test_completed_run_still_exposes_open_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-pass",
                {"point-back.md": "## Verdict\n\nPass\n"},
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Pass")
            self.assertIn("complete", payload["next"].lower())
            continuation = payload["continuation"]
            self.assertEqual(continuation["phase"]["key"], "accept")
            self.assertIsNone(continuation["blocker"])
            self.assertEqual(
                continuation["next_action"]["action_id"],
                "action.stop-after-pass",
            )
            self.assertEqual(continuation["next_action"]["owner"]["actor"], "run-operator")
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertEqual(
                Path(continuation["open_console"]["argv"][-1]).resolve(),
                run_root.resolve(),
            )

    def test_blocked_run_is_not_a_launch_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-recirculate",
                {"point-back.md": "## Verdict\n\nRecirculate\n"},
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Recirculate")
            continuation = payload["continuation"]
            self.assertEqual(
                continuation["next_action"]["action_id"],
                "action.repair-after-recirculate",
            )
            self.assertEqual(continuation["blocker"]["source"], "owner")
            self.assertEqual(
                continuation["blocker"]["action_id"],
                "action.repair-after-recirculate",
            )
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertIn("command", continuation["open_console"])

    def test_unknown_validation_stays_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(Path(tmp), "run-empty", {})
            package = _fake_package(Path(tmp), runtime=True, tests=False)
            continuation = continuation_for_run(run_root, package)
            status = continuation.capability.status
            self.assertEqual(status.implementation, "present")
            self.assertEqual(status.validation, "unknown")
            self.assertNotEqual(status.public_claim, "stable")
            self.assertNotEqual(status.validation, "trial-observed")
            self.assertIn("unknown", continuation.capability.evidence_gap or "")
            self.assertTrue(continuation.open_console.eligible)
            self.assertIsNone(continuation.phase)
            self.assertEqual(continuation.next_action["action_id"], "action.start-run")

    def test_hash_mismatch_stays_visible_and_does_not_replace_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-mismatch"
            run_root.mkdir()
            preview = run_root / "preview"
            preview.mkdir()
            (preview / "round-1.html").write_text("changed", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                json.dumps(
                    {
                        "round": 1,
                        "confirmed": True,
                        "floor_pass": True,
                        "prototype_html_hash": prototype_html_digest(b"original"),
                    }
                ),
                encoding="utf-8",
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("resume at fill", payload["next"].lower())
            self.assertNotEqual(payload["verdict"], "Pass")
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "hash-mismatched")
            self.assertIsNotNone(continuation["integrity"]["reason"])
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertEqual(continuation["blocker"]["state"], "hash-mismatched")
            self.assertEqual(
                continuation["next_action"]["label"],
                payload["next"],
            )
            self.assertTrue(continuation["open_console"]["eligible"])

    def test_inconsistent_bind_is_not_replaced_by_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-inconsistent",
                {
                    "spec.md": "# L1\n",
                    "contract-bind.json": json.dumps(
                        {
                            "open_fields": ["nav.item-count"],
                            "assumed_fields": ["nav.item-count"],
                            "stale_fields": [],
                        }
                    ),
                },
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "inconsistent")
            self.assertNotEqual(payload["verdict"], "Pass")
            self.assertTrue(continuation["open_console"]["eligible"])

    def test_malformed_confirm_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-malformed"
            run_root.mkdir()
            preview = run_root / "preview"
            preview.mkdir()
            (preview / "round-1.html").write_text("<html>1</html>", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                "{not json", encoding="utf-8"
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["continuation"]["integrity"]["state"],
                "malformed",
            )
            self.assertNotEqual(payload["verdict"], "Pass")
            self.assertTrue(payload["continuation"]["open_console"]["eligible"])

    def test_pass_does_not_hide_current_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-pass-mismatch"
            run_root.mkdir()
            (run_root / "point-back.md").write_text(
                "## Verdict\n\nPass\n", encoding="utf-8"
            )
            preview = run_root / "preview"
            preview.mkdir()
            (preview / "round-1.html").write_text("changed", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                json.dumps(
                    {
                        "round": 1,
                        "confirmed": True,
                        "floor_pass": True,
                        "prototype_html_hash": prototype_html_digest(b"original"),
                    }
                ),
                encoding="utf-8",
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Pass")
            self.assertIn("complete", payload["next"].lower())
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "hash-mismatched")
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertEqual(
                continuation["next_action"]["action_id"],
                "action.stop-after-pass",
            )
            self.assertTrue(continuation["open_console"]["eligible"])

    def test_partial_bind_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-partial",
                {
                    "spec.md": "# L1\n",
                    "contract-bind.json": '{"ok": true, "open_fields": ["nav.item',
                },
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["continuation"]["integrity"]["state"],
                "partial",
            )
            self.assertIsInstance(payload["next"], str)

    def test_real_package_console_stays_experimental_and_not_trial_observed(self) -> None:
        inventory = inspect_console_inventory(PKG)
        self.assertIsNotNone(inventory.script)
        self.assertEqual(inventory.missing, ())
        self.assertTrue(inventory.tests_present)
        self.assertEqual(inventory.trial_status, "TRIAL_NOT_RUN")
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(Path(tmp), "run-spec", {"spec.md": "# L1\n"})
            continuation = continuation_for_run(run_root, PKG)
        status = continuation.capability.status
        self.assertEqual(status.implementation, "present")
        self.assertEqual(status.validation, "tested")
        self.assertEqual(status.availability, "local")
        self.assertEqual(status.public_claim, "experimental")
        self.assertNotEqual(status.validation, "trial-observed")
        self.assertIn("trial-gated", continuation.capability.evidence_gap or "")
        self.assertTrue(continuation.open_console.eligible)

    def test_continuation_reuses_owner_projection_without_parsing_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = _write_run(
                Path(tmp),
                "run-pass",
                {"point-back.md": "## Verdict\n\nPass\n"},
            )
            continuation = continuation_for_run(run_root, PKG)
            from design_playbook.scripts.run_facts import capture_run_facts
            from design_playbook.scripts.status_projection import inspect_run

            facts = capture_run_facts(run_root=run_root)
            states = inspect_run(run_root, facts.preview, facts)
            owner = project_next_action(states, run_root, facts.preview, facts)
            self.assertEqual(
                continuation.next_action["action_id"],
                owner.primary.action_id,
            )
            self.assertEqual(continuation.next_action["label"], owner.primary.label)
            self.assertNotIn("rm -rf", continuation.next_action["label"])


if __name__ == "__main__":
    unittest.main()
