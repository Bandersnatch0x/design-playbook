"""U-20: the Preview decision buttons post once and report busy while the request runs."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser


def test_double_press_submits_once_and_marks_busy(tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "Busy", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            sent = []
            page.route("**/decide", lambda route: (sent.append(route.request.url), route.fulfill(body="ok", content_type="text/html")))
            state = page.evaluate("""() => {
              const b = document.getElementById('dpb-skip-confirm');
              b.form.requestSubmit(b); b.form.requestSubmit(b);
              return [b.getAttribute('aria-busy'), b.textContent.trim()];
            }""")
            page.wait_for_timeout(300)
            assert len(sent) == 1
            assert state[0] == "true"
            assert state[1] in ("Submitting…", "提交中…")
        finally:
            browser.close()
