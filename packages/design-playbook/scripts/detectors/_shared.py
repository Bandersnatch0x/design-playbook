"""Input coercion shared by the machine detectors (T-144).

Detector payloads come from a capture, so every field is validated here and a
malformed payload raises :class:`DetectorInputError` — a broken capture must
not read as a clean zero-finding pass.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class DetectorInputError(ValueError):
    """The payload does not match the detector's declared input contract."""


def as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DetectorInputError(
            f"{field}: expected an object, got {type(value).__name__}"
        )
    return value


def as_rows(value: Any, field: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DetectorInputError(
            f"{field}: expected a list, got {type(value).__name__}"
        )
    return list(value)


def as_text(container: Mapping[str, Any], key: str, field: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DetectorInputError(f"{field}: {key} must be a non-empty string")
    return value.strip()


def as_number(
        container: Mapping[str, Any],
        key: str,
        field: str,
        *,
        minimum: float | None = None,
) -> float:
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DetectorInputError(f"{field}: {key} must be a number")
    if minimum is not None and value < minimum:
        raise DetectorInputError(f"{field}: {key} must be >= {minimum}")
    return float(value)


def as_bool(container: Mapping[str, Any], key: str, field: str) -> bool:
    value = container.get(key, False)
    if not isinstance(value, bool):
        raise DetectorInputError(f"{field}: {key} must be a boolean")
    return value


def finding(rule_id: str, message: str, **evidence: Any) -> dict[str, Any]:
    """One detector finding (severity is the registry entry's, not ours)."""
    return {"ruleId": rule_id, "message": message, "evidence": evidence}
