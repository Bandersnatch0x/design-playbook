#!/usr/bin/env python3
"""RCV1-011: the Diagnostic-export capability gate (binary decision record).

Decision recorded by this module: ``disabled-by-gate``.

The gate asks one binary question: does this repository contain BOTH

(a) a separately accepted, versioned Diagnostic-export contract — a
    minimal JSON schema plus a Markdown human view, carrying the
    participant-review preview, the source-set and preview-hash
    binding, manual-share-only (no upload), and selected-run
    ``trial-export/`` containment — AND
(b) that exact atomic owner transaction, writing the accepted
    JSON+Markdown pair atomically under the selected run's
    ``trial-export/`` subtree?

If both exist, the outcome is ``requires-new-ticket`` and the
coordinator must split a separately scoped implementation ticket
(S36/S37). Otherwise the Diagnostic-export preview and write stay
disabled (S35): no schema is invented, no ad-hoc export payload is
authorized, no route is added, and no directory or partial file
appears. This module is a test file only — the disabled outcome owns
no runtime file.

Evidence trail, re-derived live by the tests below (the decision is
never hard-coded to "disabled"):

1. ``docs/adr/`` — ADR-0036 and ADR-0038 are Accepted and govern the
   Diagnostic export, but both defer the contract: no accepted ADR
   names a versioned ``diagnostic-export.schema.v<N>`` contract or an
   atomic export owner, and ADR-0036 itself requires that "Diagnostic
   export schemas must be minimal, inspectable, and versioned before
   implementation."
2. ``docs/specs/2026-08-25-run-snapshot-v1.md`` section 12.5 — the
   two-phase transaction (preview, then write bound to the same
   ``expectedSourceSetHash``, export request, and ``previewHash``) is
   specified but gated: the action "MUST remain disabled until the
   separate Diagnostic export schema is accepted; this snapshot
   contract does not authorize an ad-hoc export payload", and section
   17 repeats that "Snapshot v1 does not fill that missing schema."
3. ``docs/specs/2026-08-25-run-snapshot-parity.md`` section 2 — the
   ``diagnostic-export`` row is a parity gate: "no accepted v1
   JSON/Markdown schema or transaction"; preview/write stay disabled
   and "no export is written during read parity."
4. Runtime mapping — the parity Source registry registers
   ``diagnostic-export`` as an unmapped gate (no source record, no
   issuable locator); the closed typed-action allowlist
   (``actions.py``) exposes exactly refresh, view-source, and
   copy-agent-command; no HTTP route answers any export-shaped
   request; and the built snapshot carries the
   ``diagnostic-export-contract-unavailable`` limitation instead of
   any export fact.

Because the disabled outcome owns no runtime file, the gate logic
lives in this test module as the executable record of the decision:
``evaluate_diagnostic_export_gate`` is a pure function over
structured repository facts, and the ``derive_repo_facts`` scans
re-derive those facts from the live repository, so the decision flips
to ``requires-new-ticket`` (or trips loudly through the evidence
tests) the moment the repository evidence changes. S36/S37 — the
enabled preview/write phases, their stale-binding rejection, and the
atomic write-then-rebuild — are future-ticket work and are modelled
here only inside the pure gate.
"""
from __future__ import annotations

import json
import os
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
    CAPABILITY_BY_NAME,
    KIND_SERVER_ACTION,
    capability_names,
)
from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ERROR_MESSAGES,
    ROUTE_NOT_FOUND,
)
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402
from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    LOCATOR_INPUT_INVALID,
    SourceRegistryError,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ADR_DIR = _REPO_ROOT / "docs" / "adr"
_SPECS_DIR = _REPO_ROOT / "docs" / "specs"
_V1_SPEC = _SPECS_DIR / "2026-08-25-run-snapshot-v1.md"
_PARITY_SPEC = _SPECS_DIR / "2026-08-25-run-snapshot-parity.md"
_TRIAL_DOC = _REPO_ROOT / "docs" / "agents" / "run-console-read-only-trial.md"

# ---------------------------------------------------------------------------
# The pure gate: structured facts in, one binary result out.
# ---------------------------------------------------------------------------

OUTCOME_DISABLED_BY_GATE = "disabled-by-gate"
OUTCOME_REQUIRES_NEW_TICKET = "requires-new-ticket"

REASON_NO_ACCEPTED_ADR = "no-accepted-adr"
REASON_CONTRACT_NOT_NAMED = "accepted-adr-names-no-versioned-contract"
REASON_OWNER_NOT_NAMED = "accepted-adr-names-no-atomic-owner"
REASON_NO_ACCEPTED_CONTRACT = "no-separately-accepted-export-contract"
REASON_CONTRACT_INCOMPLETE = "export-contract-incomplete"
REASON_NO_OWNER_TRANSACTION = "no-owner-transaction"
REASON_OWNER_MISMATCH = "owner-not-the-named-owner"
REASON_NO_REQUIRED_BINDING = "no-required-source-set-binding"
REASON_EXPORT_BINDING_STALE = "export-binding-stale"
REASON_EXACT_CONTRACT_AND_OWNER = "versioned-contract-and-atomic-owner"

# Every requirement the separately accepted export contract must carry
# (Snapshot v1 section 12.5 plus ADR-0036 rules 1-3 and 9): a separately
# versioned minimal JSON schema and its Markdown human view, a
# participant-review preview phase, both hash bindings, manual sharing
# with no upload endpoint, and selected-run ``trial-export/``
# containment that never touches ``evidence/`` or a Manifest.
_CONTRACT_REQUIREMENTS = (
    "versioned_json_schema",
    "markdown_human_view",
    "minimal_facts_only",
    "participant_review_preview",
    "source_set_hash_binding",
    "preview_hash_binding",
    "manual_share_only",
    "trial_export_containment",
)

# What the owner transaction itself must prove: the participant
# reviewed the preview, the JSON+Markdown pair is written atomically
# (a one-file failure leaves no partial export), and the write is
# confined to the selected run's ``trial-export/`` subtree (never a
# symlinked or escaped target).
_TRANSACTION_REQUIREMENTS = (
    "participant_reviewed",
    "atomic_json_and_markdown",
    "confined_to_trial_export",
)


@dataclass(frozen=True)
class ExportBinding:
    """The binding an export transaction must round-trip exactly.

    ``source_set_hash`` is the served snapshot's source-set hash
    (Snapshot v1 section 12.5 binds every export request to it).
    ``preview_hash`` is the hash a preview phase issued for the
    reviewed candidate; it is ``None`` until a preview exists.
    """

    source_set_hash: str
    preview_hash: str | None = None


@dataclass(frozen=True)
class ExportContract:
    """A separately accepted, versioned Diagnostic-export contract.

    ``contract_id`` is the versioned contract identity (the
    ``diagnostic-export.schema.v<N>`` the accepting ADR names). Every
    requirement flag defaults to ``False``: anything the contract
    document does not itself carry stays unproven, so a silent or
    partial contract keeps the gate closed.
    """

    contract_id: str
    versioned_json_schema: bool = False
    markdown_human_view: bool = False
    minimal_facts_only: bool = False
    participant_review_preview: bool = False
    source_set_hash_binding: bool = False
    preview_hash_binding: bool = False
    manual_share_only: bool = False
    trial_export_containment: bool = False


@dataclass(frozen=True)
class AcceptedAdr:
    """An accepted ADR that covers the Diagnostic export.

    ``named_contract`` is the exact versioned contract the ADR accepts
    and ``named_owner`` the exact atomic owner transaction it maps
    (ADR-0038 requires "an explicit allowlist decision naming its
    transaction owner"). ``None`` (today's ADR-0036/0038 shape) means
    the decision covers the export rules but defers that mapping.
    """

    document: str
    named_contract: str | None = None
    named_owner: str | None = None


@dataclass(frozen=True)
class ExportTransaction:
    """An owner's persisted Diagnostic-export transaction record.

    ``owner`` names the atomic owner, ``contract_id`` the versioned
    contract it writes, and ``expected_source_set_hash`` /
    ``preview_hash`` the binding the write must round-trip. The
    requirement flags must be proven by the owner's own transaction
    seam; ``None``/``False`` means the transaction does not prove that
    fact.
    """

    owner: str | None
    contract_id: str | None = None
    expected_source_set_hash: str | None = None
    preview_hash: str | None = None
    participant_reviewed: bool = False
    atomic_json_and_markdown: bool = False
    confined_to_trial_export: bool = False


@dataclass(frozen=True)
class RepoFacts:
    """The gate's structured input, derived from the repository."""

    accepted_adr: AcceptedAdr | None
    export_contract: ExportContract | None
    owner_transaction: ExportTransaction | None
    required_binding: ExportBinding | None


@dataclass(frozen=True)
class GateResult:
    """The binary decision plus its closed reason vocabulary."""

    outcome: str
    reason: str
    mismatched_fields: tuple[str, ...] = ()


def evaluate_diagnostic_export_gate(repo_facts: RepoFacts) -> GateResult:
    """Decide the Diagnostic-export capability gate from repository facts.

    The gate flips to ``requires-new-ticket`` only when an accepted ADR
    names the exact versioned contract and its atomic owner, the
    separately accepted contract document carries every required
    property, and that owner's transaction round-trips the source-set
    and preview binding with participant review, atomic writes, and
    ``trial-export/`` confinement. Every other fact combination —
    including a complete contract with no owner, or a perfect
    transaction under a contract nobody accepted — keeps the capability
    ``disabled-by-gate``. The function is pure: it evaluates and never
    previews, writes, uploads, or calls an owner.
    """
    adr = repo_facts.accepted_adr
    if adr is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_ACCEPTED_ADR)
    if adr.named_contract is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_CONTRACT_NOT_NAMED)
    if adr.named_owner is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_OWNER_NOT_NAMED)
    contract = repo_facts.export_contract
    if contract is None:
        # Snapshot v1 is not an export schema: a named contract with no
        # separately accepted document stays disabled.
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_ACCEPTED_CONTRACT)
    mismatched = []
    if contract.contract_id != adr.named_contract:
        mismatched.append("contract_id")
    mismatched.extend(
        requirement
        for requirement in _CONTRACT_REQUIREMENTS
        if not getattr(contract, requirement)
    )
    if mismatched:
        return GateResult(
            OUTCOME_DISABLED_BY_GATE, REASON_CONTRACT_INCOMPLETE, tuple(mismatched)
        )
    transaction = repo_facts.owner_transaction
    if transaction is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_OWNER_TRANSACTION)
    if transaction.owner != adr.named_owner:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_OWNER_MISMATCH)
    binding = repo_facts.required_binding
    if binding is None:
        return GateResult(OUTCOME_DISABLED_BY_GATE, REASON_NO_REQUIRED_BINDING)
    mismatched = []
    if transaction.contract_id != adr.named_contract:
        mismatched.append("contract_id")
    if transaction.expected_source_set_hash != binding.source_set_hash:
        # S36 at the gate level: a preview accepted against another
        # source set (stale snapshot) never writes.
        mismatched.append("expected_source_set_hash")
    if not transaction.preview_hash or (
        binding.preview_hash is not None
        and transaction.preview_hash != binding.preview_hash
    ):
        # No reviewed preview hash was bound, or the preview content
        # changed between review and write.
        mismatched.append("preview_hash")
    mismatched.extend(
        requirement
        for requirement in _TRANSACTION_REQUIREMENTS
        if not getattr(transaction, requirement)
    )
    if mismatched:
        # S36/S37 at the gate level: an unreviewed, non-atomic, or
        # escaped write keeps the gate closed. The runtime rejection
        # and the atomic write belong to the future enabling ticket,
        # never to this gate.
        return GateResult(
            OUTCOME_DISABLED_BY_GATE, REASON_EXPORT_BINDING_STALE, tuple(mismatched)
        )
    return GateResult(OUTCOME_REQUIRES_NEW_TICKET, REASON_EXACT_CONTRACT_AND_OWNER)


# ---------------------------------------------------------------------------
# Repo-fact derivation: re-derive the gate's input from the live tree.
# ---------------------------------------------------------------------------

_ADR_STATUS_HEADING = re.compile(r"^##\s+Status\s*$", re.MULTILINE)
# The versioned contract spelling a future accepting ADR would carry,
# e.g. ``diagnostic-export.schema.v2`` (or the prose "Diagnostic export
# schema v2"). Today's texts never pair the export with a version.
_NAMED_CONTRACT_KEY = re.compile(
    r"diagnostic[- ]export[ .-]{0,3}(?:schema|contract)[ .-]{0,3}v([0-9]+)",
    re.IGNORECASE,
)
# The authority-registry spelling of a mapped atomic owner,
# ``diagnostic-export.<owner>`` — mirroring the ``role-attestation.<owner>``
# mapping of the sibling gate. The bare ``diagnostic-export`` key (today's
# unmapped gate) matches nothing here.
_NAMED_OWNER_KEY = re.compile(r"diagnostic-export\.([A-Za-z0-9][A-Za-z0-9.-]*)")
_NON_OWNER_SEGMENTS = frozenset(
    {"schema", "contract", "version", "preview", "write", "owner"}
)

# The binding vocabulary a real contract document must carry, mapped to
# the contract requirements above. All markers are required (lowercased
# substring match); the hash markers are the exact spec 12.5 field
# names, so prose-only variants stay unproven and fail closed.
_CONTRACT_MARKERS = {
    "versioned_json_schema": ("json", "schema"),
    "markdown_human_view": ("markdown",),
    "participant_review_preview": ("preview",),
    "source_set_hash_binding": ("sourcessethash",),
    "preview_hash_binding": ("previewhash",),
    "minimal_facts_only": ("secret",),
    "manual_share_only": ("upload",),
    "trial_export_containment": ("trial-export",),
}


def _adr_is_accepted(text: str) -> bool:
    """True only for an ADR whose Status section says Accepted."""
    match = _ADR_STATUS_HEADING.search(text)
    if match is None:
        return False
    first_line = text[match.end():].lstrip().split("\n", 1)[0].strip()
    return first_line.startswith("Accepted")


def _named_contract(text: str) -> str | None:
    """The versioned contract id the ADR accepts, if it names one."""
    for version in _NAMED_CONTRACT_KEY.findall(text):
        return f"diagnostic-export.schema.v{version}"
    return None


def _named_owner(text: str) -> str | None:
    """The concrete atomic owner segment the ADR maps, if it maps one."""
    for segment in _NAMED_OWNER_KEY.findall(text):
        lowered = segment.lower()
        if (
            "." in segment
            or lowered in _NON_OWNER_SEGMENTS
            or re.fullmatch(r"v[0-9]+", lowered)
        ):
            continue
        return segment
    return None


def scan_accepted_diagnostic_export_adrs(adr_dir: Path) -> tuple[AcceptedAdr, ...]:
    """Every accepted ADR covering the Diagnostic export, in document order.

    An ADR covers the Diagnostic export when its body mentions an
    export. ``named_contract``/``named_owner`` are non-None only when
    the ADR itself names the exact versioned contract and the exact
    atomic owner transaction of that contract.
    """
    decisions = []
    for document in sorted(adr_dir.glob("*.md")):
        text = document.read_text(encoding="utf-8")
        if not _adr_is_accepted(text):
            continue
        if "export" not in text.lower():
            continue
        decisions.append(
            AcceptedAdr(
                document=document.name,
                named_contract=_named_contract(text),
                named_owner=_named_owner(text),
            )
        )
    return tuple(decisions)


def _contract_from_document(
    contract_id: str, text: str
) -> ExportContract:
    """Derive the requirement flags a contract document itself carries."""
    lowered = text.lower()
    requirements = {
        requirement: all(marker in lowered for marker in markers)
        for requirement, markers in _CONTRACT_MARKERS.items()
    }
    return ExportContract(contract_id=contract_id, **requirements)


def scan_export_contract_documents(
    specs_dir: Path, adr_dir: Path, named_contract: str
) -> ExportContract | None:
    """The separately accepted export contract document, if one exists.

    A contract document is an ADR or spec whose text names the exact
    versioned contract the accepted ADR accepts. The requirement flags
    are derived from the binding vocabulary the document itself
    carries; anything the document does not state stays unproven, so a
    silent or partial contract keeps the gate closed.
    """
    if named_contract is None:
        return None
    version = named_contract.rsplit(".v", 1)[-1]
    for directory in (specs_dir, adr_dir):
        for document in sorted(directory.glob("*.md")):
            text = document.read_text(encoding="utf-8")
            if version in set(_NAMED_CONTRACT_KEY.findall(text)):
                return _contract_from_document(named_contract, text)
    return None


def mapped_owner_transaction(registry, run_root: Path) -> ExportTransaction | None:
    """The Diagnostic-export owner transaction the runtime maps today.

    The parity Source registry reserves ``diagnostic-export`` as an
    unmapped gate: no owner transaction exists until parity work
    replaces the gate with a real registration. When the owner is
    mapped, its persisted pair would surface under the selected run's
    ``trial-export/`` as one JSON record plus one Markdown view, and
    this derivation surfaces exactly what that record carries — review,
    atomicity, and confinement must be stated by the record itself
    (the future enabling ticket's owner seam), never synthesized here.
    """
    source = registry.source("diagnostic-export")
    if not source.mapped or source.source_ref is None:
        return None
    trial_dir = run_root / "trial-export"
    if not trial_dir.is_dir():
        return None
    json_documents = sorted(trial_dir.glob("*.json"))
    markdown_documents = sorted(trial_dir.glob("*.md"))
    if len(json_documents) != 1 or len(markdown_documents) != 1:
        return None
    try:
        record = json.loads(json_documents[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    owner = source.authority_key
    if owner.startswith("diagnostic-export."):
        owner = owner[len("diagnostic-export."):]
    return ExportTransaction(
        owner=owner,
        contract_id=record.get("contractId"),
        expected_source_set_hash=record.get("expectedSourceSetHash"),
        preview_hash=record.get("previewHash"),
        participant_reviewed=record.get("participantReviewed") is True,
        atomic_json_and_markdown=(
            record.get("atomicJsonAndMarkdown") is True
        ),
        confined_to_trial_export=record.get("confinedToTrialExport") is True,
    )


def required_export_binding(document: dict) -> ExportBinding | None:
    """The source-set binding any export request must be made against.

    Snapshot v1 section 12.5 binds every export request to the served
    snapshot's ``expectedSourceSetHash``; the preview-hash half of the
    binding is issued only by a preview phase, which does not exist
    while the capability is disabled. ``None`` means no snapshot (and
    therefore no binding) exists.
    """
    sources = document.get("sources")
    if not isinstance(sources, dict) or "sourceSetHash" not in sources:
        return None
    return ExportBinding(source_set_hash=sources["sourceSetHash"])


def derive_repo_facts(
    adr_dir: Path, specs_dir: Path, registry, run_root: Path, document: dict
) -> RepoFacts:
    """Re-derive the gate's input facts from the live repository."""
    decisions = scan_accepted_diagnostic_export_adrs(adr_dir)
    naming = [d for d in decisions if d.named_contract is not None]
    # The newest naming ADR wins; without one, the newest covering ADR
    # stands as the accepted decision that defers the contract.
    accepted = naming[-1] if naming else (decisions[-1] if decisions else None)
    contract = None
    if accepted is not None and accepted.named_contract is not None:
        contract = scan_export_contract_documents(
            specs_dir, adr_dir, accepted.named_contract
        )
    return RepoFacts(
        accepted_adr=accepted,
        export_contract=contract,
        owner_transaction=mapped_owner_transaction(registry, run_root),
        required_binding=required_export_binding(document),
    )


# ---------------------------------------------------------------------------
# Synthetic facts: the enabling shape the repository does not carry.
# ---------------------------------------------------------------------------

_DIGEST_2 = "sha256:" + "2" * 64
_DIGEST_3 = "sha256:" + "3" * 64
_DIGEST_7 = "sha256:" + "7" * 64

_BINDING = ExportBinding(source_set_hash=_DIGEST_2, preview_hash=_DIGEST_3)

# Today's shape: the accepted decisions cover the export rules but name
# neither a versioned contract nor an atomic owner.
_DEFERRED_ADR = AcceptedAdr(
    document="0036-invited-trial-data-and-role-boundary.md",
)

# The enabling shape: a future accepted ADR naming the exact versioned
# contract and the exact atomic owner transaction.
_ENABLING_ADR = AcceptedAdr(
    document="0039-diagnostic-export-contract.md",
    named_contract="diagnostic-export.schema.v2",
    named_owner="export-transaction",
)


def _complete_contract(**overrides) -> ExportContract:
    """The separately accepted contract that carries every requirement."""
    fields = {
        "contract_id": "diagnostic-export.schema.v2",
        "versioned_json_schema": True,
        "markdown_human_view": True,
        "minimal_facts_only": True,
        "participant_review_preview": True,
        "source_set_hash_binding": True,
        "preview_hash_binding": True,
        "manual_share_only": True,
        "trial_export_containment": True,
    }
    fields.update(overrides)
    return ExportContract(**fields)


def _exact_transaction(**overrides) -> ExportTransaction:
    """The owner transaction that round-trips the example binding exactly."""
    fields = {
        "owner": "export-transaction",
        "contract_id": "diagnostic-export.schema.v2",
        "expected_source_set_hash": _DIGEST_2,
        "preview_hash": _DIGEST_3,
        "participant_reviewed": True,
        "atomic_json_and_markdown": True,
        "confined_to_trial_export": True,
    }
    fields.update(overrides)
    return ExportTransaction(**fields)


def _export_shaped_files(root: Path) -> list[str]:
    """Paths under root whose name looks like an export artifact."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and any(
            token in path.name.lower()
            for token in ("export", "trial-export", "diagnostic")
        )
    )


class GateModelTest(unittest.TestCase):
    """The pure binary evaluator: every fact combination but one disables."""

    def test_no_accepted_adr_leaves_the_gate_disabled(self) -> None:
        # Even a complete contract and a perfect transaction enable
        # nothing without the accepted decision that names them.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(None, _complete_contract(), _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_ACCEPTED_ADR)
        self.assertEqual(result.mismatched_fields, ())

    def test_accepted_adr_that_names_no_versioned_contract_stays_disabled(
        self,
    ) -> None:
        # Today's ADR-0036/0038 shape: the export rules are accepted, the
        # separately versioned contract is deferred to parity work that
        # has not happened.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(
                _DEFERRED_ADR, _complete_contract(), _exact_transaction(), _BINDING
            )
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_CONTRACT_NOT_NAMED)
        self.assertEqual(result.mismatched_fields, ())

    def test_accepted_adr_that_names_no_atomic_owner_stays_disabled(self) -> None:
        # ADR-0038: any new action requires an explicit allowlist
        # decision naming its transaction owner. A contract without a
        # named atomic owner cannot be implemented by this repo.
        naming = AcceptedAdr(
            document="0039-diagnostic-export-contract.md",
            named_contract="diagnostic-export.schema.v2",
        )
        result = evaluate_diagnostic_export_gate(
            RepoFacts(naming, _complete_contract(), _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_OWNER_NOT_NAMED)
        self.assertEqual(result.mismatched_fields, ())

    def test_missing_contract_document_stays_disabled(self) -> None:
        # An ADR may name the contract, but the separately accepted
        # document must also exist: Snapshot v1 is not an export schema
        # and nobody may implement against a missing contract.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(_ENABLING_ADR, None, _exact_transaction(), _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_ACCEPTED_CONTRACT)

    def test_each_missing_contract_requirement_rejects_with_that_mismatch(
        self,
    ) -> None:
        # Every contract requirement is load-bearing: a schema without
        # the Markdown view, a non-minimal contract that could leak
        # secrets or source, a contract without the preview phase or
        # the hash bindings, one that could upload, and one without
        # trial-export containment each reject with exactly that
        # missing requirement.
        for requirement in _CONTRACT_REQUIREMENTS:
            with self.subTest(requirement=requirement):
                result = evaluate_diagnostic_export_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _complete_contract(**{requirement: False}),
                        _exact_transaction(),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_CONTRACT_INCOMPLETE)
                self.assertEqual(result.mismatched_fields, (requirement,))

    def test_a_contract_document_of_another_version_does_not_satisfy(self) -> None:
        # The accepted ADR names v2; a v1 document on disk is not the
        # named contract, whatever it carries.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(
                _ENABLING_ADR,
                _complete_contract(contract_id="diagnostic-export.schema.v1"),
                _exact_transaction(),
                _BINDING,
            )
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_CONTRACT_INCOMPLETE)
        self.assertEqual(result.mismatched_fields, ("contract_id",))

    def test_missing_owner_transaction_stays_disabled(self) -> None:
        # The named contract exists as a decision but no atomic owner
        # transaction implements it: nothing may be written.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(_ENABLING_ADR, _complete_contract(), None, _BINDING)
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_OWNER_TRANSACTION)

    def test_alternate_owner_transaction_does_not_satisfy_the_gate(self) -> None:
        # A different owner's transaction — including a Console-owned
        # generic exporter, which must never exist — cannot be
        # translated into the named owner's atomic write.
        for owner in (
            "snapshot-builder",
            "run-status-narration",
            "console-generic-exporter",
        ):
            with self.subTest(owner=owner):
                result = evaluate_diagnostic_export_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _complete_contract(),
                        _exact_transaction(owner=owner),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_OWNER_MISMATCH)
                self.assertEqual(result.mismatched_fields, ())

    def test_missing_required_binding_stays_disabled(self) -> None:
        # With no snapshot there is no source-set hash to bind an
        # export to: the capability cannot be exercised at all.
        result = evaluate_diagnostic_export_gate(
            RepoFacts(
                _ENABLING_ADR, _complete_contract(), _exact_transaction(), None
            )
        )
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_REQUIRED_BINDING)

    def test_each_changed_transaction_binding_rejects_with_that_mismatch(
        self,
    ) -> None:
        # S36 at the gate level: a stale source set, a changed preview
        # hash, an unreviewed write, a one-file (non-atomic) write, and
        # an escaped or symlinked ``trial-export/`` target each reject
        # with exactly that field, as does a transaction of another
        # contract version.
        changed = {
            "contract_id": "diagnostic-export.schema.v1",
            "expected_source_set_hash": _DIGEST_7,
            "preview_hash": _DIGEST_7,
            "participant_reviewed": False,
            "atomic_json_and_markdown": False,
            "confined_to_trial_export": False,
        }
        for field, value in changed.items():
            with self.subTest(field=field):
                result = evaluate_diagnostic_export_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _complete_contract(),
                        _exact_transaction(**{field: value}),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_EXPORT_BINDING_STALE)
                self.assertEqual(result.mismatched_fields, (field,))

    def test_a_transaction_without_a_reviewed_preview_hash_rejects(self) -> None:
        # No preview hash was bound at all: there is no reviewed
        # candidate to write, so no export may exist.
        for preview_hash in (None, ""):
            with self.subTest(preview_hash=preview_hash):
                result = evaluate_diagnostic_export_gate(
                    RepoFacts(
                        _ENABLING_ADR,
                        _complete_contract(),
                        _exact_transaction(preview_hash=preview_hash),
                        _BINDING,
                    )
                )
                self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
                self.assertEqual(result.reason, REASON_EXPORT_BINDING_STALE)
                self.assertEqual(result.mismatched_fields, ("preview_hash",))

    def test_the_exact_contract_and_owner_is_the_only_enabling_path(self) -> None:
        # The gate is a real binary evaluator, not a constant: the one
        # fact combination that carries every requirement records
        # requires-new-ticket (never an implementation).
        result = evaluate_diagnostic_export_gate(
            RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(),
                _BINDING,
            )
        )
        self.assertEqual(result.outcome, OUTCOME_REQUIRES_NEW_TICKET)
        self.assertEqual(result.reason, REASON_EXACT_CONTRACT_AND_OWNER)
        self.assertEqual(result.mismatched_fields, ())

    def test_every_fact_combination_stays_inside_the_closed_vocabulary(self) -> None:
        # The decision record itself can never leak a path, token, or
        # source digest: every outcome, reason, and mismatched field
        # across the full matrix is closed vocabulary only.
        fact_sets = {
            "no-facts": RepoFacts(None, None, None, None),
            "deferred-adr": RepoFacts(
                _DEFERRED_ADR, _complete_contract(), _exact_transaction(), _BINDING
            ),
            "naming-adr-only": RepoFacts(_ENABLING_ADR, None, None, None),
            "adr-and-contract": RepoFacts(
                _ENABLING_ADR, _complete_contract(), None, None
            ),
            "full-enabling": RepoFacts(
                _ENABLING_ADR, _complete_contract(), _exact_transaction(), _BINDING
            ),
            "leaky-contract": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(minimal_facts_only=False),
                _exact_transaction(),
                _BINDING,
            ),
            "stale-source-set": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(expected_source_set_hash=_DIGEST_7),
                _BINDING,
            ),
            "non-atomic-transaction": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(atomic_json_and_markdown=False),
                _BINDING,
            ),
            "escaped-containment": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(confined_to_trial_export=False),
                _BINDING,
            ),
            "unreviewed-transaction": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(participant_reviewed=False),
                _BINDING,
            ),
        }
        reasons = set()
        for label, facts in fact_sets.items():
            with self.subTest(facts=label):
                result = evaluate_diagnostic_export_gate(facts)
                self.assertIn(
                    result.outcome,
                    (OUTCOME_DISABLED_BY_GATE, OUTCOME_REQUIRES_NEW_TICKET),
                )
                reasons.add(result.reason)
                for value in (result.reason, *result.mismatched_fields):
                    self.assertNotIn("/", value)
                    self.assertNotIn("\\", value)
                    self.assertNotIn("sha256:", value)
                    self.assertNotIn(_DIGEST_2, value)
        self.assertEqual(
            reasons,
            {
                REASON_NO_ACCEPTED_ADR,
                REASON_CONTRACT_NOT_NAMED,
                REASON_NO_ACCEPTED_CONTRACT,
                REASON_NO_OWNER_TRANSACTION,
                REASON_CONTRACT_INCOMPLETE,
                REASON_EXPORT_BINDING_STALE,
                REASON_EXACT_CONTRACT_AND_OWNER,
            },
        )


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
    repository state changed and the RCV1-011 decision must be
    re-derived — either the outcome flips to ``requires-new-ticket``
    with the exact references, or the evidence is re-recorded.
    """

    def test_the_adr_scan_finds_the_accepted_export_decisions(self) -> None:
        self.assertTrue(_ADR_DIR.is_dir(), str(_ADR_DIR))
        decisions = scan_accepted_diagnostic_export_adrs(_ADR_DIR)
        documents = {decision.document for decision in decisions}
        # The two accepted decisions that govern the Diagnostic export.
        for document in (
            "0036-invited-trial-data-and-role-boundary.md",
            "0038-run-snapshot-contract-and-loopback-security.md",
        ):
            self.assertIn(document, documents)
        # None of the accepted export-covering decisions names the
        # separately versioned contract or its atomic owner: each
        # defers both to parity work that has not happened.
        self.assertTrue(decisions)
        for decision in decisions:
            with self.subTest(document=decision.document):
                self.assertIsNone(decision.named_contract)
                self.assertIsNone(decision.named_owner)

    def test_the_snapshot_contract_still_gates_the_export_schema(self) -> None:
        self.assertTrue(_V1_SPEC.is_file(), str(_V1_SPEC))
        text = _V1_SPEC.read_text(encoding="utf-8")
        for line in (
            "MUST remain disabled until the separate Diagnostic export schema is accepted;",
            "this snapshot contract does not authorize an ad-hoc export payload",
            "never uploads, and never counts as acceptance.",
            "versioned JSON/Markdown contract is accepted. Snapshot v1 does not fill that",
            "Diagnostic export schema is not separately accepted/enabled",
            "Preview/write actions return `ACTION_UNAVAILABLE`; no ad-hoc export is written",
            "Write is rejected; no partial JSON/Markdown pair exists",
            "Only an atomic JSON/Markdown pair appears under `trial-export/`",
            "`evidence/`, Manifest, verdict, and acceptance facts are unchanged",
            "POST /api/v1/actions/diagnostic-export/preview",
            "POST /api/v1/actions/diagnostic-export/write",
            "`expectedSourceSetHash`, export request, and `previewHash`",
        ):
            with self.subTest(line=line[:52]):
                self.assertIn(line, text)

    def test_the_parity_specification_still_gates_the_export_owner(self) -> None:
        self.assertTrue(_PARITY_SPEC.is_file(), str(_PARITY_SPEC))
        text = _PARITY_SPEC.read_text(encoding="utf-8")
        for line in (
            "**Gate:** no accepted v1 JSON/Markdown schema or transaction",
            "Preview/write action disabled with `ACTION_UNAVAILABLE`",
            "no export is written during read parity",
            "Accept a separate versioned Diagnostic export schema and atomic transaction,",
        ):
            with self.subTest(line=line[:52]):
                self.assertIn(line, text)

    def test_the_trial_protocol_documents_the_disabled_control(self) -> None:
        self.assertTrue(_TRIAL_DOC.is_file(), str(_TRIAL_DOC))
        text = _TRIAL_DOC.read_text(encoding="utf-8")
        # The trial protocol states the current state exactly: the
        # export control is disabled and no export exists.
        self.assertIn("contract is separately accepted and implemented.", text)
        self.assertIn("is disabled in the Console and no export exists.", text)

    def test_the_parity_registry_maps_no_diagnostic_export_owner(self) -> None:
        source = self.registry.source("diagnostic-export")
        self.assertFalse(source.mapped)
        self.assertIsNone(source.source_ref)
        self.assertFalse(source.viewable)
        self.assertEqual(source.capture_targets, ())
        self.assertIsNone(mapped_owner_transaction(self.registry, self.run_root))
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_no_versioned_export_contract_document_exists(self) -> None:
        # No separately versioned export contract document exists
        # anywhere in the documented decision surface: Snapshot v1 and
        # the parity spec are gates, not export schemas, and no spec or
        # ADR document is an export contract.
        for probe in ("diagnostic-export.schema.v1", "diagnostic-export.schema.v2"):
            with self.subTest(probe=probe):
                self.assertIsNone(
                    scan_export_contract_documents(_SPECS_DIR, _ADR_DIR, probe)
                )
        for document in (*_SPECS_DIR.glob("*.md"), *_ADR_DIR.glob("*.md")):
            with self.subTest(document=document.name):
                self.assertNotIn("export", document.name.lower())
        facts = derive_repo_facts(
            _ADR_DIR, _SPECS_DIR, self.registry, self.run_root, self.document
        )
        self.assertIsNone(facts.export_contract)

    def test_the_live_repo_facts_resolve_to_disabled_by_gate(self) -> None:
        facts = derive_repo_facts(
            _ADR_DIR, _SPECS_DIR, self.registry, self.run_root, self.document
        )
        result = evaluate_diagnostic_export_gate(facts)
        # The binary decision of record. If this ever fails with
        # OUTCOME_REQUIRES_NEW_TICKET, stop: report the exact ADR,
        # contract document, and owner references per the ticket and do
        # not implement S36/S37.
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        # Today's shape: the accepted decisions defer the versioned
        # contract itself — ADR-0036 gates it and no ADR names one.
        self.assertEqual(result.reason, REASON_CONTRACT_NOT_NAMED)
        self.assertEqual(result.mismatched_fields, ())


# The Snapshot v1 section 12.5 transaction shape, exactly as specified:
# the same expectedSourceSetHash, export request, and previewHash the
# write phase would require, with the ADR-0036 minimal fact set.
_EXPORT_PAYLOAD = {
    "schemaVersion": 1,
    "action": "diagnostic-export",
    "expectedSourceSetHash": _DIGEST_2,
    "exportRequest": {
        "participantId": "p-0123456789abcdef",
        "facts": [
            "first-run-completion",
            "closed-loop-integrity",
            "comprehension",
            "elapsed-time",
            "human-intervention",
            "repeat-use",
        ],
    },
    "previewHash": _DIGEST_3,
}
_EXPORT_BODY = json.dumps(_EXPORT_PAYLOAD).encode("utf-8")

# Every export-shaped route spelling, including generic export and
# trial-export routes that must not exist either.
_EXPORT_ROUTES = (
    "/api/v1/actions/diagnostic-export",
    "/api/v1/actions/diagnostic-export/",
    "/api/v1/actions/diagnostic-export/preview",
    "/api/v1/actions/diagnostic-export/write",
    "/api/v1/actions/export",
    "/api/v1/actions/export-diagnostics",
    "/api/v1/actions/trial-export",
    "/api/v1/export",
    "/api/v1/diagnostic-export",
    "/api/v1/exports",
    "/api/v1/trial-export",
)

# Outbound client machinery no run_console runtime module may contain:
# with none of these primitives present, no request — routeless or not
# — can ever become a remote fetch, upload, or telemetry call (S40).
_OUTBOUND_MARKERS = (
    "urlopen",
    "urllib.request",
    "http.client",
    "import requests",
    "from requests",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "create_connection",
    ".connect(",
)


class DisabledActionSurfaceTest(harness._ServerTestCase):
    """S35: the capability is absent — no entry, no route, no owner call."""

    def _export(self, path, *, method="POST", body=_EXPORT_BODY):
        """One export request with valid credentials and closed body."""
        headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        return self._api(
            method, path, origin=self.server.origin, headers=headers, body=body
        )

    def test_the_capability_allowlist_has_no_export_entry(self) -> None:
        self.assertEqual(
            capability_names(), ("refresh", "view-source", "copy-agent-command")
        )
        for name in ("diagnostic-export", "export", "trial-export", "exports"):
            with self.subTest(name=name):
                self.assertNotIn(name, CAPABILITY_BY_NAME)
        for capability in CAPABILITIES:
            with self.subTest(capability=capability.name):
                self.assertNotIn("export", capability.name.lower())
                self.assertNotIn("export", (capability.route or "").lower())
        # refresh stays the only server action: nothing but a full
        # snapshot rebuild can ever be dispatched, so no preview, write,
        # or upload owner call of any kind exists to make.
        server_actions = [c for c in CAPABILITIES if c.kind == KIND_SERVER_ACTION]
        self.assertEqual([c.name for c in server_actions], ["refresh"])
        # The closed runtime error vocabulary has no ACTION_UNAVAILABLE
        # code: the capability is absent (routeless), not merely refused.
        self.assertNotIn("ACTION_UNAVAILABLE", ERROR_MESSAGES)

    def test_the_server_module_declares_no_export_route(self) -> None:
        # Any future mention — even a comment — must force this gate
        # test to be re-derived consciously, mirroring the boundary
        # scans in test_actions.py.
        source = (Path(__file__).resolve().parent / "http_server.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("export", source.lower())

    def test_export_preview_and_write_posts_are_routeless(self) -> None:
        # A perfectly formed section 12.5 export request finds no route
        # at any export-shaped path: the capability is absent, not
        # merely refused.
        for path in _EXPORT_ROUTES:
            with self.subTest(path=path):
                status, _, payload = self._export(path)
                self.assertEqual(status, 404)
                harness._assert_error(payload, ROUTE_NOT_FOUND)

    def test_the_export_routes_support_no_http_method(self) -> None:
        # Unlike /api/v1/actions/refresh (405 for non-POST), the routes
        # do not exist at all: every method is a routeless 404.
        for route in (
            "/api/v1/actions/diagnostic-export/preview",
            "/api/v1/actions/diagnostic-export/write",
        ):
            for method in ("GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"):
                with self.subTest(route=route, method=method):
                    status, _, payload = self._export(route, method=method)
                    self.assertEqual(status, 404)
                    if method != "HEAD":
                        harness._assert_error(payload, ROUTE_NOT_FOUND)

    def test_export_attempts_reach_no_owner_and_write_no_file(self) -> None:
        before_tree = harness._tree_digest(self.run_root)
        _, _, served_before = self._api("GET", "/api/v1/snapshot")
        for path in _EXPORT_ROUTES:
            status, _, _ = self._export(path)
            self.assertEqual(status, 404)
        # Zero owner calls: nothing was previewed, written, uploaded, or
        # rebuilt — the served snapshot is byte-identical, the run tree
        # still has exactly its fixture bytes, and no export directory
        # or partial file appeared.
        _, _, served_after = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(served_after, served_before)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_export_shaped_files(self.run_root), [])
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_export_bodies_never_leak_secrets_paths_or_source(self) -> None:
        secret = "tok_LEAKME_0123456789abcdef"
        run_path = "C:\\Users\\participant\\secret-run"
        source_line = (
            harness._FIXTURES / "spec-script-summary.md"
        ).read_text(encoding="utf-8").splitlines()[0]
        body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export",
                "sessionToken": secret,
                "runPath": run_path,
                "sourceExcerpt": source_line,
                "expectedSourceSetHash": _DIGEST_2,
                "previewHash": _DIGEST_3,
            }
        ).encode("utf-8")
        before_tree = harness._tree_digest(self.run_root)
        for path in (
            "/api/v1/actions/diagnostic-export/preview",
            "/api/v1/actions/diagnostic-export/write",
        ):
            status, _, payload = self._export(path, body=body)
            self.assertEqual(status, 404)
            harness._assert_error(payload, ROUTE_NOT_FOUND)
            # No path, token, or source content ever reaches a
            # response — and no export-shaped artifact exists to leak
            # into, because none is ever created.
            for marker in (secret, run_path, source_line):
                with self.subTest(path=path, marker=marker[:24]):
                    self.assertNotIn(marker.encode("utf-8"), payload)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_export_shaped_files(self.run_root), [])

    def test_an_export_attempt_never_uploads(self) -> None:
        body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export",
                "uploadUrl": "https://example.invalid/collect",
                "expectedSourceSetHash": _DIGEST_2,
                "previewHash": _DIGEST_3,
            }
        ).encode("utf-8")
        before_tree = harness._tree_digest(self.run_root)
        for path in _EXPORT_ROUTES:
            status, _, payload = self._export(path, body=body)
            self.assertEqual(status, 404)
            harness._assert_error(payload, ROUTE_NOT_FOUND)
            self.assertNotIn(b"example.invalid", payload)
        # No outbound call of any kind: no run_console runtime module
        # contains an upload or client primitive at all (S40), so a
        # routeless request can never turn into a remote fetch.
        modules = [
            path
            for path in sorted(
                (Path(__file__).resolve().parent).glob("*.py")
            )
            if not path.name.startswith("test_")
        ]
        self.assertTrue(modules)
        for module in modules:
            with self.subTest(module=module.name):
                text = module.read_text(encoding="utf-8")
                hits = [marker for marker in _OUTBOUND_MARKERS if marker in text]
                self.assertEqual(hits, [], f"{module.name} has an outbound primitive")
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)

    def test_an_export_never_lands_under_evidence(self) -> None:
        evidence_dir = self.run_root / "evidence"
        before = {
            path.relative_to(self.run_root).as_posix(): path.read_bytes()
            for path in sorted(evidence_dir.iterdir())
        }
        manifest_before = (evidence_dir / "manifest.jsonl").read_bytes()
        verdict_before = self._snapshot_document()["evaluation"]["verdict"]
        body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export",
                "target": "evidence/diagnostic-export.json",
                "expectedSourceSetHash": _DIGEST_2,
                "previewHash": _DIGEST_3,
            }
        ).encode("utf-8")
        for path in _EXPORT_ROUTES:
            status, _, payload = self._export(path, body=body)
            self.assertEqual(status, 404)
            self.assertNotIn(b"evidence/diagnostic-export.json", payload)
        # ADR-0036 rule 9: an export never enters evidence/, a Manifest,
        # or an Evaluator decision — the gate keeps it disabled
        # entirely, so not one byte of Evidence, Manifest, or verdict
        # moves.
        after = {
            path.relative_to(self.run_root).as_posix(): path.read_bytes()
            for path in sorted(evidence_dir.iterdir())
        }
        self.assertEqual(after, before)
        self.assertEqual((evidence_dir / "manifest.jsonl").read_bytes(), manifest_before)
        self.assertEqual(
            self._snapshot_document()["evaluation"]["verdict"], verdict_before
        )
        self.assertEqual(_export_shaped_files(self.run_root), [])
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_a_symlinked_trial_export_target_stays_unwritten(self) -> None:
        outside = self.base / "outside-export-target"
        outside.mkdir()
        canary = outside / "canary.md"
        canary.write_text("outside bytes must never change", encoding="utf-8")
        link = self.run_root / "trial-export"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        for path in _EXPORT_ROUTES:
            status, _, _ = self._export(path)
            self.assertEqual(status, 404)
        # Nothing is ever written through the link: the victim
        # directory keeps exactly its canary bytes, the trial-export
        # entry is still only the symlink, and no export-shaped file
        # appeared anywhere in the run.
        self.assertEqual(
            canary.read_text(encoding="utf-8"), "outside bytes must never change"
        )
        self.assertEqual(
            sorted(path.name for path in outside.iterdir()), ["canary.md"]
        )
        self.assertTrue(link.is_symlink())
        self.assertEqual(sorted(path.name for path in link.iterdir()), ["canary.md"])
        self.assertEqual(_export_shaped_files(self.run_root), [])

    def test_the_registry_can_issue_no_export_locator(self) -> None:
        # No read surface either: the gate key has no source record, so
        # no opaque locator can ever be issued for an export ref.
        document = self._snapshot_document()
        expected_hash = harness._record(document, "source.specification")[
            "observedHash"
        ]
        for ref in (
            "diagnostic-export",
            "source.diagnostic-export",
            "source.trial-export",
            "source.diagnostic-export.export",
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(SourceRegistryError) as caught:
                    self.session.registry.issue_locator(
                        source_ref=ref, expected_hash=expected_hash, now=harness._NOW
                    )
                self.assertEqual(caught.exception.code, LOCATOR_INPUT_INVALID)


class DisabledSnapshotLimitationTest(_BuiltSnapshotTestCase):
    """S35: the limitation is visible and gates nothing globally."""

    def test_the_export_limitation_is_visible_known_and_closed(self) -> None:
        self.assertEqual(validate_snapshot(self.document), self.document)
        matches = [
            item
            for item in self.document["limitations"]["items"]
            if item["result"]["code"] == "diagnostic-export-contract-unavailable"
        ]
        self.assertEqual(len(matches), 1)
        item = matches[0]
        self.assertEqual(
            item["id"], "limitations.items.diagnostic-export-contract-unavailable"
        )
        self.assertEqual(item["availability"], "known")
        self.assertEqual(
            item["result"]["summary"],
            "Diagnostic export is unavailable until its contract is accepted.",
        )
        # The record is the closed capability limitation: it claims no
        # export state, affects no assertion, and carries no free-form
        # Console narration.
        self.assertEqual(set(item["result"]), {"code", "summary", "affectsAssertionIds"})
        self.assertEqual(item["result"]["affectsAssertionIds"], [])

    def test_the_export_limitation_degrades_no_assertion_or_verdict(self) -> None:
        # S35 keeps the missing capability local: no assertion carries
        # an export-shaped reason, and the fixture verdict and the
        # other assertions stay known. The disabled control never
        # degrades unrelated facts.
        codes = set()
        stack = [self.document]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "id" in node and "approval" in node:
                    reason = node.get("reason")
                    if reason is not None:
                        codes.add(reason["code"])
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        for forbidden in (
            "export-missing",
            "export-unavailable",
            "diagnostic-export-missing",
            "export-contract-stale",
        ):
            self.assertNotIn(forbidden, codes)
        verdict = self.document["evaluation"]["verdict"]
        self.assertEqual(verdict["availability"], "known")
        self.assertEqual(verdict["result"], "Pass")
        known = [
            node["id"]
            for node in self._assertions()
            if node["availability"] == "known"
        ]
        self.assertGreater(len(known), 1)

    def _assertions(self) -> list[dict]:
        """Every assertion-shaped node (``id`` plus ``approval``)."""
        nodes = []
        stack = [self.document]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "id" in node and "approval" in node:
                    nodes.append(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        return nodes

    def test_the_snapshot_carries_no_export_fact_outside_the_limitation(self) -> None:
        # The only place "export" appears anywhere in the document is
        # the closed limitation record: no export transaction, preview,
        # path, or fact is projected anywhere else.
        offenders = []

        def walk(path: str, node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    child = f"{path}.{key}" if path else key
                    if "export" in key.lower():
                        offenders.append(child)
                    walk(child, value)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(f"{path}[{index}]", item)
            elif isinstance(node, str) and "export" in node.lower():
                offenders.append(path)

        walk("", self.document)
        self.assertEqual(
            offenders,
            [
                "limitations.items[0].id",
                "limitations.items[0].result.code",
                "limitations.items[0].result.summary",
            ],
        )

    def test_the_ui_renders_the_disabled_export_control_with_the_limitation(self) -> None:
        # The limitation is visible in the rendered Console: the export
        # control exists only as a disabled button described by the
        # diagnostic-export limitation reason, in both locales.
        source = (Path(__file__).resolve().parent / "app.js").read_text(
            encoding="utf-8"
        )
        for token in (
            't("export_diagnostics")',
            "limitation_diagnostic_export_contract_unavailable",
            "export_reason_default",
            '"diagnostic-export-contract-unavailable"',
            "unavailable-export-reason",
            'disabled: "disabled"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)


class GateWriteBoundaryTest(unittest.TestCase):
    """The gate evaluates only: it never previews, writes, or uploads."""

    def test_gate_evaluation_across_the_full_fact_matrix_writes_nothing(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        run_root = harness._make_root(base)
        session = RunConsoleSession(
            run_root=run_root,
            package_root=harness._PKG_ROOT,
            now_fn=harness._Clock(harness._NOW),
        )
        document = session.build_snapshot()
        served_before = json.dumps(document, sort_keys=True).encode("utf-8")
        tree_before = harness._tree_digest(run_root)
        files_before = sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file()
        )
        evidence_before = {
            path.relative_to(run_root).as_posix(): path.read_bytes()
            for path in sorted((run_root / "evidence").iterdir())
        }
        fact_sets = {
            "no-facts": RepoFacts(None, None, None, None),
            "deferred-adr-only": RepoFacts(_DEFERRED_ADR, None, None, None),
            "naming-adr-only": RepoFacts(_ENABLING_ADR, None, None, None),
            "adr-and-contract": RepoFacts(
                _ENABLING_ADR, _complete_contract(), None, None
            ),
            "contract-and-transaction": RepoFacts(
                _ENABLING_ADR, _complete_contract(), _exact_transaction(), None
            ),
            "full-enabling": RepoFacts(
                _ENABLING_ADR, _complete_contract(), _exact_transaction(), _BINDING
            ),
            "leaky-contract": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(minimal_facts_only=False),
                _exact_transaction(),
                _BINDING,
            ),
            "stale-source-set": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(expected_source_set_hash=_DIGEST_7),
                _BINDING,
            ),
            "changed-preview": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(preview_hash=_DIGEST_7),
                _BINDING,
            ),
            "non-atomic-transaction": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(atomic_json_and_markdown=False),
                _BINDING,
            ),
            "escaped-containment": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(confined_to_trial_export=False),
                _BINDING,
            ),
            "unreviewed-transaction": RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(participant_reviewed=False),
                _BINDING,
            ),
        }
        results = {}
        for label, facts in fact_sets.items():
            with self.subTest(facts=label):
                results[label] = evaluate_diagnostic_export_gate(facts)
                self.assertIn(
                    results[label].outcome,
                    (OUTCOME_DISABLED_BY_GATE, OUTCOME_REQUIRES_NEW_TICKET),
                )
        # Even the fully enabling evaluation only records the outcome —
        # the future preview/write phases belong to a new ticket, never
        # to the gate — and every other fact set stays disabled.
        self.assertEqual(
            results["full-enabling"].outcome, OUTCOME_REQUIRES_NEW_TICKET
        )
        for label in fact_sets:
            if label != "full-enabling":
                with self.subTest(disabled=label):
                    self.assertEqual(
                        results[label].outcome, OUTCOME_DISABLED_BY_GATE
                    )
        # Zero files across the whole matrix: no export directory, no
        # partial JSON or Markdown, no Evidence or Manifest change, and
        # the built snapshot document is untouched by every evaluation.
        files_after = sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files_after, files_before)
        self.assertEqual(harness._tree_digest(run_root), tree_before)
        evidence_after = {
            path.relative_to(run_root).as_posix(): path.read_bytes()
            for path in sorted((run_root / "evidence").iterdir())
        }
        self.assertEqual(evidence_after, evidence_before)
        self.assertFalse((run_root / "trial-export").exists())
        self.assertEqual(_export_shaped_files(run_root), [])
        self.assertEqual(
            json.dumps(document, sort_keys=True).encode("utf-8"), served_before
        )
        self.assertEqual(validate_snapshot(document), document)


if __name__ == "__main__":
    unittest.main()
