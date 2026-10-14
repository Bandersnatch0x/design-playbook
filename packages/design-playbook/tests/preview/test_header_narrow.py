"""U-22 (E-18): narrow-width header actions stay reachable.

Both locales are pinned explicitly: resolving the locale from ``LANG`` made
machines run different label strings (en labels are wider) against the same
pixel budget, so the outcome depended on the environment instead of the
shell. At the 600px breakpoint edge every action fits with no sideways
scrolling. At 480px — outside the declared viewports, where the shell
chooses ``overflow-x: auto`` — every action must stay reachable by scrolling
and the scrollbar must stay visible.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

REACH = """() => {
  const h = document.querySelector('.dpb-header');
  const hr = h.getBoundingClientRect();
  const max = h.scrollWidth - h.clientWidth;
  const offscreen = [];
  const unreachable = [];
  for (const el of document.querySelectorAll('.dpb-header button, .dpb-header a[href]')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('[hidden]')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (r.left < hr.left - 0.5 || r.right > hr.right + 0.5) offscreen.push(el.id || el.className);
    const leftInContent = r.left - hr.left + h.scrollLeft;
    h.scrollLeft = Math.min(Math.max(0, leftInContent - 8), max);
    const scrolled = el.getBoundingClientRect();
    if (scrolled.left < hr.left - 0.5 || scrolled.right > hr.right + 0.5) {
      unreachable.push(el.id || el.className);
    }
    h.scrollLeft = 0;
  }
  h.scrollLeft = max;
  const reached = max <= 1 || h.scrollLeft >= max - 0.5;
  h.scrollLeft = 0;
  const style = getComputedStyle(h);
  return {sbw: style.scrollbarWidth, overflowX: style.overflowX,
          overflow: max > 1, offscreen, unreachable, reached};
}"""


@pytest.mark.parametrize("width", [600, 480])
@pytest.mark.parametrize("ui_locale", ["zh-CN", "en"])
def test_header_actions_are_reachable(tmp_path, width, ui_locale, monkeypatch):
    monkeypatch.setenv("DPB_PREVIEW_LANG", ui_locale)
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
    assert res["unreachable"] == [], res
    if width == 600:
        # The breakpoint edge itself: everything fits, no sideways scrolling.
        assert res["offscreen"] == [], res
        assert not res["overflow"], res
    elif res["overflow"]:
        # Past the declared viewports the shell scrolls by design; the scroll
        # must actually work, not just exist in the computed style.
        assert res["overflowX"] in ("auto", "scroll"), res
        assert res["reached"], res
