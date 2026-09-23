#!/usr/bin/env python3
"""Shared helpers for the Playwright-driven preview frontend tests.

Not named ``test_*`` on purpose: pytest must not collect this module.

Why this exists: the first-use coachmark (REC-03) is a non-modal card, so it
no longer blocks pointer input — but every frontend test still asserts a
deterministic start state, so the helpers offer one visible-only-when-present
dismissal. Unlike the old full-viewport onboarding scrim, a forgotten
coachmark cannot swallow clicks (it sits in a corner and never covers the
canvas), so the brutal failure mode documented here in v9 is gone by design.
"""
from __future__ import annotations

# Coachmark shows once per localStorage origin, so a reload inside one test
# legitimately finds no card to close.
COACHMARK_WAIT_MS = 2000


def dismiss_onboarding(page: object, *, timeout_ms: int = COACHMARK_WAIT_MS) -> bool:
    """Close the first-use coachmark card if it is showing.

    Returns True when a card was actually dismissed, False when there was
    none to dismiss (already seen this origin). Never raises for absence —
    absence is a legitimate state — but a card that refuses to close is a
    real failure and does raise.
    """
    card = page.locator("#dpb-coachmark")
    try:
        card.wait_for(state="visible", timeout=timeout_ms)
    except Exception:  # noqa: BLE001 - playwright TimeoutError, absent by design
        return False
    page.click("#dpb-coachmark-close")
    page.wait_for_function(
        "() => { const c = document.getElementById('dpb-coachmark');"
        " return !c || c.hidden; }"
    )
    return True
