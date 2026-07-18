"""ADR-0008 floor logic + confirm/log records + prototype target resolution.

Sibling module split from server.py; behavior unchanged. Holds the
feedback-floor check, confirm JSON + log writers, prototype path helpers,
and the ``--self-check`` floor cases.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from util import _now_iso


def _preview_dir_for(path: Path | None) -> Path:
    if path is not None:
        return path.parent
    scratch = Path.cwd() / ".scratch" / "preview-adapter" / "preview"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch



def _ensure_prototype(path_arg: str | None, html: str | None, round_n: int,
                      preview_dir: Path) -> Path:
    if path_arg:
        p = Path(path_arg)
        if not p.is_file():
            raise ValueError(f"prototype path does not exist: {path_arg}")
        return p
    if not html:
        raise ValueError("path or html is required")
    preview_dir.mkdir(parents=True, exist_ok=True)
    target = preview_dir / f"round-{round_n}.html"
    target.write_text(html, encoding="utf-8")
    return target



def _append_log(preview_dir: Path, *, round_n: int, report_ref: str,
                feedback: str, aborted: bool, selected: list[str],
                anchors: list[dict[str, Any]] | None = None,
                floor_pass: bool | None = None,
                floor_failure: str = "") -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    log_path = preview_dir / "log.md"
    if not log_path.is_file():
        log_path.write_text("# preview log\n", encoding="utf-8")
    block = (
        f"\n## round {round_n}\n"
        f"- report_ref: {report_ref}\n"
        f"- timestamp: {_now_iso()}\n"
        f"- feedback: {feedback or ''}\n"
        f"- selected: {', '.join(selected) if selected else ''}\n"
        f"- aborted: {str(aborted).lower()}\n"
        f"- anchors: {len(anchors or [])}\n"
    )
    if floor_pass is not None:
        block += f"- floor_pass: {str(floor_pass).lower()}\n"
        if floor_failure:
            block += f"- floor_failure: {floor_failure}\n"
    if anchors:
        for i, a in enumerate(anchors, 1):
            sel = a.get("selector") or ""
            note = a.get("comment") or ""
            label = a.get("label") or ""
            block += f"  - [{i}] {sel} | {label} | {note}\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(block)



def _write_confirm(preview_dir: Path, *, round_n: int, report_ref: str,
                   selected: list[str], feedback: str,
                   prototype: Path,
                   confirmed: bool, floor_pass: bool,
                   floor_failure: str = "") -> Path:
    digest = hashlib.sha256(prototype.read_bytes()).hexdigest()
    record = {
        "round": round_n,
        "report_ref": report_ref,
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": selected,
        "feedback": feedback,
        "timestamp": _now_iso(),
        "prototype_path": f"preview/{prototype.name}",
        "prototype_html_hash": digest,
    }
    if floor_failure:
        record["floor_failure"] = floor_failure
    out = preview_dir / f"confirm-round-{round_n}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return out



def _check_feedback_floor(feedback: str,
                          anchors: list[dict[str, Any]]) -> tuple[bool, str]:
    """ADR-0008 preview feedback floor (structural, machine-checkable).

    Passes when: feedback is non-empty (OR >=1 anchor present) AS the trigger,
    AND every present anchor carries a non-empty selector AND a non-empty
    comment. So a non-empty feedback with an incomplete anchor still fails.
    Deliberately structural; semantic quality is left to ui-evaluator (G6).
    Returns (floor_pass, floor_failure_reason).
    """
    feedback = (feedback or "").strip()
    trigger = bool(feedback) or bool(anchors)
    if not trigger:
        return False, "confirm with no substantive feedback: empty feedback and no anchor"
    if anchors:
        for a in anchors:
            if not isinstance(a, dict):
                return False, "anchor is not an object"
            sel = str(a.get("selector") or "").strip()
            note = str(a.get("comment") or "").strip()
            if not sel or not note:
                return False, (
                    "anchor missing non-empty selector and comment: "
                    f"selector={sel!r} comment={note!r}")
    return True, ""



def _self_check_floor() -> None:
    """ADR-0008 floor branch logic self-check (ponytail: one runnable check)."""
    cases = [
        ("empty + no anchors", "", [], False),
        ("whitespace-only feedback", "   \n  ", [], False),
        ("non-empty feedback no anchors", "ok", [], True),
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
    ]
    for label, fb, anc, want in cases:
        got, _ = _check_feedback_floor(fb, anc)
        assert got == want, f"{label}: want {want}, got {got}"
    print("FLOOR SELF-CHECK PASSED")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check_floor()
    else:
        serve()

