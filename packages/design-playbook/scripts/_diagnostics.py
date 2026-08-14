"""Stable structured diagnostics for validate_run (vNext ticket 02).

One finding model feeds both text and JSON projections. Rule IDs are stable
identifiers independent from display prose; text keeps the human-readable
``message`` field so existing FAIL line consumers stay valid.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
OUTPUT_FORMATS = frozenset({"text", "json"})


@dataclass(frozen=True)
class Finding:
    """One gate diagnostic with machine fields plus a human message."""

    rule_id: str
    severity: str
    owner: str
    expected: str
    actual: str
    repair: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finding(
        rule_id: str,
        message: str,
        *,
        owner: str,
        expected: str,
        actual: str,
        repair: str,
        severity: str = SEVERITY_ERROR) -> Finding:
    """Build a finding; ``message`` is the text-projection line body."""
    return Finding(
        rule_id=rule_id,
        severity=severity,
        owner=owner,
        expected=expected,
        actual=actual,
        repair=repair,
        message=message,
    )


def render_text(errors: Iterable[Finding], warnings: Iterable[Finding]) -> str:
    """Project findings into the historical readable validator report.

    The historical ``FAIL``/``WARN`` message lines are byte-identical to the
    pre-structure projection; when a finding carries a ``repair`` guidance a
    continuation line is appended below it (review advisory, R4) so the
    default text face stays as actionable as ``--format json`` without
    changing any existing line's format.
    """
    errs = list(errors)
    warns = list(warnings)
    lines: list[str] = []
    if errs:
        lines.append("RUN INVALID:")
        lines.extend(_text_lines(errs, "FAIL"))
        lines.extend(_text_lines(warns, "WARN"))
    else:
        lines.append("RUN OK: artifacts satisfy the deterministic seam")
        lines.extend(_text_lines(warns, "WARN"))
    return "\n".join(lines) + ("\n" if lines else "")


def _text_lines(items: Iterable[Finding], label: str) -> list[str]:
    """One ``FAIL``/``WARN`` line per finding, plus a fix line when set.

    The fix line indents to the message column (the 8-character
    ``"  FAIL  "`` prefix) so consumers filtering on line prefixes or the
    historical message substrings are unaffected.
    """
    out: list[str] = []
    for item in items:
        out.append(f"  {label}  {item.message}")
        if item.repair:
            out.append(f"        fix:  {item.repair}")
    return out


def render_json(errors: Iterable[Finding], warnings: Iterable[Finding]) -> str:
    """Project findings as a JSON list (errors first, then warnings)."""
    payload = [item.to_dict() for item in list(errors) + list(warnings)]
    return json_dumps(payload) + "\n"


def json_dumps(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def usage_finding(message: str) -> Finding:
    """Operational/usage diagnostic (exit 2 path)."""
    return finding(
        "USAGE.invalid_format",
        message,
        owner="validate_run.py",
        expected="--format text|json",
        actual=message,
        repair="Pass --format text or --format json",
    )
