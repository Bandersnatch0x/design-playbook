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
    records and returns the maximum ``<n>`` as an int, or None when
    ``preview/`` is missing or holds no round artifacts.

    Numeric — not lexicographic — so ``round-10`` > ``round-2``. The old
    ``sorted(glob("confirm-round-*.json"))`` ordering was the stale-confirm
    bug (issues 02 / 03): it let a historic round-1 confirm satisfy the gate
    while round-2 sat undecided.

    Exported for D-domain ``run_status`` to reuse as the single source of
    "which round is current"; do not re-sort confirm filenames there.
    """
    preview = run_root / "preview"
    if not preview.is_dir():
        return None
    try:
        entries = list(preview.iterdir())
    except OSError:
        return None
    nums = [
        n for n in (_round_from_name(p.name) for p in entries if p.is_file())
        if n is not None
    ]
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
            and confirm_data.get("floor_pass") is True)


def _confirm_round(path: Path, data: dict) -> int | None:
    """Round number of a confirm record: prefer the JSON ``round`` field,
    fall back to the ``confirm-round-<n>.json`` filename."""
    raw = data.get("round")
    if isinstance(raw, bool):  # bool is an int subtype; reject explicitly
        return _round_from_name(path.name)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw)
    return _round_from_name(path.name)


def _prototype_target(data: dict, run_root: Path) -> Path | None:
    """Resolve the prototype html a confirm record refers to.

    Uses the trusted-side-written ``prototype_path`` (e.g.
    ``preview/round-2.html``) and falls back to ``preview/round-<n>.html``
    derived from the record's round. Returns None if no prototype file is
    found **inside ``<run_root>/preview/``**.

    Containment (LOW-2): a ``prototype_path`` that resolves outside
    ``preview/`` (e.g. ``../secret.txt``) is treated as a missing prototype.
    The validator never hashes files outside ``preview/`` even when their
    recorded hash would match — the read side must mirror the preview/
    boundary the write side already enforces.
    """
    preview_root = (run_root / "preview").resolve()
    candidates: list[Path] = []
    ref = data.get("prototype_path")
    if isinstance(ref, str) and ref.strip():
        raw = Path(ref.strip())
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.append(run_root / raw)
            candidates.append(run_root / "preview" / raw.name)
    rnd = data.get("round")
    if isinstance(rnd, int) and not isinstance(rnd, bool):
        candidates.append(run_root / "preview" / f"round-{rnd}.html")
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            resolved = cand.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(preview_root)
        except ValueError:
            # Outside preview/ (LOW-2): treat as missing, never hash.
            continue
        return resolved
    return None


def _verify_prototype_hash(data: dict, run_root: Path) -> list[str]:
    """Verify ``prototype_html_hash`` when the confirm record carries one.

    The hash is written by the trusted-side ``confirm.py`` as
    ``sha256(<prototype bytes>)``; the validator (also trusted) recomputes it
    from the prototype html currently on disk and compares. The hash source
    stays on the trusted side and is never self-reported by the prototype
    (issue 02 / T01 trust boundary).

    Returns an empty list for legacy records that have no
    ``prototype_html_hash`` (skipped, not failed) so historic runs that
    predate the field are not broken.
    """
    stored = data.get("prototype_html_hash")
    if not isinstance(stored, str) or not stored:
        return []
    target = _prototype_target(data, run_root)
    if target is None:
        return [
            "G5 preview: confirmed record carries prototype_html_hash but "
            "its prototype html is missing"
        ]
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != stored:
        return [
            "G5 preview: confirmed record prototype_html_hash mismatch "
            "(prototype altered after confirm)"
        ]
    return []
