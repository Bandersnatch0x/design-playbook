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
    """Project findings into the historical readable validator report."""
    errs = list(errors)
    warns = list(warnings)
    lines: list[str] = []
    if errs:
        lines.append("RUN INVALID:")
        for item in errs:
            lines.append(f"  FAIL  {item.message}")
        for item in warns:
            lines.append(f"  WARN  {item.message}")
    else:
        lines.append("RUN OK: artifacts satisfy the deterministic seam")
        for item in warns:
            lines.append(f"  WARN  {item.message}")
    return "\n".join(lines) + ("\n" if lines else "")


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
