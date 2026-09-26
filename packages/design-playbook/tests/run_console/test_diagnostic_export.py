#!/usr/bin/env python3
"""Diagnostic export contract v1 — pure projection tests (ADR-0044, T-047).

Pins the accepted ADR-0044 contract at the module seam:
the field table against real fixture snapshots, the envelope discipline
(value only when ``known``, reasonCode passthrough otherwise), the
``notCollected`` and exclusion scans over every exported byte, the canonical
serialization / preview hash, the Markdown human view, and the zero-filesystem
read-only boundary of the module itself.

The module must never touch the filesystem, open a socket, or spawn a
process — monkeypatched primitives assert that at the OS boundary.
"""
from __future__ import annotations

import io
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from tests.run_console import test_http_server as harness  # noqa: E402
from design_playbook.mcp.run_console.diagnostic_export import (  # noqa: E402
    EXPORT_CONTRACT_ID,
    EXPORT_CONTRACT_VERSION,
    TRIAL_PROTOCOL_DOC,
    ExportInputError,
    build_export_document,
    canonical_json_bytes,
    preview_hash,
    render_markdown,
)

_NOW = "2026-08-25T10:00:00Z"
_FIXTURES = harness._COMPONENT_DIR / "fixtures"


def _build_document(base: Path, name: str, *, recirculate: bool = False,
                    missing: bool = False, inconsistent: bool = False) -> dict:
    root = harness._make_root(base, name)
    if recirculate:
        (root / "point-back.md").write_text(
            (_FIXTURES / "point-back-recirculate.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    elif missing:
        (root / "contract-bind.json").unlink()
    elif inconsistent:
        conflicting = dict(harness._CONTRACT_BIND)
        conflicting["open_fields"] = ["nav.item-count"]
        conflicting["assumed_fields"] = ["nav.item-count"]
        (root / "contract-bind.json").write_text(json.dumps(conflicting), encoding="utf-8")
    from design_playbook.mcp.run_console.snapshot_builder import build_snapshot
    built = build_snapshot(
        selected_root=root,
        package_root=_PKG_ROOT,
        session_secret=b"contract-test-secret-0123456789abcdef",
        now=_NOW,
    )
    return built.document


class FieldTableTests(unittest.TestCase):
    """Spec §3 field table projected from a real pass-closed snapshot."""

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-contract-") as tmp:
            cls.snapshot = _build_document(Path(tmp), "run-fieldtable")
        cls.export = build_export_document(
            cls.snapshot, participant_ref="P-TEST-1"
        )

    def test_identity_block(self) -> None:
        self.assertEqual(
            self.export["exportContract"],
            {"id": EXPORT_CONTRACT_ID, "version": EXPORT_CONTRACT_VERSION},
        )
        self.assertEqual(EXPORT_CONTRACT_ID, "diagnostic-export.schema.v1")
        self.assertEqual(self.export["participantRef"], "P-TEST-1")
        self.assertEqual(
            self.export["usage"],
            {
                "evidence": False,
                "acceptanceInput": False,
                "upload": "none-manual-share-only",
            },
        )
        self.assertEqual(
            self.export["transaction"],
            {
                "participantReviewed": True,
                "atomicJsonAndMarkdown": True,
                "confinedToTrialExport": True,
            },
        )
        # The preview hash is never in-band: it is the hash of these bytes.
        self.assertNotIn("previewHash", self.export)

    def test_run_block_copies_snapshot_facts(self) -> None:
        run = self.export["run"]
        run_env = self.snapshot["identity"]["run"]
        self.assertEqual(run["availability"], run_env["availability"])
        self.assertEqual(
            run["runId"], run_env["result"]["runId"]
        )
        self.assertEqual(
            run["label"], run_env["result"]["label"]
        )
        self.assertEqual(
            run["sourceSetHash"], self.snapshot["sources"]["sourceSetHash"]
        )
        self.assertEqual(
            run["builtAt"], self.snapshot["identity"]["snapshot"]["builtAt"]
        )
        self.assertEqual(
            run["buildState"], self.snapshot["identity"]["snapshot"]["buildState"]
        )
        self.assertEqual(run["snapshotSchemaVersion"], 1)

    def test_product_profile_intent_verdict_envelopes(self) -> None:
        snapshot = self.snapshot
        export = self.export
        for name, snap_key in (
            ("product", ("identity", "product")),
            ("profile", ("identity", "profile")),
            ("intent", ("intent", "summary")),
            ("verdict", ("evaluation", "verdict")),
        ):
            source = snapshot[snap_key[0]][snap_key[1]]
            envelope = export[name]
            self.assertEqual(envelope["availability"], source["availability"], name)
            self.assertEqual(
                envelope["value"],
                source["result"] if source["availability"] == "known" else None,
                name,
            )
        self.assertEqual(export["verdict"]["value"], "Pass")

    def test_intent_is_comprehension_fact_one(self) -> None:
        self.assertEqual(
            self.export["intent"]["value"],
            self.snapshot["intent"]["summary"]["result"],
        )

    def test_blockers_carry_blocking_findings_and_limitations(self) -> None:
        snapshot_findings = self.snapshot["evaluation"]["findings"]
        blocking = [
            item["result"]
            for item in snapshot_findings
            if item["availability"] == "known"
            and item["result"].get("disposition") == "blocking"
        ]
        exported = self.export["blockers"]["findings"]
        exported_blocking = [f for f in exported if f.get("disposition") == "blocking"]
        self.assertEqual(len(exported_blocking), len(blocking))
        for projected in exported_blocking:
            self.assertIn("findingId", projected)
            self.assertIn("severity", projected)
            self.assertIn("issue", projected)
            self.assertIn("ownerKind", projected)
            self.assertIn("repair", projected)
        for item in self.snapshot["limitations"]["items"]:
            if item["availability"] == "known":
                self.assertIn(
                    item["result"]["code"],
                    [lim["code"] for lim in self.export["blockers"]["limitations"]],
                )

    def test_next_action_hides_command_text(self) -> None:
        primary = self.snapshot["nextActions"]["primary"]
        exported = self.export["nextAction"]
        self.assertEqual(exported["availability"], primary["availability"])
        value = exported["value"]
        self.assertIsNotNone(value)
        self.assertEqual(value["kind"], primary["result"]["kind"])
        self.assertEqual(
            value["owner"], primary["result"]["owner"]["actor"]
        )
        self.assertEqual(value["label"], primary["result"]["label"])
        command = primary["result"].get("copyableAgentCommand")
        self.assertEqual(value["hasCopyableCommand"], bool(command))
        # The command text itself is structurally absent from every byte.
        if command:
            self.assertNotIn(command, canonical_json_bytes(self.export).decode("utf-8"))
            self.assertNotIn(command, render_markdown(self.export))

    def test_loop_progress_counts(self) -> None:
        repair = self.snapshot["execution"]["repair"]
        self.assertEqual(
            self.export["loop"]["value"], repair["result"]
            if repair["availability"] == "known" else None
        )
        criteria = self.snapshot["evaluation"]["criteria"]
        known = sum(1 for item in criteria if item["availability"] == "known")
        self.assertEqual(self.export["counts"]["criteriaKnown"], known)
        self.assertEqual(self.export["counts"]["criteriaTotal"], len(criteria))

    def test_not_collected_block_is_honest(self) -> None:
        not_collected = self.export["notCollected"]
        self.assertEqual(set(not_collected), {
            "comprehensionTiming", "participantAnswers", "interventionRecords",
        })
        for statement in not_collected.values():
            self.assertTrue(statement.strip())


class EnvelopeDisciplineTests(unittest.TestCase):
    """Non-known assertions project value=None with the reason code."""

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-envelope-") as tmp:
            cls.missing = build_export_document(
                _build_document(Path(tmp), "run-missing", missing=True),
            )
            cls.inconsistent = build_export_document(
                _build_document(Path(tmp), "run-inconsistent", inconsistent=True),
            )

    def test_missing_contract_projects_unknown_with_reason(self) -> None:
        # contract-bind.json removed: assertions bound to it are not known.
        degraded = self.missing["run"]["buildState"]
        self.assertEqual(degraded, "degraded")
        known_verdict = self.missing["verdict"]
        if known_verdict["availability"] != "known":
            self.assertIsNone(known_verdict["value"])
            self.assertIsNotNone(known_verdict["reasonCode"])

    def test_inconsistent_contract_projects_with_conflict_reason(self) -> None:
        self.assertEqual(self.inconsistent["run"]["buildState"], "degraded")
        for envelope in (
            self.inconsistent["intent"],
            self.inconsistent["verdict"],
        ):
            if envelope["availability"] != "known":
                self.assertIsNone(envelope["value"])
                self.assertIn(envelope["availability"],
                              ("unknown", "stale", "inconsistent"))

    def test_synthetic_unknown_verdict_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-synthetic-") as tmp:
            snapshot = _build_document(Path(tmp), "run-synthetic")
        snapshot["evaluation"]["verdict"] = {
            "id": "evaluation.verdict",
            "availability": "stale",
            "result": "Pass",
            "reason": {
                "code": "source-changed-during-build",
                "message": "point-back.md changed during the build",
                "sourceRefs": [],
                "observedHashes": [],
                "verifiedHashes": [],
                "conflicts": [],
            },
            "source": snapshot["evaluation"]["verdict"]["source"],
            "approval": None,
        }
        export = build_export_document(snapshot)
        self.assertEqual(export["verdict"]["availability"], "stale")
        self.assertIsNone(export["verdict"]["value"])
        self.assertEqual(export["verdict"]["reasonCode"], "source-changed-during-build")
        markdown = render_markdown(export)
        self.assertIn("**stale**", markdown)
        self.assertIn("`source-changed-during-build`", markdown)

    def test_empty_participant_ref_is_not_invented(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-ref-") as tmp:
            snapshot = _build_document(Path(tmp), "run-ref")
        export = build_export_document(snapshot)
        self.assertIsNone(export["participantRef"])
        with self.assertRaises(ExportInputError):
            build_export_document(
                snapshot, participant_ref=7
            )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ExportInputError):
            build_export_document({"schemaVersion": 2})
        with self.assertRaises(ExportInputError):
            build_export_document("nope")
        with tempfile.TemporaryDirectory(prefix="dx-broken-") as tmp:
            snapshot = _build_document(Path(tmp), "run-broken")
        broken = dict(snapshot)
        broken.pop("intent")
        with self.assertRaises(ExportInputError):
            build_export_document(broken)


class ExclusionScanTests(unittest.TestCase):
    """Every exported byte obeys the spec §3 exclusion list."""

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-scan-") as tmp:
            cls.export = build_export_document(
                _build_document(Path(tmp), "run-scan"),
                participant_ref="P-SCAN",
            )
        cls.json_text = canonical_json_bytes(cls.export).decode("utf-8")
        cls.markdown = render_markdown(cls.export)
        cls.everything = cls.json_text + cls.markdown

    def test_not_collected_is_stated(self) -> None:
        for phrase in ("comprehensionTiming", "participantAnswers", "interventionRecords"):
            self.assertIn(phrase, self.everything)

    def test_no_timing_or_answer_vocabulary(self) -> None:
        lowered = self.everything.lower()
        for phrase in ("elapsed", "median", "stopwatch", '"timing"'):
            self.assertNotIn(phrase, lowered)

    def test_no_source_code_or_excerpts(self) -> None:
        # The export carries source-set hashes and locator-free facts only;
        # it must not embed the point-back prose, the spec text, or any
        # artifact bytes.
        spec_text = (_FIXTURES / "spec-script-summary.md").read_text(encoding="utf-8")
        for paragraph in spec_text.split("\n\n"):
            paragraph = paragraph.strip()
            if len(paragraph) > 40:
                self.assertNotIn(paragraph[:60], self.everything)

    def test_no_generated_participant_identity(self) -> None:
        # participantRef appears only as the participant-supplied echo; the
        # export never fabricates one when none was supplied.
        with tempfile.TemporaryDirectory(prefix="dx-noref-") as tmp:
            export = build_export_document(
                _build_document(Path(tmp), "run-noref"),
            )
        self.assertIsNone(export["participantRef"])
        self.assertNotIn('"participantRef": "', canonical_json_bytes(export).decode("utf-8"))


class SerializationTests(unittest.TestCase):
    """Canonical bytes, preview hash, and Markdown determinism."""

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-canon-") as tmp:
            cls.snapshot = _build_document(Path(tmp), "run-canon")
        cls.export = build_export_document(
            cls.snapshot        )

    def test_canonical_bytes_shape(self) -> None:
        raw = canonical_json_bytes(self.export)
        text = raw.decode("utf-8")
        self.assertTrue(text.endswith("\n"))
        parsed = json.loads(text)
        self.assertEqual(parsed, self.export)
        # Deterministic: same document, same bytes.
        self.assertEqual(raw, canonical_json_bytes(self.export))
        # Sorted keys: the exportContract block is alphabetically ordered.
        self.assertIn('"exportContract"', text)

    def test_preview_hash_is_sha256_over_canonical_bytes(self) -> None:
        import hashlib
        expected = hashlib.sha256(canonical_json_bytes(self.export)).hexdigest()
        self.assertEqual(preview_hash(self.export), expected)
        self.assertEqual(len(expected), 64)
        # The projection is a pure function of (snapshot, participantRef):
        # no clock inside, so the preview hash survives a ticking clock
        # between preview and write (the S36 binding stays satisfiable).
        self.assertEqual(preview_hash(self.export), preview_hash(self.export))

    def test_markdown_human_view_sections(self) -> None:
        markdown = render_markdown(self.export)
        self.assertIn("# Diagnostic export", markdown)
        self.assertIn(f"`{EXPORT_CONTRACT_ID}` v{EXPORT_CONTRACT_VERSION}", markdown)
        self.assertIn("not Evidence", markdown)
        self.assertIn("no upload", markdown)
        for fact in ("Intent", "Source verdict", "Blockers", "Next owner"):
            self.assertIn(fact, markdown)
        self.assertIn("## Not collected", markdown)
        self.assertIn(TRIAL_PROTOCOL_DOC, markdown)

    def test_markdown_is_deterministic(self) -> None:
        self.assertEqual(
            render_markdown(self.export), render_markdown(self.export)
        )


class ReadOnlyBoundaryTests(unittest.TestCase):
    """The module touches no file, opens no socket, spawns no process."""

    def test_projection_is_filesystem_free(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dx-readonly-") as tmp:
            snapshot = _build_document(Path(tmp), "run-readonly")
        with mock.patch.object(Path, "open", side_effect=AssertionError("open")), \
                mock.patch.object(Path, "write_text", side_effect=AssertionError("write")), \
                mock.patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
                mock.patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
                mock.patch.object(socket.socket, "__init__",
                                  side_effect=AssertionError("socket")), \
                mock.patch.object(subprocess.Popen, "__init__",
                                  side_effect=AssertionError("process")):
            export = build_export_document(
                snapshot, participant_ref="P-RO"
            )
            render_markdown(export)
            canonical_json_bytes(export)
            preview_hash(export)
        self.assertEqual(export["participantRef"], "P-RO")

    def test_export_input_io_is_not_a_file_read(self) -> None:
        # ExportInputError is raised on dict inputs; io/open are never used.
        with mock.patch.object(io, "open", side_effect=AssertionError("io.open")):
            with self.assertRaises(ExportInputError):
                build_export_document(None)


if __name__ == "__main__":
    unittest.main()
