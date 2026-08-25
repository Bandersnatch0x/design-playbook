"""Source-bound Run Snapshot v1 builder.

One build of one selected canonical run root produces exactly one atomic,
contract-valid Run Snapshot v1 document:

- the fixed Source registry (slice A) is selected for the session first;
- every allowlisted parser input is captured once through the owner seams
  (RunFacts, Specification, Point-back, run status, run metadata, G6
  evidence) and hashed at capture time -- this module never re-implements
  an owner parser;
- after projection, and after the optional mid-build hook, the same
  registry entries are read and hashed again: a source that changed during
  the build makes its dependent assertions ``stale`` with unequal
  observed/verified hashes and degrades the whole build -- a previously
  served snapshot is never substituted for the failed build;
- missing, unreadable, malformed, partially-written, and conflicting
  sources surface as typed non-known results inside the one document.

The builder writes nothing, opens no socket, and every failure is one
stable, path-free :class:`SnapshotBuildError`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from design_playbook.mcp.evidence.containment import read_artifact
from design_playbook.mcp.run_console.contract import (
    SNAPSHOT_VERSION,
    validate_snapshot,
)
from design_playbook.mcp.run_console.source_registry import (
    RegisteredSource,
    SourceRegistry,
    SourceRegistryError,
    select_source_registry,
)
from design_playbook.scripts.escalation_signals import effective_tier
from design_playbook.scripts.g1_spec import (
    SpecificationProjectionError,
    project_specification,
)
from design_playbook.scripts.g6_evidence import check_evidence
from design_playbook.scripts.pointback_projection import (
    NonKnownFinding,
    PointBackProjectionError,
    VerdictDisposition,
    project_pointback,
)
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts
from design_playbook.scripts.run_metadata import (
    project_limitations,
    project_package_metadata,
)
from design_playbook.scripts.run_profile import validate_run_profile
from design_playbook.scripts.run_status import (
    inspect_run,
    inspect_vnext,
    project_next_action,
)

SELECTED_RUN_INVALID = "selected-run-invalid"
BUILD_INPUT_INVALID = "build-input-invalid"
BUILD_FAILED = "build-failed"

_ERROR_MESSAGES = {
    SELECTED_RUN_INVALID: "The selected run selection is invalid.",
    BUILD_INPUT_INVALID: "The snapshot build input is invalid.",
    BUILD_FAILED: "The snapshot build could not be completed.",
}

# Fixed reason messages; none of them carries a path or caller input.
_REASON_MESSAGES = {
    "not-produced": "The owning stage has not produced this value yet.",
    "source-missing": "The source bound to this assertion is missing.",
    "source-unreadable": "The source bound to this assertion could not be read.",
    "source-malformed": "The source bound to this assertion is malformed.",
    "no-canonical-value": "The owner reports no canonical value for this assertion.",
    "dependency-unavailable": "A dependency of this assertion is unavailable.",
    "owner-unmapped": "No existing authority owner is mapped for this assertion.",
    "partial-write": "The source was observed during a partial write.",
    "invariant-violation": "Current source records violate an invariant.",
    "source-changed-during-build": "The source changed during the build.",
}

_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$"
)
_DOMAIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
_SOURCE_REF_PATTERN = re.compile(
    r"^source\.[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$"
)

# The retained-fields source-set digest of the v1 contract: the producer
# emits exactly this form for sources.sourceSetHash,
# identity.snapshot.sourceSetHash, and each assertion's set hashes.
_RETAINED_FIELDS = (
    "sourceRef",
    "authorityKey",
    "readState",
    "observedHash",
    "verifiedHash",
    "freshness",
)

# G6 owner rule ids that make a ledger-referenced artifact unbindable for
# the Snapshot (the Manifest binding is missing or escapes containment).
# Capture-contract quality findings (G6.capture_*) do not unbind evidence
# at this boundary.
_UNBINDABLE_RULES = frozenset(
    {"G6.artifact_missing", "G6.escape", "G6.no_binding", "G6.unknown_criterion"}
)
_DEGRADING_RULES = frozenset({"G6.artifact_missing", "G6.escape"})

# Fixed source refs of the fifteen-key registry (parity section 2).
_REF_SELECTED_RUN = "source.selected-run"
_REF_PACKAGE = "source.package-metadata"
_REF_PROFILE = "source.run-profile"
_REF_SPEC = "source.specification"
_REF_CONTRACT = "source.contract-bind"
_REF_RUN_FACTS = "source.run-facts"
_REF_PREVIEW = "source.preview"
_REF_REPAIR = "source.repair-report"
_REF_EVALUATOR = "source.evaluator-report"
_REF_LEDGER = "source.evidence-ledger"
_REF_MANIFEST = "source.evidence-manifest"
_REF_STATUS = "source.run-status"
_REF_LIMITATIONS = "source.owner-limitations.run-metadata"


class SnapshotBuildError(ValueError):
    """A stable, path-free snapshot build failure."""

    def __init__(self, code: str) -> None:
        super().__init__(_ERROR_MESSAGES.get(code, code))
        self.code = code


@dataclass(frozen=True)
class BuiltSnapshot:
    """One built document together with the registry that issued it."""

    document: dict[str, Any]
    registry: SourceRegistry


@dataclass(frozen=True)
class _Capture:
    """One full capture of every parser input the build consumes."""

    facts: RunFacts
    contract_text: str | None
    contract_state: str
    manifest_text: str | None
    manifest_state: str
    package_text: str | None
    package_state: str


@dataclass(frozen=True)
class _Observation:
    """One source as observed by one capture pass."""

    authority_key: str
    kind: str
    read_state: str
    hash: str | None


@dataclass(frozen=True)
class _ReasonSkeleton:
    """A reason before the final source records exist."""

    code: str
    message: str
    refs: tuple[str, ...]
    conflicts: tuple[dict[str, str], ...] = ()


@dataclass
class _DraftAssertion:
    """One assertion before end-of-build verification."""

    assertion_id: str
    refs: tuple[str, ...]
    availability: str
    result: Any
    reason: _ReasonSkeleton | None


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _digest_text(encoded)


def _records_digest(records: list[dict[str, Any]]) -> str:
    retained = [
        {key: record[key] for key in _RETAINED_FIELDS} for record in records
    ]
    return _digest_text(
        json.dumps(retained, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def _verified_view(record: dict[str, Any]) -> dict[str, Any]:
    """The record as the source set would look after re-verification."""
    if record["freshness"] == "changed":
        updated = dict(record)
        updated["observedHash"] = record["verifiedHash"]
        updated["freshness"] = "current"
        return updated
    return record


def _slug(value: str) -> str:
    return value.strip().lower().replace(".", "-")


class _Builder:
    """One snapshot build over one selected run root."""

    def __init__(
        self, registry: SourceRegistry, package_root: Path, now: str
    ) -> None:
        self._registry = registry
        self._run_root = registry.selected_root
        self._package_root = package_root
        self._now = now
        self._sources: dict[str, RegisteredSource] = {
            source.source_ref: source
            for source in registry.sources
            if source.source_ref is not None
        }
        self._records: dict[str, dict[str, Any]] = {}
        self._drafts: list[_DraftAssertion] = []
        self._manifest_degraded = False
        self._artifact_sources: dict[str, RegisteredSource] = {}
        self._artifact_hashes_observed: dict[str, str | None] = {}
        self._artifact_hashes_verified: dict[str, str | None] = {}
        self._limitations: tuple[Any, ...] = ()
        self._limitations_digest = ""

    # -- orchestration ------------------------------------------------

    def build(self, mid_build_hook: Callable[[], None] | None) -> dict[str, Any]:
        capture = self._capture()
        self._project(capture)
        if mid_build_hook is not None:
            mid_build_hook()
        verify = self._capture()
        self._artifact_hashes_verified = {
            relpath: self._read_artifact_hash(relpath)
            for relpath in self._artifact_sources
        }
        document = self._assemble(capture, verify)
        # The build is atomic: it returns only a contract-valid document.
        validate_snapshot(document)
        return document

    # -- capture ------------------------------------------------------

    def _capture(self) -> _Capture:
        facts = capture_run_facts(run_root=self._run_root)
        contract_text, contract_state = self._read_optional_text(
            self._run_root / "contract-bind.json"
        )
        manifest_text, manifest_state = self._read_optional_text(
            self._run_root / "evidence" / "manifest.jsonl"
        )
        package_text, package_state = self._read_optional_text(
            self._package_root / ".claude-plugin" / "plugin.json"
        )
        return _Capture(
            facts=facts,
            contract_text=contract_text,
            contract_state=contract_state,
            manifest_text=manifest_text,
            manifest_state=manifest_state,
            package_text=package_text,
            package_state=package_state,
        )

    def _read_optional_text(self, path: Path) -> tuple[str | None, str]:
        if not path.is_file():
            return None, "missing"
        try:
            return path.read_text(encoding="utf-8"), "complete"
        except (OSError, UnicodeDecodeError):
            return None, "unreadable"

    def _read_artifact_hash(self, relpath: str) -> str | None:
        result = read_artifact(relpath, self._run_root)
        if not result.ok or result.path is None:
            return None
        try:
            data = result.path.read_bytes()
        except OSError:
            return None
        return _digest_bytes(data)

    # -- read states --------------------------------------------------

    def _spec_state(self, facts: RunFacts) -> str:
        for error in facts.read_errors:
            if error.artifact == "spec":
                return error.code
        if facts.spec_path is None:
            # No spec file exists: the owner selects no path and records no
            # read error for an unselected file, so absence maps here.
            return "missing"
        return "complete"

    def _pointback_state(self, facts: RunFacts) -> str:
        for error in facts.read_errors:
            if error.artifact == "point_back":
                return error.code
        return "complete"

    def _plan_state(self, facts: RunFacts) -> str:
        for error in facts.read_errors:
            if error.artifact == "plan":
                # The owner drops missing-plan facts; only failures remain.
                return "unreadable"
        if not (self._run_root / "plan.md").is_file():
            return "missing"
        return "complete"

    def _manifest_state(self, facts: RunFacts, capture: _Capture) -> str:
        if self._manifest_degraded:
            # The Manifest was read, but a declared binding cannot be
            # established (missing or escaping artifact, rejected artifact
            # name, unreadable artifact bytes): the manifest record maps to a
            # malformed read so the degradation is explicit in the source set.
            return "malformed"
        for error in facts.read_errors:
            if error.artifact == "manifest":
                return "unreadable" if error.code == "unreadable" else "malformed"
        return capture.manifest_state

    # -- projection (owner seams over captured inputs) -----------------

    def _project(self, capture: _Capture) -> None:
        facts = capture.facts

        # identity.run: the selected-session fact from the registry.
        self._draft(
            "identity.run",
            (_REF_SELECTED_RUN,),
            "known",
            {"runId": self._registry.run_id, "label": None},
        )

        # identity.product: package metadata owner.
        product = project_package_metadata(self._package_root)
        if product.availability == "known" and product.value is not None:
            self._draft(
                "identity.product",
                (_REF_PACKAGE,),
                "known",
                {"name": product.value.name, "version": product.value.version},
            )
        else:
            self._draft_unknown(
                "identity.product",
                (_REF_PACKAGE,),
                product.reason or "source-missing",
            )

        # identity.profile: run-profile owner over the captured plan text.
        plan_state = self._plan_state(facts)
        if plan_state == "missing":
            self._draft_unknown("identity.profile", (_REF_PROFILE,), "source-missing")
        elif plan_state == "unreadable":
            self._draft_unknown(
                "identity.profile", (_REF_PROFILE,), "source-unreadable"
            )
        else:
            profile = facts.run_profile
            if profile is None:
                self._draft_unknown(
                    "identity.profile", (_REF_PROFILE,), "not-produced"
                )
            elif validate_run_profile(profile):
                self._draft_unknown(
                    "identity.profile", (_REF_PROFILE,), "source-malformed"
                )
            else:
                self._draft(
                    "identity.profile",
                    (_REF_PROFILE,),
                    "known",
                    {
                        "declaredTier": profile.tier or None,
                        "effectiveTier": effective_tier(
                            profile.tier, profile.upgrades
                        ),
                        "confirmedBy": "human" if profile.confirmed_by else None,
                    },
                )

        # intent: specification owner over the captured spec text.
        spec_state = self._spec_state(facts)
        spec_summary: str | None = None
        spec_criteria: tuple[Any, ...] = ()
        spec_code: str | None = None
        if spec_state == "missing":
            spec_code = "source-missing"
        elif spec_state == "unreadable":
            spec_code = "source-unreadable"
        else:
            try:
                projection = project_specification(facts.spec_text)
            except SpecificationProjectionError:
                spec_code = "source-malformed"
            else:
                spec_summary = projection.summary
                spec_criteria = projection.criteria
        if spec_code is None:
            self._draft("intent.summary", (_REF_SPEC,), "known", spec_summary)
        else:
            self._draft_unknown("intent.summary", (_REF_SPEC,), spec_code)
        for criterion in spec_criteria:
            self._draft(
                f"intent.criteria.{_slug(criterion.criterion_id)}",
                (_REF_SPEC,),
                "known",
                {
                    "criterionId": criterion.criterion_id,
                    "title": criterion.title,
                    "given": criterion.given,
                    "when": criterion.when,
                    "then": criterion.then,
                },
            )

        # intent.contract: the captured contract-bind authority record.
        self._project_contract(capture)

        # execution.progress: stage registry over the captured facts.
        states = inspect_run(
            self._run_root, preview_snapshot=facts.preview, run_facts=facts
        )
        skipped = (
            dict(facts.run_profile.skipped) if facts.run_profile is not None else {}
        )
        observed_stages = []
        for state in states:
            if state.present:
                presence, skip_reason = "present", None
            elif state.key in skipped:
                presence, skip_reason = "skipped", skipped[state.key]
            else:
                presence, skip_reason = "absent", None
            observed_stages.append(
                {
                    "stageId": state.key,
                    "label": state.skill,
                    "presence": presence,
                    "skipReason": skip_reason,
                }
            )
        latest = next(
            (state.key for state in reversed(states) if state.present), None
        )
        self._draft(
            "execution.progress",
            (_REF_RUN_FACTS, _REF_PROFILE),
            "known",
            {"observedStages": observed_stages, "latestObservedStage": latest},
        )

        # execution.preview: preview integrity owner.
        snapshot = facts.preview
        if snapshot is None or not snapshot.occurred:
            preview_result: dict[str, Any] = {"state": "absent", "round": None}
        else:
            confirm = snapshot.canonical_current_confirm
            if (
                confirm is not None
                and isinstance(confirm.data, dict)
                and confirm.data.get("aborted") is True
            ):
                preview_state = "aborted"
            elif confirm is not None and confirm.valid:
                preview_state = "confirmed"
            elif confirm is not None:
                preview_state = "invalid"
            else:
                preview_state = "open"
            preview_result = {
                "state": preview_state,
                "round": snapshot.current_round,
            }
        self._draft("execution.preview", (_REF_PREVIEW,), "known", preview_result)

        # execution.repair: repair narration owner.
        pointback_state = self._pointback_state(facts)
        if pointback_state == "missing":
            self._draft_unknown("execution.repair", (_REF_REPAIR,), "source-missing")
        elif pointback_state == "unreadable":
            self._draft_unknown(
                "execution.repair", (_REF_REPAIR,), "source-unreadable"
            )
        else:
            narration = inspect_vnext(self._run_root, run_facts=facts).repair
            if narration is None:
                repair_result = {
                    "rounds": 0,
                    "closeReason": None,
                    "waitingForHuman": False,
                    "routes": [],
                }
            else:
                repair_result = {
                    "rounds": narration.rounds,
                    "closeReason": narration.close_reason,
                    "waitingForHuman": narration.wait_user,
                    "routes": [route for route, _count in narration.routes],
                }
            self._draft(
                "execution.repair",
                (_REF_REPAIR, _REF_PROFILE),
                "known",
                repair_result,
            )

        # evaluation: point-back owner over the captured point-back text.
        self._project_evaluation(facts, pointback_state, spec_criteria)

        # nextActions: next-action owner over the same captured facts.
        action = project_next_action(
            states,
            self._run_root,
            preview_snapshot=facts.preview,
            run_facts=facts,
        ).primary
        self._draft(
            "next-actions.primary",
            (_REF_STATUS,),
            "known",
            {
                "actionId": action.action_id,
                "kind": action.kind.value,
                "label": action.label,
                "owner": {
                    "actor": action.owner.actor.value,
                    "role": action.owner.role,
                },
                "copyableAgentCommand": action.copyable_agent_command,
            },
        )
        # The owner emits no alternatives; the empty list is owner-known.

    def _project_contract(self, capture: _Capture) -> None:
        if capture.contract_state == "missing":
            self._draft_unknown("intent.contract", (_REF_CONTRACT,), "source-missing")
            return
        if capture.contract_state == "unreadable":
            self._draft_unknown(
                "intent.contract", (_REF_CONTRACT,), "source-unreadable"
            )
            return
        try:
            payload = json.loads(capture.contract_text or "")
        except json.JSONDecodeError:
            # A torn write of a JSON authority record is a partial write.
            self._draft_unknown("intent.contract", (_REF_CONTRACT,), "partial-write")
            return
        if not isinstance(payload, dict):
            self._draft_unknown(
                "intent.contract", (_REF_CONTRACT,), "source-malformed"
            )
            return
        field_lists: dict[str, list[str]] = {}
        for name in ("open_fields", "assumed_fields", "stale_fields"):
            value = payload.get(name)
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                self._draft_unknown(
                    "intent.contract", (_REF_CONTRACT,), "source-malformed"
                )
                return
            field_lists[name] = value
        blockers = payload.get("blockers", [])
        if not isinstance(blockers, list):
            self._draft_unknown(
                "intent.contract", (_REF_CONTRACT,), "source-malformed"
            )
            return
        open_fields = set(field_lists["open_fields"])
        assumed_fields = set(field_lists["assumed_fields"])
        stale_fields = set(field_lists["stale_fields"])
        overlap = (
            (open_fields & assumed_fields)
            | (open_fields & stale_fields)
            | (assumed_fields & stale_fields)
        )
        if overlap:
            self._drafts.append(
                _DraftAssertion(
                    "intent.contract",
                    (_REF_CONTRACT,),
                    "inconsistent",
                    None,
                    _ReasonSkeleton(
                        "invariant-violation",
                        _REASON_MESSAGES["invariant-violation"],
                        (_REF_CONTRACT,),
                        (
                            {
                                "sourceRef": _REF_CONTRACT,
                                "summary": (
                                    "The contract bind record assigns one field "
                                    "to conflicting resolutions."
                                ),
                            },
                        ),
                    ),
                )
            )
            return
        self._draft(
            "intent.contract",
            (_REF_CONTRACT,),
            "known",
            {
                "openFields": sorted(open_fields),
                "assumedFields": sorted(assumed_fields),
                "staleFields": sorted(stale_fields),
                "blocking": bool(blockers),
            },
        )

    def _project_evaluation(
        self,
        facts: RunFacts,
        pointback_state: str,
        spec_criteria: tuple[Any, ...],
    ) -> None:
        criteria_ids = tuple(c.criterion_id for c in spec_criteria)
        verdict_result: str | None = None
        verdict_code: str | None = None
        coverage_result: dict[str, Any] | None = None
        coverage_code: str | None = None
        evaluated: list[tuple[Any, list[dict[str, Any]]]] = []
        findings: list[Any] = []
        if pointback_state == "missing":
            verdict_code = coverage_code = "source-missing"
        elif pointback_state == "unreadable":
            verdict_code = coverage_code = "source-unreadable"
        elif not criteria_ids:
            # The point-back source is readable, but the declared criterion
            # set it must be projected against is unavailable.
            verdict_code = coverage_code = "dependency-unavailable"
        else:
            try:
                pointback = project_pointback(facts.pointback_text, criteria_ids)
            except PointBackProjectionError:
                verdict_code = coverage_code = "source-malformed"
            else:
                if pointback.verdict in (
                    VerdictDisposition.PASS,
                    VerdictDisposition.RECIRCULATE,
                ):
                    verdict_result = pointback.verdict.value
                else:
                    verdict_code = "no-canonical-value"
                coverage_result = {
                    "declared": pointback.coverage.declared,
                    "reviewed": pointback.coverage.reviewed,
                    "unreviewed": pointback.coverage.unreviewed,
                    "complete": pointback.coverage.complete,
                }
                for evaluation in pointback.criteria:
                    bindings = self._evidence_bindings(facts, criteria_ids, evaluation)
                    evaluated.append((evaluation, bindings))
                findings = list(pointback.findings)

        if verdict_code is None:
            self._draft(
                "evaluation.verdict", (_REF_EVALUATOR,), "known", verdict_result
            )
        else:
            self._draft_unknown(
                "evaluation.verdict", (_REF_EVALUATOR,), verdict_code
            )
        if coverage_code is None:
            self._draft(
                "evaluation.coverage", (_REF_LEDGER,), "known", coverage_result
            )
        else:
            self._draft_unknown("evaluation.coverage", (_REF_LEDGER,), coverage_code)

        for evaluation, bindings in evaluated:
            self._draft(
                f"evaluation.criteria.{_slug(evaluation.criterion_id)}",
                (_REF_LEDGER, _REF_MANIFEST),
                "known",
                {
                    "criterionId": evaluation.criterion_id,
                    "outcome": evaluation.outcome,
                    "requiredProof": evaluation.required_proof,
                    "observedSummary": evaluation.observed_summary,
                    "evidenceBindings": bindings,
                },
            )

        unmapped_ids: list[str] = []
        for finding in findings:
            assertion_id = f"evaluation.findings.{finding.finding_id}"
            if isinstance(finding, NonKnownFinding):
                unmapped_ids.append(assertion_id)
                self._draft_unknown(
                    assertion_id, (_REF_EVALUATOR,), "owner-unmapped"
                )
                continue
            self._draft(
                assertion_id,
                (_REF_EVALUATOR,),
                "known",
                {
                    "findingId": finding.finding_id,
                    "criterionIds": list(finding.criterion_ids),
                    "issue": finding.issue,
                    "severity": finding.severity,
                    "disposition": finding.disposition,
                    "owner": {
                        "kind": finding.owner.kind,
                        "domainId": self._safe_domain_id(finding.owner.domain_id),
                        "sourceRef": self._safe_source_ref(finding.owner.source_ref),
                    },
                    "repair": finding.repair,
                },
            )

        # limitations: run-metadata owner (never caller-authored prose).
        self._limitations = project_limitations(
            owner_unmapped_assertion_ids=tuple(sorted(unmapped_ids))
        )
        self._limitations_digest = _digest_json(
            [
                {
                    "code": item.code,
                    "summary": item.summary,
                    "affectsAssertionIds": list(item.affects_assertion_ids),
                }
                for item in self._limitations
            ]
        )
        for limitation in self._limitations:
            self._draft(
                f"limitations.items.{_slug(limitation.code)}",
                (_REF_LIMITATIONS,),
                "known",
                {
                    "code": limitation.code,
                    "summary": limitation.summary,
                    "affectsAssertionIds": list(limitation.affects_assertion_ids),
                },
            )

    def _evidence_bindings(
        self, facts: RunFacts, criteria_ids: tuple[str, ...], evaluation: Any
    ) -> list[dict[str, Any]]:
        """Project the Manifest evidence binding for one ledger row.

        The G6 owner seam decides whether the row's artifact is bound; this
        method only reads the bound artifact through containment and hashes
        it. Unbound or escaped artifacts are never projected as evidence.
        """
        token = evaluation.artifact_token
        if not isinstance(token, str) or not token.casefold().startswith("evidence/"):
            return []
        g6_findings = check_evidence(
            facts.pointback_text,
            len(criteria_ids),
            facts.evidence_dir,
            self._run_root,
            observed_rows=[(evaluation.criterion_id, token)],
            entries=self._manifest_entries(facts),
        )
        if any(finding.rule_id in _UNBINDABLE_RULES for finding in g6_findings):
            if any(finding.rule_id in _DEGRADING_RULES for finding in g6_findings):
                self._manifest_degraded = True
            return []
        leaf = token[len("evidence/"):]
        try:
            source = self._registry.derive_evidence_artifact_source(leaf)
        except SourceRegistryError:
            self._manifest_degraded = True
            return []
        relpath = source.capture_targets[0]
        artifact_hash = self._read_artifact_hash(relpath)
        if artifact_hash is None:
            self._manifest_degraded = True
            return []
        self._artifact_sources[relpath] = source
        self._sources[source.source_ref] = source
        self._artifact_hashes_observed[relpath] = artifact_hash
        slug = source.source_ref[len("source.evidence-artifact."):]
        return [
            {
                "artifactId": f"evidence-artifact.{slug}",
                "sourceRef": source.source_ref,
                "contentHash": artifact_hash,
            }
        ]

    def _manifest_entries(self, facts: RunFacts) -> list[dict[str, Any]]:
        try:
            return list(facts.manifest_entries)
        except (json.JSONDecodeError, TypeError):
            return []

    # -- drafts --------------------------------------------------------

    def _draft(
        self,
        assertion_id: str,
        refs: tuple[str, ...],
        availability: str,
        result: Any,
    ) -> None:
        self._drafts.append(
            _DraftAssertion(assertion_id, tuple(sorted(refs)), availability, result, None)
        )

    def _draft_unknown(
        self, assertion_id: str, refs: tuple[str, ...], code: str
    ) -> None:
        self._drafts.append(
            _DraftAssertion(
                assertion_id,
                tuple(sorted(refs)),
                "unknown",
                None,
                _ReasonSkeleton(
                    code, _REASON_MESSAGES[code], tuple(sorted(refs)), ()
                ),
            )
        )

    @staticmethod
    def _safe_domain_id(value: Any) -> str | None:
        if isinstance(value, str) and _DOMAIN_ID_PATTERN.fullmatch(value):
            return value
        return None

    @staticmethod
    def _safe_source_ref(value: Any) -> str | None:
        if isinstance(value, str) and _SOURCE_REF_PATTERN.fullmatch(value):
            return value
        return None

    # -- observations and records --------------------------------------

    def _preview_digest(self, snapshot: Any) -> dict[str, Any]:
        if snapshot is None:
            return {
                "occurred": False,
                "occurrenceSources": [],
                "currentRound": None,
                "facts": [],
            }
        return {
            "occurred": snapshot.occurred,
            "occurrenceSources": sorted(snapshot.occurrence_sources),
            "currentRound": snapshot.current_round,
            "facts": [fact.code for fact in snapshot.facts],
        }

    def _observations(
        self, capture: _Capture, artifact_hashes: dict[str, str | None]
    ) -> dict[str, _Observation]:
        facts = capture.facts
        observations: dict[str, _Observation] = {}

        def add(
            source: RegisteredSource, read_state: str, hash_value: str | None
        ) -> None:
            observations[source.source_ref or ""] = _Observation(
                authority_key=source.authority_key,
                kind=source.kind,
                read_state=read_state,
                hash=hash_value,
            )

        add(
            self._registry.source("session.selected-run"),
            "complete",
            _digest_text(self._registry.run_id),
        )
        add(
            self._registry.source("package.metadata"),
            capture.package_state,
            _digest_text(capture.package_text)
            if capture.package_text is not None
            else None,
        )
        plan_state = self._plan_state(facts)
        add(
            self._registry.source("run.profile"),
            plan_state,
            _digest_text(facts.plan_text) if plan_state == "complete" else None,
        )
        spec_state = self._spec_state(facts)
        add(
            self._registry.source("intent.specification"),
            spec_state,
            _digest_text(facts.spec_text) if spec_state == "complete" else None,
        )
        add(
            self._registry.source("intent.contract"),
            capture.contract_state,
            _digest_text(capture.contract_text)
            if capture.contract_text is not None
            else None,
        )
        add(
            self._registry.source("execution.stage-registry"),
            "complete",
            _digest_json(sorted(facts.existing_paths)),
        )
        add(
            self._registry.source("execution.preview"),
            "complete",
            _digest_json(self._preview_digest(facts.preview)),
        )
        pointback_state = self._pointback_state(facts)
        for key in ("execution.repair", "evaluation.evaluator", "evaluation.ledger"):
            add(
                self._registry.source(key),
                pointback_state,
                _digest_text(facts.pointback_text)
                if pointback_state == "complete"
                else None,
            )
        manifest_state = self._manifest_state(facts, capture)
        add(
            self._registry.source("evaluation.manifest"),
            manifest_state,
            _digest_text(capture.manifest_text)
            if manifest_state == "complete"
            else None,
        )
        add(
            self._registry.source("run.next-action"),
            "complete",
            _digest_json(
                [
                    sorted(facts.existing_paths),
                    facts.pointback_text,
                    self._preview_digest(facts.preview),
                ]
            ),
        )
        add(
            self._registry.source("run.limitations"),
            "complete",
            self._limitations_digest,
        )
        for relpath, source in self._artifact_sources.items():
            hash_value = artifact_hashes.get(relpath)
            add(source, "complete" if hash_value is not None else "missing", hash_value)
        return observations

    def _finalize_records(
        self,
        observed: dict[str, _Observation],
        verified: dict[str, _Observation],
    ) -> None:
        for ref in sorted(observed):
            observation = observed[ref]
            verification = verified.get(ref)
            observed_hash = observation.hash
            if observed_hash is None:
                verified_hash, freshness, verified_at = None, "unverified", None
            elif verification is None or verification.hash is None:
                verified_hash, freshness, verified_at = None, "unverified", None
            elif verification.hash == observed_hash:
                verified_hash, freshness, verified_at = (
                    observed_hash,
                    "current",
                    self._now,
                )
            else:
                verified_hash, freshness, verified_at = (
                    verification.hash,
                    "changed",
                    self._now,
                )
            source = self._sources[ref]
            locator = None
            if source.viewable and observed_hash is not None:
                locator = self._registry.issue_locator(
                    source_ref=ref, expected_hash=observed_hash, now=self._now
                )
            self._records[ref] = {
                "sourceRef": ref,
                "authorityKey": observation.authority_key,
                "kind": observation.kind,
                "locator": locator,
                "readState": observation.read_state,
                "observedHash": observed_hash,
                "verifiedHash": verified_hash,
                "freshness": freshness,
                "observedAt": self._now,
                "verifiedAt": verified_at,
            }

    # -- assembly ------------------------------------------------------

    def _finalize_reason(self, skeleton: _ReasonSkeleton) -> dict[str, Any]:
        refs = sorted(set(skeleton.refs))
        observed = [
            self._records[ref]["observedHash"]
            for ref in refs
            if self._records[ref]["observedHash"] is not None
        ]
        verified = [
            self._records[ref]["verifiedHash"]
            for ref in refs
            if self._records[ref]["verifiedHash"] is not None
        ]
        conflicts = []
        for conflict in skeleton.conflicts:
            record = self._records[conflict["sourceRef"]]
            conflicts.append(
                {
                    "sourceRef": conflict["sourceRef"],
                    "hash": record["observedHash"],
                    "summary": conflict["summary"],
                }
            )
        return {
            "code": skeleton.code,
            "message": skeleton.message,
            "sourceRefs": refs,
            "observedHashes": observed,
            "verifiedHashes": verified,
            "conflicts": conflicts,
        }

    def _assertion_source(self, refs: tuple[str, ...]) -> dict[str, Any]:
        records = [self._records[ref] for ref in refs]
        return {
            "refs": list(refs),
            "observedSetHash": _records_digest(records),
            "verifiedSetHash": _records_digest(
                [_verified_view(record) for record in records]
            ),
        }

    def _finalize_assertions(self) -> list[dict[str, Any]]:
        finalized: list[dict[str, Any]] = []
        for draft in self._drafts:
            refs = draft.refs
            changed = [
                ref for ref in refs if self._records[ref]["freshness"] == "changed"
            ]
            availability, result, reason = (
                draft.availability,
                draft.result,
                draft.reason,
            )
            if changed and availability in ("known", "unknown"):
                availability = "stale"
                result = None
                reason = _ReasonSkeleton(
                    "source-changed-during-build",
                    _REASON_MESSAGES["source-changed-during-build"],
                    tuple(changed),
                    (),
                )
            finalized.append(
                {
                    "id": draft.assertion_id,
                    "availability": availability,
                    "result": result,
                    "reason": None if reason is None else self._finalize_reason(
                        reason
                    ),
                    "source": self._assertion_source(refs),
                    "approval": None,
                }
            )
        finalized.sort(key=lambda assertion: assertion["id"])
        return finalized

    def _assemble(self, capture: _Capture, verify: _Capture) -> dict[str, Any]:
        observed = self._observations(capture, self._artifact_hashes_observed)
        verified = self._observations(verify, self._artifact_hashes_verified)
        self._finalize_records(observed, verified)
        assertions = self._finalize_assertions()
        items = [self._records[ref] for ref in sorted(self._records)]
        source_set_hash = _records_digest(items)
        # The contract derives buildState solely from the document state: any
        # non-current source record or non-known assertion degrades it.
        degraded = any(
            record["freshness"] != "current" for record in items
        ) or any(
            assertion["availability"] != "known" for assertion in assertions
        )
        by_id = {assertion["id"]: assertion for assertion in assertions}

        def family(prefix: str) -> list[dict[str, Any]]:
            return [
                assertion
                for assertion in assertions
                if assertion["id"].startswith(prefix)
            ]

        return {
            "schemaVersion": SNAPSHOT_VERSION,
            "identity": {
                "snapshot": {
                    "builtAt": self._now,
                    "sourceSetHash": source_set_hash,
                    "buildState": "degraded" if degraded else "current",
                },
                "run": by_id["identity.run"],
                "product": by_id["identity.product"],
                "profile": by_id["identity.profile"],
            },
            "intent": {
                "summary": by_id["intent.summary"],
                "criteria": family("intent.criteria."),
                "contract": by_id["intent.contract"],
            },
            "execution": {
                "progress": by_id["execution.progress"],
                "preview": by_id["execution.preview"],
                "repair": by_id["execution.repair"],
            },
            "evaluation": {
                "verdict": by_id["evaluation.verdict"],
                "criteria": family("evaluation.criteria."),
                "findings": family("evaluation.findings."),
                "coverage": by_id["evaluation.coverage"],
            },
            "nextActions": {
                "primary": by_id["next-actions.primary"],
                "alternatives": family("next-actions.alternative."),
            },
            "limitations": {"items": family("limitations.items.")},
            "sources": {"sourceSetHash": source_set_hash, "items": items},
        }


def _validate_build_input(
    selected_root: object,
    package_root: object,
    session_secret: object,
    now: object,
    mid_build_hook: object,
) -> None:
    if not isinstance(now, str) or _TIMESTAMP_PATTERN.fullmatch(now) is None:
        raise SnapshotBuildError(BUILD_INPUT_INVALID)
    if mid_build_hook is not None and not callable(mid_build_hook):
        raise SnapshotBuildError(BUILD_INPUT_INVALID)
    if not isinstance(selected_root, Path):
        raise SnapshotBuildError(BUILD_INPUT_INVALID)
    if not isinstance(package_root, Path):
        raise SnapshotBuildError(BUILD_INPUT_INVALID)
    if not isinstance(session_secret, bytes) or not session_secret:
        raise SnapshotBuildError(BUILD_INPUT_INVALID)


def build_snapshot(
    *,
    selected_root: Path,
    package_root: Path,
    session_secret: bytes,
    now: str | None = None,
    mid_build_hook: Callable[[], None] | None = None,
) -> BuiltSnapshot:
    """Build one immutable Run Snapshot v1 document for the selected run.

    The document is assembled from one captured, hashed source set that is
    re-verified at end-of-build; the returned :class:`BuiltSnapshot` pairs
    the contract-valid document with the registry that issued its opaque
    source locators.  A failed build raises one typed
    :class:`SnapshotBuildError` and never returns a previous snapshot.
    """
    _validate_build_input(
        selected_root, package_root, session_secret, now, mid_build_hook
    )
    try:
        registry = select_source_registry(selected_root, package_root, session_secret)
    except SourceRegistryError as error:
        raise SnapshotBuildError(error.code) from None
    except TypeError:
        raise SnapshotBuildError(BUILD_INPUT_INVALID) from None
    builder = _Builder(registry, package_root, now)
    try:
        document = builder.build(mid_build_hook)
    except SnapshotBuildError:
        raise
    except Exception:
        raise SnapshotBuildError(BUILD_FAILED) from None
    return BuiltSnapshot(document=document, registry=registry)
