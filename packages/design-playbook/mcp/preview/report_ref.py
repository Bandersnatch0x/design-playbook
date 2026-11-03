"""One resolution rule for a Preview decision's ``report_ref`` (G5 + transaction).

A confirmed record binds a ``report_ref``; the G5 gate checks it against
``--decision-report`` and the preview transaction derives the criteria the
operator reviews. Resolving it in two places meant the same run could show
empty criteria in the shell while G5 passed. This module owns the candidate
order and the ``spec.md`` derivation both callers share.
"""
from __future__ import annotations

from pathlib import Path

from design_playbook.scripts.g1_spec import (
    SpecificationProjectionError,
    project_specification,
)


def resolve_report_path(
    ref: str, *, preview_dir: Path, decision_report: Path | None = None
) -> Path | None:
    """The decision report a ref names, or ``None``.

    Relative refs are tried against the run root (the parent of ``preview/``),
    the preview directory itself, the decision report's directory, and the
    current directory -- in that order, so every caller resolves the same run
    the same way.
    """
    raw = Path(ref)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(preview_dir.parent / raw)
        candidates.append(preview_dir / raw)
        if decision_report is not None:
            candidates.append(decision_report.parent / raw)
        candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def spec_path_for(report_path: Path) -> Path:
    """The specification a decision report was written against."""
    return report_path.parent / "spec.md"


def criteria_from_report_ref(
    ref: str, *, preview_dir: Path, decision_report: Path | None = None
) -> list[dict[str, str]]:
    """The L6 criteria the operator reviews, or ``[]`` when the run cannot say."""
    report_path = resolve_report_path(
        ref, preview_dir=preview_dir, decision_report=decision_report
    )
    if report_path is None:
        return []
    try:
        spec_path = spec_path_for(report_path)
        if not spec_path.is_file():
            return []
        projection = project_specification(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SpecificationProjectionError):
        return []
    return [
        {"id": item.criterion_id, "title": item.title or "", "then": item.then}
        for item in projection.criteria
    ]
