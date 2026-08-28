#!/usr/bin/env python3
"""Snapshot builder tests: one-shot capture, owner parse, re-verify, atom.

These tests pin the RCV1-005 slice-B contract for
``design_playbook.mcp.run_console.snapshot_builder``:

- one build captures the allowlisted sources once, hashes the exact
  captured parser inputs, parses through owner seams, re-verifies the
  same registry entries at end-of-build, and returns one atomic,
  contract-valid Snapshot document;
- stale (TOCTOU), partial-write, inconsistent, missing, unreadable, and
  malformed sources surface as typed degraded results inside the
  document, never as a retry that serves the previous snapshot;
- the builder reads only allowlisted targets, writes nothing, and leaks
  no path, root, username, or stack trace.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview.integrity import (  # noqa: E402
    prototype_html_digest,
)
from design_playbook.mcp.run_console.contract import (  # noqa: E402
    validate_snapshot,
)
from design_playbook.mcp.run_console.snapshot_builder import (  # noqa: E402
    BuiltSnapshot,
    SnapshotBuildError,
    build_snapshot,
)
from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    select_source_registry,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SESSION_SECRET = b"builder-test-session-secret-005"
_NOW = "2026-08-25T10:00:00Z"
_LOCATOR = re.compile(r"^src_[A-Za-z0-9_-]{16,}$")

_CONTRACT_BIND = {
    "ok": True,
    "schemaVersion": 1,
    "contract_sha": "a" * 64,
    "decision_log_sha": "b" * 64,
    "open_fields": [],
    "assumed_fields": [],
    "stale_fields": [],
    "blockers": [],
}
_MANIFEST_ENTRY = {
    "criterion": "L6.3",
    "artifact": "L6.3-error.png",
    "ts": "2026-08-25T09:00:00+08:00",
}
_ARTIFACT_BYTES = b"fake-png-bytes-for-l6-3"

# Owner-valid scenario point-backs: the Point-back projection seam rejects
# a Recirculate verdict without a Findings section and a bare unaudited
# text, so the scenarios reuse the canonical fixture shapes.
_RECIRCULATE_POINTBACK = (
    _FIXTURES / "point-back-recirculate.md"
).read_text(encoding="utf-8")

# An unaudited skeleton point-back: audited: false, all rows n/a, with the
# anti-forgery placeholder verdict that must never earn a Pass.
_UNAUDITED_POINTBACK = (
    _FIXTURES / "point-back-unaudited.md"
).read_text(encoding="utf-8")


def _write(root: Path, relpath: str, text: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _make_pass_root(base: Path, name: str = "run-a") -> Path:
    """A complete current run root through the inherited fixtures."""
    root = base / name
    root.mkdir(parents=True)
    _write(root, "spec.md", (_FIXTURES / "spec-script-summary.md").read_text(encoding="utf-8"))
    _write(root, "plan.md", (_FIXTURES / "plan-profile.md").read_text(encoding="utf-8"))
    _write(
        root,
        "point-back.md",
        (_FIXTURES / "point-back-pass-closed.md").read_text(encoding="utf-8"),
    )
    _write(root, "contract-bind.json", json.dumps(_CONTRACT_BIND))
    _write(root, "evidence/manifest.jsonl", json.dumps(_MANIFEST_ENTRY) + "\n")
    (root / "evidence" / "L6.3-error.png").write_bytes(_ARTIFACT_BYTES)
    (root / "preview").mkdir()
    return root


def _build(root: Path, **kwargs: object) -> BuiltSnapshot:
    return build_snapshot(
        selected_root=root,
        package_root=_PKG_ROOT,
        session_secret=_SESSION_SECRET,
        **kwargs,  # type: ignore[arg-type]
    )


def _assertion(document: dict, assertion_id: str) -> dict:
    """Fetch one assertion by id from anywhere in the document."""
    found = [
        assertion
        for assertion in _iter_assertions(document)
        if assertion["id"] == assertion_id
    ]
    assert len(found) == 1, f"expected exactly one {assertion_id}"
    return found[0]


def _iter_assertions(document: dict):
    fixed_paths = (
        ("identity", "run"),
        ("identity", "product"),
        ("identity", "profile"),
        ("intent", "summary"),
        ("intent", "contract"),
        ("execution", "progress"),
        ("execution", "preview"),
        ("execution", "repair"),
        ("evaluation", "verdict"),
        ("evaluation", "coverage"),
        ("nextActions", "primary"),
    )
    for path in fixed_paths:
        yield document[path[0]][path[1]]
    yield from document["intent"]["criteria"]
    yield from document["evaluation"]["criteria"]
    yield from document["evaluation"]["findings"]
    yield from document["nextActions"]["alternatives"]
    yield from document["limitations"]["items"]


def _source(document: dict, source_ref: str) -> dict:
    for item in document["sources"]["items"]:
        if item["sourceRef"] == source_ref:
            return item
    raise AssertionError(f"no source record {source_ref}")


class _BuilderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_pass_root(self.base)
        self.built = _build(self.run_root, now=_NOW)
        self.document = self.built.document

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _rebuild(self) -> dict:
        return _build(self.run_root, now=_NOW).document


class PassBuildTest(_BuilderTestCase):
    def test_document_is_contract_valid_and_current(self) -> None:
        validated = validate_snapshot(self.document)
        self.assertEqual(validated, self.document)
        self.assertEqual(self.document["schemaVersion"], 1)
        self.assertEqual(
            set(self.document),
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
        self.assertEqual(
            self.document["identity"]["snapshot"]["buildState"], "current"
        )

    def test_every_assertion_is_known(self) -> None:
        assertions = list(_iter_assertions(self.document))
        self.assertGreaterEqual(len(assertions), 20)
        for assertion in assertions:
            with self.subTest(assertion_id=assertion["id"]):
                self.assertEqual(assertion["availability"], "known")
                self.assertIsNotNone(assertion["result"])
                self.assertIsNone(assertion["reason"])
                self.assertIsNone(assertion["approval"])
                observed = assertion["source"]["observedSetHash"]
                verified = assertion["source"]["verifiedSetHash"]
                self.assertIsNotNone(observed)
                self.assertEqual(observed, verified)

    def test_domain_values_match_owner_truth(self) -> None:
        self.assertEqual(
            self.document["identity"]["run"]["result"],
            {"runId": self.built.registry.run_id, "label": None},
        )
        self.assertEqual(
            self.document["identity"]["product"]["result"]["name"],
            "design-playbook",
        )
        self.assertEqual(
            self.document["identity"]["profile"]["result"],
            {"declaredTier": "P2", "effectiveTier": "P2", "confirmedBy": "human"},
        )
        self.assertEqual(
            self.document["evaluation"]["verdict"]["result"], "Pass"
        )
        self.assertEqual(
            self.document["execution"]["preview"]["result"],
            {"state": "absent", "round": None},
        )
        self.assertEqual(
            self.document["execution"]["repair"]["result"],
            {"rounds": 0, "closeReason": "pass", "waitingForHuman": False, "routes": []},
        )
        self.assertEqual(
            self.document["evaluation"]["coverage"]["result"],
            {"declared": 5, "reviewed": 5, "unreviewed": 0, "complete": True},
        )
        self.assertEqual(
            self.document["intent"]["contract"]["result"],
            {
                "openFields": [],
                "assumedFields": [],
                "staleFields": [],
                "blocking": False,
            },
        )
        self.assertEqual(
            self.document["nextActions"]["primary"]["result"]["actionId"],
            "action.stop-after-pass",
        )
        self.assertEqual(self.document["nextActions"]["alternatives"], [])
        self.assertEqual(
            [item["result"]["code"] for item in self.document["limitations"]["items"]],
            [
                "diagnostic-export-contract-unavailable",
                "role-attestation-owner-unmapped",
            ],
        )

    def test_progress_follows_stage_registry_order(self) -> None:
        result = self.document["execution"]["progress"]["result"]
        self.assertEqual(
            [stage["stageId"] for stage in result["observedStages"]],
            [
                "baseline",
                "reference",
                "spec",
                "plan",
                "decision",
                "preview",
                "fill",
                "craft",
                "evidence",
                "accept",
            ],
        )
        by_id = {stage["stageId"]: stage for stage in result["observedStages"]}
        self.assertEqual(by_id["baseline"]["presence"], "skipped")
        self.assertEqual(
            by_id["baseline"]["skipReason"], "adapter absent, no baseline needed"
        )
        self.assertEqual(by_id["spec"]["presence"], "present")
        self.assertEqual(by_id["preview"]["presence"], "absent")
        self.assertEqual(result["latestObservedStage"], "accept")

    def test_evidence_binding_exists_only_for_the_bound_artifact(self) -> None:
        criteria = {
            item["id"]: item["result"]
            for item in self.document["evaluation"]["criteria"]
        }
        for criterion_id in ("l6-1", "l6-2", "l6-4", "l6-5"):
            self.assertEqual(criteria[f"evaluation.criteria.{criterion_id}"]["evidenceBindings"], [])
        binding = criteria["evaluation.criteria.l6-3"]["evidenceBindings"]
        self.assertEqual(len(binding), 1)
        self.assertEqual(
            binding[0]["artifactId"], "evidence-artifact.l6-3-error-png"
        )
        self.assertEqual(
            binding[0]["sourceRef"], "source.evidence-artifact.l6-3-error-png"
        )
        self.assertEqual(
            binding[0]["contentHash"],
            "sha256:" + hashlib.sha256(_ARTIFACT_BYTES).hexdigest(),
        )

    def test_sources_items_are_complete_current_and_located(self) -> None:
        items = self.document["sources"]["items"]
        refs = [item["sourceRef"] for item in items]
        self.assertEqual(refs, sorted(refs))
        self.assertEqual(len(refs), len(set(refs)))
        self.assertIn("source.evidence-artifact.l6-3-error-png", refs)
        locators = []
        for item in items:
            with self.subTest(source_ref=item["sourceRef"]):
                self.assertEqual(item["readState"], "complete")
                self.assertEqual(item["freshness"], "current")
                self.assertEqual(item["observedHash"], item["verifiedHash"])
                self.assertIsNotNone(item["observedHash"])
                self.assertIsNotNone(item["verifiedAt"])
                if item["authorityKey"] == "run.limitations":
                    self.assertIsNone(item["locator"])
                else:
                    self.assertIsNotNone(item["locator"], item["sourceRef"])
                    self.assertIsNotNone(_LOCATOR.match(item["locator"]))
                    locators.append(item["locator"])
        self.assertEqual(len(locators), len(set(locators)))

    def test_rebuild_with_fixed_clock_is_equivalent_modulo_locators(self) -> None:
        again = _build(self.run_root, now=_NOW).document
        self.assertEqual(
            _normalized(self.document), _normalized(again), "semantic drift"
        )

    def test_document_leaks_no_path_root_or_username(self) -> None:
        serialized = json.dumps(self.document, ensure_ascii=False)
        for forbidden in (
            str(self.run_root),
            self.run_root.name,
            str(self.base),
            "\\",
            "Users",
            "traceback",
        ):
            self.assertNotIn(forbidden, serialized)


def _normalized(document: dict) -> str:
    """Canonical semantic form: sorted keys, volatile values normalized."""
    def scrub(value, path=()):
        if isinstance(value, dict):
            return {key: scrub(item, path + (key,)) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item, path) for item in value]
        if (
            path[-1:] == ("locator",)
            and isinstance(value, str)
        ):
            return "<locator>"
        if (
            path[-1:] in (("builtAt",), ("observedAt",), ("verifiedAt",))
            and isinstance(value, str)
        ):
            return "<time>"
        return value

    return json.dumps(scrub(document), ensure_ascii=False, sort_keys=True)


class DegradingBuildTest(_BuilderTestCase):
    def test_toctou_mutation_marks_dependent_assertions_stale(self) -> None:
        original = self.document

        def mutate() -> None:
            (self.run_root / "spec.md").write_text(
                "# Mutated\n\n## L1 定位与意图\n\n- 一句话定义：mutated summary\n",
                encoding="utf-8",
            )

        rebuilt = _build(self.run_root, now=_NOW, mid_build_hook=mutate).document
        self.assertEqual(
            rebuilt["identity"]["snapshot"]["buildState"], "degraded"
        )
        spec_record = _source(rebuilt, "source.specification")
        self.assertEqual(spec_record["freshness"], "changed")
        self.assertNotEqual(
            spec_record["observedHash"], spec_record["verifiedHash"]
        )
        for assertion_id in ("intent.summary", "intent.criteria.l6-1"):
            assertion = _assertion(rebuilt, assertion_id)
            self.assertEqual(assertion["availability"], "stale")
            self.assertIsNone(assertion["result"])
            self.assertEqual(
                assertion["reason"]["code"], "source-changed-during-build"
            )
            self.assertNotEqual(
                assertion["source"]["observedSetHash"],
                assertion["source"]["verifiedSetHash"],
            )
        # No substitution of the previous snapshot: the new build has no
        # current Pass predicate from the old bytes.
        self.assertEqual(
            _assertion(rebuilt, "identity.product")["availability"], "known"
        )
        self.assertNotEqual(
            _assertion(rebuilt, "intent.summary")["source"]["observedSetHash"],
            _assertion(original, "intent.summary")["source"]["observedSetHash"],
        )

    def test_missing_spec_degrades_only_dependent_assertions(self) -> None:
        (self.run_root / "spec.md").unlink()
        document = self._rebuild()
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )
        spec_record = _source(document, "source.specification")
        self.assertEqual(spec_record["readState"], "missing")
        self.assertIsNone(spec_record["observedHash"])
        self.assertEqual(spec_record["freshness"], "unverified")
        summary = _assertion(document, "intent.summary")
        self.assertEqual(summary["availability"], "unknown")
        self.assertIsNone(summary["result"])
        self.assertEqual(summary["reason"]["code"], "source-missing")
        self.assertEqual(document["intent"]["criteria"], [])
        for assertion_id in (
            "evaluation.verdict",
            "evaluation.coverage",
        ):
            assertion = _assertion(document, assertion_id)
            self.assertEqual(assertion["availability"], "unknown")
            self.assertEqual(
                assertion["reason"]["code"], "dependency-unavailable"
            )
        self.assertEqual(document["evaluation"]["findings"], [])
        # Unrelated assertions keep their own availability.
        self.assertEqual(
            _assertion(document, "identity.product")["availability"], "known"
        )
        self.assertEqual(
            _assertion(document, "execution.preview")["availability"], "known"
        )

    def test_missing_plan_degrades_profile_only(self) -> None:
        (self.run_root / "plan.md").unlink()
        document = self._rebuild()
        profile = _assertion(document, "identity.profile")
        self.assertEqual(profile["availability"], "unknown")
        self.assertEqual(profile["reason"]["code"], "source-missing")
        self.assertEqual(_source(document, "source.run-profile")["readState"], "missing")
        self.assertEqual(
            _assertion(document, "execution.progress")["availability"], "known"
        )
        progress = document["execution"]["progress"]["result"]
        self.assertEqual(
            [stage["presence"] for stage in progress["observedStages"] if stage["stageId"] == "plan"][0],
            "absent",
        )
        self.assertEqual(
            _assertion(document, "evaluation.verdict")["availability"], "known"
        )

    def test_missing_point_back_degrades_evaluation_and_repair(self) -> None:
        (self.run_root / "point-back.md").unlink()
        document = self._rebuild()
        for assertion_id in (
            "evaluation.verdict",
            "evaluation.coverage",
            "execution.repair",
        ):
            assertion = _assertion(document, assertion_id)
            self.assertEqual(assertion["availability"], "unknown")
            self.assertEqual(assertion["reason"]["code"], "source-missing")
        self.assertEqual(document["evaluation"]["criteria"], [])
        self.assertEqual(_source(document, "source.evaluator-report")["readState"], "missing")
        # Next action remains known from the remaining owner facts.
        self.assertEqual(
            _assertion(document, "next-actions.primary")["availability"], "known"
        )

    def test_unreadable_plan_maps_to_source_unreadable(self) -> None:
        (self.run_root / "plan.md").write_bytes(b"\xff\xfe not utf-8")
        document = self._rebuild()
        profile = _assertion(document, "identity.profile")
        self.assertEqual(profile["availability"], "unknown")
        self.assertEqual(profile["reason"]["code"], "source-unreadable")
        self.assertEqual(_source(document, "source.run-profile")["readState"], "unreadable")

    def test_malformed_spec_is_source_malformed(self) -> None:
        (self.run_root / "spec.md").write_text(
            "# Spec\n\n## L1 定位与意图\n\n- 一句话定义：summary\n\n"
            "## L6 验收标准\n\n- Given x\n",
            encoding="utf-8",
        )
        document = self._rebuild()
        summary = _assertion(document, "intent.summary")
        self.assertEqual(summary["availability"], "unknown")
        self.assertEqual(summary["reason"]["code"], "source-malformed")
        self.assertEqual(_source(document, "source.specification")["readState"], "complete")

    def test_unaudited_point_back_keeps_criteria_known(self) -> None:
        (self.run_root / "point-back.md").write_text(
            _UNAUDITED_POINTBACK, encoding="utf-8"
        )
        document = self._rebuild()
        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "unknown")
        self.assertIsNone(verdict["result"])
        self.assertEqual(verdict["reason"]["code"], "no-canonical-value")
        for item in document["evaluation"]["criteria"]:
            self.assertEqual(item["availability"], "known")
            self.assertEqual(item["result"]["outcome"], "notApplicable")
        coverage = _assertion(document, "evaluation.coverage")
        self.assertEqual(
            coverage["result"],
            {"declared": 5, "reviewed": 0, "unreviewed": 5, "complete": False},
        )

    def test_repeated_verdict_is_no_canonical_value(self) -> None:
        (self.run_root / "point-back.md").write_text(
            (_FIXTURES / "point-back-repeated-verdict.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        document = self._rebuild()
        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "unknown")
        self.assertEqual(verdict["reason"]["code"], "no-canonical-value")
        known = [
            item for item in document["evaluation"]["findings"]
            if item["availability"] == "known"
        ]
        unmapped = [
            item for item in document["evaluation"]["findings"]
            if item["availability"] != "known"
        ]
        self.assertEqual(len(known), 3)
        self.assertEqual(len(unmapped), 3)
        for item in unmapped:
            self.assertEqual(item["reason"]["code"], "owner-unmapped")
        codes = [
            item["result"]["code"]
            for item in document["limitations"]["items"]
        ]
        self.assertIn("owner-unmapped", codes)

    def test_recirculate_point_back_is_known_recirculate(self) -> None:
        (self.run_root / "point-back.md").write_text(
            _RECIRCULATE_POINTBACK, encoding="utf-8"
        )
        document = self._rebuild()
        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "known")
        self.assertEqual(verdict["result"], "Recirculate")

    def test_truncated_contract_bind_is_partial_write(self) -> None:
        (self.run_root / "contract-bind.json").write_text(
            '{"ok": true, "open_fields": ["nav.item', encoding="utf-8"
        )
        document = self._rebuild()
        contract = _assertion(document, "intent.contract")
        self.assertEqual(contract["availability"], "unknown")
        self.assertIsNone(contract["result"])
        self.assertEqual(contract["reason"]["code"], "partial-write")

    def test_conflicting_contract_bind_is_inconsistent(self) -> None:
        conflicting = dict(_CONTRACT_BIND)
        conflicting["open_fields"] = ["nav.item-count"]
        conflicting["assumed_fields"] = ["nav.item-count"]
        (self.run_root / "contract-bind.json").write_text(
            json.dumps(conflicting), encoding="utf-8"
        )
        document = self._rebuild()
        contract = _assertion(document, "intent.contract")
        self.assertEqual(contract["availability"], "inconsistent")
        self.assertIsNone(contract["result"])
        self.assertEqual(contract["reason"]["code"], "invariant-violation")
        conflicts = contract["reason"]["conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["sourceRef"], "source.contract-bind")
        self.assertEqual(
            conflicts[0]["hash"],
            _source(document, "source.contract-bind")["observedHash"],
        )

    def test_missing_artifact_keeps_outcome_known_without_binding(self) -> None:
        (self.run_root / "evidence" / "L6.3-error.png").unlink()
        document = self._rebuild()
        criterion = _assertion(document, "evaluation.criteria.l6-3")
        self.assertEqual(criterion["availability"], "known")
        self.assertEqual(criterion["result"]["outcome"], "pass")
        self.assertEqual(criterion["result"]["evidenceBindings"], [])
        refs = [item["sourceRef"] for item in document["sources"]["items"]]
        self.assertNotIn("source.evidence-artifact.l6-3-error-png", refs)
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )

    def test_unbound_manifest_entry_yields_no_binding(self) -> None:
        entry = dict(_MANIFEST_ENTRY)
        entry["criterion"] = "L6.2"
        _write(self.run_root, "evidence/manifest.jsonl", json.dumps(entry) + "\n")
        document = self._rebuild()
        criterion = _assertion(document, "evaluation.criteria.l6-3")
        self.assertEqual(criterion["availability"], "known")
        self.assertEqual(criterion["result"]["evidenceBindings"], [])


class PreviewConfirmProjectionTest(_BuilderTestCase):
    """execution.preview confirm mapping (parity spec section 2, issue #106).

    A flags-valid current confirm projects ``confirmed`` only while the
    Preview integrity owner reports no prototype hash mismatch; a mismatch
    can never be upgraded to ``confirmed``. The fixture records follow the
    confirm-round-*.json shape the Preview transaction writer produces.
    """

    _PROTOTYPE = "<html><body>round one</body></html>"

    def setUp(self) -> None:
        super().setUp()
        _write(self.run_root, "preview/round-1.html", self._PROTOTYPE)

    def _confirm_record(self, **overrides: object) -> dict:
        record: dict = {
            "round": 1,
            "report_ref": "decision-report.md",
            "confirmed": True,
            "floor_pass": True,
            "selected_options": ["确认通过"],
            "feedback": "确认通过，无修改意见",
            "timestamp": "2026-08-25T09:00:00+08:00",
            "prototype_path": "preview/round-1.html",
            "prototype_html_hash": prototype_html_digest(
                self._PROTOTYPE.encode("utf-8")
            ),
            "decision_id": "d" * 32,
        }
        record.update(overrides)
        return {key: value for key, value in record.items() if value is not None}

    def _preview_result(self) -> dict:
        document = self._rebuild()
        self.assertEqual(validate_snapshot(document), document)
        assertion = _assertion(document, "execution.preview")
        self.assertEqual(assertion["availability"], "known")
        return assertion["result"]

    def test_confirmed_with_matching_prototype_hash_is_confirmed(self) -> None:
        _write(
            self.run_root,
            "preview/confirm-round-1.json",
            json.dumps(self._confirm_record(), ensure_ascii=False),
        )
        self.assertEqual(
            self._preview_result(), {"state": "confirmed", "round": 1}
        )

    def test_prototype_hash_mismatch_is_never_upgraded_to_confirmed(self) -> None:
        _write(
            self.run_root,
            "preview/confirm-round-1.json",
            json.dumps(
                self._confirm_record(
                    prototype_html_hash=prototype_html_digest(
                        b"<html><body>original, since altered</body></html>"
                    )
                ),
                ensure_ascii=False,
            ),
        )
        result = self._preview_result()
        self.assertNotEqual(result["state"], "confirmed")
        self.assertEqual(result, {"state": "invalid", "round": 1})

    def test_confirmed_without_expected_digest_stays_confirmed(self) -> None:
        # The owner has no stored digest to check against (pre-0.4.4 or
        # hand-written record); the spec's non-upgradable set is only
        # unreadable/malformed/hash mismatch.
        _write(
            self.run_root,
            "preview/confirm-round-1.json",
            json.dumps(
                self._confirm_record(prototype_html_hash=None),
                ensure_ascii=False,
            ),
        )
        self.assertEqual(
            self._preview_result(), {"state": "confirmed", "round": 1}
        )

    def test_aborted_confirm_projects_aborted(self) -> None:
        _write(
            self.run_root,
            "preview/confirm-round-1.json",
            json.dumps(self._confirm_record(aborted=True), ensure_ascii=False),
        )
        self.assertEqual(
            self._preview_result(), {"state": "aborted", "round": 1}
        )

    def test_unconfirmed_record_projects_invalid(self) -> None:
        _write(
            self.run_root,
            "preview/confirm-round-1.json",
            json.dumps(
                self._confirm_record(
                    confirmed=False,
                    floor_pass=False,
                    feedback="",
                    selected_options=["需要修改"],
                ),
                ensure_ascii=False,
            ),
        )
        self.assertEqual(
            self._preview_result(), {"state": "invalid", "round": 1}
        )

    def test_round_without_confirm_projects_open(self) -> None:
        self.assertEqual(self._preview_result(), {"state": "open", "round": 1})


class BuilderSafetyTest(_BuilderTestCase):
    def test_invalid_build_input_is_a_typed_error(self) -> None:
        for kwargs in (
            {"now": "not-a-timestamp"},
            {"now": None},
            {"mid_build_hook": "not-callable"},
        ):
            with self.subTest(kwargs=repr(kwargs)[:60]):
                with self.assertRaises(SnapshotBuildError):
                    _build(self.run_root, **kwargs)  # type: ignore[arg-type]

    def test_failed_rebuild_after_prior_success_is_a_typed_error(self) -> None:
        first = self.document
        import shutil

        shutil.rmtree(self.run_root)
        with self.assertRaises(SnapshotBuildError) as caught:
            _build(self.run_root, now=_NOW)
        self.assertEqual(caught.exception.code, "selected-run-invalid")
        self.assertNotIn(str(self.base), str(caught.exception))
        # The previously returned document is untouched and was never
        # re-served: the failed rebuild raises instead.
        self.assertEqual(
            first["identity"]["snapshot"]["buildState"], "current"
        )

    def test_builder_reads_only_allowlisted_targets(self) -> None:
        hostile = {
            "browser-payload.json": '{"sources": ["source.evil"]}',
            "evil.py": "print('evil')\n",
            "random-dir/x.txt": "not allowlisted\n",
        }
        for name, text in hostile.items():
            _write(self.run_root, name, text)
        registry = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        recorded: list[Path] = []
        original_read_text = Path.read_text
        original_read_bytes = Path.read_bytes

        def recording_read_text(self_path: Path, *args: object, **kwargs: object) -> str:
            recorded.append(self_path)
            return original_read_text(self_path, *args, **kwargs)  # type: ignore[arg-type]

        def recording_read_bytes(self_path: Path, *args: object) -> bytes:
            recorded.append(self_path)
            return original_read_bytes(self_path, *args)  # type: ignore[arg-type]

        Path.read_text = recording_read_text  # type: ignore[method-assign]
        Path.read_bytes = recording_read_bytes  # type: ignore[method-assign]
        try:
            _build(self.run_root, now=_NOW)
        finally:
            Path.read_text = original_read_text  # type: ignore[method-assign]
            Path.read_bytes = original_read_bytes  # type: ignore[method-assign]
        read_run_files = [
            path for path in recorded if path.is_relative_to(self.run_root)
        ]
        self.assertTrue(read_run_files)
        for path in read_run_files:
            relpath = path.relative_to(self.run_root).as_posix()
            with self.subTest(relpath=relpath):
                self.assertTrue(
                    registry.allows_target(relpath),
                    f"builder read non-allowlisted target {relpath}",
                )
        for name in hostile:
            self.assertFalse(any(p.name == name for p in read_run_files))

    def test_builder_writes_nothing(self) -> None:
        def digest(root: Path) -> str:
            hasher = hashlib.sha256()
            for path in sorted(root.rglob("*")):
                rel = path.relative_to(root).as_posix()
                hasher.update(rel.encode("utf-8"))
                if path.is_file():
                    hasher.update(path.read_bytes())
                else:
                    hasher.update(b"<dir>")
            return hasher.hexdigest()

        before = digest(self.run_root)
        _build(self.run_root, now=_NOW)

        def mutate() -> None:
            pass  # even a no-op hook must not trigger writes

        _build(self.run_root, now=_NOW, mid_build_hook=mutate)
        self.assertEqual(before, digest(self.run_root))

    def test_symlinked_artifact_is_not_read_and_not_bound(self) -> None:
        outside = self.base / "outside-secret.png"
        outside.write_bytes(b"outside bytes must never be read")
        artifact = self.run_root / "evidence" / "L6.3-error.png"
        artifact.unlink()
        try:
            os.symlink(outside, artifact)
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        recorded: list[Path] = []
        original_read_bytes = Path.read_bytes

        def recording(self_path: Path, *args: object) -> bytes:
            recorded.append(self_path)
            return original_read_bytes(self_path, *args)  # type: ignore[arg-type]

        Path.read_bytes = recording  # type: ignore[method-assign]
        try:
            document = _build(self.run_root, now=_NOW).document
        finally:
            Path.read_bytes = original_read_bytes  # type: ignore[method-assign]
        self.assertNotIn(outside, recorded)
        criterion = _assertion(document, "evaluation.criteria.l6-3")
        self.assertEqual(criterion["result"]["evidenceBindings"], [])
        refs = [item["sourceRef"] for item in document["sources"]["items"]]
        self.assertNotIn("source.evidence-artifact.l6-3-error-png", refs)

    def test_built_snapshot_exposes_document_and_registry(self) -> None:
        self.assertIsInstance(self.built, BuiltSnapshot)
        self.assertEqual(
            self.built.registry.run_id,
            self.document["identity"]["run"]["result"]["runId"],
        )


if __name__ == "__main__":
    unittest.main()
