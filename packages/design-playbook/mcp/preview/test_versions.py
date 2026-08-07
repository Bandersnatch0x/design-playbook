#!/usr/bin/env python3
"""Contract tests for the Preview local version control (versions.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transaction  # noqa: E402
import util  # noqa: E402
import versions  # noqa: E402
from versions import (  # noqa: E402
    VersionError,
    create_named_version,
    fork,
    list_versions,
    state_at,
    timeline,
)


def _seed_round(
    preview_dir: Path, round_n: int, html: str,
    *, confirmed: bool = True, feedback: str = "ok",
) -> dict:
    digest = util.prototype_html_digest(html.encode("utf-8"))
    binding = transaction._binding(
        round_n=round_n, prototype_hash=digest, report_ref="r.md",
        summary="s", options=["确认通过", "需要修改"])
    entry = {
        "schema_version": 1,
        "decision_id": f"d-{round_n}",
        "timestamp": f"2026-08-07T00:0{round_n}:00+08:00",
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
            digest = util.prototype_html_digest(b"<html>x</html>")
            binding = transaction._binding(
                round_n=1, prototype_hash=digest, report_ref="r.md",
                summary="s", options=["确认通过", "需要修改"])
            entry = {
                "schema_version": 1,
                "decision_id": "d-1",
                "timestamp": "2026-08-07T00:01:00+08:00",
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
            with self.assertRaises(VersionError):
                fork(
                    src, branch="alt", from_round=1,
                    new_dir=Path(tmp) / "fork-alt",
                    report_ref="alt.md", summary="备选方案")


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
