#!/usr/bin/env python3
"""Tests for the owner projection publisher (R12 thin interface).

The publisher only transcribes owner-decided facts. These tests hold it to
that: every positive case asserts the exact document written, and every
negative case asserts a refusal (exit 2, nothing written) rather than a guess.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.publish_owner_projection import (  # noqa: E402
    PROJECTION_ROOT,
    PROJECTION_VERSION,
    ProjectionPublishError,
    artifact_basename,
    build_projection,
    check_run_id,
    criteria_rows,
    evidence_rows,
    finding_rows,
    main,
    map_verdict,
    prefixed_digest,
    projection_path,
    read_manifest,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
#: Two ledger rows: a passing criterion and a not-applicable one.
LEDGER = """
criterion: L6.1
required: evidence/L6.1.png
observed: evidence/L6.1.png (captured populated state)
result: pass

criterion: L6.2
required: evidence/L6.2.png
observed: evidence/L6.2.png
result: N/A
"""


def _manifest_entry(criterion: str, artifact: str, digest: str) -> dict:
    return {
        "ts": "2026-09-26T12:00:00+00:00",
        "criterion": criterion,
        "artifact": artifact,
        "sha256": digest,
        "request": {"schemaVersion": 1},
    }


class PublisherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.run = self.base / "run"
        (self.run / "evidence").mkdir(parents=True)
        self.project = self.base / "project"
        self.project.mkdir()
        self.ledger = self.base / "ledger.md"
        self.ledger.write_text(LEDGER, encoding="utf-8")
        self.entries = [
            _manifest_entry("L6.1", "L6.1.png", DIGEST_A),
            _manifest_entry("L6.2", "L6.2.png", DIGEST_B),
        ]
        (self.run / "evidence" / "manifest.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in self.entries) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def publish_document(self, **overrides) -> dict:
        kwargs = {
            "run_id": "run-1",
            "owner": "ui-evaluator",
            "project_id": "p-1",
            "runner": "design-playbook ui-evaluator",
            "entries": self.entries,
            "ledger_text": LEDGER,
            "generated_at": "2026-09-26T12:30:00+00:00",
        }
        kwargs.update(overrides)
        return build_projection(**kwargs)


class TranscriptionTest(PublisherTestCase):
    def test_document_carries_the_versions_and_owners_the_reader_expects(self) -> None:
        document = self.publish_document()
        self.assertEqual(document["version"], PROJECTION_VERSION)
        self.assertEqual(document["owner"], "ui-evaluator")
        self.assertEqual(document["runId"], "run-1")
        self.assertEqual(document["projectId"], "p-1")
        self.assertEqual(document["generatedAt"], "2026-09-26T12:30:00+00:00")

    def test_evidence_rows_copy_the_owner_binding_verbatim(self) -> None:
        rows = evidence_rows(self.entries)
        self.assertEqual(rows[0]["evidenceId"], "L6.1.png")
        self.assertEqual(rows[0]["criterionId"], "L6.1")
        self.assertEqual(rows[0]["hash"], "sha256:" + DIGEST_A)
        self.assertEqual(rows[0]["capturedAt"], "2026-09-26T12:00:00+00:00")
        # The manifest states no kind or media type, so none is invented.
        self.assertNotIn("kind", rows[0])
        self.assertNotIn("mediaType", rows[0])

    def test_evidence_kind_is_carried_only_when_the_owner_states_it(self) -> None:
        entry = dict(self.entries[0], kind="screenshot", mediaType="image/png")
        row = evidence_rows([entry])[0]
        self.assertEqual(row["kind"], "screenshot")
        self.assertEqual(row["mediaType"], "image/png")

    def test_criteria_verdicts_come_from_the_ledger(self) -> None:
        rows = criteria_rows(LEDGER, self.entries)
        self.assertEqual([row["criterionId"] for row in rows], ["L6.1", "L6.2"])
        self.assertEqual(rows[0]["verdict"], "pass")
        # N/A is not applicable, which is not a pass.
        self.assertEqual(rows[1]["verdict"], "unknown")

    def test_criterion_evidence_hashes_come_from_the_manifest(self) -> None:
        rows = criteria_rows(LEDGER, self.entries)
        self.assertEqual(rows[0]["evidenceHashes"], ["sha256:" + DIGEST_A])
        self.assertEqual(rows[1]["evidenceHashes"], ["sha256:" + DIGEST_B])

    def test_criterion_source_hash_is_the_bound_artifact_digest(self) -> None:
        rows = criteria_rows(LEDGER, self.entries)
        self.assertEqual(rows[0]["sourceHash"], "sha256:" + DIGEST_A)

    def test_criterion_without_a_bound_artifact_omits_the_source_hash(self) -> None:
        # No manifest binding for L6.2 beyond its own entry: drop the binding
        # and the hash must be omitted, never invented.
        rows = criteria_rows(LEDGER, [self.entries[0]])
        self.assertNotIn("sourceHash", rows[1])
        self.assertEqual(rows[1]["evidenceHashes"], [])

    def test_a_criterion_row_never_claims_a_semantic_role_it_was_not_given(self) -> None:
        rows = criteria_rows(LEDGER, self.entries)
        self.assertNotIn("role", rows[0])

    def test_findings_are_only_what_was_supplied(self) -> None:
        self.assertEqual(self.publish_document()["findings"], [])
        supplied = [
            {
                "findingId": "f-1",
                "severity": "high",
                "summary": "contrast fails",
                "criterionId": "L6.2",
                "pointBack": {"kind": "source", "path": "a.css", "note": "fix"},
            }
        ]
        rows = finding_rows(supplied)
        self.assertEqual(rows[0]["findingId"], "f-1")
        self.assertEqual(rows[0]["severity"], "high")
        self.assertEqual(rows[0]["pointBack"]["repairOwner"], "")


class VerdictMappingTest(unittest.TestCase):
    def test_owner_vocabulary_maps_and_unknown_values_are_refused(self) -> None:
        for raw, expected in (
            ("pass", "pass"),
            ("fail", "fail"),
            ("blocked", "blocked"),
            ("N/A", "unknown"),
            ("n/a", "unknown"),
            ("PASS", "pass"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(map_verdict(raw), expected)
        for bad in ("green", "", "maybe", None, 7):
            with self.subTest(bad=bad), self.assertRaises(ProjectionPublishError):
                map_verdict(bad)


class RunIdGuardTest(unittest.TestCase):
    def test_hostile_run_ids_are_refused(self) -> None:
        for bad in (
            "",
            " ",
            ".",
            "..",
            "../escape",
            "..\\escape",
            "a/b",
            "a\\b",
            "C:\\abs",
            "nul\x00byte",
        ):
            with self.subTest(bad=bad), self.assertRaises(ProjectionPublishError):
                check_run_id(bad)

    def test_a_plain_segment_is_accepted(self) -> None:
        for good in ("run-1", "L6.run_2", "2026-09-26T12-00-00Z"):
            with self.subTest(good=good):
                self.assertEqual(check_run_id(good), good)

    def test_projection_path_stays_under_the_project_root(self) -> None:
        root = Path("root").resolve()
        target = projection_path(root, "run-1")
        self.assertEqual(
            target, root / PROJECTION_ROOT / "run-1" / "projection.json"
        )
        with self.assertRaises(ProjectionPublishError):
            projection_path(root, "../escape")


class DigestTest(unittest.TestCase):
    def test_digest_is_normalised_and_validated(self) -> None:
        self.assertEqual(prefixed_digest(DIGEST_A.upper()), "sha256:" + DIGEST_A)
        for bad in ("", "abc", "z" * 64, None, 42):
            with self.subTest(bad=bad), self.assertRaises(ProjectionPublishError):
                prefixed_digest(bad)


class RefusalTest(PublisherTestCase):
    def test_missing_owner_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            self.publish_document(owner="")

    def test_unknown_ledger_result_is_refused(self) -> None:
        ledger = LEDGER.replace("result: pass", "result: probably")
        with self.assertRaises(ProjectionPublishError):
            criteria_rows(ledger, self.entries)

    def test_ledger_row_without_a_result_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            criteria_rows(
                "criterion: L6.1\nrequired: evidence/L6.1.png\n", self.entries
            )

    def test_ledger_row_without_a_criterion_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            criteria_rows("required: x\nresult: pass\n", self.entries)

    def test_duplicate_rows_for_one_criterion_are_refused(self) -> None:
        duplicated = (
            "criterion: L6.1\nobserved: evidence/L6.1.png\nresult: pass\n\n"
            "criterion: L6.1\nobserved: evidence/L6.1.png\nresult: fail\n"
        )
        with self.assertRaises(ProjectionPublishError):
            criteria_rows(duplicated, self.entries)

    def test_a_ledger_with_no_rows_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            criteria_rows("just prose, no fields\n", self.entries)

    def test_manifest_line_that_is_not_json_is_refused(self) -> None:
        (self.run / "evidence" / "manifest.jsonl").write_text(
            "{not json}\n", encoding="utf-8"
        )
        with self.assertRaises(ProjectionPublishError):
            read_manifest(self.run)

    def test_entry_without_artifact_or_criterion_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            evidence_rows([{"criterion": "L6.1", "sha256": DIGEST_A}])
        with self.assertRaises(ProjectionPublishError):
            evidence_rows([{"artifact": "a.png", "sha256": DIGEST_A}])

    def test_non_hex_manifest_digest_is_refused(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            evidence_rows([_manifest_entry("L6.1", "a.png", "not-a-digest")])

    def test_findings_must_be_a_list_of_identified_objects(self) -> None:
        with self.assertRaises(ProjectionPublishError):
            finding_rows({"findingId": "f"})
        with self.assertRaises(ProjectionPublishError):
            finding_rows([{"summary": "no id"}])
        with self.assertRaises(ProjectionPublishError):
            finding_rows([{"findingId": "f", "pointBack": "not-an-object"}])

    def test_missing_manifest_is_refused(self) -> None:
        (self.run / "evidence" / "manifest.jsonl").unlink()
        with self.assertRaises(ProjectionPublishError):
            read_manifest(self.run)


class CliTest(PublisherTestCase):
    def _argv(self, *extra: str) -> list[str]:
        return [
            str(self.run),
            "--project-root",
            str(self.project),
            "--run-id",
            "run-1",
            "--owner",
            "ui-evaluator",
            "--ledger",
            str(self.ledger),
            *extra,
        ]

    def test_publish_writes_the_reader_path_and_leaves_nothing_else(self) -> None:
        self.assertEqual(main(self._argv()), 0)
        target = self.project / PROJECTION_ROOT / "run-1" / "projection.json"
        self.assertTrue(target.is_file())
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], PROJECTION_VERSION)
        self.assertEqual(document["owner"], "ui-evaluator")
        self.assertEqual([row["criterionId"] for row in document["criteria"]],
                         ["L6.1", "L6.2"])
        # No temporary file survives the atomic replace.
        leftovers = [
            path.name
            for path in target.parent.iterdir()
            if path.name != "projection.json"
        ]
        self.assertEqual(leftovers, [])

    def test_stdout_mode_writes_no_file(self) -> None:
        self.assertEqual(main(self._argv("--stdout")), 0)
        self.assertFalse(
            (self.project / PROJECTION_ROOT).exists(),
            "dry run must not create the projection tree",
        )

    def test_a_refusal_exits_non_zero_and_writes_nothing(self) -> None:
        self.ledger.write_text(
            "criterion: L6.1\nobserved: evidence/L6.1.png\nresult: shrug\n",
            encoding="utf-8",
        )
        self.assertEqual(main(self._argv()), 2)
        self.assertFalse((self.project / PROJECTION_ROOT).exists())

    def test_findings_file_is_consumed(self) -> None:
        findings = self.base / "findings.json"
        findings.write_text(
            json.dumps([{"findingId": "f-1", "summary": "x"}]), encoding="utf-8"
        )
        self.assertEqual(main(self._argv("--findings", str(findings))), 0)
        document = json.loads(
            (
                self.project / PROJECTION_ROOT / "run-1" / "projection.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(document["findings"][0]["findingId"], "f-1")

    def test_missing_ledger_file_exits_with_an_error(self) -> None:
        self.assertEqual(
            main(self._argv("--ledger", str(self.base / "nope.md"))), 3
        )


class ArtifactTokenTest(unittest.TestCase):
    def test_observed_tokens_reduce_to_the_bare_artifact(self) -> None:
        for token, expected in (
            ("evidence/L6.1.png", "L6.1.png"),
            ("L6.1.png", "L6.1.png"),
            ("evidence/sub/L6.1.png", "sub/L6.1.png"),
        ):
            with self.subTest(token=token):
                self.assertEqual(artifact_basename(token), expected)


class ConstantsTest(unittest.TestCase):
    def test_constants_match_the_workbench_reader_when_it_is_importable(self) -> None:
        # Cross-package contract check. Skipped when the workbench package is
        # not present in this tree rather than guessed at.
        workbench = PACKAGE.parent / "design-playbook-workbench"
        if not (workbench / "design_playbook_workbench" / "owners.py").is_file():
            self.skipTest("workbench package is not in this tree")
        sys.path.insert(0, str(workbench))
        try:
            from design_playbook_workbench import owners  # noqa: PLC0415
        finally:
            sys.path.remove(str(workbench))
        self.assertEqual(PROJECTION_VERSION, owners.PROJECTION_VERSION)
        self.assertEqual(PROJECTION_ROOT, owners.PROJECTION_ROOT)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
