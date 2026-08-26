#!/usr/bin/env python3
"""RCV1-010: the Role-attestation capability gate (binary decision record).

Decision recorded by this module: ``disabled-by-gate``.

The gate asks one binary question: does this repository contain BOTH

(a) a newly accepted ADR naming the exact Role-attestation owner
    transaction, AND
(b) that exact existing owner transaction, round-tripping every
    Snapshot v1 claim binding — assertion ID, claim ID, claim hash,
    role, authority key, source ref, source hash, source-set hash, and
    the explicit human ``confirm`` decision?

If both exist, the outcome is ``requires-new-ticket`` and the
coordinator must split a separately scoped implementation ticket
(S31/S32). Otherwise the Role-attestation action remains disabled
(S33/S34): no owner is invented, no generic confirmation store or
temporary Console owner appears, and no route is added. This module is
a test file only — the disabled outcome owns no runtime file.

Evidence trail, re-derived live by the tests below (the decision is
never hard-coded to "disabled"):

1. ``docs/adr/`` — ADR-0036, ADR-0037, and ADR-0038 are Accepted and
   cover Role attestation, but each defers the owner: no ADR contains
   the authority-registry mapping ``role-attestation.<owner>`` with a
   concrete owner, and ADR-0038 itself requires "an explicit allowlist
   change with an identified transaction owner" for any new action.
2. ``docs/specs/2026-08-25-run-snapshot-parity.md`` section 2 — the
   ``role-attestation.<owner>`` row is a parity gate: "no
   transaction/read seam preserving the full
   claim/assertion/role/authority/source-hash binding is proven"; the
   action stays disabled with no generic confirmation file.
3. Runtime mapping — the parity Source registry registers
   ``role-attestation.owner`` as an unmapped gate (no source record,
   no issuable locator); the closed typed-action allowlist
   (``actions.py``) exposes exactly refresh, view-source, and
   copy-agent-command; and no HTTP route answers any
   attestation-shaped request.
4. No claim binding — a real built Snapshot v1 document carries no
   ``approval`` object at all, so no attestation record or owner
   transaction exists anywhere to round-trip.

Because the disabled outcome owns no runtime file, the gate logic lives
in this test module as the executable record of the decision:
``evaluate_role_attestation_gate`` is a pure function over structured
repository facts, and the ``derive_repo_facts`` scans re-derive those
facts from the live repository, so the decision flips to
``requires-new-ticket`` (or trips loudly through the evidence tests)
the moment the repository evidence changes. S31/S32 — the enabled
action and its ``CLAIM_BINDING_STALE`` runtime rejection — are
future-ticket work and are modelled here only inside the pure gate.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mcp.run_console import test_http_server as harness  # noqa: E402

from design_playbook.mcp.run_console.actions import (  # noqa: E402
    CAPABILITIES,
    capability_names,
)
from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ROUTE_NOT_FOUND,
)
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402
from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    LOCATOR_INPUT_INVALID,
    SourceRegistryError,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ADR_DIR = _REPO_ROOT / "docs" / "adr"
_PARITY_SPEC = _REPO_ROOT / "docs" / "specs" / "2026-08-25-run-snapshot-parity.md"

# ---------------------------------------------------------------------------
# The pure gate: structured facts in, one binary result out.
# ---------------------------------------------------------------------------

OUTCOME_DISABLED_BY_GATE = "disabled-by-gate"
OUTCOME_REQUIRES_NEW_TICKET = "requires-new-ticket"

REASON_NO_ACCEPTED_ADR = "no-accepted-adr"
REASON_OWNER_NOT_NAMED = "accepted-adr-names-no-exact-owner"
REASON_NO_OWNER_TRANSACTION = "no-owner-transaction"
REASON_OWNER_MISMATCH = "owner-not-the-named-owner"
REASON_NO_REQUIRED_BINDING = "no-claim-binding-to-round-trip"
REASON_NOT_HUMAN_SUBMITTED = "confirmation-not-human-submitted"
REASON_CLAIM_BINDING_STALE = "claim-binding-stale"
REASON_EXACT_ROUND_TRIP = "exact-owner-round-trips-every-binding"

# Every Snapshot v1 section 12.4 binding field an owner transaction must
# round-trip exactly (plus the explicit confirm decision, checked
# alongside these as a round-trip field).
_BINDING_FIELDS = (
    "assertion_id",
    "claim_id",
    "claim_hash",
    "role",
    "authority_key",
    "source_ref",
    "source_hash",
    "source_set_hash",
)


@dataclass(frozen=True)
class ClaimBinding:
    """The Snapshot v1 claim binding an attestation must preserve.

    Fields mirror the section 12.4 closed request exactly: the
    assertion and claim identity, the claim hash, the requested role,
    the authority key, the bound source ref and hash, and the
    source-set hash of the snapshot the request was made against.
    """

    assertion_id: str
    claim_id: str
    claim_hash: str
    role: str
    authority_key: str
    source_ref: str
    source_hash: str
    source_set_hash: str


@dataclass(frozen=True)
class OwnerTransaction:
    """An owner's persisted Role-attestation transaction record.

    ``owner`` names the authority owner (the ``<owner>`` segment of the
    ``role-attestation.<owner>`` registry key). The binding fields must
    round-trip the :class:`ClaimBinding` exactly, ``decision`` must be
    the explicit ``"confirm"``, and ``submitted_by`` must record an
    explicit human submission. ``None`` means the transaction does not
    prove that fact.
    """

    owner: str | None
    assertion_id: str | None = None
    claim_id: str | None = None
    claim_hash: str | None = None
    role: str | None = None
    authority_key: str | None = None
    source_ref: str | None = None
    source_hash: str | None = None
    source_set_hash: str | None = None
    decision: str | None = None
    submitted_by: str | None = None


@dataclass(frozen=True)
class AcceptedAdr:
    """An accepted ADR that covers Role attestation.

    ``named_owner`` is the exact owner transaction the ADR maps — the
    concrete ``<owner>`` of a ``role-attestation.<owner>`` registry key.
    ``None`` (today's ADR-0036/0037/0038 shape) means the decision
    covers the attestation rules but defers the owner mapping.
    """

    document: str
    named_owner: str | None = None


@dataclass(frozen=True)
class RepoFacts:
    """The gate's structured input, derived from the repository."""

    accepted_adr: AcceptedAdr | None
    owner_transaction: OwnerTransaction | None
    required_binding: ClaimBinding | None


@dataclass(frozen=True)
class GateResult:
    """The binary decision plus its closed reason vocabulary."""

    outcome: str
    reason: str
    mismatched_fields: tuple[str, ...] = ()


def evaluate_role_attestation_gate(repo_facts: RepoFacts) -> GateResult:
    """Decide the Role-attestation capability gate from repository facts.

    The gate flips to ``requires-new-ticket`` only when an accepted ADR
    names the exact owner, that owner's transaction exists, and the
    transaction round-trips the required claim binding with an explicit
    human ``confirm`` decision. Every other fact combination — including
    a perfectly bound transaction submitted by an agent — keeps the
    capability ``disabled-by-gate``. The function is pure: it evaluates
    and never writes a file, invokes an owner, or confirms anything.
    """
    adr = repo_facts.accepted_adr
    if adr is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_ACCEPTED_ADR)
    if adr.named_owner is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_OWNER_NOT_NAMED)
    transaction = repo_facts.owner_transaction
    if transaction is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_OWNER_TRANSACTION)
    if transaction.owner != adr.named_owner:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_OWNER_MISMATCH)
    binding = repo_facts.required_binding
    if binding is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_REQUIRED_BINDING)
    if transaction.submitted_by != "human":
        # Snapshot v1 section 6 rule 10: an Agent, workflow continuation,
        # Run operator action, or earlier role click can never synthesize
        # a valid attestation — even one whose every binding field is
        # exactly right.
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NOT_HUMAN_SUBMITTED)
    mismatched = []
    if transaction.decision != "confirm":
        mismatched.append("decision")
    mismatched.extend(
        field
        for field in _BINDING_FIELDS
        if getattr(transaction, field) != getattr(binding, field)
    )
    if mismatched:
        # S32 at the gate level: any changed binding, cross-role reuse,
        # or missing confirm decision keeps the gate closed. The runtime
        # CLAIM_BINDING_STALE rejection belongs to the future enabling
        # ticket, never to this gate.
        return GateResult(
            OUTCOME_DISABLED_BY_GATE, REASON_CLAIM_BINDING_STALE, tuple(mismatched)
        )
    return GateResult(OUTCOME_REQUIRES_NEW_TICKET, REASON_EXACT_ROUND_TRIP)


# ---------------------------------------------------------------------------
# Repo-fact derivation: re-derive the gate's input from the live tree.
# ---------------------------------------------------------------------------

_ADR_STATUS_HEADING = re.compile(r"^##\s+Status\s*$", re.MULTILINE)
# The authority-registry spelling of a mapped owner,
# ``role-attestation.<owner>`` (Snapshot v1 section 8). The bare
# ``owner`` segment is the parity registry's unmapped gate key; the
# spec's ``<owner>`` placeholder cannot match the character class.
_NAMED_OWNER_KEY = re.compile(r"role-attestation\.([A-Za-z0-9][A-Za-z0-9.-]*)")
_GATE_KEY_SEGMENT = "owner"


def _adr_is_accepted(text: str) -> bool:
    """True only for an ADR whose Status section says Accepted."""
    match = _ADR_STATUS_HEADING.search(text)
    if match is None:
        return False
    first_line = text[match.end():].lstrip().split("\n", 1)[0].strip()
    return first_line.startswith("Accepted")


def _named_owner(text: str) -> str | None:
    """The concrete owner segment the ADR maps, if it maps one."""
    for segment in _NAMED_OWNER_KEY.findall(text):
        if segment != _GATE_KEY_SEGMENT:
            return segment
    return None


def scan_accepted_role_attestation_adrs(adr_dir: Path) -> tuple[AcceptedAdr, ...]:
    """Every accepted ADR covering Role attestation, in document order.

    An ADR covers Role attestation when its body mentions attestation.
    ``named_owner`` is non-None only when the ADR itself maps the
    concrete ``role-attestation.<owner>`` registry key of the exact
    owner transaction.
    """
    decisions = []
    for document in sorted(adr_dir.glob("*.md")):
        text = document.read_text(encoding="utf-8")
        if not _adr_is_accepted(text):
            continue
        if "attest" not in text.lower():
            continue
        decisions.append(
            AcceptedAdr(document=document.name, named_owner=_named_owner(text))
        )
    return tuple(decisions)


def _assertion_nodes(document: dict):
    """Every assertion-shaped node (``id`` plus ``approval``) in a snapshot."""
    stack = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "id" in node and "approval" in node:
                yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def required_claim_binding(document: dict) -> ClaimBinding | None:
    """The first claim binding the snapshot requires an attestation for.

    Snapshot v1 carries the requirement per assertion as the
    ``approval`` projection (section 6). ``None`` means no claim
    currently demands a role attestation.
    """
    for assertion in _assertion_nodes(document):
        approval = assertion["approval"]
        if approval is not None:
            return ClaimBinding(
                assertion_id=assertion["id"],
                claim_id=approval["claimId"],
                claim_hash=approval["claimHash"],
                role=approval["requiredRole"],
                authority_key=approval["authorityKey"],
                source_ref=approval["sourceRef"],
                source_hash=approval["sourceHash"],
                source_set_hash=document["sources"]["sourceSetHash"],
            )
    return None


def mapped_owner_transaction(registry, document: dict) -> OwnerTransaction | None:
    """The Role-attestation owner transaction the runtime maps today.

    The parity Source registry reserves ``role-attestation.owner`` as an
    unmapped gate: no owner transaction exists until parity work
    replaces the gate with a real registration. When the owner is
    mapped, its persisted record would surface in the snapshot as a
    ``valid``/``invalidated`` approval — and even then the snapshot
    contract deliberately carries no submitter, so the explicit human
    confirm decision must be proven by the owner's own transaction seam
    (the future enabling ticket), never synthesized here.
    """
    source = registry.source("role-attestation.owner")
    if not source.mapped or source.source_ref is None:
        return None
    owner = source.authority_key
    if owner.startswith("role-attestation."):
        owner = owner[len("role-attestation."):]
    for assertion in _assertion_nodes(document):
        approval = assertion["approval"]
        if approval is not None and approval["state"] in ("valid", "invalidated"):
            return OwnerTransaction(
                owner=owner,
                assertion_id=assertion["id"],
                claim_id=approval["claimId"],
                claim_hash=approval["claimHash"],
                role=approval["requiredRole"],
                authority_key=approval["authorityKey"],
                source_ref=approval["sourceRef"],
                source_hash=approval["sourceHash"],
                source_set_hash=document["sources"]["sourceSetHash"],
            )
    return None


def derive_repo_facts(adr_dir: Path, registry, document: dict) -> RepoFacts:
    """Re-derive the gate's input facts from the live repository."""
    decisions = scan_accepted_role_attestation_adrs(adr_dir)
    naming = [d for d in decisions if d.named_owner is not None]
    # The newest naming ADR wins; without one, the newest covering ADR
    # stands as the accepted decision that defers the owner.
    accepted = naming[-1] if naming else (decisions[-1] if decisions else None)
    return RepoFacts(
        accepted_adr=accepted,
        owner_transaction=mapped_owner_transaction(registry, document),
        required_binding=required_claim_binding(document),
    )


# ---------------------------------------------------------------------------
# Synthetic facts: the Snapshot v1 section 6/12.4 example binding.
# ---------------------------------------------------------------------------

_DIGEST_4 = "sha256:" + "4" * 64
_DIGEST_5 = "sha256:" + "5" * 64
_DIGEST_6 = "sha256:" + "6" * 64
_DIGEST_7 = "sha256:" + "7" * 64

_BINDING = ClaimBinding(
    assertion_id="intent.summary",
    claim_id="claim.intent.checkout-safety",
    claim_hash=_DIGEST_4,
    role="product",
    authority_key="intent.contract",
    source_ref="source.intent-contract",
    source_hash=_DIGEST_5,
    source_set_hash=_DIGEST_6,
)

_ENABLING_ADR = AcceptedAdr(
    document="0039-role-attestation-owner-transaction.md",
    named_owner="contract-decision",
)


def _exact_transaction(**overrides) -> OwnerTransaction:
    """The owner transaction that round-trips the example binding exactly."""
    fields = {
        "owner": "contract-decision",
        "assertion_id": "intent.summary",
        "claim_id": "claim.intent.checkout-safety",
        "claim_hash": _DIGEST_4,
        "role": "product",
        "authority_key": "intent.contract",
        "source_ref": "source.intent-contract",
        "source_hash": _DIGEST_5,
        "source_set_hash": _DIGEST_6,
        "decision": "confirm",
        "submitted_by": "human",
    }
    fields.update(overrides)
    return OwnerTransaction(**fields)


def _attestation_shaped_files(root: Path) -> list[str]:
    """Paths under root whose name looks like an attestation artifact."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and any(
            token in path.name.lower() for token in ("attest", "confirm", "approval")
        )
    )


class GateModelTest(unittest.TestCase):
    """The pure binary evaluator: every fact combination but one disables."""

    def test_no_accepted_adr_leaves_the_gate_disabled(self) -> None:
        # Even a perfect owner transaction enables nothing without the
        # accepted decision that names its owner.
        result = evaluate_role_attestation_gate(
            RepoFacts(None, _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_ACCEPTED_ADR)
        self.assertEqual(result.mismatched_fields, ())

    def test_accepted_adr_that_names_no_exact_owner_stays_disabled(self) -> None:
        # Today's ADR-0036/0037/0038 shape: the rules are accepted, the
        # owner mapping is deferred to parity work that has not happened.
        deferred = AcceptedAdr(
            document="0038-run-snapshot-contract.md", named_owner=None
        )
        result = evaluate_role_attestation_gate(
            RepoFacts(deferred, _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_OWNER_NOT_NAMED)
        self.assertEqual(result.mismatched_fields, ())

    def test_missing_owner_transaction_stays_disabled(self) -> None:
        # The named owner exists as a decision but no transaction of its
        # round-trips the binding: the exact owner is missing.
        result = evaluate_role_attestation_gate(
            RepoFacts(_ENABLING_ADR, None, _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_OWNER_TRANSACTION)

    def test_alternate_owner_transaction_does_not_satisfy_the_gate(self) -> None:
        # A different owner's transaction — including a Console-owned
        # generic store, which must never exist — cannot be translated
        # into the named owner's confirmation.
        for owner in (
            "preview-transaction",
            "run-status-narration",
            "console-generic-store",
        ):
            with self.subTest(owner=owner):
                result = evaluate_role_attestation_gate(
                    RepoFacts(_ENABLING_ADR, _exact_transaction(owner=owner), _BINDING)
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_OWNER_MISMATCH)
                self.assertEqual(result.mismatched_fields, ())

    def test_missing_required_binding_stays_disabled(self) -> None:
        result = evaluate_role_attestation_gate(
            RepoFacts(_ENABLING_ADR, _exact_transaction(), None)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_REQUIRED_BINDING)

    def test_agent_submitted_confirmation_never_counts(self) -> None:
        # Snapshot v1 section 6 rule 10: an Agent, workflow continuation,
        # Run operator action, or earlier role click can never synthesize
        # a valid attestation — even one whose binding is perfect.
        for submitted_by in (
            "agent",
            "workflow-continuation",
            "run-operator",
            "earlier-role-click",
            "console-ui",
            "human-agent",
            "",
            None,
        ):
            with self.subTest(submitted_by=submitted_by):
                result = evaluate_role_attestation_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _exact_transaction(submitted_by=submitted_by),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_NOT_HUMAN_SUBMITTED)
                self.assertEqual(result.mismatched_fields, ())

    def test_only_an_explicit_confirm_decision_round_trips(self) -> None:
        for decision in (
            "deny",
            "reject",
            "confirmed",
            "Confirm",
            "confirm ",
            "approve",
            None,
        ):
            with self.subTest(decision=decision):
                result = evaluate_role_attestation_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _exact_transaction(decision=decision),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_CLAIM_BINDING_STALE)
                self.assertEqual(result.mismatched_fields, ("decision",))

    def test_cross_role_record_reuse_is_rejected(self) -> None:
        # S32: roles cannot inherit one another's confirmation. A design
        # or engineering attestation never satisfies a product claim,
        # even for the same person and the same claim binding.
        for role in ("design", "engineering"):
            with self.subTest(role=role):
                result = evaluate_role_attestation_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _exact_transaction(role=role),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_CLAIM_BINDING_STALE)
                self.assertIn("role", result.mismatched_fields)

    def test_each_changed_binding_field_rejects_with_that_mismatch(self) -> None:
        # S32: every binding field is load-bearing — a changed claim
        # hash, source hash, or source-set (snapshot) hash each reject
        # with exactly that field, as do changed IDs, role, authority
        # key, and source ref.
        changed = {
            "assertion_id": "intent.criteria",
            "claim_id": "claim.intent.checkout-safety.v2",
            "claim_hash": _DIGEST_7,
            "role": "design",
            "authority_key": "intent.specification",
            "source_ref": "source.specification",
            "source_hash": _DIGEST_7,
            "source_set_hash": _DIGEST_7,
        }
        self.assertEqual(tuple(changed), _BINDING_FIELDS)
        for field, value in changed.items():
            with self.subTest(field=field):
                result = evaluate_role_attestation_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _exact_transaction(**{field: value}),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_CLAIM_BINDING_STALE)
                self.assertEqual(result.mismatched_fields, (field,))

    def test_the_exact_round_trip_is_the_only_enabling_path(self) -> None:
        # The gate is a real binary evaluator, not a constant: the one
        # fact combination that preserves every binding records
        # requires-new-ticket (never an implementation).
        result = evaluate_role_attestation_gate(
            RepoFacts(_ENABLING_ADR, _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_REQUIRES_NEW_TICKET)
        self.assertEqual(result.reason, REASON_EXACT_ROUND_TRIP)
        self.assertEqual(result.mismatched_fields, ())


class _BuiltSnapshotTestCase(unittest.TestCase):
    """One fixture run root with one real built snapshot (RCV1-005 seams)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = harness._make_root(self.base)
        self.session = RunConsoleSession(
            run_root=self.run_root,
            package_root=harness._PKG_ROOT,
            now_fn=harness._Clock(harness._NOW),
        )
        self.document = self.session.build_snapshot()
        self.registry = self.session.registry


class RepoDecisionEvidenceTest(_BuiltSnapshotTestCase):
    """The live repository facts that resolve the gate, re-derived here.

    These tests are the tripwire: when one fails, the documented
    repository state changed and the RCV1-010 decision must be
    re-derived — either the outcome flips to ``requires-new-ticket``
    with the exact references, or the evidence is re-recorded.
    """

    def test_the_adr_scan_finds_the_accepted_attestation_decisions(self) -> None:
        self.assertTrue(_ADR_DIR.is_dir(), str(_ADR_DIR))
        decisions = scan_accepted_role_attestation_adrs(_ADR_DIR)
        documents = {decision.document for decision in decisions}
        # The three accepted decisions that cover Role attestation rules.
        for document in (
            "0036-invited-trial-data-and-role-boundary.md",
            "0037-local-single-run-console-lifecycle.md",
            "0038-run-snapshot-contract-and-loopback-security.md",
        ):
            self.assertIn(document, documents)
        # None of them names the exact owner transaction: each defers it.
        self.assertTrue(decisions)
        for decision in decisions:
            with self.subTest(document=decision.document):
                self.assertIsNone(decision.named_owner)

    def test_the_parity_specification_still_gates_the_owner_mapping(self) -> None:
        self.assertTrue(_PARITY_SPEC.is_file(), str(_PARITY_SPEC))
        text = _PARITY_SPEC.read_text(encoding="utf-8")
        self.assertIn("role-attestation.<owner>", text)
        self.assertIn("Action disabled", text)
        self.assertIn("no generic confirmation file", text)

    def test_the_parity_registry_maps_no_role_attestation_owner(self) -> None:
        source = self.registry.source("role-attestation.owner")
        self.assertFalse(source.mapped)
        self.assertIsNone(source.source_ref)
        self.assertFalse(source.viewable)
        self.assertEqual(source.capture_targets, ())
        self.assertIsNone(mapped_owner_transaction(self.registry, self.document))

    def test_the_built_snapshot_carries_no_claim_binding(self) -> None:
        for assertion in _assertion_nodes(self.document):
            with self.subTest(assertion_id=assertion["id"]):
                self.assertIsNone(assertion["approval"])
        self.assertIsNone(required_claim_binding(self.document))

    def test_the_live_repo_facts_resolve_to_disabled_by_gate(self) -> None:
        facts = derive_repo_facts(_ADR_DIR, self.registry, self.document)
        result = evaluate_role_attestation_gate(facts)
        # The binary decision of record. If this ever fails with
        # OUTCOME_REQUIRES_NEW_TICKET, stop: report the exact ADR and
        # owner references per the ticket and do not implement S31/S32.
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertIn(
            result.reason,
            {
                REASON_NO_ACCEPTED_ADR,
                REASON_OWNER_NOT_NAMED,
                REASON_NO_OWNER_TRANSACTION,
                REASON_OWNER_MISMATCH,
                REASON_NO_REQUIRED_BINDING,
                REASON_NOT_HUMAN_SUBMITTED,
                REASON_CLAIM_BINDING_STALE,
            },
        )


# The Snapshot v1 section 12.4 closed request, exactly as specified.
_ATTESTATION_PAYLOAD = {
    "schemaVersion": 1,
    "action": "role-attestation",
    "expectedSourceSetHash": _DIGEST_6,
    "assertionId": "intent.summary",
    "claimId": "claim.intent.checkout-safety",
    "claimHash": _DIGEST_4,
    "role": "product",
    "authorityKey": "intent.contract",
    "sourceRef": "source.intent-contract",
    "sourceHash": _DIGEST_5,
    "decision": "confirm",
}
_ATTESTATION_BODY = json.dumps(_ATTESTATION_PAYLOAD).encode("utf-8")

# Every attestation-shaped route spelling, including generic
# confirmation routes that must not exist either.
_ATTESTATION_ROUTES = (
    "/api/v1/actions/role-attestation",
    "/api/v1/actions/role-attestation/",
    "/api/v1/actions/role-attestation/confirm",
    "/api/v1/actions/attest-role",
    "/api/v1/actions/attest",
    "/api/v1/actions/role-attestations",
    "/api/v1/attestation",
    "/api/v1/role-attestation",
    "/api/v1/approvals",
    "/api/v1/confirm",
)


class DisabledActionSurfaceTest(harness._ServerTestCase):
    """S34: the capability is absent — no entry, no route, no owner call."""

    def _attest(self, path, *, method="POST", body=_ATTESTATION_BODY):
        """One attestation request with valid credentials and closed body."""
        headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        return self._api(
            method, path, origin=self.server.origin, headers=headers, body=body
        )

    def test_the_capability_allowlist_has_no_role_attestation_entry(self) -> None:
        self.assertEqual(
            capability_names(), ("refresh", "view-source", "copy-agent-command")
        )
        for name in ("role-attestation", "attest-role", "attest", "attestation"):
            with self.subTest(name=name):
                self.assertNotIn(name, CAPABILITIES)
        for name in CAPABILITIES:
            with self.subTest(capability=name):
                self.assertNotIn("attest", name.lower())
        self.assertEqual(CAPABILITIES[0], "refresh")

    def test_the_server_module_declares_no_attestation_route(self) -> None:
        # Any future mention — even a comment — must force this gate
        # test to be re-derived consciously, mirroring the boundary
        # scans in test_actions.py.
        source = (Path(__file__).resolve().parent / "http_server.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("attest", source.lower())

    def test_role_attestation_action_posts_are_routeless(self) -> None:
        # A perfectly formed section 12.4 confirm request finds no route
        # at any attestation-shaped path: the capability is absent, not
        # merely refused.
        for path in _ATTESTATION_ROUTES:
            with self.subTest(path=path):
                status, _, payload = self._attest(path)
                self.assertEqual(status, 404)
                harness._assert_error(payload, ROUTE_NOT_FOUND)

    def test_the_role_attestation_route_supports_no_http_method(self) -> None:
        # Unlike /api/v1/actions/refresh (405 for non-POST), the route
        # does not exist at all: every method is a routeless 404.
        for method in ("GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"):
            with self.subTest(method=method):
                status, _, payload = self._attest(
                    "/api/v1/actions/role-attestation", method=method
                )
                self.assertEqual(status, 404)
                if method != "HEAD":
                    harness._assert_error(payload, ROUTE_NOT_FOUND)

    def test_attestation_attempts_reach_no_owner_and_write_no_file(self) -> None:
        before_tree = harness._tree_digest(self.run_root)
        _, _, served_before = self._api("GET", "/api/v1/snapshot")
        for path in _ATTESTATION_ROUTES:
            status, _, _ = self._attest(path)
            self.assertEqual(status, 404)
        # Zero owner calls: nothing was rebuilt, confirmed, or written —
        # the served snapshot is byte-identical, the run tree still has
        # exactly its fixture bytes, and no confirmation file appeared.
        _, _, served_after = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(served_after, served_before)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_attestation_shaped_files(self.run_root), [])

    def test_the_registry_can_issue_no_attestation_locator(self) -> None:
        # No read surface either: the gate key has no source record, so
        # no opaque locator can ever be issued for an attestation ref.
        document = self._snapshot_document()
        expected_hash = harness._record(document, "source.specification")[
            "observedHash"
        ]
        for ref in (
            "role-attestation.owner",
            "source.role-attestation.claim.intent.checkout-safety",
            "source.attestation",
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(SourceRegistryError) as caught:
                    self.session.registry.issue_locator(
                        source_ref=ref, expected_hash=expected_hash, now=harness._NOW
                    )
                self.assertEqual(caught.exception.code, LOCATOR_INPUT_INVALID)


class DisabledSnapshotLimitationTest(_BuiltSnapshotTestCase):
    """S34/S33: the limitation is visible and gates nothing globally."""

    def test_the_role_attestation_limitation_is_visible_known_and_closed(self) -> None:
        self.assertEqual(validate_snapshot(self.document), self.document)
        matches = [
            item
            for item in self.document["limitations"]["items"]
            if item["result"]["code"] == "role-attestation-owner-unmapped"
        ]
        self.assertEqual(len(matches), 1)
        item = matches[0]
        self.assertEqual(item["id"], "limitations.items.role-attestation-owner-unmapped")
        self.assertEqual(item["availability"], "known")
        self.assertEqual(
            item["result"]["summary"],
            "Role attestation is unavailable until an existing owner is mapped.",
        )
        # The record is the closed owner limitation: it scopes semantic
        # authority and claims no identity, employment, organization
        # membership, entitlement, or legal consent fact.
        self.assertEqual(set(item["result"]), {"code", "summary", "affectsAssertionIds"})
        self.assertEqual(item["result"]["affectsAssertionIds"], [])

    def test_missing_attestation_degrades_no_assertion(self) -> None:
        # S33: with no owner mapped, no claim requires an attestation, so
        # no assertion is unknown or stale because of one. The missing
        # capability never degrades unrelated assertions — the fixture
        # verdict and 20+ other assertions stay known.
        codes = set()
        for assertion in _assertion_nodes(self.document):
            self.assertIsNone(assertion["approval"])
            reason = assertion["reason"]
            if reason is not None:
                codes.add(reason["code"])
        self.assertNotIn("attestation-missing", codes)
        self.assertNotIn("attestation-invalidated", codes)
        verdict = self.document["evaluation"]["verdict"]
        self.assertEqual(verdict["availability"], "known")
        self.assertEqual(verdict["result"], "Pass")
        known = [
            assertion["id"]
            for assertion in _assertion_nodes(self.document)
            if assertion["availability"] == "known"
        ]
        self.assertGreater(len(known), 1)

    def test_no_global_three_role_gate_or_identity_claim_appears(self) -> None:
        # S33: the only role-bearing structure in the document is the
        # next-action owner role; there is no product+design+engineering
        # approval gate and no attester-identity field anywhere.
        role_paths = []
        attest_keys = []
        stack = [("", self.document)]
        while stack:
            path, node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    child = f"{path}.{key}" if path else key
                    if "role" in key.lower():
                        role_paths.append(child)
                    if "attest" in key.lower():
                        attest_keys.append(child)
                    stack.append((child, value))
            elif isinstance(node, list):
                stack.extend(
                    (path, item) for item in node if isinstance(item, (dict, list))
                )
        self.assertEqual(attest_keys, [])
        for path in role_paths:
            with self.subTest(path=path):
                self.assertTrue(path.startswith("nextActions."), path)

    def test_the_ui_renders_the_disabled_attest_control_with_the_limitation(self) -> None:
        # The limitation is visible in the rendered Console: the attest
        # control exists only as a disabled button described by the
        # role-attestation limitation reason, in both locales.
        source = (Path(__file__).resolve().parent / "app.js").read_text(
            encoding="utf-8"
        )
        for token in (
            't("attest_role")',
            "limitation_role_attestation_owner_unmapped",
            "role_reason_default",
            "unavailable-role-reason",
            '"role-attestation-owner-unmapped"',
            'disabled: "disabled"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)


class GateWriteBoundaryTest(unittest.TestCase):
    """The gate evaluates only: it never writes, calls, or confirms."""

    def test_gate_evaluation_writes_no_file_and_confirms_nothing(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        run_root = harness._make_root(base)
        before = sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file()
        )
        fact_sets = {
            "no-facts": RepoFacts(None, None, None),
            "adr-only": RepoFacts(_ENABLING_ADR, None, None),
            "adr-and-owner": RepoFacts(_ENABLING_ADR, _exact_transaction(), None),
            "full-enabling": RepoFacts(
                _ENABLING_ADR, _exact_transaction(), _BINDING
            ),
        }
        results = {}
        for label, facts in fact_sets.items():
            with self.subTest(facts=label):
                results[label] = evaluate_role_attestation_gate(facts)
        # Even the fully enabling evaluation only records the outcome —
        # the future owner call belongs to a new ticket, never to the
        # gate, and every evaluation stays inside the two outcomes.
        self.assertEqual(results["full-enabling"].outcome, OUTCOME_REQUIRES_NEW_TICKET)
        for label, result in results.items():
            with self.subTest(outcome=label):
                self.assertIn(
                    result.outcome,
                    (OUTCOME_DISABLED_BY_GATE, OUTCOME_REQUIRES_NEW_TICKET),
                )
        after = sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file()
        )
        self.assertEqual(after, before)
        self.assertEqual(_attestation_shaped_files(run_root), [])


if __name__ == "__main__":
    unittest.main()
