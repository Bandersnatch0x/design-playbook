#!/usr/bin/env python3
"""Shared helpers for the Playwright-driven preview frontend tests.

Not named ``test_*`` on purpose: pytest must not collect this module.

Why this exists: the v9 shell shows a first-use onboarding card behind a
full-viewport ``.dpb-modal-scrim``. Every frontend test that drives real
pointer input has to clear it first, and the failure mode when one forgets is
brutal — Playwright resolves actionability for ``frame_locator`` targets
*inside* the iframe, where a parent overlay is invisible, so the click is
swallowed with no error, the pin never lands, and ``collect_review`` sits on
its 1800-second ``done.wait`` until the whole suite looks hung. That is not
hypothetical: it cost a 30-minute hang in the full pytest run.

Three test modules need this. Keeping one copy means a change to the
onboarding markup breaks them together and visibly, instead of leaving one
behind to hang in CI.
"""
from __future__ import annotations

# Onboarding is shown once per localStorage origin, so a reload inside one
# test legitimately finds no card to close.
ONBOARDING_WAIT_MS = 2000

_MODAL_HIDDEN_JS = (
    "() => { const modal = document.getElementById('dpb-onboarding-modal'); "
    "return !modal || modal.hidden; }"
)


def dismiss_onboarding(page: object, *, timeout_ms: int = ONBOARDING_WAIT_MS) -> bool:
    """Close the first-use onboarding card if it is showing.

    Returns True when a card was actually dismissed, False when there was
    none to dismiss (already seen this origin). Never raises for absence —
    absence is a legitimate state — but a card that refuses to close is a
    real failure and does raise.
    """
    modal = page.locator("#dpb-onboarding-modal")
    try:
        modal.wait_for(state="visible", timeout=timeout_ms)
    except Exception:  # noqa: BLE001 - playwright TimeoutError, absent by design
        return False
    page.click("#dpb-onboarding-dismiss")
    page.wait_for_function(_MODAL_HIDDEN_JS)
    return True
