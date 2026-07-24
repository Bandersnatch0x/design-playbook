"""G5 prototype-integrity helpers, split from validate_run.py (review H4).

High-coherence cluster of functions that decide *which preview round is
current* and *whether a confirm record is usable* for the G5 gate and for
the D-domain state machine (``scripts/run_status.py``). They share one
trust boundary — the trusted side writes ``confirm-round-<n>.json`` and
``prototype_html_hash``; the validator (also trusted) re-derives them from
disk (issue 02 / T01). Keeping them together in a sibling module lets both
``validate_run.check_preview`` and ``run_status`` depend on the same code
without re-sorting confirm filenames or re-deriving the confirmed+floor
rule (issue 03).

Sibling-import mechanics: this directory (``packages/design-playbook/
scripts/``) is not a package (no ``__init__.py``). ``validate_run.py``
imports it via ``sys.path`` — the same mechanism ``run_status.py`` already
uses to import ``validate_run``. When ``validate_run.py`` runs as a script
the interpreter puts this directory on ``sys.path[0]`` automatically, so
the bare ``import _preview_integrity`` resolves in both the subprocess and
the imported-module cases.
"""
import hashlib
import re
from pathlib import Path


def _round_from_name(name: str) -> int | None:
    """Extract the numeric round from a ``round-<n>.html`` or
    ``confirm-round-<n>.json`` filename. Returns None if it does not match."""
    match = re.match(r"^(?:confirm-)?round-(\d+)\.(?:html|json)$", name, re.I)
    return int(match.group(1)) if match else None


def latest_numeric_round(run_root: Path) -> int | None:
    """Return the highest numeric round seen under ``<run_root>/preview/``.

    Scans both ``round-<n>.html`` prototypes and ``confirm-round-<n>.json``
    records, plus round headings in ``preview/log.md`` (deletion-rollback
    protection). Returns the maximum ``<n>`` as an int, or None when
    ``preview/`` is missing or holds no round artifacts.

    Numeric — not lexicographic — so ``round-10`` > ``round-2``. The old
    ``sorted(glob("confirm-round-*.json"))`` ordering was the stale-confirm
    bug (issues 02 / 03): it let a historic round-1 confirm satisfy the gate
    while round-2 sat undecided.

    Exported for D-domain ``run_status`` to reuse as the single source of
    "which round is current"; do not re-sort confirm filenames there.
    """
    import re

    preview = run_root / "preview"
    if not preview.is_dir():
        return None

    nums: list[int] = []

    # Scan filesystem artifacts
    try:
        entries = list(preview.iterdir())
    except OSError:
        entries = []
    for p in entries:
        if p.is_file():
            n = _round_from_name(p.name)
            if n is not None:
                nums.append(n)

    # Scan log.md for round headings (format: "## round <n>")
    log_path = preview / "log.md"
    try:
        if log_path.is_file():
            log_content = log_path.read_text(encoding="utf-8")
            nums.extend(
                int(m.group(1))
                for m in re.finditer(r"^## round (\d+)", log_content, re.MULTILINE)
            )
    except OSError:
        pass

    return max(nums) if nums else None


def is_confirmed_valid(confirm_data: object) -> bool:
    """True iff a confirm record is a valid (decided-positive) confirmation.

    Validity = ``confirmed is True`` AND ``floor_pass is True`` (ADR-0008
    feedback floor). Accepts the parsed JSON value of any type; non-dict →
    False.

    Exported as the single judgment shared by ``check_preview`` (G5) and
    D-domain ``run_status`` so the validator and the state machine cannot
    drift on what counts as a usable confirm (issue 03).
    """
    if not isinstance(confirm_data, dict):
        return False
    return (confirm_data.get("confirmed") is True
            and confirm_data.get("floor_pass") is True
            and confirm_data.get("aborted") is not True)


def _confirm_round(path: Path, data: dict) -> int | None:
    """Round number of a confirm record: prefer the JSON ``round`` field,
    fall back to the ``confirm-round-<n>.json`` filename.

    If both the filename round and the JSON ``round`` field exist, they must
    be equal (round互证). Otherwise the record is excluded from current.
    """
    filename_round = _round_from_name(path.name)
    raw = data.get("round")
    json_round: int | None = None
    if isinstance(raw, bool):  # bool is an int subtype; reject explicitly
        json_round = None
    elif isinstance(raw, int):
        json_round = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        json_round = int(raw)

    # Round互证: if both exist, they must match
    if filename_round is not None and json_round is not None:
        if filename_round != json_round:
            return None  # Mismatch: exclude from current
    # Prefer JSON round, fallback to filename
    return json_round if json_round is not None else filename_round


def _prototype_target(data: dict, run_root: Path) -> Path | None:
    """Resolve the prototype html a confirm record refers to.

    The target is **always** ``preview/round-<latest>.html`` derived from the
    latest numeric round (never from the record's ``prototype_path`` field).
    The ``prototype_path`` field is kept only as metadata (LOW-2 containment).

    Returns None if the target file is missing or outside ``preview/``.
    """
    preview_root = (run_root / "preview").resolve()
    latest = latest_numeric_round(run_root)
    if latest is None:
        return None
    target = run_root / "preview" / f"round-{latest}.html"
    try:
        if not target.is_file():
            return None
        resolved = target.resolve()
        resolved.relative_to(preview_root)  # Containment (LOW-2)
        return resolved
    except (OSError, ValueError):
        return None


def prototype_html_digest(raw: bytes) -> str:
    """SHA-256 of prototype bytes with newlines normalized to LF.

    Windows ``core.autocrlf`` rewrites working-tree bytes on checkout; a raw
    digest then disagrees between the machine that wrote the confirm record
    and a Linux CI runner validating the same git blob. Line-ending noise is
    not a prototype content change for G5 integrity (issue 02 / T01).

    Must stay in lockstep with ``mcp/preview/confirm.prototype_html_digest``.
    """
    return hashlib.sha256(
        raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()


def _verify_prototype_hash(data: dict, run_root: Path) -> list[str]:
    """Verify ``prototype_html_hash`` when the confirm record carries one.

    The hash is written by the trusted-side ``confirm.py`` as
    ``prototype_html_digest(<prototype bytes>)`` (LF-normalized SHA-256);
    the validator (also trusted) recomputes it from the prototype html
    currently on disk and compares. The hash source stays on the trusted
    side and is never self-reported by the prototype (issue 02 / T01).

    Missing ``prototype_html_hash`` FAILs (since 0.4.4+ adapter always
    writes it; absence indicates hand-written or pre-0.4.4 records).
    """
    stored = data.get("prototype_html_hash")
    if not isinstance(stored, str) or not stored:
        return [
            "G5 preview: confirmed record missing prototype_html_hash "
            "(pre-0.4.4 record or hand-written — re-run preview*)"
        ]
    target = _prototype_target(data, run_root)
    if target is None:
        return [
            "G5 preview: confirmed record carries prototype_html_hash but "
            "its prototype html is missing"
        ]
    digest = prototype_html_digest(target.read_bytes())
    if digest != stored:
        return [
            "G5 preview: confirmed record prototype_html_hash mismatch "
            "(prototype altered after confirm)"
        ]
    return []
