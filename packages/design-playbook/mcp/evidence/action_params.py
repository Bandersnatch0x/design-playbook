"""Pure action-parameter facts shared by preflight and capture runtime.

Mirrors execute_capture_plan handler contracts: empty fill/type/select values
and wait ms=0 are legal; missing required keys and wrong types are not.
No Playwright and no filesystem I/O.

Action verb dialect is owned HERE, not duplicated by the callers: ``do`` is
canonicalized via :func:`normalize_action_do` (strip + lower) so ``"Click"``,
``" click "`` and ``"FILL"`` resolve to the same handler as ``"click"``. Both
preflight and runtime feed the raw action through this one normalizer before
checking ``KNOWN_DOS`` or parameter rules — no second dialect (FIX-03).

The ``index`` argument is 0-based everywhere (``actions[0]``); preflight and
runtime emit identical labels for the same position (FIX-03).
"""
from __future__ import annotations

from typing import Any

KNOWN_DOS = frozenset(
    {
        "click",
        "fill",
        "type",
        "press",
        "wait_for_selector",
        "wait_for_state",
        "wait",
        "sleep",
        "select_option",
    }
)


def normalize_action_do(do: object) -> str:
    """Canonical action verb: strip surrounding whitespace and lowercase.

    Shared by preflight and runtime so ``"Click"``, ``" click "`` and
    ``"FILL"`` all hit the same handler as ``"click"``. Returns ``""`` for a
    non-string or blank value so callers can detect the missing/empty-do case
    through one falsy check instead of re-implementing strip/lower.
    """
    if not isinstance(do, str):
        return ""
    return do.strip().lower()


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def action_param_errors(action: dict[str, Any], index: int) -> list[str]:
    """Human details for parameter violations. Empty list = would run.

    ``index`` is 0-based (``actions[0]``) and matches the runtime's
    ``_run_actions`` labeling so preflight and provider messages align for the
    same position. ``do`` is normalized internally — callers pass the raw
    action object.
    """
    do = normalize_action_do(action.get("do"))
    if not do or do not in KNOWN_DOS:
        return [f"actions[{index}].do must be one of the v1 actions"]
    label = f"actions[{index}]"
    errors: list[str] = []
    if do in {"click", "fill", "type", "wait_for_selector", "select_option"}:
        selector = action.get("selector")
        if not isinstance(selector, str) or not selector:
            errors.append(f"{label}.selector required for {do}")
    if do in {"fill", "type"}:
        if "value" in action:
            if not isinstance(action.get("value"), str):
                errors.append(f"{label}.value must be a string")
        elif "text" in action and not isinstance(action.get("text"), str):
            errors.append(f"{label}.text must be a string")
    if do == "press":
        key = action.get("key") or action.get("value")
        if not isinstance(key, str) or not key:
            errors.append(f"{label}.key required for press")
    if do == "wait_for_state":
        state = action.get("state")
        if not isinstance(state, str) or not state:
            errors.append(f"{label}.state required for wait_for_state")
    if do in {"wait", "sleep"}:
        if "ms" in action:
            ms = action.get("ms")
            if not _is_number(ms) or ms < 0:  # type: ignore[operator]
                errors.append(f"{label}.ms must be a non-negative number")
        elif "timeout_ms" in action:
            ms = action.get("timeout_ms")
            if not _is_number(ms) or ms < 0:  # type: ignore[operator]
                errors.append(f"{label}.timeout_ms must be a non-negative number")
    if do == "select_option":
        value = action.get("value")
        label_value = action.get("label")
        if value is None and label_value is None:
            errors.append(f"{label}.value or label required for select_option")
        if value is not None and not isinstance(value, str):
            errors.append(f"{label}.value must be a string")
        if label_value is not None and not isinstance(label_value, str):
            errors.append(f"{label}.label must be a string")
    return errors
