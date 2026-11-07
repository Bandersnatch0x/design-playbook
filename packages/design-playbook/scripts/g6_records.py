"""Shared G6 ledger, manifest, and artifact-fact helpers (ADR-0023, ADR-0025).

``ledger_observed`` is the G6 projection over the single Evidence ledger
syntax-facts module (``mcp.evidence.ledger_syntax``): it projects the
``(criterion, leading-artifact-token)`` pairs G6 consumes from the parsed
rows. ``manifest_entries`` reads the on-disk manifest.
``collect_evidence_artifacts`` freezes one immutable fact per explicitly
referenced artifact: its canonical reference, containment outcome, actual
SHA-256, and byte count. The facts are collected once and consume no file
bytes afterwards; whether a reference is valid evidence remains G6 policy.
Both the hard evidence gate and soft warnings consume these projections;
neither policy module owns ledger parsing - the syntax facts come from one
deep module (ADR-0025).
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from design_playbook.mcp.evidence import containment
from design_playbook.mcp.evidence.ledger_syntax import LedgerFacts, parse_ledger
from design_playbook.scripts.stages import EVIDENCE_PREFIX


def ledger_observed(
    text: str,
    ledger_facts: LedgerFacts | None = None,
) -> list[tuple[str, str]]:
    """Return ``(criterion, observed-token)`` pairs for each contributing row.

    Projects the G6 view from the single ledger syntax-facts module
    (ADR-0025). The criterion is the first whitespace-delimited token of the
    row's first ``criterion`` value; the observed token is the derived leading
    artifact token of the row's first ``observed`` value. A row contributes a
    pair only when both are non-empty - matching the historical parser's
    ``^criterion:\\s*(\\S+)`` and ``^observed:\\s*(.+)`` row-inclusion rule.

    Trailing commentary after the token (whitespace or a (full/half-width)
    paren / comma / colon) is tolerated, so authors can annotate ``evidence/``
    rows without a false-positive G6 fail (issue 03). Free-text observed is
    unaffected - G6 only checks ``evidence/`` rows, and a leading token
    starting with ``evidence/`` never appears in free text.

    Keep the tolerated separators in sync with
    ``mcp/evidence/ledger_syntax.py`` and skills/ui-evaluator/SKILL.md (which
    teaches authors what punctuation may follow the artifact path).
    """
    pairs: list[tuple[str, str]] = []
    facts = ledger_facts or parse_ledger(text)
    for row in facts.rows:
        criterion_values = row.values("criterion")
        if not criterion_values or not criterion_values[0]:
            continue
        if not row.raw_observed:
            continue
        criterion_token = criterion_values[0].split()[0]
        pairs.append((criterion_token, row.artifact_token))
    return pairs


def manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read evidence/manifest.jsonl as one dict per non-empty valid line.

    The run-facts adapter is imported here rather than at module scope:
    ``run_facts`` imports this module's artifact-fact collector, so a
    top-level back-import would close a cycle.
    """
    from design_playbook.scripts.run_facts import capture_run_facts

    return list(capture_run_facts(
        evidence_dir=evidence_dir, collect_evidence=False).manifest_entries)


# A fact's detail is diagnostic text, not path authority; keep it short.
_DETAIL_LIMIT = 200
# Fixed digest chunk: memory stays bounded regardless of artifact size.
_DIGEST_CHUNK_BYTES = 64 * 1024
# Stable read-failure code beside the containment owner's reason codes.
REASON_UNREADABLE = "unreadable"


@dataclass(frozen=True)
class EvidenceArtifactFact:
    """One referenced artifact's captured containment and byte facts.

    ``reference`` is the canonical run-relative token (``evidence/<leaf>``);
    ``artifact`` is the manifest's evidence-relative leaf, or ``None`` when the
    token never had that shape. ``reason`` is empty on success and one stable
    containment or read code otherwise. No path and no file bytes are kept.
    """

    reference: str
    artifact: str | None
    sha256: str | None = None
    size: int | None = None
    reason: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.reason == ""


def normalise_evidence_reference(reference: str) -> tuple[str, str | None]:
    """Split one reference into (canonical token, manifest leaf).

    The leading ``evidence/`` segment is matched case-insensitively and
    rewritten once to the canonical spelling, matching the write boundary and
    the existing G6 read path. A token without that prefix keeps its text and
    has no manifest leaf; containment still decides whether it may resolve.
    """
    if reference.casefold().startswith(EVIDENCE_PREFIX):
        leaf = reference[len(EVIDENCE_PREFIX):]
        return EVIDENCE_PREFIX + leaf, leaf
    return reference, None


def _digest_stream(stream) -> tuple[str, int]:
    """Digest a binary stream in fixed-size chunks without keeping its bytes."""
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(_DIGEST_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _open_binary(path: Path):
    """One seam for the byte read; tests use it to prove a single read."""
    return path.open("rb")


def _artifact_fact(
    canonical: str, leaf: str | None, run_root: Path
) -> EvidenceArtifactFact:
    result = containment.read_artifact(canonical, run_root)
    if not result.ok:
        return EvidenceArtifactFact(
            reference=canonical, artifact=leaf, reason=result.reason)
    assert result.path is not None
    try:
        with _open_binary(result.path) as stream:
            digest, size = _digest_stream(stream)
    except OSError as error:
        return EvidenceArtifactFact(
            reference=canonical, artifact=leaf, reason=REASON_UNREADABLE,
            detail=str(error)[:_DETAIL_LIMIT])
    return EvidenceArtifactFact(
        reference=canonical, artifact=leaf, sha256=digest, size=size)


def collect_evidence_artifacts(
    references: Iterable[str], *, run_root: Path
) -> tuple[EvidenceArtifactFact, ...]:
    """Freeze one fact per unique referenced artifact under an explicit root.

    Only the handed-in references are resolved and read; nothing scans the
    manifest, the evidence directory, or the filesystem. Deduplication is by
    canonical token, so the same reference (including a case-variant
    ``EVIDENCE/`` prefix) is read once. ``run_root`` is the only authority
    root: a caller holding an evidence directory passes its parent, and no cwd
    or manifest path widens it. Files that containment rejects are recorded as
    facts without a read.
    """
    facts: list[EvidenceArtifactFact] = []
    seen: set[str] = set()
    for reference in references:
        canonical, leaf = normalise_evidence_reference(reference)
        if canonical in seen:
            continue
        seen.add(canonical)
        facts.append(_artifact_fact(canonical, leaf, run_root))
    return tuple(facts)


def evidence_authority(
    run_root: Path | None, evidence_dir: Path | None,
) -> Path | None:
    """The one explicit root artifact references may be read under.

    ``run_root`` wins; an explicit ``evidence_dir`` contributes only its
    parent. When both are named they must agree - the manifest root and the
    file root never split. Any other source (``state.project_root``, a manifest
    path, cwd) is not authority; without a root the references stay
    uncollected. Both I/O seams (capture and the compatibility gate) share this
    one decision so neither can read a manifest under one root and bytes under
    another.
    """
    if run_root is not None:
        if evidence_dir is not None:
            try:
                if evidence_dir.resolve() != (run_root / "evidence").resolve():
                    return None
            except OSError:
                return None
        return run_root
    if evidence_dir is not None:
        return evidence_dir.parent
    return None


def binding_instant(ts: object) -> datetime | None:
    """Parse one manifest ``ts`` into an offset-aware instant.

    ``None`` means the value is unusable as an ordering fact: not a string,
    blank, not ISO-8601, or naive. A stamp without an offset names no instant
    of its own - it would only be comparable through the reader's clock - so
    it is rejected rather than guessed. ``Z``/``z`` normalize to ``+00:00``
    and are the only offsets rewritten; everything else round-trips through
    ``datetime.fromisoformat``.
    """
    if not isinstance(ts, str):
        return None
    text = ts.strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def latest_by_instant(entries: list[dict]) -> dict | None:
    """The entry with the greatest parsable ``ts``; ``None`` when any is not.

    Ordering is by real instant, so mixed offsets (``Z`` vs ``+08:00``) pick
    the later capture rather than the lexicographically larger string.
    ``None`` covers an empty list and any entry whose ``ts`` is unusable: the
    caller owns whether that is a hard error (the G6 gate) or a reason to
    stay quiet (soft warnings).
    """
    stamped: list[tuple[datetime, dict]] = []
    for entry in entries:
        instant = binding_instant(entry.get("ts"))
        if instant is None:
            return None
        stamped.append((instant, entry))
    if not stamped:
        return None
    return max(stamped, key=lambda pair: pair[0])[1]
