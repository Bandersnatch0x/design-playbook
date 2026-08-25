#!/usr/bin/env python3
"""Executable Run Snapshot v1 consumer-contract tests."""
from __future__ import annotations

from copy import deepcopy
import json
import sys
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.contract import (  # noqa: E402
    SNAPSHOT_CONTRACT_INVALID,
    SNAPSHOT_VERSION_UNSUPPORTED,
    SnapshotContractError,
    validate_snapshot,
)

_HASH_1 = "sha256:" + "1" * 64
_HASH_2 = "sha256:" + "2" * 64
_HASH_3 = "sha256:" + "3" * 64
_SOURCE_SET_HASH = "sha256:ae4087e19ce6bf9b20bf13d07ef52f306c8ecd9ed17f8df509854348ae8220cd"
_CHANGED_SET_HASH = "sha256:c54403acd026068030b77133287ff0eb5ad0c3b9fb1caec87ac3a7faf4b1ac8c"


def _source(
    source_ref: str,
    authority_key: str,
    *,
    observed_hash: str = _HASH_1,
    verified_hash: str = _HASH_1,
    freshness: str = "current",
) -> dict[str, object]:
    return {
        "sourceRef": source_ref,
        "authorityKey": authority_key,
        "kind": "authority-record",
        "locator": None,
        "readState": "complete",
        "observedHash": observed_hash,
        "verifiedHash": verified_hash,
        "freshness": freshness,
        "observedAt": "2026-08-25T08:00:00Z",
        "verifiedAt": "2026-08-25T08:00:00Z",
    }


def _reason(
    code: str,
    source_refs: list[str],
    *,
    observed_hashes: list[str] | None = None,
    verified_hashes: list[str] | None = None,
    conflicts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "message": "The current authority facts do not yield a current value.",
        "sourceRefs": source_refs,
        "observedHashes": observed_hashes or [],
        "verifiedHashes": verified_hashes or [],
        "conflicts": conflicts or [],
    }


def _assertion(
    assertion_id: str,
    result: object,
    *,
    source_refs: list[str] | None = None,
) -> dict[str, object]:
    refs = source_refs or ["source.common"]
    return {
        "id": assertion_id,
        "availability": "known",
        "result": result,
        "reason": None,
        "source": {
            "refs": refs,
            "observedSetHash": _HASH_1,
            "verifiedSetHash": _HASH_1,
        },
        "approval": None,
    }


def _valid_snapshot() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "identity": {
            "snapshot": {
                "builtAt": "2026-08-25T08:00:00Z",
                "sourceSetHash": _SOURCE_SET_HASH,
                "buildState": "current",
            },
            "run": _assertion(
                "identity.run",
                {"runId": "run_AQIDBAUGBwgJCgsMDQ4PEA", "label": None},
            ),
            "product": _assertion(
                "identity.product",
                {"name": "design-playbook", "version": "0.20.2"},
            ),
            "profile": _assertion(
                "identity.profile",
                {
                    "declaredTier": "P2",
                    "effectiveTier": "P2",
                    "confirmedBy": "human",
                },
            ),
        },
        "intent": {
            "summary": _assertion("intent.summary", "Deliver a safe checkout."),
            "criteria": [
                _assertion(
                    "intent.criteria.checkout-safe",
                    {
                        "criterionId": "checkout-safe",
                        "title": "Checkout remains safe",
                        "given": "A valid cart",
                        "when": "The shopper checks out",
                        "then": "The purchase succeeds once",
                    },
                )
            ],
            "contract": _assertion(
                "intent.contract",
                {
                    "openFields": [],
                    "assumedFields": [],
                    "staleFields": [],
                    "blocking": False,
                },
            ),
        },
        "execution": {
            "progress": _assertion(
                "execution.progress",
                {
                    "observedStages": [
                        {
                            "stageId": "spec",
                            "label": "Specification",
                            "presence": "present",
                            "skipReason": None,
                        }
                    ],
                    "latestObservedStage": "spec",
                },
            ),
            "preview": _assertion(
                "execution.preview", {"state": "absent", "round": None}
            ),
            "repair": _assertion(
                "execution.repair",
                {
                    "rounds": 0,
                    "closeReason": "pass",
                    "waitingForHuman": False,
                    "routes": [],
                },
            ),
        },
        "evaluation": {
            "verdict": _assertion(
                "evaluation.verdict", "Pass", source_refs=["source.evaluator-report"]
            ),
            "criteria": [
                _assertion(
                    "evaluation.criteria.checkout-safe",
                    {
                        "criterionId": "checkout-safe",
                        "outcome": "pass",
                        "requiredProof": "Rendered checkout proof",
                        "observedSummary": "The checkout completed once.",
                        "evidenceBindings": [
                            {
                                "artifactId": "artifact.checkout",
                                "sourceRef": "source.evaluator-report",
                                "contentHash": _HASH_3,
                            }
                        ],
                    },
                )
            ],
            "findings": [
                _assertion(
                    "evaluation.findings.checkout-copy",
                    {
                        "findingId": "checkout-copy",
                        "criterionIds": ["checkout-safe"],
                        "issue": "One label is ambiguous.",
                        "severity": "S1",
                        "disposition": "advisory",
                        "owner": {
                            "kind": "declaration",
                            "domainId": "intent.summary",
                            "sourceRef": "source.common",
                        },
                        "repair": "Clarify the label.",
                    },
                )
            ],
            "coverage": _assertion(
                "evaluation.coverage",
                {"declared": 1, "reviewed": 1, "unreviewed": 0, "complete": True},
            ),
        },
        "nextActions": {
            "primary": _assertion(
                "next-actions.primary",
                {
                    "actionId": "action.stop-after-pass",
                    "kind": "stop",
                    "label": "Run complete.",
                    "owner": {"actor": "run-operator", "role": None},
                    "copyableAgentCommand": None,
                },
            ),
            "alternatives": [],
        },
        "limitations": {"items": []},
        "sources": {
            "sourceSetHash": _SOURCE_SET_HASH,
            "items": [
                _source("source.common", "session.selected-run"),
                _source(
                    "source.evaluator-report",
                    "evaluation.evaluator",
                    observed_hash=_HASH_3,
                    verified_hash=_HASH_3,
                ),
            ],
        },
    }


def _assert_contract_invalid(test: unittest.TestCase, document: object) -> None:
    with test.assertRaises(SnapshotContractError) as ctx:
        validate_snapshot(document)
    test.assertEqual(ctx.exception.code, SNAPSHOT_CONTRACT_INVALID)


class SnapshotContractVersionTests(unittest.TestCase):
    """S01/S02: only the complete integer-v1 root crosses the seam."""

    def test_s02_rejects_missing_string_and_unknown_versions(self) -> None:
        for version in (None, "1", 0, 2, True):
            with self.subTest(version=version):
                document = {} if version is None else {"schemaVersion": version}
                with self.assertRaises(SnapshotContractError) as ctx:
                    validate_snapshot(document)
                self.assertEqual(ctx.exception.code, SNAPSHOT_VERSION_UNSUPPORTED)
                self.assertEqual(
                    ctx.exception.to_envelope(request_id="req_test"),
                    {
                        "schemaVersion": 1,
                        "error": {
                            "code": SNAPSHOT_VERSION_UNSUPPORTED,
                            "message": "The Run Snapshot version is not supported.",
                            "requestId": "req_test",
                            "retryable": False,
                        },
                    },
                )

    def test_s01_rejects_v1_without_the_seven_sections_as_contract_invalid(self) -> None:
        with self.assertRaises(SnapshotContractError) as ctx:
            validate_snapshot({"schemaVersion": 1})
        self.assertEqual(ctx.exception.code, SNAPSHOT_CONTRACT_INVALID)


class SnapshotContractShapeTests(unittest.TestCase):
    """S01/S03/S04: closed shape plus globally unique ordered addresses."""

    def test_s01_accepts_complete_closed_v1_document(self) -> None:
        document = _valid_snapshot()
        validated = validate_snapshot(document)
        self.assertEqual(validated, document)
        self.assertIsNot(validated, document)

    def test_s03_rejects_missing_and_unknown_fields_at_fixed_boundaries(self) -> None:
        cases: list[dict[str, object]] = []
        missing = _valid_snapshot()
        del missing["evaluation"]["coverage"]  # type: ignore[index]
        cases.append(missing)
        unknown = _valid_snapshot()
        unknown["intent"]["summary"]["rawPath"] = "C:\\secret"  # type: ignore[index]
        cases.append(unknown)
        nested_unknown = _valid_snapshot()
        nested_unknown["sources"]["items"][0]["filename"] = "point-back.md"  # type: ignore[index]
        cases.append(nested_unknown)
        for document in cases:
            with self.subTest(document=document):
                _assert_contract_invalid(self, document)

    def test_s04_rejects_duplicate_assertion_ids_and_source_refs(self) -> None:
        duplicate_id = _valid_snapshot()
        duplicate_id["intent"]["criteria"][0]["id"] = "intent.summary"  # type: ignore[index]
        duplicate_ref = _valid_snapshot()
        duplicate_ref["sources"]["items"][1]["sourceRef"] = "source.common"  # type: ignore[index]
        for document in (duplicate_id, duplicate_ref):
            with self.subTest(document=document):
                _assert_contract_invalid(self, document)

    def test_rejects_unsorted_assertion_arrays_and_source_refs(self) -> None:
        assertions = _valid_snapshot()
        alternative = _assertion(
            "next-actions.alternatives.z-last",
            {
                "actionId": "action.z-last",
                "kind": "stop",
                "label": "Last",
                "owner": {"actor": "run-operator", "role": None},
                "copyableAgentCommand": None,
            },
        )
        first = deepcopy(alternative)
        first["id"] = "next-actions.alternatives.a-first"
        first["result"]["actionId"] = "action.a-first"  # type: ignore[index]
        assertions["nextActions"]["alternatives"] = [alternative, first]  # type: ignore[index]

        refs = _valid_snapshot()
        refs["evaluation"]["verdict"]["source"]["refs"] = [  # type: ignore[index]
            "source.evaluator-report",
            "source.common",
        ]
        for document in (assertions, refs):
            with self.subTest(document=document):
                _assert_contract_invalid(self, document)


class SnapshotContractAssertionTests(unittest.TestCase):
    """S05-S11/S13-S14: availability never strengthens a domain result."""

    def test_s05_rejects_invalid_known_assertion_bindings(self) -> None:
        variants = []
        for mutate in (
            lambda assertion: assertion.update(result=None),
            lambda assertion: assertion.update(
                reason=_reason("source-malformed", ["source.evaluator-report"])
            ),
            lambda assertion: assertion["source"].update(refs=[]),
            lambda assertion: assertion["source"].update(verifiedSetHash=_HASH_2),
        ):
            document = _valid_snapshot()
            mutate(document["evaluation"]["verdict"])  # type: ignore[index]
            variants.append(document)
        for document in variants:
            with self.subTest(document=document):
                _assert_contract_invalid(self, document)

    def test_s06_rejects_non_null_unknown_result(self) -> None:
        document = _valid_snapshot()
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="unknown",
            reason=_reason(
                "not-produced",
                ["source.evaluator-report"],
                observed_hashes=[_HASH_3],
                verified_hashes=[_HASH_3],
            ),
        )
        _assert_contract_invalid(self, document)

    def test_s07_accepts_stale_pass_only_with_changed_binding_and_degraded_build(self) -> None:
        document = _valid_snapshot()
        document["sources"]["sourceSetHash"] = _CHANGED_SET_HASH  # type: ignore[index]
        document["identity"]["snapshot"].update(  # type: ignore[index]
            sourceSetHash=_CHANGED_SET_HASH, buildState="degraded"
        )
        source = document["sources"]["items"][1]  # type: ignore[index]
        source.update(verifiedHash=_HASH_2, freshness="changed")
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="stale",
            reason=_reason(
                "source-changed-during-build",
                ["source.evaluator-report"],
                observed_hashes=[_HASH_3],
                verified_hashes=[_HASH_2],
            ),
        )
        assertion["source"].update(verifiedSetHash=_HASH_2)
        self.assertEqual(
            validate_snapshot(document)["evaluation"]["verdict"]["availability"],
            "stale",
        )

    def test_s08_accepts_null_inconsistent_result_with_named_conflicts(self) -> None:
        document = _valid_snapshot()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="inconsistent",
            result=None,
            reason=_reason(
                "conflicting-authorities",
                ["source.common", "source.evaluator-report"],
                observed_hashes=[_HASH_1, _HASH_3],
                verified_hashes=[_HASH_1, _HASH_3],
                conflicts=[
                    {
                        "sourceRef": "source.common",
                        "hash": _HASH_1,
                        "summary": "The first authority reports Pass.",
                    },
                    {
                        "sourceRef": "source.evaluator-report",
                        "hash": _HASH_3,
                        "summary": "The second authority reports Recirculate.",
                    },
                ],
            ),
        )
        assertion["source"]["refs"] = ["source.common", "source.evaluator-report"]
        validated = validate_snapshot(document)
        self.assertIsNone(validated["evaluation"]["verdict"]["result"])

    def test_s09_accepts_known_not_applicable_domain_result(self) -> None:
        document = _valid_snapshot()
        document["evaluation"]["criteria"][0]["result"]["outcome"] = (  # type: ignore[index]
            "notApplicable"
        )
        validated = validate_snapshot(document)
        self.assertEqual(
            validated["evaluation"]["criteria"][0]["result"]["outcome"],
            "notApplicable",
        )

    def test_s10_accepts_unknown_not_produced_without_degrading_unrelated_assertions(self) -> None:
        document = _valid_snapshot()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["execution"]["preview"]  # type: ignore[index]
        assertion.update(
            availability="unknown",
            result=None,
            reason=_reason(
                "not-produced",
                ["source.common"],
                observed_hashes=[_HASH_1],
                verified_hashes=[_HASH_1],
            ),
        )
        validated = validate_snapshot(document)
        self.assertEqual(validated["execution"]["preview"]["availability"], "unknown")
        self.assertEqual(validated["evaluation"]["verdict"]["availability"], "known")

    def test_s11_accepts_unknown_no_canonical_value_and_never_selects_pass(self) -> None:
        document = _valid_snapshot()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="unknown",
            result=None,
            reason=_reason(
                "no-canonical-value",
                ["source.evaluator-report"],
                observed_hashes=[_HASH_3],
                verified_hashes=[_HASH_3],
            ),
        )
        self.assertIsNone(validate_snapshot(document)["evaluation"]["verdict"]["result"])

    def test_s12_same_document_validates_to_byte_equivalent_detached_values(self) -> None:
        document = _valid_snapshot()
        first = validate_snapshot(document)
        second = validate_snapshot(document)
        canonical = lambda value: json.dumps(  # noqa: E731
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        self.assertEqual(canonical(first), canonical(second))
        self.assertIsNot(first, second)

    def test_s13_rejects_changed_source_claimed_as_current_build(self) -> None:
        document = _valid_snapshot()
        document["sources"]["sourceSetHash"] = _CHANGED_SET_HASH  # type: ignore[index]
        document["identity"]["snapshot"]["sourceSetHash"] = _CHANGED_SET_HASH  # type: ignore[index]
        document["sources"]["items"][1].update(  # type: ignore[index]
            verifiedHash=_HASH_2, freshness="changed"
        )
        _assert_contract_invalid(self, document)

    def test_s14_accepts_unknown_partial_write_without_prior_value(self) -> None:
        document = _valid_snapshot()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="unknown",
            result=None,
            reason=_reason("partial-write", ["source.evaluator-report"]),
        )
        self.assertEqual(
            validate_snapshot(document)["evaluation"]["verdict"]["reason"]["code"],
            "partial-write",
        )


class SnapshotContractInvariantTests(unittest.TestCase):
    """Hashes, approvals, timestamps, build state, and safe errors are coherent."""

    def test_rejects_malformed_digest_timestamp_locator_and_run_id(self) -> None:
        variants = []
        for path, value in (
            (("identity", "snapshot", "sourceSetHash"), "sha256:ABC"),
            (("identity", "snapshot", "builtAt"), "2026-08-25T08:00:00+00:00"),
            (("identity", "snapshot", "builtAt"), "2026-02-31T08:00:00Z"),
            (("identity", "run", "result", "runId"), "C:\\repo\\run"),
            (("sources", "items", 0, "locator"), "../point-back.md"),
        ):
            document = _valid_snapshot()
            target: object = document
            for segment in path[:-1]:
                target = target[segment]  # type: ignore[index]
            target[path[-1]] = value  # type: ignore[index]
            variants.append(document)
        for document in variants:
            with self.subTest(document=document):
                _assert_contract_invalid(self, document)

    def test_rejects_source_verification_before_observation(self) -> None:
        document = _valid_snapshot()
        document["sources"]["items"][0]["verifiedAt"] = "2026-08-25T07:59:59Z"  # type: ignore[index]
        _assert_contract_invalid(self, document)

    def test_rejects_inconsistent_source_set_hash(self) -> None:
        document = _valid_snapshot()
        document["sources"]["sourceSetHash"] = _HASH_2  # type: ignore[index]
        document["identity"]["snapshot"]["sourceSetHash"] = _HASH_2  # type: ignore[index]
        _assert_contract_invalid(self, document)

    def test_approval_binding_rules_are_enforced(self) -> None:
        document = _valid_snapshot()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["intent"]["summary"]  # type: ignore[index]
        assertion.update(
            availability="unknown",
            result=None,
            reason=_reason(
                "attestation-missing",
                ["source.common"],
                observed_hashes=[_HASH_1],
                verified_hashes=[_HASH_1],
            ),
            approval={
                "claimId": "claim.intent.checkout-safety",
                "claimHash": _HASH_2,
                "requiredRole": "product",
                "authorityKey": "intent.contract",
                "sourceRef": "source.common",
                "sourceHash": _HASH_1,
                "state": "missing",
                "attestationId": None,
            },
        )
        validate_snapshot(document)

        invalid = deepcopy(document)
        invalid["intent"]["summary"]["approval"]["attestationId"] = "attestation.fake"
        _assert_contract_invalid(self, invalid)

        wrong_source = deepcopy(document)
        wrong_source["intent"]["summary"]["approval"]["sourceHash"] = _HASH_2
        _assert_contract_invalid(self, wrong_source)

    def test_rejects_path_token_and_traceback_in_safe_reason_text(self) -> None:
        for leaked in (
            "The source C:\\private\\run\\point-back.md is missing.",
            "Authorization: Bearer secret-value",
            "Traceback (most recent call last): internal failure",
        ):
            with self.subTest(leaked=leaked):
                document = _valid_snapshot()
                document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
                assertion = document["evaluation"]["verdict"]  # type: ignore[index]
                assertion.update(
                    availability="unknown",
                    result=None,
                    reason=_reason(
                        "source-unreadable",
                        ["source.evaluator-report"],
                        observed_hashes=[_HASH_3],
                        verified_hashes=[_HASH_3],
                    ),
                )
                assertion["reason"]["message"] = leaked
                _assert_contract_invalid(self, document)

    def test_error_envelope_never_includes_rejected_document_details(self) -> None:
        secret = "token_secret C:\\private\\run Traceback (most recent call last)"
        document = _valid_snapshot()
        document["unknown"] = secret
        with self.assertRaises(SnapshotContractError) as ctx:
            validate_snapshot(document)
        rendered = json.dumps(ctx.exception.to_envelope(request_id="req_safe"))
        self.assertNotIn(secret, rendered)
        self.assertNotIn("private", rendered)
        self.assertEqual(set(ctx.exception.to_envelope(request_id="req_safe")), {"schemaVersion", "error"})

    def test_schema_artifact_freezes_version_sections_and_closed_objects(self) -> None:
        schema = json.loads(
            Path(__file__).with_name("snapshot_v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertEqual(
            set(schema["required"]),
            {
                "schemaVersion",
                "identity",
                "intent",
                "execution",
                "evaluation",
                "nextActions",
                "limitations",
                "sources",
            },
        )

        def object_schemas(node: object):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    yield node
                for value in node.values():
                    yield from object_schemas(value)
            elif isinstance(node, list):
                for value in node:
                    yield from object_schemas(value)

        self.assertTrue(all(item.get("additionalProperties") is False for item in object_schemas(schema)))


if __name__ == "__main__":
    unittest.main()
