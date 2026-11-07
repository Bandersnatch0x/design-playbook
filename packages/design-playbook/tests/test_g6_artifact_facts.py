#!/usr/bin/env python3
"""T-159 phase A: immutable referenced-artifact facts in the G6 records owner.

The collector freezes the bytes of each explicitly referenced artifact once,
under an explicit run root. These cases prove the facts are real (actual bytes,
modified bytes, read errors, containment escapes) and that each unique
reference is opened once with a bounded read buffer. They say nothing about
whether a repair succeeded: changed bytes are facts, not a verdict.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.evidence import containment  # noqa: E402
from design_playbook.scripts import g6_records  # noqa: E402
from design_playbook.scripts.g6_records import (  # noqa: E402
    collect_evidence_artifacts,
    normalise_evidence_reference,
)


class _RecordingStream:
    """A stream that records the buffer size each read asks for."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.requested: list[int] = []

    def read(self, size: int) -> bytes:
        self.requested.append(size)
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class EvidenceArtifactFactTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t159-g6-")
        self.addCleanup(self._tmp.cleanup)
        self.run_root = Path(self._tmp.name)
        self.evidence = self.run_root / "evidence"
        self.evidence.mkdir()

    def _write(self, name: str, data: bytes) -> Path:
        path = self.evidence / name
        path.write_bytes(data)
        return path

    def _facts(self, *references: str):
        return collect_evidence_artifacts(references, run_root=self.run_root)

    def test_actual_bytes_are_digested_and_each_reference_read_once(self) -> None:
        data = b"real-png-bytes-" * 7
        self._write("a.png", data)
        opened: list[Path] = []
        real_open = g6_records._open_binary

        def recording(path: Path):
            opened.append(path)
            return real_open(path)

        with mock.patch.object(g6_records, "_open_binary", recording):
            facts = self._facts(
                "evidence/a.png", "evidence/a.png", "EVIDENCE/a.png")
        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(
            (fact.reference, fact.artifact, fact.reason),
            ("evidence/a.png", "a.png", ""))
        self.assertEqual(fact.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(fact.size, len(data))
        self.assertEqual(len(opened), 1)

    def test_modified_bytes_are_a_new_fact_while_the_old_fact_stays_frozen(self) -> None:
        path = self._write("a.png", b"before")
        first = self._facts("evidence/a.png")[0]
        path.write_bytes(b"after")
        second = self._facts("evidence/a.png")[0]
        self.assertEqual(first.sha256, hashlib.sha256(b"before").hexdigest())
        self.assertEqual(second.sha256, hashlib.sha256(b"after").hexdigest())
        self.assertNotEqual(first.sha256, second.sha256)
        with self.assertRaises(FrozenInstanceError):
            first.sha256 = second.sha256

    def test_missing_directory_and_escapes_are_facts_without_a_read(self) -> None:
        (self.evidence / "folder").mkdir()
        cases = {
            "evidence/missing.png": containment.REASON_NOT_REGULAR_FILE,
            "evidence/folder": containment.REASON_NOT_REGULAR_FILE,
            "evidence/../outside.png": containment.REASON_DOTDOT_SEGMENT,
            "spec.md": containment.REASON_CANONICAL_ESCAPE,
            str(self.evidence / "a.png"): containment.REASON_ABSOLUTE_PATH,
        }
        with mock.patch.object(g6_records, "_open_binary") as reader:
            facts = self._facts(*cases)
        reader.assert_not_called()
        self.assertEqual(len(facts), len(cases))
        for fact, expected in zip(facts, cases.values()):
            with self.subTest(reference=fact.reference):
                self.assertEqual(fact.reason, expected)
                self.assertIsNone(fact.sha256)
                self.assertIsNone(fact.size)

    def test_symlink_escape_is_a_fact_without_a_read(self) -> None:
        outside = self.run_root / "outside.png"
        outside.write_bytes(b"secret")
        link = self.evidence / "link.png"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with mock.patch.object(g6_records, "_open_binary") as reader:
            fact = self._facts("evidence/link.png")[0]
        reader.assert_not_called()
        self.assertIn(fact.reason, containment.RESOLUTION_ESCAPE_REASONS)
        self.assertIsNone(fact.sha256)

    def test_read_error_is_a_stable_bounded_fact(self) -> None:
        self._write("a.png", b"x")
        with mock.patch.object(
                g6_records, "_open_binary",
                side_effect=PermissionError("denied " + "x" * 400)):
            fact = self._facts("evidence/a.png")[0]
        self.assertEqual(fact.reason, g6_records.REASON_UNREADABLE)
        self.assertIsNone(fact.sha256)
        self.assertIsNone(fact.size)
        self.assertIn("denied", fact.detail)
        self.assertLessEqual(len(fact.detail), g6_records._DETAIL_LIMIT)

    def test_large_file_stream_is_read_in_bounded_chunks(self) -> None:
        payload = b"x" * (g6_records._DIGEST_CHUNK_BYTES * 3 + 7)
        stream = _RecordingStream(payload)
        digest, size = g6_records._digest_stream(stream)
        self.assertEqual(size, len(payload))
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertTrue(stream.requested)
        self.assertTrue(
            all(n <= g6_records._DIGEST_CHUNK_BYTES
                for n in stream.requested))

    def test_large_file_on_disk_is_digested_correctly(self) -> None:
        payload = b"y" * (g6_records._DIGEST_CHUNK_BYTES * 5 + 3)
        self._write("big.bin", payload)
        fact = self._facts("evidence/big.bin")[0]
        self.assertEqual(fact.reason, "")
        self.assertEqual(fact.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(fact.size, len(payload))

    def test_prefix_normalisation_strips_the_evidence_segment_once(self) -> None:
        self.assertEqual(
            normalise_evidence_reference("evidence/a.png"),
            ("evidence/a.png", "a.png"))
        self.assertEqual(
            normalise_evidence_reference("EVIDENCE/a.png"),
            ("evidence/a.png", "a.png"))
        self.assertEqual(
            normalise_evidence_reference("a.png"), ("a.png", None))


if __name__ == "__main__":
    unittest.main()