"""Preview request preparation: criteria, prototype resolution, floor self-check.

These helpers turn a preview request into the inputs the transaction needs (the
criteria list, the prototype path and its digest) and carry the ADR-0008 floor
self-check. None of them touches a lock or a ledger file, so they live apart
from the transaction that owns persistence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from design_playbook.mcp.preview.integrity import (
    evaluate_feedback_floor,
    prototype_html_digest,
    prototype_name,
)
from design_playbook.mcp.preview.visual_batch import has_effective_visual_edits
from design_playbook.scripts.g1_spec import (
    SpecificationProjectionError,
    project_specification,
)


def _preview_dir_for(path: Path | None) -> Path:
    if path is not None:
        return path.parent
    scratch = Path.cwd() / ".scratch" / "preview-adapter" / "preview"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def _criteria_from_report_ref(report_ref: str) -> list[dict[str, str]]:
    try:
        report_path = Path(report_ref).expanduser().resolve()
        if not report_path.is_file():
            return []
        spec_path = report_path.parent / "spec.md"
        if not spec_path.is_file():
            return []
        projection = project_specification(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SpecificationProjectionError):
        return []
    return [
        {"id": item.criterion_id, "title": item.title or "", "then": item.then}
        for item in projection.criteria
    ]


def _criteria_review_from_submission(
    submission: dict[str, Any], criteria: list[dict[str, str]]
) -> list[dict[str, Any]]:
    if not criteria:
        return []
    raw = submission.get("criteria_review")
    posted: dict[str, bool] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            criterion_id = str(item.get("id") or "").strip()
            if criterion_id:
                posted[criterion_id] = item.get("checked") is True
    return [
        {"id": item["id"], "title": item["title"], "checked": posted.get(item["id"], False)}
        for item in criteria
    ]


def _resolve_prototype(
    path_arg: str | None, html: str | None, round_n: int,
    preview_dir: Path,
) -> tuple[Path, str]:
    """Resolve prototype source to a path and compute its digest.

    Single source for prototype resolution: path mode reads the file, html
    mode computes from inline bytes. Returns (prototype_path, digest) so
    callers can build the binding without re-reading. Does NOT write the
    html file — that is _ensure_prototype's job.
    """
    if path_arg:
        prototype = Path(path_arg)
        if not prototype.is_file():
            raise ValueError(f"prototype path does not exist: {path_arg}")
        return prototype, prototype_html_digest(prototype.read_bytes())
    if not html:
        raise ValueError("path or html is required")
    return (
        preview_dir / prototype_name(round_n),
        prototype_html_digest(html.encode("utf-8")),
    )


def _ensure_prototype(path_arg: str | None, html: str | None, round_n: int,
                      preview_dir: Path) -> Path:
    """Resolve and materialize the prototype file on disk."""
    prototype, _ = _resolve_prototype(path_arg, html, round_n, preview_dir)
    if not path_arg:
        preview_dir.mkdir(parents=True, exist_ok=True)
        prototype.write_text(html, encoding="utf-8")
    return prototype


def _self_check(condition: bool, message: str) -> None:
    """Self-check assertion that still fires under `python -O`.

    A bare `assert` is compiled out under -O, so a self-check built from one
    reports success on a broken floor without ever running the comparison.
    """
    if not condition:
        raise AssertionError(message)


def self_check_floor() -> None:
    """ADR-0008 floor branch logic self-check (ponytail: one runnable check)."""
    cases = [
        ("empty + no anchors", "", [], False),
        ("whitespace-only feedback", "   \n  ", [], False),
        ("short feedback passes (structural floor)", "ok", [], True),
        ("short CJK feedback passes ('太挤了' is substantive)", "太挤了", [], True),
        ("'安师大' passes floor; semantic junk is G6's job (ADR-0008)", "安师大", [], True),
        ("longer feedback passes", "fix it", [], True),
        ("anchor with comment", "", [{"selector": "h2", "comment": "x"}], True),
        ("anchor no comment (0015 garbage)", "",
         [{"selector": "h2", "comment": ""}], False),
        ("anchor empty selector", "",
         [{"selector": "", "comment": "x"}], False),
        ("non-dict anchor", "", ["not-a-dict"], False),
        ("feedback + incomplete anchor still fails", "ok",
         [{"selector": "h2", "comment": ""}], False),
        ("two anchors one incomplete fails", "",
         [{"selector": "h2", "comment": "x"}, {"selector": "p", "comment": ""}], False),
        ("two anchors both complete passes", "",
         [{"selector": "h2", "comment": "x"}, {"selector": "p", "comment": "y"}], True),
        ("short feedback + good anchor passes", "hi",
         [{"selector": "h2", "comment": "x"}], True),
    ]
    for label, fb, anc, want in cases:
        got = evaluate_feedback_floor(fb, anc).passed
        _self_check(got == want, f"{label}: want {want}, got {got}")
    # The 2026-10-08 amendment added a third trigger, a validated visual batch
    # whose net effect changes a value. Every case above calls the floor with
    # has_visual_edits defaulted to False, so the branch the amendment added was
    # not covered by this check at all.
    #
    # Only one case below is sensitive to the flag. The floor returns before it
    # consults the flag whenever an anchor is incomplete or absent, so a case that
    # pairs the flag with an incomplete anchor asserts the anchor rule again and
    # covers nothing new; those live in the list above instead.
    edit_cases = [
        ("validated edits alone pass", "", [], True),
    ]
    for label, fb, anc, want in edit_cases:
        got = evaluate_feedback_floor(fb, anc, has_visual_edits=True).passed
        _self_check(got == want, f"{label} (with edits): want {want}, got {got}")
    # The flag itself is decided elsewhere, so the substance of the amendment is
    # only checked if that decision is checked. It is passed as a literal above.
    from design_playbook.mcp.preview.visual_batch import normalize_visual_batch
    for label, edits, want in [
        ("a real change counts",
         [{"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"}], True),
        ("a no-op does not count",
         [{"locator": "#a", "property": "color", "oldValue": "red", "newValue": "red"}], False),
        ("a chain undone to its baseline does not count", [
            {"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"},
            {"locator": "#a", "property": "color", "oldValue": "red", "newValue": ""},
        ], False),
        ("a change and its reversal under two viewport labels do not count", [
            {"kind": "style", "viewport": "desktop", "locator": "#a",
             "property": "color", "oldValue": "", "newValue": "red"},
            {"kind": "style", "viewport": "mobile", "locator": "#a",
             "property": "color", "oldValue": "red", "newValue": ""},
        ], False),
        ("one surviving change beside an undone chain counts", [
            {"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"},
            {"locator": "#a", "property": "color", "oldValue": "red", "newValue": ""},
            {"locator": "#a", "property": "padding", "oldValue": "8px", "newValue": "16px"},
        ], True),
        # 2026-10-09: only the parent shell's own edit is evidence. The
        # prototype shares the bridge window, so what it reports is not proof a
        # human reviewed anything, and neither is an agent's own tool call.
        ("a frame gesture alone does not count",
         [{"source": "frame", "locator": "#a", "property": "color",
           "oldValue": "", "newValue": "red"}], False),
        ("an agent tool edit alone does not count",
         [{"source": "agent", "locator": "#a", "property": "color",
           "oldValue": "", "newValue": "red"}], False),
        ("a case-only CSS value does not count",
         [{"kind": "style", "locator": "#a", "property": "color",
           "oldValue": "red", "newValue": "RED"}], False),
        ("a kind-only round trip does not count", [
            {"kind": "style", "locator": "#a", "property": "padding",
             "oldValue": "8px", "newValue": "16px"},
            {"kind": "layout", "locator": "#a", "property": "padding",
             "oldValue": "16px", "newValue": "8px"},
        ], False),
    ]:
        # These cases are about the net effect; the provenance cases declare
        # their own source, so the rest default to the reviewer's own shell.
        edits = [{"source": "shell", **edit} for edit in edits]
        batch = normalize_visual_batch({"edits": edits}, source_hash="self-check")
        got = has_effective_visual_edits(batch)
        _self_check(got == want, f"{label}: want {want}, got {got}")
    # An edit with no declared provenance is not attributable, and the shell
    # always declares one, so it cannot be evidence either. Asserted outside the
    # loop because that loop defaults a missing source to the shell.
    unattributed = normalize_visual_batch(
        {"edits": [{"kind": "style", "locator": "#a", "property": "color",
                    "oldValue": "", "newValue": "red"}]}, source_hash="self-check")
    _self_check(not has_effective_visual_edits(unattributed),
                "an edit with no declared source must not count")
    print("FLOOR SELF-CHECK PASSED")
