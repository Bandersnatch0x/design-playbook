#!/usr/bin/env python3
"""RCV1-005 slice C: read-parity matrix and the opaque locator resolver.

These tests pin the RCV1-005 slice-C contract:

- every fixture scenario from the parity specification is built through the
  real owner seams (read-only imports) and compared against the Snapshot
  document with exact value/availability agreement -- the parity oracle is
  the owner APIs themselves, never a re-implemented Console parser;
- rebuilding the same immutable source set under a fixed clock is
  byte-equivalent after only the approved volatile treatments (timestamps
  and locators), across fifty rebuilds (S12/S42);
- the selected-run boundary (S41) and the no-leak boundary (S19) hold;
- the opaque locator resolver returns a bounded, plain, contained,
  hash-checked, read-only excerpt (S20-S23) and rejects unknown, expired,
  cross-session, cross-run, path-looking, traversal, encoded, absolute,
  symlink-escaping, and hash-changed requests uniformly, reading zero
  bytes outside the bound source;
- the run_console implementation modules contain no copied owner parser
  regex, no write call, and no network/exec primitive.
"""
from __future__ import annotations

import hashlib
import html
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

from design_playbook.mcp.run_console.contract import (  # noqa: E402
    validate_snapshot,
)
from design_playbook.mcp.run_console.projection import (  # noqa: E402
    SOURCE_HASH_MISMATCH,
    SOURCE_LOCATOR_INVALID,
    SourceViewError,
    resolve_source_excerpt,
)
from design_playbook.mcp.run_console.snapshot_builder import (  # noqa: E402
    SnapshotBuildError,
    build_snapshot,
)
from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    select_source_registry,
)
from design_playbook.scripts.escalation_signals import effective_tier  # noqa: E402
from design_playbook.scripts.g1_spec import project_specification  # noqa: E402
from design_playbook.scripts.pointback_projection import (  # noqa: E402
    VerdictDisposition,
    project_pointback,
)
from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402
from design_playbook.scripts.run_metadata import (  # noqa: E402
    project_package_metadata,
)
from design_playbook.scripts.status_projection import (  # noqa: E402
    inspect_run,
    inspect_vnext,
    project_next_action,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PASS_FIXTURES = _PKG_ROOT / "tests" / "fixtures" / "pass"
_SESSION_SECRET = b"parity-test-session-secret-005"
_OTHER_SECRET = b"parity-test-other-secret-005"
_NOW = "2026-08-25T10:00:00Z"
_LATER = "2026-08-25T11:30:00Z"
_LOCATOR = re.compile(r"^src_[A-Za-z0-9_-]{16,}$")
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

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
_HTML_ARTIFACT = (
    _FIXTURES / "evidence-artifact.html"
).read_text(encoding="utf-8")


def _write(root: Path, relpath: str, text: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _make_root(
    base: Path,
    name: str = "run-a",
    *,
    pointback: str = "point-back-pass-closed.md",
    spec: str = "spec-script-summary.md",
    artifact: bytes = _ARTIFACT_BYTES,
) -> Path:
    """Compose one scenario run root from the shared fixtures."""
    root = base / name
    root.mkdir(parents=True)
    _write(root, "spec.md", (_FIXTURES / spec).read_text(encoding="utf-8"))
    _write(root, "plan.md", (_FIXTURES / "plan-profile.md").read_text(encoding="utf-8"))
    _write(
        root, "point-back.md", (_FIXTURES / pointback).read_text(encoding="utf-8")
    )
    _write(root, "contract-bind.json", json.dumps(_CONTRACT_BIND))
    _write(root, "evidence/manifest.jsonl", json.dumps(_MANIFEST_ENTRY) + "\n")
    (root / "evidence" / "L6.3-error.png").write_bytes(artifact)
    (root / "preview").mkdir()
    return root


def _build(root: Path, **kwargs: object):
    return build_snapshot(
        selected_root=root,
        package_root=_PKG_ROOT,
        session_secret=_SESSION_SECRET,
        now=_NOW,
        **kwargs,  # type: ignore[arg-type]
    )


def _assertion(document: dict, assertion_id: str) -> dict:
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


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized(document: dict) -> str:
    """Canonical semantic form per the parity specification.

    Only ``builtAt``/``observedAt``/``verifiedAt`` and non-null locators are
    normalized, and only after independently checking timestamp shape and
    locator opacity/uniqueness. Everything else must compare exactly.
    """
    locators: list[str] = []

    def scrub(value, path=(), source_ref=None):
        if isinstance(value, dict):
            ref = value.get("sourceRef") if "sourceRef" in value else source_ref
            return {
                key: scrub(item, path + (key,), ref)
                for key, item in sorted(value.items())
            }
        if isinstance(value, list):
            return [scrub(item, path + (index,), source_ref)
                    for index, item in enumerate(value)]
        if path and path[-1] == "locator" and value is not None:
            if not isinstance(value, str) or not _LOCATOR.fullmatch(value):
                raise AssertionError(f"non-opaque locator {value!r}")
            locators.append(value)
            return f"<locator:{source_ref}>"
        if path and path[-1] in ("builtAt", "observedAt", "verifiedAt"):
            if value is not None:
                if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
                    raise AssertionError(f"non-timestamp {value!r}")
                return "<time>"
            return None
        return value

    scrubbed = scrub(document)
    if len(locators) != len(set(locators)):
        raise AssertionError("duplicate locators")
    return json.dumps(scrubbed, ensure_ascii=False, sort_keys=True)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class _ParityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _owner_truth(self, root: Path):
        """Project the same captured inputs through the owner seams only."""
        facts = capture_run_facts(run_root=root)
        spec = project_specification(facts.spec_text)
        criteria_ids = tuple(criterion.criterion_id
                             for criterion in spec.criteria)
        pointback = project_pointback(facts.pointback_text, criteria_ids)
        states = inspect_run(
            root, preview_snapshot=facts.preview, run_facts=facts
        )
        primary = project_next_action(
            states, root, preview_snapshot=facts.preview, run_facts=facts
        ).primary
        repair = inspect_vnext(root, run_facts=facts).repair
        return facts, spec, pointback, states, primary, repair


class PassParityTest(_ParityTestCase):
    """Scenario ``pass``: owner and Snapshot agree on every domain value."""

    def test_owner_truth_matches_snapshot_domain_values(self) -> None:
        built = _build(self.run_root)
        document = built.document
        self.assertEqual(validate_snapshot(document), document)
        self.assertEqual(document["identity"]["snapshot"]["buildState"], "current")

        facts, spec, pointback, states, primary, repair = self._owner_truth(
            self.run_root
        )

        # identity: package owner, run identity, profile owner.
        product = project_package_metadata(_PKG_ROOT)
        self.assertEqual(product.availability, "known")
        self.assertIsNotNone(product.value)
        self.assertEqual(
            document["identity"]["product"]["result"],
            {
                "name": product.value.name,
                "version": product.value.version,
            },
        )
        self.assertEqual(
            document["identity"]["run"]["result"],
            {"runId": built.registry.run_id, "label": None},
        )
        profile = facts.run_profile
        self.assertEqual(
            document["identity"]["profile"]["result"],
            {
                "declaredTier": profile.tier or None,
                "effectiveTier": effective_tier(profile.tier, profile.upgrades),
                "confirmedBy": "human" if profile.confirmed_by else None,
            },
        )

        # intent: specification owner, verbatim (hostile summary included).
        self.assertEqual(document["intent"]["summary"]["result"], spec.summary)
        self.assertEqual(
            [
                {
                    "criterionId": item["result"]["criterionId"],
                    "title": item["result"]["title"],
                    "given": item["result"]["given"],
                    "when": item["result"]["when"],
                    "then": item["result"]["then"],
                }
                for item in document["intent"]["criteria"]
            ],
            [
                {
                    "criterionId": criterion.criterion_id,
                    "title": criterion.title,
                    "given": criterion.given,
                    "when": criterion.when,
                    "then": criterion.then,
                }
                for criterion in spec.criteria
            ],
        )

        # execution: stage registry plus run-profile skip declarations (the
        # two owner seams that feed execution.progress per the parity spec).
        progress = document["execution"]["progress"]["result"]
        skipped = dict(facts.run_profile.skipped) if facts.run_profile else {}
        self.assertEqual(
            [stage["stageId"] for stage in progress["observedStages"]],
            [state.key for state in states],
        )
        self.assertEqual(
            [stage["presence"] for stage in progress["observedStages"]],
            [
                "present"
                if state.present
                else ("skipped" if state.key in skipped else "absent")
                for state in states
            ],
        )
        self.assertEqual(
            [stage["skipReason"] for stage in progress["observedStages"]],
            [
                None if state.present else skipped.get(state.key)
                for state in states
            ],
        )
        self.assertEqual(
            progress["latestObservedStage"],
            next(
                (state.key for state in reversed(states) if state.present),
                None,
            ),
        )
        self.assertEqual(
            document["execution"]["preview"]["result"], {"state": "absent", "round": None}
        )
        self.assertEqual(
            document["execution"]["repair"]["result"],
            {
                "rounds": repair.rounds,
                "closeReason": repair.close_reason,
                "waitingForHuman": repair.wait_user,
                "routes": [route for route, _count in repair.routes],
            },
        )

        # evaluation: point-back owner, criterion by criterion.
        self.assertEqual(
            document["evaluation"]["verdict"]["result"], pointback.verdict.value
        )
        self.assertEqual(
            document["evaluation"]["coverage"]["result"],
            {
                "declared": pointback.coverage.declared,
                "reviewed": pointback.coverage.reviewed,
                "unreviewed": pointback.coverage.unreviewed,
                "complete": pointback.coverage.complete,
            },
        )
        snapshot_criteria = {
            item["result"]["criterionId"]: item["result"]
            for item in document["evaluation"]["criteria"]
        }
        for evaluation in pointback.criteria:
            owner_result = {
                "criterionId": evaluation.criterion_id,
                "outcome": evaluation.outcome,
                "requiredProof": evaluation.required_proof,
                "observedSummary": evaluation.observed_summary,
            }
            snapshot_result = dict(snapshot_criteria[evaluation.criterion_id])
            bindings = snapshot_result.pop("evidenceBindings")
            self.assertEqual(snapshot_result, owner_result)
            # Manifest binding: only the ledger row whose owner artifact
            # token is an evidence/ reference gets one contained binding,
            # hashed over the captured artifact bytes and tied to its own
            # source record; prose-observed rows bind nothing.
            token = evaluation.artifact_token
            if not (
                isinstance(token, str) and token.casefold().startswith("evidence/")
            ):
                self.assertEqual(bindings, [])
                continue
            self.assertEqual(len(bindings), 1)
            binding = bindings[0]
            self.assertEqual(
                binding["contentHash"],
                "sha256:" + hashlib.sha256(_ARTIFACT_BYTES).hexdigest(),
            )
            record = _source(document, binding["sourceRef"])
            self.assertEqual(record["observedHash"], binding["contentHash"])
            self.assertEqual(
                binding["artifactId"],
                "evidence-artifact."
                + binding["sourceRef"][len("source.evidence-artifact."):],
            )

        # nextActions: structured next-action owner, alternatives owner-known.
        self.assertEqual(
            document["nextActions"]["primary"]["result"],
            {
                "actionId": primary.action_id,
                "kind": primary.kind.value,
                "label": primary.label,
                "owner": {
                    "actor": primary.owner.actor.value,
                    "role": primary.owner.role,
                },
                "copyableAgentCommand": primary.copyable_agent_command,
            },
        )
        self.assertEqual(document["nextActions"]["alternatives"], [])

    def test_s42_fifty_rebuilds_have_zero_semantic_drift(self) -> None:
        baseline = _normalized(_build(self.run_root).document)
        for index in range(49):
            self.assertEqual(
                _normalized(_build(self.run_root).document),
                baseline,
                f"semantic drift on rebuild {index + 2}",
            )

    def test_s41_snapshot_contains_only_the_selected_run(self) -> None:
        other_root = _make_root(
            self.base, "run-b", pointback="point-back-recirculate.md"
        )
        built = _build(self.run_root)
        other_registry = select_source_registry(
            selected_root=other_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        self.assertNotEqual(built.registry.run_id, other_registry.run_id)
        serialized = json.dumps(built.document, ensure_ascii=False)
        self.assertNotIn(other_registry.run_id, serialized)
        self.assertNotIn("Recirculate", serialized)
        # Locators never cross runs: run-a's locator is unknown to run-b.
        spec_record = _source(built.document, "source.specification")
        self.assertIsNone(
            other_registry.lookup_locator(spec_record["locator"], now=_NOW)
        )

    def test_s19_document_leaks_no_path_root_or_username(self) -> None:
        serialized = json.dumps(_build(self.run_root).document, ensure_ascii=False)
        for forbidden in (
            str(self.run_root),
            str(self.base),
            self.run_root.name,
            "\\",
            "Users",
            "traceback",
        ):
            self.assertNotIn(forbidden, serialized)


class ScenarioParityTest(_ParityTestCase):
    """The remaining seven fixture scenarios, owner truth versus Snapshot."""

    def test_recirculate_scenario_matches_owner_verdict(self) -> None:
        root = _make_root(
            self.base, "run-recirculate", pointback="point-back-recirculate.md"
        )
        document = _build(root).document
        self.assertEqual(validate_snapshot(document), document)
        _, _, pointback, _, primary, _ = self._owner_truth(root)
        self.assertEqual(pointback.verdict, VerdictDisposition.RECIRCULATE)
        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "known")
        self.assertEqual(verdict["result"], "Recirculate")
        # The stray "Pass" prose never becomes a verdict or a next action.
        self.assertIn("Pass", (root / "point-back.md").read_text(encoding="utf-8"))
        self.assertNotEqual(verdict["result"], "Pass")
        self.assertEqual(
            document["nextActions"]["primary"]["result"]["actionId"],
            primary.action_id,
        )

    def test_unaudited_scenario_never_yields_pass(self) -> None:
        # Skeleton pair straight from the owner fixtures.
        root = self.base / "run-skeleton"
        root.mkdir(parents=True, exist_ok=True)
        _write(
            root, "spec.md",
            (_PASS_FIXTURES / "skeleton.spec.md").read_text(encoding="utf-8"),
        )
        _write(
            root, "point-back.md",
            (_PASS_FIXTURES / "skeleton.point-back.md").read_text(encoding="utf-8"),
        )
        _write(root, "plan.md", (_FIXTURES / "plan-profile.md").read_text(encoding="utf-8"))
        _write(root, "contract-bind.json", json.dumps(_CONTRACT_BIND))
        _write(root, "evidence/manifest.jsonl", json.dumps(_MANIFEST_ENTRY) + "\n")
        (root / "evidence" / "L6.3-error.png").write_bytes(_ARTIFACT_BYTES)
        (root / "preview").mkdir(exist_ok=True)

        document = _build(root).document
        self.assertEqual(validate_snapshot(document), document)
        _, spec, pointback, _, _, _ = self._owner_truth(root)
        self.assertEqual(pointback.verdict, VerdictDisposition.UNAUDITED)

        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "unknown")
        self.assertIsNone(verdict["result"])
        self.assertEqual(verdict["reason"]["code"], "no-canonical-value")
        # Skeleton ledger rows stay known not-applicable per owner policy.
        self.assertEqual(
            [item["result"]["outcome"] for item in document["evaluation"]["criteria"]],
            [
                evaluation.outcome
                for evaluation in pointback.criteria
            ],
        )
        self.assertTrue(
            all(
                item["result"]["outcome"] == "notApplicable"
                for item in document["evaluation"]["criteria"]
            )
        )
        coverage = _assertion(document, "evaluation.coverage")
        self.assertEqual(
            coverage["result"],
            {
                "declared": pointback.coverage.declared,
                "reviewed": pointback.coverage.reviewed,
                "unreviewed": pointback.coverage.unreviewed,
                "complete": pointback.coverage.complete,
            },
        )
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )

    def test_missing_scenario_matches_owner_lifecycle_classification(self) -> None:
        # (missing file, [(dependent assertion, its reason source ref), ...])
        rows = (
            (
                "spec.md",
                (("intent.summary", "source.specification"),),
            ),
            (
                "plan.md",
                (("identity.profile", "source.run-profile"),),
            ),
            (
                "point-back.md",
                (
                    ("evaluation.verdict", "source.evaluator-report"),
                    ("evaluation.coverage", "source.evidence-ledger"),
                    ("execution.repair", "source.repair-report"),
                ),
            ),
            (
                "contract-bind.json",
                (("intent.contract", "source.contract-bind"),),
            ),
        )
        for relpath, pairs in rows:
            with self.subTest(missing=relpath):
                root = _make_root(
                    self.base,
                    "run-missing-" + relpath.replace("/", "-").replace(".", "-"),
                )
                (root / relpath).unlink()
                document = _build(root).document
                self.assertEqual(validate_snapshot(document), document)
                self.assertEqual(
                    document["identity"]["snapshot"]["buildState"], "degraded"
                )
                for assertion_id, source_ref in pairs:
                    assertion = _assertion(document, assertion_id)
                    self.assertEqual(assertion["availability"], "unknown")
                    self.assertIsNone(assertion["result"])
                    self.assertEqual(
                        assertion["reason"]["code"], "source-missing"
                    )
                    self.assertIn(source_ref, assertion["reason"]["sourceRefs"])
                    record = _source(document, source_ref)
                    self.assertEqual(record["readState"], "missing")
                    self.assertIsNone(record["observedHash"])
                    self.assertEqual(record["freshness"], "unverified")
                # Unrelated assertions keep their own availability.
                for unrelated in ("identity.product", "execution.preview"):
                    self.assertEqual(
                        _assertion(document, unrelated)["availability"], "known"
                    )
                # Owner lifecycle classification agrees the source is gone.
                facts = capture_run_facts(run_root=root)
                if relpath == "spec.md":
                    self.assertIsNone(facts.spec_path)
                    self.assertEqual(facts.spec_text, "")
                elif relpath == "point-back.md":
                    self.assertIn(
                        "point_back",
                        [
                            error.artifact
                            for error in facts.read_errors
                            if error.code == "missing"
                        ],
                    )

    def test_missing_manifest_keeps_criteria_known_without_bindings(self) -> None:
        root = _make_root(self.base, "run-manifest")
        (root / "evidence" / "manifest.jsonl").unlink()
        document = _build(root).document
        self.assertEqual(validate_snapshot(document), document)
        record = _source(document, "source.evidence-manifest")
        self.assertEqual(record["readState"], "missing")
        self.assertEqual(record["freshness"], "unverified")
        for item in document["evaluation"]["criteria"]:
            self.assertEqual(item["availability"], "known")
            self.assertEqual(item["result"]["evidenceBindings"], [])
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )

    def test_stale_scenario_marks_dependent_assertions_stale(self) -> None:
        original = (self.run_root / "point-back.md").read_text(encoding="utf-8")
        replacement = (
            _FIXTURES / "point-back-recirculate.md"
        ).read_text(encoding="utf-8")

        def mutate() -> None:
            (self.run_root / "point-back.md").write_text(
                replacement, encoding="utf-8"
            )

        document = _build(self.run_root, mid_build_hook=mutate).document
        self.assertEqual(validate_snapshot(document), document)
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )
        record = _source(document, "source.evaluator-report")
        self.assertEqual(record["freshness"], "changed")
        # Observed is the pre-mutation capture; verified is the re-read.
        self.assertEqual(record["observedHash"], _digest(original))
        self.assertEqual(record["verifiedHash"], _digest(replacement))
        self.assertNotEqual(record["observedHash"], record["verifiedHash"])
        verdict = _assertion(document, "evaluation.verdict")
        self.assertEqual(verdict["availability"], "stale")
        self.assertIsNone(verdict["result"])
        self.assertEqual(
            verdict["reason"]["code"], "source-changed-during-build"
        )
        self.assertNotEqual(
            verdict["source"]["observedSetHash"],
            verdict["source"]["verifiedSetHash"],
        )

    def test_partial_write_scenario_is_typed_partial_write(self) -> None:
        root = _make_root(self.base, "run-partial")
        (root / "contract-bind.json").write_text(
            '{"ok": true, "open_fields": ["nav.item', encoding="utf-8"
        )
        document = _build(root).document
        self.assertEqual(validate_snapshot(document), document)
        contract = _assertion(document, "intent.contract")
        self.assertEqual(contract["availability"], "unknown")
        self.assertIsNone(contract["result"])
        self.assertEqual(contract["reason"]["code"], "partial-write")
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )
        # The torn record is never retried into a mixed source set.
        self.assertEqual(
            _source(document, "source.contract-bind")["freshness"], "current"
        )

    def test_inconsistent_hash_scenario_selects_no_winner(self) -> None:
        root = _make_root(self.base, "run-inconsistent")
        conflicting = dict(_CONTRACT_BIND)
        conflicting["open_fields"] = ["nav.item-count"]
        conflicting["assumed_fields"] = ["nav.item-count"]
        (root / "contract-bind.json").write_text(
            json.dumps(conflicting), encoding="utf-8"
        )
        document = _build(root).document
        self.assertEqual(validate_snapshot(document), document)
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
        self.assertEqual(
            document["identity"]["snapshot"]["buildState"], "degraded"
        )

    def test_failed_rebuild_after_success_never_serves_the_old_snapshot(self) -> None:
        first = _build(self.run_root).document
        self.assertEqual(
            first["identity"]["snapshot"]["buildState"], "current"
        )
        (self.run_root / "spec.md").write_text(
            "# Spec\n\n## L1 定位与意图\n\n- 一句话定义：summary\n\n"
            "## L6 验收标准\n\n- Given x\n",
            encoding="utf-8",
        )
        second = _build(self.run_root).document
        self.assertNotEqual(
            first["identity"]["snapshot"]["buildState"],
            second["identity"]["snapshot"]["buildState"],
        )
        self.assertEqual(
            _assertion(second, "intent.summary")["reason"]["code"],
            "source-malformed",
        )
        with self.assertRaises(SnapshotBuildError):
            build_snapshot(
                selected_root=self.run_root,
                package_root=_PKG_ROOT,
                session_secret=_SESSION_SECRET,
                now="not-a-timestamp",
            )


class LocatorResolverTest(_ParityTestCase):
    """Scenario ``malicious-locator`` plus the S20-S23 excerpt contract."""

    def _resolve(self, registry, locator, *, now=_NOW, max_chars=4000):
        return resolve_source_excerpt(
            registry=registry,
            package_root=_PKG_ROOT,
            locator=locator,
            now=now,
            max_chars=max_chars,
        )

    def test_valid_locator_returns_bounded_plain_hash_checked_excerpt(self) -> None:
        built = _build(self.run_root)
        record = _source(built.document, "source.specification")
        excerpt = self._resolve(built.registry, record["locator"])
        self.assertEqual(excerpt.source_ref, "source.specification")
        self.assertEqual(excerpt.content_hash, record["observedHash"])
        raw = (self.run_root / "spec.md").read_text(encoding="utf-8")
        self.assertEqual(excerpt.text, html.escape(raw[:4000], quote=False))
        self.assertLessEqual(len(excerpt.text), 4000)
        # Plain text only: no executable markup and no path disclosure.
        self.assertNotIn("<", excerpt.text)
        self.assertNotIn(">", excerpt.text)
        self.assertNotIn(str(self.run_root), excerpt.text)

    def test_artifact_locator_reads_only_the_bound_contained_artifact(self) -> None:
        built = _build(self.run_root)
        record = _source(
            built.document, "source.evidence-artifact.l6-3-error-png"
        )
        excerpt = self._resolve(built.registry, record["locator"], max_chars=100)
        self.assertEqual(excerpt.source_ref, "source.evidence-artifact.l6-3-error-png")
        self.assertEqual(excerpt.content_hash, record["observedHash"])
        self.assertLessEqual(len(excerpt.text), 100)

    def test_html_script_content_is_returned_as_escaped_text(self) -> None:
        root = _make_root(
            self.base, "run-html", artifact=_HTML_ARTIFACT.encode("utf-8")
        )
        built = _build(root)
        record = _source(
            built.document, "source.evidence-artifact.l6-3-error-png"
        )
        excerpt = self._resolve(built.registry, record["locator"], max_chars=4000)
        self.assertIn("<script", _HTML_ARTIFACT)
        self.assertNotIn("<script", excerpt.text.lower())
        self.assertNotIn("<img", excerpt.text.lower())
        self.assertNotIn("<", excerpt.text)
        self.assertEqual(
            excerpt.text, html.escape(_HTML_ARTIFACT[:4000], quote=False)
        )

    def test_locator_matrix_is_uniformly_invalid(self) -> None:
        built = _build(self.run_root)
        valid = _source(built.document, "source.specification")["locator"]
        other_session = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_OTHER_SECRET,
        )
        other_root = _make_root(self.base, "run-b")
        other_run = select_source_registry(
            selected_root=other_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        expired = built.registry.issue_locator(
            source_ref="source.specification",
            expected_hash=_source(built.document, "source.specification")[
                "observedHash"
            ],
            now=_NOW,
            ttl_seconds=1,
        )
        hostile = (
            valid[:-4] + "AAAA",  # well-formed but unknown
            "src_../../../etc/passwd",
            "src_%2e%2e%2fevidence",
            "src_C:\\windows\\system32",
            "src_/etc/passwd",
            "src_.",
            "src_short",
            "",
            "not-a-locator",
            "src_<script>alert(1)</script>",
            None,
            123,
            ("src", "tuple"),
        )
        messages = set()
        for locator in hostile:
            with self.subTest(locator=repr(locator)[:40]):
                with self.assertRaises(SourceViewError) as caught:
                    self._resolve(built.registry, locator)
                self.assertEqual(caught.exception.code, SOURCE_LOCATOR_INVALID)
                messages.add(str(caught.exception))
        # Expired, cross-session, and cross-run are the same uniform answer.
        for registry, locator, now in (
            (built.registry, expired, _LATER),
            (other_session, valid, _NOW),
            (other_run, valid, _NOW),
        ):
            with self.subTest(cross=locator is valid):
                with self.assertRaises(SourceViewError) as caught:
                    self._resolve(registry, locator, now=now)
                self.assertEqual(caught.exception.code, SOURCE_LOCATOR_INVALID)
                messages.add(str(caught.exception))
        # Uniform: one message, and it discloses no path or token detail.
        self.assertEqual(len(messages), 1)
        message = messages.pop()
        self.assertNotIn(str(self.run_root), message)
        self.assertNotIn("evidence", message)

    def test_hash_changed_source_is_rejected_without_newer_excerpt(self) -> None:
        built = _build(self.run_root)
        locator = _source(built.document, "source.specification")["locator"]
        (self.run_root / "spec.md").write_text(
            (self.run_root / "spec.md").read_text(encoding="utf-8") + "\n- later\n",
            encoding="utf-8",
        )
        with self.assertRaises(SourceViewError) as caught:
            self._resolve(built.registry, locator)
        self.assertEqual(caught.exception.code, SOURCE_HASH_MISMATCH)
        self.assertNotIn(str(self.run_root), str(caught.exception))

    def test_symlink_escape_reads_zero_outside_bytes(self) -> None:
        outside = self.base / "outside-secret.png"
        outside.write_bytes(b"outside bytes must never be read")
        built = _build(self.run_root)
        locator = _source(
            built.document, "source.evidence-artifact.l6-3-error-png"
        )["locator"]
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
            with self.assertRaises(SourceViewError) as caught:
                self._resolve(built.registry, locator)
        finally:
            Path.read_bytes = original_read_bytes  # type: ignore[method-assign]
        self.assertEqual(caught.exception.code, SOURCE_LOCATOR_INVALID)
        self.assertNotIn(outside, recorded)
        self.assertTrue(
            all(path.resolve().is_relative_to(self.run_root) for path in recorded)
        )

    def test_resolution_is_read_only_and_side_effect_free(self) -> None:
        built = _build(self.run_root)
        locator = _source(built.document, "source.specification")["locator"]
        before = _tree_digest(self.base)
        self._resolve(built.registry, locator)
        for hostile in ("", "src_unknown-token-value", locator + "x"):
            with self.assertRaises(SourceViewError):
                self._resolve(built.registry, hostile)
        self.assertEqual(_tree_digest(self.base), before)


class ExcerptPlainTextTest(_ParityTestCase):
    """Spec section 10: excerpts are plain text with control chars removed."""

    def _resolve(self, registry, locator, *, max_chars=4000):
        return resolve_source_excerpt(
            registry=registry,
            package_root=_PKG_ROOT,
            locator=locator,
            now=_NOW,
            max_chars=max_chars,
        )

    def _artifact_excerpt(self, payload: bytes, *, name: str, max_chars: int = 4000):
        """Excerpt of an artifact holding exact hostile bytes, plus its record."""
        root = _make_root(self.base, name, artifact=payload)
        built = _build(root)
        record = _source(
            built.document, "source.evidence-artifact.l6-3-error-png"
        )
        excerpt = self._resolve(
            built.registry, record["locator"], max_chars=max_chars
        )
        return excerpt, record

    def test_nul_and_c0_c1_del_control_characters_are_removed(self) -> None:
        payload = "a\x00b\x01c\x07d\x0be\x7ff\x85g\x9bh".encode("utf-8")
        excerpt, record = self._artifact_excerpt(payload, name="run-ctrl")
        self.assertEqual(excerpt.text, "abcdefgh")
        # Stripping never feeds the hash: parity with the Snapshot holds.
        self.assertEqual(excerpt.content_hash, record["observedHash"])
        self.assertEqual(
            excerpt.content_hash,
            "sha256:" + hashlib.sha256(payload).hexdigest(),
        )

    def test_ansi_color_sequence_is_stripped_without_residue(self) -> None:
        excerpt, _ = self._artifact_excerpt(
            "\x1b[31mred\x1b[0m plain".encode("utf-8"), name="run-ansi"
        )
        self.assertEqual(excerpt.text, "red plain")
        self.assertNotIn("[31m", excerpt.text)
        self.assertNotIn("\x1b", excerpt.text)

    def test_lone_escape_is_removed(self) -> None:
        excerpt, _ = self._artifact_excerpt(b"a\x1bz", name="run-esc")
        self.assertEqual(excerpt.text, "az")

    def test_tab_newline_survive_and_crlf_normalizes(self) -> None:
        excerpt, _ = self._artifact_excerpt(
            b"col1\tcol2\r\nline2\rline3\nline4", name="run-ws"
        )
        self.assertEqual(excerpt.text, "col1\tcol2\nline2\nline3\nline4")

    def test_truncation_still_applies_after_stripping(self) -> None:
        payload = ("\x1b[31m" + "x" * 50 + "\x1b[0m").encode("utf-8")
        excerpt, _ = self._artifact_excerpt(
            payload, name="run-trunc", max_chars=10
        )
        # The stripped prefix never consumes the bound; the bound holds.
        self.assertEqual(excerpt.text, "x" * 10)
        self.assertLessEqual(len(excerpt.text), 10)

    def test_text_source_excerpt_is_stripped_while_hash_parity_holds(self) -> None:
        # The text-source branch (normalized-text hashing) must strip the
        # same characters from its excerpt without breaking hash parity.
        root = _make_root(self.base, "run-text-ctrl")
        spec_path = root / "spec.md"
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8")
            + "\n\x1b[31mhostile\x1b[0m\x00\ttail\n",
            encoding="utf-8",
        )
        built = _build(root)
        record = _source(built.document, "source.specification")
        excerpt = self._resolve(built.registry, record["locator"])
        self.assertEqual(excerpt.source_ref, "source.specification")
        self.assertEqual(excerpt.content_hash, record["observedHash"])
        self.assertNotIn("\x00", excerpt.text)
        self.assertNotIn("\x1b", excerpt.text)
        self.assertNotIn("[31m", excerpt.text)
        self.assertIn("hostile", excerpt.text)
        self.assertIn("\ttail", excerpt.text)


class BoundaryScanTest(unittest.TestCase):
    """Gate condition: no copied owner parser, no writes, no network/exec."""

    _RUN_CONSOLE = Path(__file__).resolve().parent
    _OWNER_SCRIPTS = _PKG_ROOT / "scripts"

    def test_no_owner_parser_regex_is_copied(self) -> None:
        owner_patterns: set[str] = set()
        for path in self._OWNER_SCRIPTS.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            owner_patterns.update(
                match[0] or match[1]
                for match in re.findall(
                    r"re\.compile\(\s*r?(?:'([^']*)'|\"([^\"]*)\")", text
                )
            )
        self.assertTrue(owner_patterns)
        for name in ("snapshot_builder.py", "projection.py"):
            text = (self._RUN_CONSOLE / name).read_text(encoding="utf-8")
            copied = [
                match[0] or match[1]
                for match in re.findall(
                    r"re\.compile\(\s*r?(?:'([^']*)'|\"([^\"]*)\")", text
                )
                if (match[0] or match[1]) in owner_patterns
            ]
            self.assertEqual(copied, [], f"{name} copies owner regexes")

    def test_builder_and_resolver_write_nothing_and_open_no_sockets(self) -> None:
        forbidden = (
            ".write_text(",
            ".write_bytes(",
            "open(",
            ".mkdir(",
            ".unlink(",
            ".rmdir(",
            ".rename(",
            "os.replace",
            "os.remove",
            "shutil.",
            "subprocess",
            "import socket",
            "socket(",
            "socket.",
            "urllib",
            "import requests",
            "requests.",
            "http.client",
            "http.server",
            "os.system",
            "eval(",
            "exec(",
        )
        for name in ("snapshot_builder.py", "projection.py"):
            text = (self._RUN_CONSOLE / name).read_text(encoding="utf-8")
            hits = [token for token in forbidden if token in text]
            self.assertEqual(hits, [], f"{name} contains forbidden calls")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
