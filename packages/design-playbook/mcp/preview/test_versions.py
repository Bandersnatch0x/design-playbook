#!/usr/bin/env python3
"""Contract tests for the Preview local version control (versions.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview import versions  # noqa: E402
from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from design_playbook.mcp.preview.versions import (  # noqa: E402
    VersionCommittedError,
    VersionError,
    VersionProjectionError,
    create_named_version,
    fork,
    list_versions,
    refresh_version_projection,
    state_at,
    timeline,
)


def _seed_round(
    preview_dir: Path, round_n: int, html: str,
    *, confirmed: bool = True, feedback: str = "ok",
) -> dict:
    digest = prototype_html_digest(html.encode("utf-8"))
    binding = transaction._binding(
        round_n=round_n, prototype_hash=digest, report_ref="r.md",
        summary="s", options=["确认通过", "需要修改"])
    entry = {
        "schema_version": 1,
        "decision_id": f"d-{round_n}",
        "timestamp": f"2026-08-07T00:0{round_n}:00+08:00",
        "prototype_mode": "html",
        "prototype_path": str(preview_dir / f"round-{round_n}.html"),
        "binding": binding,
        "outcome": {
            "confirmed": bool(confirmed),
            "user_confirmed": bool(confirmed),
            "floor_pass": bool(confirmed),
            "floor_failure": "",
            "selected_options": ["确认通过"] if confirmed else ["需要修改"],
            "feedback": feedback,
            "anchors": [],
            "aborted": False,
            "rejected": not confirmed,
            "rejection": "",
        },
    }
    (preview_dir / f"round-{round_n}.html").write_text(html, encoding="utf-8")
    transaction._atomic_write(
        preview_dir / f"decision-round-{round_n}.json",
        transaction._json_text(entry))
    if confirmed:
        transaction._atomic_write(
            preview_dir / f"confirm-round-{round_n}.json",
            transaction._json_text(transaction._confirm_record(entry)))
    return entry


class NamedVersionTests(unittest.TestCase):
    def test_requires_existing_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VersionError):
                create_named_version(
                    Path(tmp), round_n=1, name="初稿", kind="confirmed")

    def test_writes_append_only_record_and_refreshes_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            v1 = create_named_version(
                d, round_n=1, name="初稿", kind="confirmed")
            self.assertEqual(v1["seq"], 1)
            self.assertEqual(v1["round"], 1)
            self.assertEqual(v1["kind"], "confirmed")
            self.assertEqual(v1["name"], "初稿")

            path = d / "version-1.json"
            self.assertTrue(path.is_file())
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record, v1)

            v2 = create_named_version(
                d, round_n=1, name="初稿·修订", kind="custom")
            self.assertEqual(v2["seq"], 2)
            self.assertEqual(len(list_versions(d)), 2)

            log = (d / "log.md").read_text(encoding="utf-8")
            self.assertIn("## versions", log)
            self.assertIn("初稿", log)
            self.assertIn("初稿·修订", log)

    def test_name_and_kind_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            with self.assertRaises(VersionError):
                create_named_version(d, round_n=1, name="   ")
            with self.assertRaises(VersionError):
                create_named_version(d, round_n=1, name="x" * 81)
            with self.assertRaises(VersionError):
                create_named_version(d, round_n=1, name="ok", kind="bogus")

    def test_note_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            v = create_named_version(
                d, round_n=1, name="初稿", note="n" * 500)
            self.assertEqual(len(v["note"]), 200)

    def test_projection_failure_reports_committed_version_and_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")

            with mock.patch.object(
                versions, "_refresh_log", side_effect=OSError("injected failure"),
            ):
                with self.assertRaises(VersionProjectionError) as caught:
                    create_named_version(d, round_n=1, name="release")

            error = caught.exception
            self.assertTrue(error.committed)
            self.assertEqual(error.version_record["seq"], 1)
            self.assertEqual(error.version_record_path, d / "version-1.json")
            self.assertEqual(
                error.repair_action, "refresh_version_projection(preview_dir)")
            self.assertEqual([v["seq"] for v in list_versions(d)], [1])

            projection_path = refresh_version_projection(d)

            self.assertEqual(projection_path, d / "log.md")
            self.assertIn(
                "release", projection_path.read_text(encoding="utf-8"))
            self.assertEqual([v["seq"] for v in list_versions(d)], [1])

    def test_lock_exit_failure_reports_committed_without_projection_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            lock = mock.MagicMock()
            lock.__enter__.return_value = None
            lock.__exit__.side_effect = VersionError("ownership lost")

            with mock.patch.object(versions, "_version_lock", return_value=lock):
                with self.assertRaises(VersionCommittedError) as caught:
                    create_named_version(d, round_n=1, name="release")

            error = caught.exception
            self.assertNotIsInstance(error, VersionProjectionError)
            self.assertTrue(error.committed)
            self.assertEqual(error.version_record["seq"], 1)
            self.assertIn("do not retry", error.repair_action)
            self.assertEqual([v["seq"] for v in list_versions(d)], [1])

    def test_concurrent_writers_preserve_both_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            next_seq = versions._next_seq
            writers_ready = threading.Barrier(2)
            records: list[dict] = []
            errors: list[Exception] = []

            def synchronized_next_seq(preview_dir: Path) -> int:
                seq = next_seq(preview_dir)
                try:
                    writers_ready.wait(timeout=0.25)
                except threading.BrokenBarrierError:
                    pass
                return seq

            def write(name: str) -> None:
                try:
                    records.append(create_named_version(
                        d, round_n=1, name=name))
                except Exception as exc:  # captured for the parent assertion
                    errors.append(exc)

            with mock.patch.object(
                versions, "_next_seq", side_effect=synchronized_next_seq,
            ):
                threads = [
                    threading.Thread(target=write, args=("writer-a",)),
                    threading.Thread(target=write, args=("writer-b",)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)

            self.assertFalse(errors)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(sorted(record["seq"] for record in records), [1, 2])
            self.assertEqual(
                {record["name"] for record in list_versions(d)},
                {"writer-a", "writer-b"},
            )

    def test_active_version_lock_is_not_reclaimed_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            entered = threading.Event()
            release = threading.Event()
            acquired = threading.Event()
            holder_errors: list[BaseException] = []
            contender_errors: list[Exception] = []

            def hold_lock() -> None:
                try:
                    with versions._version_lock(d):
                        entered.set()
                        release.wait(timeout=2)
                except BaseException as exc:
                    holder_errors.append(exc)

            def contend_for_lock() -> None:
                try:
                    with versions._version_lock(d):
                        acquired.set()
                except VersionError as exc:
                    contender_errors.append(exc)

            with (
                mock.patch.object(versions, "VERSION_LOCK_STALE_SECONDS", 0.05),
                mock.patch.object(versions, "VERSION_LOCK_HEARTBEAT_SECONDS", 0.01,
                                  create=True),
                mock.patch.object(versions, "VERSION_LOCK_TIMEOUT_SECONDS", 0.08),
                mock.patch.object(versions, "VERSION_LOCK_POLL_SECONDS", 0.005),
            ):
                holder = threading.Thread(target=hold_lock)
                holder.start()
                self.assertTrue(entered.wait(timeout=1))
                time.sleep(0.08)

                contender = threading.Thread(target=contend_for_lock)
                contender.start()
                contender.join(timeout=1)
                release.set()
                holder.join(timeout=1)

            self.assertFalse(acquired.is_set())
            self.assertEqual(len(contender_errors), 1)
            self.assertFalse(holder_errors)
            self.assertFalse(holder.is_alive())
            self.assertFalse(contender.is_alive())

    def test_log_projection_is_serialized_with_decision_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            create_named_version(d, round_n=1, name="initial")

            rendered_stale = threading.Event()
            release_stale = threading.Event()
            transaction_done = threading.Event()
            errors: list[BaseException] = []
            render = versions._render_versions_log

            def delayed_render(preview_dir: Path) -> str:
                value = render(preview_dir)
                if threading.current_thread().name == "stale-projection":
                    rendered_stale.set()
                    if not release_stale.wait(timeout=2):
                        raise TimeoutError("stale projection was not released")
                return value

            def refresh_version_projection() -> None:
                try:
                    versions._refresh_log(d)
                except BaseException as exc:
                    errors.append(exc)

            def commit_decision_projection(entry: dict) -> None:
                try:
                    transaction._commit_projections(d, entry)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    transaction_done.set()

            with mock.patch.object(
                versions, "_render_versions_log", side_effect=delayed_render,
            ):
                stale = threading.Thread(
                    target=refresh_version_projection, name="stale-projection")
                stale.start()
                self.assertTrue(rendered_stale.wait(timeout=1))
                second = _seed_round(d, 2, "<html>v2</html>")
                current = threading.Thread(
                    target=commit_decision_projection, args=(second,))
                current.start()
                was_serialized = not transaction_done.wait(timeout=0.1)
                release_stale.set()
                stale.join(timeout=2)
                current.join(timeout=2)

            self.assertTrue(was_serialized)
            self.assertFalse(errors)
            log = (d / "log.md").read_text(encoding="utf-8")
            self.assertIn("## round 2", log)
            self.assertIn("initial", log)


class StateAtTests(unittest.TestCase):
    def test_replayable_state_html_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            _seed_round(d, 2, "<html>v2</html>")
            create_named_version(d, round_n=1, name="初稿", kind="confirmed")

            state = state_at(d, 2)
            self.assertEqual(state["round"], 2)
            self.assertEqual(state["prototype_html"], "<html>v2</html>")
            self.assertEqual(state["digest"], state["binding"]["digest"])
            self.assertIsNotNone(state["confirm"])
            self.assertEqual(state["outcome"]["confirmed"], True)
            # versions bounded at or before N
            self.assertEqual([v["name"] for v in state["versions"]], ["初稿"])

    def test_missing_round_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VersionError):
                state_at(Path(tmp), 1)

    def test_rejects_tampered_html_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>trusted</html>")
            (d / "round-1.html").write_text(
                "<html>tampered</html>", encoding="utf-8")

            with self.assertRaisesRegex(VersionError, "digest mismatch"):
                state_at(d, 1)

    def test_rejects_missing_html_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>trusted</html>")
            (d / "round-1.html").unlink()

            with self.assertRaisesRegex(VersionError, "snapshot missing"):
                state_at(d, 1)

    def test_rejects_corrupt_confirm_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            (d / "confirm-round-1.json").write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(VersionError, "confirm record unreadable"):
                state_at(d, 1)

    def test_rejects_confirm_for_another_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            confirm_path = d / "confirm-round-1.json"
            confirm = json.loads(confirm_path.read_text(encoding="utf-8"))
            confirm["decision_id"] = "d-other"
            confirm_path.write_text(json.dumps(confirm), encoding="utf-8")

            with self.assertRaisesRegex(VersionError, "decision mismatch"):
                state_at(d, 1)

    def test_rejects_confirm_with_invalid_authority_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            confirm_path = d / "confirm-round-1.json"
            valid = json.loads(confirm_path.read_text(encoding="utf-8"))
            invalid_records = {
                "empty": {},
                "round": {**valid, "round": 2},
                "report": {**valid, "report_ref": "other.md"},
                "floor": {**valid, "floor_pass": False},
                "prototype": {**valid, "prototype_html_hash": "0" * 64},
                "decision type": {**valid, "decision_id": []},
                "feedback": {**valid, "feedback": "tampered"},
                "selection": {**valid, "selected_options": []},
                "timestamp": {**valid, "timestamp": "other"},
            }

            for label, record in invalid_records.items():
                with self.subTest(label=label):
                    confirm_path.write_text(json.dumps(record), encoding="utf-8")
                    with self.assertRaisesRegex(
                        VersionError, "confirm record invalid",
                    ):
                        state_at(d, 1)

    def test_accepts_valid_legacy_confirm_without_decision_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            confirm_path = d / "confirm-round-1.json"
            confirm = json.loads(confirm_path.read_text(encoding="utf-8"))
            del confirm["decision_id"]
            confirm_path.write_text(json.dumps(confirm), encoding="utf-8")

            self.assertEqual(state_at(d, 1)["confirm"], confirm)

    def test_unconfirmed_round_has_no_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>", confirmed=False)
            state = state_at(d, 1)
            self.assertIsNone(state["confirm"])
            self.assertEqual(state["outcome"]["rejected"], True)


class ForkTests(unittest.TestCase):
    def test_derives_independent_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "preview"
            src.mkdir()
            _seed_round(src, 1, "<html>base</html>")
            new = Path(tmp) / "fork-alt"
            result = fork(
                src, branch="alt", from_round=1,
                new_dir=new, report_ref="alt.md", summary="备选方案")
            record = result["fork"]
            self.assertEqual(record["branch"], "alt")
            self.assertEqual(record["forked_from_round"], 1)
            self.assertEqual(record["forked_from_digest"],
                             state_at(src, 1)["digest"])
            self.assertTrue((new / "fork.json").is_file())
            self.assertEqual(
                (new / "round-1.html").read_text(encoding="utf-8"),
                "<html>base</html>")
            self.assertEqual(result["start_prototype"], str(new / "round-1.html"))

    def test_fork_requires_html_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "preview"
            src.mkdir()
            # path-mode style: decision entry but no round-N.html snapshot
            digest = prototype_html_digest(b"<html>x</html>")
            binding = transaction._binding(
                round_n=1, prototype_hash=digest, report_ref="r.md",
                summary="s", options=["确认通过", "需要修改"])
            entry = {
                "schema_version": 1,
                "decision_id": "d-1",
                "timestamp": "2026-08-07T00:01:00+08:00",
                "prototype_path": str(src / "prototype.html"),
                "binding": binding,
                "outcome": {
                    "confirmed": True, "user_confirmed": True, "floor_pass": True,
                    "floor_failure": "", "selected_options": ["确认通过"],
                    "feedback": "ok", "anchors": [], "aborted": False,
                    "rejected": False, "rejection": "",
                },
            }
            transaction._atomic_write(
                src / "decision-round-1.json",
                transaction._json_text(entry))
            state = state_at(src, 1)
            self.assertIsNone(state["prototype_html"])
            self.assertEqual(state["prototype_path"], str(src / "prototype.html"))
            with self.assertRaises(VersionError):
                fork(
                    src, branch="alt", from_round=1,
                    new_dir=Path(tmp) / "fork-alt",
                    report_ref="alt.md", summary="备选方案")

    def test_refuses_to_modify_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "preview"
            src.mkdir()
            _seed_round(src, 1, "<html>base</html>")
            new = Path(tmp) / "fork-alt"
            new.mkdir()
            existing = new / "round-1.html"
            existing.write_text("<html>keep</html>", encoding="utf-8")

            with self.assertRaisesRegex(VersionError, "destination already exists"):
                fork(
                    src, branch="alt", from_round=1,
                    new_dir=new, report_ref="alt.md", summary="备选方案")

            self.assertEqual(
                existing.read_text(encoding="utf-8"), "<html>keep</html>")
            self.assertFalse((new / "fork.json").exists())

    def test_failed_fork_is_cleaned_up_and_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "preview"
            src.mkdir()
            _seed_round(src, 1, "<html>base</html>")
            new = Path(tmp) / "fork-alt"
            atomic_write = versions._atomic_write

            def fail_commit(path: Path, content: str) -> None:
                if path.name == "fork.json":
                    raise OSError("injected fork commit failure")
                atomic_write(path, content)

            with mock.patch.object(
                versions, "_atomic_write", side_effect=fail_commit,
            ):
                with self.assertRaisesRegex(
                    VersionError, "fork initialization failed",
                ):
                    fork(
                        src, branch="alt", from_round=1,
                        new_dir=new, report_ref="alt.md", summary="备选方案")

            self.assertFalse(new.exists())
            result = fork(
                src, branch="alt", from_round=1,
                new_dir=new, report_ref="alt.md", summary="备选方案")
            self.assertEqual(result["fork"]["branch"], "alt")

    def test_interrupted_fork_never_exposes_partial_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "preview"
            src.mkdir()
            _seed_round(src, 1, "<html>base</html>")
            new = Path(tmp) / "fork-alt"
            atomic_write = versions._atomic_write

            def interrupt_commit(path: Path, content: str) -> None:
                if path.name == "fork.json":
                    raise SystemExit("injected process interruption")
                atomic_write(path, content)

            with mock.patch.object(
                versions, "_atomic_write", side_effect=interrupt_commit,
            ):
                with self.assertRaises(SystemExit):
                    fork(
                        src, branch="alt", from_round=1,
                        new_dir=new, report_ref="alt.md", summary="备选方案")

            self.assertFalse(new.exists())
            result = fork(
                src, branch="alt", from_round=1,
                new_dir=new, report_ref="alt.md", summary="备选方案")
            self.assertEqual(result["fork"]["branch"], "alt")


class TimelineTests(unittest.TestCase):
    def test_merges_decisions_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _seed_round(d, 1, "<html>v1</html>")
            _seed_round(d, 2, "<html>v2</html>")
            create_named_version(d, round_n=1, name="初稿", kind="confirmed")
            items = timeline(d)
            self.assertEqual(len(items), 3)
            types = sorted(i["event_type"] for i in items)
            self.assertEqual(types, ["decision", "decision", "version"])
            # every item carries the timestamp key used for ordering
            for item in items:
                self.assertIsInstance(item["timestamp"], str)


if __name__ == "__main__":
    unittest.main()
