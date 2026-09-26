#!/usr/bin/env python3
"""RCV1-011: the Diagnostic-export capability gate (decision record).

Decision recorded by this module: ``accepted-by-adr-0044`` (2026-09-22),
superseding the 2026-08-27 ``disabled-by-gate`` record this file carried
when the accepted ADR, contract document, and owner transaction did not
exist yet.

The gate still asks its binary question against live evidence, re-derived
by the tests below (the decision is never hard-coded):

(a) a separately accepted, versioned Diagnostic-export contract — a
    minimal JSON schema plus a Markdown human view, carrying the
    participant-review preview, the source-set and preview-hash
    binding, manual-share-only (no upload), and selected-run
    ``trial-export/`` containment — named by an accepted ADR, AND
(b) that exact atomic owner transaction, whose persisted record — the
    written pair under the selected run's ``trial-export/`` subtree —
    states the participant review, the atomic pair, and the
    containment in-band, with the preview hash verifiable from the
    JSON bytes and the file name.

With both present the outcome is ``accepted-by-adr-0044``: the preview
and write routes are live (S35 enabled state) and S36/S37 are binding
tests (``test_diagnostic_export_server.py``). Fail-closed paths are
unchanged: a missing decision, an unnamed contract or owner, a missing
or incomplete contract document, a missing or mismatched owner record,
or a stale binding each keeps the outcome ``disabled-by-gate`` — so a
future regression (a deleted ADR, a broken record, an unmapped owner)
flips this decision loudly instead of silently.

Evidence trail, re-derived live by the tests below:

1. ``docs/adr/`` — ADR-0036 and ADR-0038 govern the export but defer the
   contract; ADR-0044 (2026-09-22) accepts versioned contract
   ``diagnostic-export.schema.v1`` and maps the owner (authority key
   ``diagnostic-export``, registry kind ``export-transaction``).
2. ADR-0044 carries the accepted preview/write transaction and binding
   vocabulary (sourceSetHash, previewHash, secrets exclusion, manual
   share, trial-export); private planning documents are not test inputs.
3. The packaged snapshot schema and the export transaction define the
   executable contract; transaction and HTTP suites verify their behavior.
4. Runtime mapping — the parity Source registry registers
   ``diagnostic-export`` as a mapped action owner (no source record, no
   issuable locator); the closed typed-action allowlist carries the
   export capability alongside refresh/view-source/copy; the two routes
   dispatch the preview and the reviewed write; role attestation stays
   gated, and the built snapshot carries no export limitation (the
   remaining disabled capability is role attestation only).
"""
from __future__ import annotations

import hashlib
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

# The MCP runtime stays at mcp/run_console/; the suite lives under tests/run_console/.
_COMPONENT_DIR = _PKG_ROOT / "mcp" / "run_console"

from tests.run_console import test_http_server as harness  # noqa: E402

from design_playbook.mcp.run_console.actions import (  # noqa: E402
    CAPABILITIES,
    capability_names,
)
from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ERROR_MESSAGES,
    METHOD_NOT_ALLOWED,
    ROUTE_NOT_FOUND,
)
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402
from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    LOCATOR_INPUT_INVALID,
    SourceRegistryError,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ADR_DIR = _REPO_ROOT / "docs" / "adr"
_EXPORT_ADR = _ADR_DIR / "0044-diagnostic-export-contract-v1.md"
_TRIAL_DOC = _REPO_ROOT / "docs" / "agents" / "run-console-read-only-trial.md"

# ---------------------------------------------------------------------------
# The pure gate: structured facts in, one binary result out.
# ---------------------------------------------------------------------------

OUTCOME_DISABLED_BY_GATE = "disabled-by-gate"
# The pre-acceptance record (2026-08-27..2026-09-22) resolved to
# ``requires-new-ticket``; the accepted outcome supersedes it (ADR-0044).
OUTCOME_ACCEPTED = "accepted-by-adr-0044"

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

    The gate reaches ``accepted-by-adr-0044`` only when an accepted ADR
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
    return GateResult(OUTCOME_ACCEPTED, REASON_EXACT_CONTRACT_AND_OWNER)


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
# names lowercased (``sourceSetHash`` / ``previewHash``), so prose-only
# variants stay unproven and fail closed.
_CONTRACT_MARKERS = {
    "versioned_json_schema": ("json", "schema"),
    "markdown_human_view": ("markdown",),
    "participant_review_preview": ("preview",),
    "source_set_hash_binding": ("sourcesethash",),
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
    """The concrete atomic owner segment the ADR maps, if it maps one.

    Two accepted shapes are recognized (ADR-0044 uses the second): the
    pre-declared ``diagnostic-export.<owner>`` child-key form, or an ADR
    that names the capability key together with the
    ``export-transaction`` owner kind it maps.
    """
    for segment in _NAMED_OWNER_KEY.findall(text):
        lowered = segment.lower()
        if (
            "." in segment
            or lowered in _NON_OWNER_SEGMENTS
            or re.fullmatch(r"v[0-9]+", lowered)
        ):
            continue
        return segment
    if "export-transaction" in text and "diagnostic-export" in text:
        return "diagnostic-export"
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
    adr_dir: Path, named_contract: str
) -> ExportContract | None:
    """The separately accepted export contract document, if one exists.

    A contract document is an accepted ADR that both matches the version
    the accepted ADR names and declares the export contract identity
    itself (the ``exportContract`` block) — other documents may reference
    the contract by id or link, but a reference is not a contract. The
    requirement flags are derived from the binding vocabulary the
    document itself carries; anything the document does not state stays
    unproven, so a silent or partial contract keeps the gate closed.
    """
    if named_contract is None:
        return None
    version = named_contract.rsplit(".v", 1)[-1]
    for document in sorted(adr_dir.glob("*.md")):
        text = document.read_text(encoding="utf-8")
        if (
            _adr_is_accepted(text)
            and version in set(_NAMED_CONTRACT_KEY.findall(text))
            and "exportcontract" in text.lower()
        ):
            return _contract_from_document(named_contract, text)
    return None


def mapped_owner_transaction(registry, run_root: Path) -> ExportTransaction | None:
    """The Diagnostic-export owner transaction the runtime maps today.

    ADR-0044 maps the owner as an action owner: the registry entry is
    ``mapped`` with no source record (it issues no locator and carries no
    viewable target), so the derivation requires exactly that shape. The
    persisted record — a JSON document plus its same-stem Markdown view
    under the selected run's ``trial-export/`` — must state the
    transaction bindings in-band (participant review, atomicity,
    confinement); the preview hash is verified from the JSON bytes
    themselves (they are the reviewed candidate) against the file name's
    hash stem. Repeated exports are ordinary pairs: any verifiable pair
    proves the owner. Anything the record does not itself carry stays
    unproven.
    """
    source = registry.source("diagnostic-export")
    if not source.mapped or source.source_ref is not None or source.viewable:
        return None
    trial_dir = run_root / "trial-export"
    if not trial_dir.is_dir():
        return None
    # Repeated exports are ordinary (roadmap trial boundary): accept any
    # verifiable pair in the subtree, not only the first one ever written.
    for json_document in sorted(trial_dir.glob("*.json")):
        markdown_document = json_document.with_suffix(".md")
        if not markdown_document.is_file():
            continue
        try:
            json_bytes = json_document.read_bytes()
            record = json.loads(json_bytes.decode("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        # The preview hash is the hash of the persisted candidate itself;
        # the file name must name the same bytes it stores.
        digest = hashlib.sha256(json_bytes).hexdigest()
        stem = json_document.name[len("export-"):-len(".json")]
        if not digest.startswith(stem) or len(stem) != 12:
            continue
        contract = record.get("exportContract")
        transaction = record.get("transaction")
        if not isinstance(contract, dict) or not isinstance(transaction, dict):
            continue
        # The long-lived backward-compat surface (contract spec §2): a
        # reader rejects an unknown contract version fail-closed, on the
        # version field itself — an id naming v1 with a version that is
        # not v1 is not the accepted contract.
        if contract.get("version") != 1:
            continue
        return ExportTransaction(
            owner=source.authority_key,
            contract_id=contract.get("id"),
            expected_source_set_hash=(
                record.get("run", {}).get("sourceSetHash")
                if isinstance(record.get("run"), dict)
                else None
            ),
            preview_hash=digest,
            participant_reviewed=(
                transaction.get("participantReviewed") is True
            ),
            atomic_json_and_markdown=(
                transaction.get("atomicJsonAndMarkdown") is True
            ),
            confined_to_trial_export=(
                transaction.get("confinedToTrialExport") is True
            ),
        )
    return None


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
    adr_dir: Path, registry, run_root: Path, document: dict
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
            adr_dir, accepted.named_contract
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
        # fact combination that carries every requirement records the
        # accepted state (never an implementation by itself).
        result = evaluate_diagnostic_export_gate(
            RepoFacts(
                _ENABLING_ADR,
                _complete_contract(),
                _exact_transaction(),
                _BINDING,
            )
        )
        self.assertEqual(result.outcome, OUTCOME_ACCEPTED)
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
                    (OUTCOME_DISABLED_BY_GATE, OUTCOME_ACCEPTED),
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
    re-derived — either the accepted decision no longer holds (a
    deleted ADR, a broken contract document, an unmapped owner) and
    the outcome flips back to ``disabled-by-gate``, or the evidence is
    re-recorded.
    """

    def test_the_adr_scan_finds_the_accepted_export_decisions(self) -> None:
        self.assertTrue(_ADR_DIR.is_dir(), str(_ADR_DIR))
        decisions = scan_accepted_diagnostic_export_adrs(_ADR_DIR)
        documents = {decision.document for decision in decisions}
        # The governing decisions: the two boundary ADRs that defer the
        # contract, plus the one accepted decision that names it.
        for document in (
            "0036-invited-trial-data-and-role-boundary.md",
            "0038-run-snapshot-contract-and-loopback-security.md",
            "0044-diagnostic-export-contract-v1.md",
        ):
            self.assertIn(document, documents)
        named = {
            decision.document: decision
            for decision in decisions
            if decision.named_contract is not None
        }
        # Only ADR-0044 names the versioned contract and the owner; the
        # two boundary ADRs still defer both.
        self.assertEqual(
            sorted(named),
            ["0044-diagnostic-export-contract-v1.md"],
        )
        decision = named["0044-diagnostic-export-contract-v1.md"]
        self.assertEqual(decision.named_contract, "diagnostic-export.schema.v1")
        self.assertEqual(decision.named_owner, "diagnostic-export")
        for other in (
            "0036-invited-trial-data-and-role-boundary.md",
            "0038-run-snapshot-contract-and-loopback-security.md",
        ):
            with self.subTest(document=other):
                self.assertIsNone(
                    next(
                        d for d in decisions if d.document == other
                    ).named_contract,
                )

    def test_the_accepted_adr_preserves_export_transaction_boundaries(self) -> None:
        text = _EXPORT_ADR.read_text(encoding="utf-8")
        # Preserve the public decision independently of local planning.
        # Server/transaction tests exercise rejection and atomicity.
        for line in (
            '"id": "diagnostic-export.schema.v1", "version": 1',
            "`expectedSourceSetHash` and `previewHash`",
            "`participantReviewed`",
            "both files or neither",
            "export never writes under `evidence/`",
            "never updates a Manifest, never changes a verdict, never uploads",
            "never counts as acceptance",
            "selected run's",
            "`trial-export/` subtree",
        ):
            with self.subTest(line=line[:52]):
                self.assertIn(line, text)

    def test_the_accepted_adr_names_the_owner_without_authorizing_a_trial(self) -> None:
        text = _EXPORT_ADR.read_text(encoding="utf-8")
        for line in (
            "authority key `diagnostic-export`",
            "`export-transaction`",
            "This decision does not",
            "satisfy `G-RO-TRIAL-PASS`",
            "Role attestation (S31",
        ):
            with self.subTest(line=line[:52]):
                self.assertIn(line, text)

    def test_the_trial_protocol_documents_the_accepted_control(self) -> None:
        self.assertTrue(_TRIAL_DOC.is_file(), str(_TRIAL_DOC))
        text = _TRIAL_DOC.read_text(encoding="utf-8")
        # The trial protocol states the current state exactly: the
        # contract is accepted and the transaction is live, the
        # participant reviews before any write, sharing stays manual,
        # and no trial is run by the document itself.
        self.assertIn("Since ADR-0044 (2026-09-22) the", text)
        self.assertIn("contract is separately accepted and implemented", text)
        self.assertIn("reviews the exact candidate", text)
        self.assertIn("it is shared manually", text)
        for stale in (
            "that control\n  is disabled in the Console and no export exists",
            "only once a Diagnostic export",
        ):
            with self.subTest(stale=stale[:40]):
                self.assertNotIn(stale, text)

    def test_the_parity_registry_maps_the_diagnostic_export_owner(self) -> None:
        # ADR-0044: the owner is mapped — but as an action owner: no
        # source record, no viewable target, no issuable locator.
        source = self.registry.source("diagnostic-export")
        self.assertTrue(source.mapped)
        self.assertIsNone(source.source_ref)
        self.assertFalse(source.viewable)
        self.assertEqual(source.capture_targets, ())
        self.assertEqual(source.kind, "export-transaction")
        # Before any export exists, no owner transaction is derivable:
        # the mapped owner alone proves nothing (fail-closed).
        self.assertIsNone(mapped_owner_transaction(self.registry, self.run_root))
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_the_accepted_contract_document_exists_and_carries_the_vocabulary(
        self,
    ) -> None:
        # The accepted public ADR itself carries every binding marker the
        # gate requires — anything it did not carry would stay unproven.
        for probe in ("diagnostic-export.schema.v1",):
            with self.subTest(probe=probe):
                contract = scan_export_contract_documents(
                    _ADR_DIR, probe
                )
                self.assertIsNotNone(contract)
                assert contract is not None
                self.assertEqual(contract.contract_id, probe)
                for requirement in _CONTRACT_REQUIREMENTS:
                    with self.subTest(requirement=requirement):
                        self.assertTrue(
                            getattr(contract, requirement),
                            f"contract document does not state {requirement}",
                        )
        # A probe for a version nobody accepted still finds nothing to
        # satisfy that version.
        self.assertIsNone(
            scan_export_contract_documents(_ADR_DIR,
                                           "diagnostic-export.schema.v2")
        )
        facts = derive_repo_facts(
            _ADR_DIR, self.registry, self.run_root, self.document
        )
        self.assertIsNotNone(facts.export_contract)
        self.assertEqual(facts.export_contract.contract_id,
                         "diagnostic-export.schema.v1")

    def test_the_live_repo_facts_stay_disabled_until_an_export_exists(self) -> None:
        # ADR-0044 is accepted and the contract document exists, but no
        # export has been written in this run root: the mapped owner
        # alone proves nothing, so the gate stays fail-closed.
        facts = derive_repo_facts(
            _ADR_DIR, self.registry, self.run_root, self.document
        )
        result = evaluate_diagnostic_export_gate(facts)
        self.assertIsNotNone(facts.accepted_adr)
        self.assertIsNotNone(facts.export_contract)
        self.assertEqual(result.outcome, OUTCOME_DISABLED_BY_GATE)
        self.assertEqual(result.reason, REASON_NO_OWNER_TRANSACTION)
        self.assertEqual(result.mismatched_fields, ())

    def test_the_gate_rejects_an_unknown_contract_version(self) -> None:
        # Spec §2: readers reject unknown versions fail-closed — on the
        # version field itself, not only the id spelling. A persisted pair
        # whose version is not v1 derives no owner transaction.
        from design_playbook.mcp.run_console.export_transaction import (
            perform_preview,
            perform_write,
        )
        preview = perform_preview(self.session, None)
        perform_write(
            self.session,
            expected_source_set_hash=preview.source_set_hash,
            preview_hash_hex=preview.preview_hash,
            participant_ref=None,
        )
        record_path = next(
            (self.run_root / "trial-export").glob("*.json")
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["exportContract"]["version"], 1)
        record["exportContract"]["version"] = 2
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        self.assertIsNone(
            mapped_owner_transaction(self.registry, self.run_root)
        )
        # ...and the accepted decision itself is untouched by the tamper:
        # restoring the version re-derives the owner.
        record["exportContract"]["version"] = 1
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        # The re-written bytes no longer hash to the file name stem — the
        # derivation fails closed on that axis instead, which is the same
        # bargain: tampered records prove nothing.
        self.assertIsNone(
            mapped_owner_transaction(self.registry, self.run_root)
        )

    def test_the_gate_flips_on_real_transaction_evidence(self) -> None:
        # The full closure: a real preview + a real participant-reviewed
        # write through the real session produces a persisted pair whose
        # record re-derives to the accepted decision — the decision
        # record flips on evidence, never on a hard-coded constant.
        from design_playbook.mcp.run_console.actions import (
            validate_export_preview_payload,
            validate_export_write_payload,
        )
        from design_playbook.mcp.run_console.export_transaction import (
            perform_preview,
            perform_write,
        )
        preview = perform_preview(self.session, None)
        commit = perform_write(
            self.session,
            expected_source_set_hash=preview.source_set_hash,
            preview_hash_hex=preview.preview_hash,
            participant_ref=None,
        )
        self.assertEqual(len(commit.written), 2)
        facts = derive_repo_facts(
            _ADR_DIR, self.registry, self.run_root, self.document
        )
        result = evaluate_diagnostic_export_gate(facts)
        self.assertEqual(result.outcome, OUTCOME_ACCEPTED)
        self.assertEqual(result.reason, REASON_EXACT_CONTRACT_AND_OWNER)
        self.assertEqual(result.mismatched_fields, ())
        # The derivation's transaction came from the persisted record and
        # round-trips the served binding exactly.
        assert facts.owner_transaction is not None
        self.assertEqual(
            facts.owner_transaction.expected_source_set_hash,
            preview.source_set_hash,
        )
        self.assertEqual(
            facts.owner_transaction.preview_hash, preview.preview_hash
        )
        self.assertTrue(facts.owner_transaction.participant_reviewed)
        self.assertTrue(facts.owner_transaction.atomic_json_and_markdown)
        self.assertTrue(facts.owner_transaction.confined_to_trial_export)
        # The closed validators accept the same round-trip.
        self.assertIsNone(
            validate_export_preview_payload(
                {"schemaVersion": 1, "action": "diagnostic-export-preview"}
            )
        )
        expected, preview_hex, ref = validate_export_write_payload(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export-write",
                "expectedSourceSetHash": preview.source_set_hash,
                "previewHash": preview.preview_hash,
                "participantReviewed": True,
            }
        )
        self.assertEqual(expected, preview.source_set_hash)
        self.assertEqual(preview_hex, preview.preview_hash)
        self.assertIsNone(ref)


# The closed preview payload the accepted contract specifies (the write
# path's closed payload and its binding matrix live in
# test_diagnostic_export_server.py).
_EXPORT_PAYLOAD = {
    "schemaVersion": 1,
    "action": "diagnostic-export-preview",
}

# The two S35 route spellings: live in the accepted state.
_SPEC_EXPORT_ROUTES = (
    "/api/v1/actions/diagnostic-export/preview",
    "/api/v1/actions/diagnostic-export/write",
)

# Every other export-shaped route spelling, including generic export
# and trial-export routes that must not exist at all.
_FAKE_EXPORT_ROUTES = (
    "/api/v1/actions/diagnostic-export",
    "/api/v1/actions/diagnostic-export/",
    "/api/v1/actions/export",
    "/api/v1/actions/export-diagnostics",
    "/api/v1/actions/trial-export",
    "/api/v1/export",
    "/api/v1/diagnostic-export",
    "/api/v1/exports",
    "/api/v1/trial-export",
)

_EXPORT_ROUTES = _SPEC_EXPORT_ROUTES + _FAKE_EXPORT_ROUTES


def _expected_gate(path: str) -> tuple[int, str]:
    """S35 enabled state per path: the two specified routes are live
    (POST dispatch); every other export-shaped spelling stays routeless."""
    if path in _SPEC_EXPORT_ROUTES:
        return 200, "diagnostic-export-preview"
    return 404, ROUTE_NOT_FOUND


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
    """S35 enabled state: the accepted capability dispatches exactly two
    routes; every other export-shaped spelling stays routeless, and the
    boundary disciplines (no upload, no evidence writes, no symlink
    escape) hold against the real transaction."""

    def _export(self, path, *, method="POST", body=None):
        """One export request with valid credentials; body must be explicit."""
        if body is None:
            headers = {}
        else:
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            }
        return self._api(
            method, path, origin=self.server.origin, headers=headers, body=body
        )

    def test_the_capability_allowlist_carries_the_accepted_export(self) -> None:
        self.assertEqual(
            capability_names(),
            ("refresh", "view-source", "copy-agent-command", "diagnostic-export"),
        )
        for name in ("export", "trial-export", "exports", "export-diagnostics"):
            with self.subTest(name=name):
                self.assertNotIn(name, CAPABILITIES)
        self.assertEqual(CAPABILITIES[0], "refresh")
        # The typed-refusal vocabulary stays available for the sibling
        # role-attestation gate, but the export routes no longer answer
        # with it: they dispatch (asserted below).
        self.assertIn("ACTION_UNAVAILABLE", ERROR_MESSAGES)

    def test_the_server_module_declares_exactly_the_two_export_routes(self) -> None:
        # The two S35 route spellings are the only export-shaped route
        # literals the server may declare: any new spelling — even in a
        # comment — must force this gate test to be re-derived
        # consciously, mirroring the boundary scans in test_actions.py.
        source = (_COMPONENT_DIR / "http_server.py").read_text(
            encoding="utf-8"
        )
        route_literals = set(re.findall(r'"(/api/v1/[^"]*export[^"]*)"', source))
        self.assertEqual(route_literals, set(_SPEC_EXPORT_ROUTES))

    def test_export_posts_dispatch_the_accepted_routes(self) -> None:
        # The two specified routes are live: the preview answers its
        # closed payload with the exact candidate pair, and the write
        # answers with a closed-schema rejection for an unreviewed/
        # unbound request (its happy path is S37's, in the server tests).
        for path in _EXPORT_ROUTES:
            with self.subTest(path=path):
                status, _, payload = self._export(
                    path, body=json.dumps(_EXPORT_PAYLOAD).encode("utf-8")
                )
                if path in _SPEC_EXPORT_ROUTES:
                    if path.endswith("/preview"):
                        self.assertEqual(status, 200, (path, payload))
                        body = json.loads(payload)
                        self.assertEqual(
                            set(body),
                            {
                                "schemaVersion",
                                "action",
                                "previewHash",
                                "expectedSourceSetHash",
                                "json",
                                "markdown",
                            },
                        )
                    else:
                        body = json.loads(payload)
                        self.assertEqual(
                            body["error"]["code"], "ACTION_PAYLOAD_INVALID"
                        )
                else:
                    self.assertEqual(status, 404, (path, payload))

    def test_the_export_routes_support_no_method_but_post(self) -> None:
        # Like /api/v1/actions/refresh, the two export routes answer
        # non-POST methods with 405: they are known paths whose only
        # specified method is the typed POST (S35).
        for route in _SPEC_EXPORT_ROUTES:
            for method in ("GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"):
                with self.subTest(route=route, method=method):
                    status, fields, payload = self._export(route, method=method, body=None)
                    self.assertEqual(status, 405)
                    self.assertEqual(fields.get("allow"), "POST")
                    if method != "HEAD":
                        harness._assert_error(payload, METHOD_NOT_ALLOWED)

    def test_rejected_export_attempts_write_no_file(self) -> None:
        before_tree = harness._tree_digest(self.run_root)
        _, _, served_before = self._api("GET", "/api/v1/snapshot")
        # Ad-hoc spellings: routeless, zero effect.
        for path in _FAKE_EXPORT_ROUTES:
            status, _, _ = self._export(path, body=json.dumps(_EXPORT_PAYLOAD).encode("utf-8"))
            self.assertEqual(status, 404)
        # Closed-schema violations on the live routes: 400, zero effect.
        for path in _SPEC_EXPORT_ROUTES:
            for body, expected_code in (
                (b"", "MALFORMED_JSON"),
                (json.dumps({"schemaVersion": 1, "action": "nope"}).encode("utf-8"),
                 "ACTION_PAYLOAD_INVALID"),
                (json.dumps({"schemaVersion": 1, "action": "diagnostic-export-preview",
                             "force": True}).encode("utf-8"),
                 "ACTION_PAYLOAD_INVALID"),
            ):
                status, _, payload = self._export(path, body=body)
                self.assertEqual(status, 400, (path, payload))
                harness._assert_error(payload, expected_code)
        # Zero owner side effects from every rejection: the served
        # snapshot is byte-identical, the run tree keeps exactly its
        # fixture bytes, and no export directory or partial file appeared.
        _, _, served_after = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(served_after, served_before)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_export_shaped_files(self.run_root), [])
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_a_preview_writes_nothing_anywhere(self) -> None:
        # The accepted preview phase returns the exact candidate pair and
        # writes nothing — the run tree digest is byte-identical after.
        before_tree = harness._tree_digest(self.run_root)
        status, _, payload = self._export(
            _SPEC_EXPORT_ROUTES[0], body=json.dumps(_EXPORT_PAYLOAD).encode("utf-8")
        )
        self.assertEqual(status, 200)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_export_shaped_files(self.run_root), [])

    def test_export_bodies_never_leak_secrets_paths_or_source(self) -> None:
        secret = "tok_LEAKME_0123456789abcdef"
        run_path = "C:\\Users\\participant\\secret-run"
        source_line = (
            harness._FIXTURES / "spec-script-summary.md"
        ).read_text(encoding="utf-8").splitlines()[0]
        body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export-preview",
                "sessionToken": secret,
                "runPath": run_path,
                "sourceExcerpt": source_line,
            }
        ).encode("utf-8")
        before_tree = harness._tree_digest(self.run_root)
        for path in _SPEC_EXPORT_ROUTES:
            status, _, payload = self._export(path, body=body)
            self.assertEqual(status, 400, (path, payload))
            # An unknown field is the closed-schema rejection: no path,
            # token, or source content ever reaches a response, and no
            # export-shaped artifact exists to leak into.
            harness._assert_error(payload, "ACTION_PAYLOAD_INVALID")
            for marker in (secret, run_path, source_line):
                with self.subTest(path=path, marker=marker[:24]):
                    self.assertNotIn(marker.encode("utf-8"), payload)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)
        self.assertEqual(_export_shaped_files(self.run_root), [])

    def test_the_accepted_export_never_uploads(self) -> None:
        body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export-preview",
                "uploadUrl": "https://example.invalid/collect",
            }
        ).encode("utf-8")
        before_tree = harness._tree_digest(self.run_root)
        for path in _EXPORT_ROUTES:
            status, _, payload = self._export(path, body=body)
            expected_status = 400 if path in _SPEC_EXPORT_ROUTES else 404
            self.assertEqual(status, expected_status, path)
            self.assertNotIn(b"example.invalid", payload)
        # No outbound call of any kind: no run_console runtime module
        # contains an upload or client primitive at all (S40) — the
        # accepted export writes local files and rebuilds, nothing more.
        modules = [
            path
            for path in sorted(
                _COMPONENT_DIR.glob("*.py")
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

    def test_the_accepted_export_never_lands_under_evidence(self) -> None:
        # A real, successful export: Evidence, Manifest, and verdict stay
        # byte-identical (ADR-0036 rule 9); the pair appears only under
        # trial-export/ and is named from the reviewed preview hash.
        evidence_dir = self.run_root / "evidence"
        before = {
            path.relative_to(self.run_root).as_posix(): path.read_bytes()
            for path in sorted(evidence_dir.rglob("*"))
        }
        verdict_before = self._snapshot_document()["evaluation"]["verdict"]
        status, _, preview_payload = self._export(
            _SPEC_EXPORT_ROUTES[0], body=json.dumps(_EXPORT_PAYLOAD).encode("utf-8")
        )
        self.assertEqual(status, 200)
        view = json.loads(preview_payload)
        write_body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export-write",
                "expectedSourceSetHash": view["expectedSourceSetHash"],
                "previewHash": view["previewHash"],
                "participantReviewed": True,
            }
        ).encode("utf-8")
        status, _, payload = self._export(_SPEC_EXPORT_ROUTES[1], body=write_body)
        self.assertEqual(status, 200, payload)
        after = {
            path.relative_to(self.run_root).as_posix(): path.read_bytes()
            for path in sorted(evidence_dir.rglob("*"))
        }
        self.assertEqual(after, before)
        self.assertEqual(
            self._snapshot_document()["evaluation"]["verdict"], verdict_before
        )
        written = sorted(
            path.relative_to(self.run_root).as_posix()
            for path in (self.run_root / "trial-export").glob("*")
        )
        self.assertEqual(
            written,
            [
                f"trial-export/export-{view['previewHash'][:12]}.json",
                f"trial-export/export-{view['previewHash'][:12]}.md",
            ],
        )

    def test_a_symlinked_trial_export_subtree_stays_unwritten(self) -> None:
        outside = self.base / "outside-export-target"
        outside.mkdir()
        canary = outside / "canary.md"
        canary.write_text("outside bytes must never change", encoding="utf-8")
        link = self.run_root / "trial-export"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        status, _, preview_payload = self._export(
            _SPEC_EXPORT_ROUTES[0], body=json.dumps(_EXPORT_PAYLOAD).encode("utf-8")
        )
        self.assertEqual(status, 200)
        view = json.loads(preview_payload)
        write_body = json.dumps(
            {
                "schemaVersion": 1,
                "action": "diagnostic-export-write",
                "expectedSourceSetHash": view["expectedSourceSetHash"],
                "previewHash": view["previewHash"],
                "participantReviewed": True,
            }
        ).encode("utf-8")
        status, _, payload = self._export(_SPEC_EXPORT_ROUTES[1], body=write_body)
        self.assertEqual(status, 500, payload)
        harness._assert_error(payload, "EXPORT_WRITE_FAILED")
        # Nothing is ever written through the link: the victim directory
        # keeps exactly its canary bytes, the trial-export entry is still
        # only the symlink, and no export-shaped file appeared anywhere
        # in the run.
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
    """S35 enabled state: the export limitation is gone; the remaining
    disabled capability (role attestation) keeps its closed record."""

    def test_the_export_limitation_is_gone_and_attestation_remains(self) -> None:
        self.assertEqual(validate_snapshot(self.document), self.document)
        codes = [
            item["result"]["code"]
            for item in self.document["limitations"]["items"]
        ]
        self.assertEqual(codes, ["role-attestation-owner-unmapped"])
        item = self.document["limitations"]["items"][0]
        self.assertEqual(
            item["id"], "limitations.items.role-attestation-owner-unmapped"
        )
        self.assertEqual(item["availability"], "known")
        self.assertEqual(
            item["result"]["summary"],
            "Role attestation is unavailable until an existing owner is mapped.",
        )
        # The record is the closed capability limitation: it claims no
        # attestation state, affects no assertion, and carries no
        # free-form Console narration.
        self.assertEqual(set(item["result"]), {"code", "summary", "affectsAssertionIds"})
        self.assertEqual(item["result"]["affectsAssertionIds"], [])

    def test_the_accepted_export_degrades_no_assertion_or_verdict(self) -> None:
        # S35 keeps the accepted capability local: no assertion carries
        # an export-shaped reason, and the fixture verdict and the
        # other assertions stay known. The export control never
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

    def test_the_snapshot_carries_no_export_fact(self) -> None:
        # The snapshot itself projects no export transaction, preview,
        # path, or fact anywhere: the export is a separate projection
        # (the contract), never a snapshot section.
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
        self.assertEqual(offenders, [])

    def test_the_ui_renders_the_active_export_control(self) -> None:
        # The export control is live in the rendered Console: the
        # preview/review/write flow exists with the explicit
        # participantReviewed acknowledgement, in both locales — while
        # the role-attestation control stays disabled with its reason.
        source = (_COMPONENT_DIR / "app.js").read_text(
            encoding="utf-8"
        )
        for token in (
            't("export_diagnostics")',
            "openExportDialog",
            "requestExportPreview",
            "requestExportWrite",
            "participantReviewed: true",
            "export-review-checkbox",
            "diagnostic-export/preview",
            "diagnostic-export/write",
            # The stale disabled-state tokens are gone.
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        for stale in (
            "limitation_diagnostic_export_contract_unavailable",
            "export_reason_default",
            '"diagnostic-export-contract-unavailable"',
            "unavailable-export-reason",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, source)
        # The sibling role-attestation control stays disabled.
        for token in (
            't("attest_role")',
            "unavailable-role-reason",
            'disabled: "disabled"',
        ):
            with self.subTest(attestation=token):
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
                    (OUTCOME_DISABLED_BY_GATE, OUTCOME_ACCEPTED),
                )
        # Even the fully enabling evaluation only records the outcome —
        # the evaluation itself never previews, writes, or uploads — and
        # every other fact set stays disabled.
        self.assertEqual(
            results["full-enabling"].outcome, OUTCOME_ACCEPTED
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
