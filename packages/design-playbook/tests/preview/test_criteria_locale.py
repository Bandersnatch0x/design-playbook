"""Criteria copy is run data, so a bilingual run ships both languages.

The preview shell already has one language switcher. The criteria view must ride
that switcher rather than adding a second control, and a single-language run must
keep rendering the text it was given in both locales.
"""
from __future__ import annotations

import re
import sys
import tempfile
import threading
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlrequest

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview import control, review_session  # noqa: E402

BILINGUAL = [
    {
        "id": "AC-1",
        "title": "Interaction feels direct",
        "then": "Click, resize, style without friction",
        "title_zh": "交互响应直接",
        "title_en": "Interaction feels direct",
        "then_zh": "点击、缩放与样式调整均无阻滞",
        "then_en": "Click, resize, style without friction",
    },
    {"id": "AC-2", "title": "Only authored once", "then": "No translation supplied"},
]


def test_each_locale_falls_back_to_the_plain_field_then_the_other_locale() -> None:
    items = control._normalise_criteria(BILINGUAL)

    first, second = items
    assert first["title_zh"] == "交互响应直接"
    assert first["title_en"] == "Interaction feels direct"
    assert first["then_zh"] == "点击、缩放与样式调整均无阻滞"

    # A single-language criterion must render in both locales, not blank out.
    assert second["title_zh"] == second["title_en"] == "Only authored once"
    assert second["then_zh"] == second["then_en"] == "No translation supplied"


def test_a_locale_only_override_fills_the_other_one() -> None:
    items = control._normalise_criteria([
        {"id": "AC-1", "title_en": "English only", "then_en": "Then in English"},
    ])
    assert items[0]["title_zh"] == "English only"
    assert items[0]["title_en"] == "English only"


def test_cards_carry_both_locales_and_the_primary_title_attribute() -> None:
    html = control._render_criteria_cards(control._normalise_criteria(BILINGUAL))
    assert 'class="dpb-crit-zh"' in html and 'class="dpb-crit-en"' in html
    assert "交互响应直接" in html and "Interaction feels direct" in html
    # The posted title stays the authored one; the transaction records the
    # caller's criteria anyway, so this attribute is informational only.
    assert 'data-criterion-title="Interaction feels direct"' in html


def test_criteria_follow_the_one_existing_language_switcher() -> None:
    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(_PKG_ROOT / 'tests'))
    from preview_e2e_helpers import dismiss_onboarding

    prototype = '<!doctype html><html><body><h2 id="t">Criteria locale</h2></body></html>'
    adapter = _PrintOnlyAdapter()
    box: dict = {}

    def collect(path, summary, options, round_n, *, criteria=None):
        return review_session.collect_review(
            path, summary, options, round_n, browser_adapter=adapter, criteria=BILINGUAL
        )

    def run() -> None:
        from design_playbook.mcp.preview.transaction import run_preview_transaction
        work = Path(tempfile.mkdtemp(prefix='dpb-crit-locale-'))
        p = work / 'round-1.html'
        p.write_text(prototype, encoding='utf-8')
        box['result'] = run_preview_transaction(
            path_arg=str(p), html=None, summary='criteria locale', round_n=1,
            report_ref='r.md', options=['确认通过', '需要修改'], collect=collect,
        )

    thread = threading.Thread(target=run, name='criteria-locale', daemon=True)
    thread.start()
    assert adapter.ready.wait(30), 'the preview session never came up'

    token = re.search(
        r'name="dpb_token"[^>]*value="([^"]+)"',
        urlrequest.build_opener(urlrequest.ProxyHandler({})).open(
            adapter.url, timeout=20).read().decode('utf-8'),
    )
    assert token, 'the served page must carry the one-time token'

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.goto(adapter.url, wait_until='domcontentloaded')
            dismiss_onboarding(page)
            page.locator('#dpb-tab-spec').click()

            # One switcher, and it is the shell's existing one.
            assert page.evaluate(
                "() => document.querySelectorAll('#dpb-language-toggle').length") == 1
            assert page.evaluate("""() => [...document.querySelectorAll('button')]
                .filter(b => /lang|语言/i.test((b.id || '') +
                  (b.getAttribute('data-i18n') || ''))).map(b => b.id)""") == ['dpb-language-toggle']

            def visible(selector: str) -> list[str]:
                return page.evaluate(
                    "sel => [...document.querySelectorAll(sel)]"
                    ".filter(e => e.offsetParent !== null).map(e => e.textContent)", selector)

            # Do not assume the starting locale: assert that the visible language
            # follows the switcher, whichever way it starts.
            first = page.locator('#dpb-root').get_attribute('lang')
            page.keyboard.press('l')
            page.wait_for_timeout(200)
            second = page.locator('#dpb-root').get_attribute('lang')
            assert second != first

            zh_visible = visible('#dpb-spec-view .dpb-crit-zh')
            en_visible = visible('#dpb-spec-view .dpb-crit-en')
            assert bool(zh_visible) != bool(en_visible), 'exactly one language is on screen'
            assert bool(zh_visible) == second.startswith('zh')
            # The single-language criterion is present in both locales.
            assert 'Only authored once' in page.locator('#dpb-spec-view').inner_text()
            assert 'No translation supplied' in page.locator('#dpb-spec-view').inner_text()
        finally:
            browser.close()

    # End the session. A transaction that never receives a decision keeps its
    # heartbeat thread alive past this test, and that thread then collides with
    # another test's global os.replace mock.
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
    opener.open(urlrequest.Request(
        adapter.url + 'decide',
        data=urlparse.urlencode({
            'choice': '确认通过', 'feedback': 'criteria locale', 'anchors_json': '[]',
            'criteria_json': '[]', 'visual_edits_json': '', 'dpb_round': '1',
            'dpb_token': token.group(1),
        }).encode(),
        method='POST',
    ), timeout=30).read()
    thread.join(40)
    assert box.get('result', {}).get('confirmed') is True, 'the session must end cleanly'


class _PrintOnlyAdapter:
    def __init__(self) -> None:
        self.url: str | None = None
        self.ready = threading.Event()

    def open(self, url: str):
        self.url = url
        self.ready.set()
        return {"url": url}

    def close(self, handle) -> None:
        pass
