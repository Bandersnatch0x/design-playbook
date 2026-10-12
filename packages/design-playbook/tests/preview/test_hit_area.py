"""U-09 (E-09): every interactive control keeps a hit area at or above the registry floor."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_PKG = Path(__file__).resolve().parents[2]
if str(_PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(_PKG / "scripts"))

import rules_registry  # noqa: E402

SMALL_TARGETS = """([scope, floor]) => {
  const out = [];
  const sel = 'button,a[href],input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab],[role=menuitem],[tabindex]:not([tabindex="-1"])';
  for (const el of document.querySelector(scope).querySelectorAll(sel)) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('[hidden]')) continue;
    if (el.type === 'checkbox' || el.type === 'radio') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (Math.min(r.width, r.height) < floor) {
      out.push({tag: el.tagName.toLowerCase() + '.' + (el.className || '') + '#' + el.id,
                w: Math.round(r.width), h: Math.round(r.height)});
    }
  }
  return out;
}"""


def hit_floor() -> float:
    registry = _PKG / "skills" / "design-playbook" / "references" / "rules.md"
    entries = rules_registry.parse_registry(registry.read_text(encoding="utf-8"))
    return rules_registry.threshold(entries, "A11Y-04", "hit-area-floor").value


@pytest.fixture(params=[1280, 768])
def shell(request, tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "Hit area", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context(viewport={"width": request.param, "height": 900}).new_page()
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            yield page
        finally:
            browser.close()


def test_shell_controls_meet_the_hit_area_floor(shell):
    small = shell.evaluate(SMALL_TARGETS, ["#dpb-root", hit_floor()])
    assert small == [], small
