#!/usr/bin/env python3
"""Tests for the evidence manifest write-side CLI (M-002 D4 / T-065)."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.evidence_manifest import (  # noqa: E402
    ManifestAppendError,
    append_entry,
    main,
)
from design_playbook.scripts.g6_evidence import check_evidence  # noqa: E402
from design_playbook.scripts.g6_records import manifest_entries  # noqa: E402

# A capture-contract-v1 request snapshot, verbatim shape of the
# execute_capture_plan result's `request` field.
REQ = {
    "schemaVersion": 1,
    "viewport": {
        "width": 1280,
        "height": 800,
        "devicePixelRatio": 1.0,
        "colorScheme": "light",
    },
    "freeze": {"enabled": True, "waitFonts": True, "networkIdle": False},
}


class EvidenceManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run = Path(self._tmp.name) / "run"
        (self.run / "evidence").mkdir(parents=True)
        (self.run / "evidence" / "shot.png").write_bytes(b"png-bytes")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_append_writes_one_binding_line(self) -> None:
        entry = append_entry(self.run, "L6.2", "shot.png", REQ, source="unit-test")
        self.assertEqual(entry["criterion"], "L6.2")
        self.assertEqual(entry["artifact"], "shot.png")
        self.assertEqual(entry["source"], "unit-test")
        self.assertEqual(entry["request"], REQ)
        self.assertEqual(
            entry["sha256"], hashlib.sha256(b"png-bytes").hexdigest()
        )
        lines = (self.run / "evidence" / "manifest.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["criterion"], "L6.2")

    def test_append_is_append_only(self) -> None:
        append_entry(self.run, "L6.1", "shot.png", REQ)
        append_entry(self.run, "L6.2", "shot.png", REQ)
        lines = (self.run / "evidence" / "manifest.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(len(lines), 2)

    def test_rejects_directory_parts(self) -> None:
        for bad in ("sub/shot.png", "sub\\shot.png", "..\\shot.png"):
            with self.assertRaises(ManifestAppendError, msg=bad):
                append_entry(self.run, "L6.1", bad, REQ)

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(ManifestAppendError):
            append_entry(self.run, "L6.1", "C:/abs/shot.png", REQ)

    def test_rejects_missing_artifact(self) -> None:
        with self.assertRaises(ManifestAppendError) as ctx:
            append_entry(self.run, "L6.1", "nope.png", REQ)
        self.assertIn("not_regular_file", str(ctx.exception))

    def test_rejects_non_contract_request(self) -> None:
        for bad in ({}, {"schemaVersion": 2}, {"schemaVersion": 1}):
            with self.assertRaises(ManifestAppendError, msg=str(bad)):
                append_entry(self.run, "L6.1", "shot.png", bad)

    def test_g6_readside_parses_cli_output(self) -> None:
        append_entry(self.run, "L6.2", "shot.png", REQ)
        entries = manifest_entries(self.run / "evidence")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["criterion"], "L6.2")
        self.assertEqual(entries[0]["artifact"], "shot.png")

    def test_cli_appended_row_passes_g6(self) -> None:
        """End-to-end: a CLI-bound row satisfies check_evidence (T-065 #3)."""
        code = main([
            "evidence_manifest.py", "append", str(self.run),
            "--criterion", "L6.1", "--artifact", "shot.png",
            "--request", json.dumps(REQ),
        ])
        self.assertEqual(code, 0)
        findings = check_evidence(
            "",
            1,
            self.run / "evidence",
            self.run,
            observed_rows=[("L6.1", "evidence/shot.png")],
        )
        self.assertEqual(findings, [])

    def test_cli_rejects_bad_artifact_with_correct_form(self) -> None:
        code = main([
            "evidence_manifest.py", "append", str(self.run),
            "--criterion", "L6.1", "--artifact", "sub/shot.png",
            "--request", json.dumps(REQ),
        ])
        self.assertEqual(code, 2)

    def test_cli_happy_path(self) -> None:
        code = main([
            "evidence_manifest.py", "append", str(self.run),
            "--criterion", "L6.1", "--artifact", "shot.png",
            "--request", json.dumps(REQ),
        ])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
