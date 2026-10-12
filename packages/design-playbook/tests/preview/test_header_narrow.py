"""U-22 (E-18): at 600px every header action is reachable without sideways scrolling."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

REACH = """() => {
  const out = [];
  const w = document.documentElement.clientWidth;
  for (const el of document.querySelectorAll('.dpb-header button, .dpb-header a[href]')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (r.left < 0 || r.right > w + 0.5) out.push(el.id || el.className);
  }
  const h = document.querySelector('.dpb-header');
  return {out, overflow: h.scrollWidth > h.clientWidth + 1, sbw: getComputedStyle(h).scrollbarWidth};
}"""


@pytest.mark.parametrize("width", [600, 480])
def test_header_actions_fit_without_scrolling(tmp_path, width):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "Narrow", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context(viewport={"width": width, "height": 900}).new_page()
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            res = page.evaluate(REACH)
        finally:
            browser.close()
    assert res["sbw"] != "none"
    assert res["out"] == [], res
    assert not res["overflow"], res
