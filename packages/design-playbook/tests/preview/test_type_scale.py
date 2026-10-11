"""U-08 (E-13): rendered text on the Preview shell stays above the registry size floors."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_PKG = Path(__file__).resolve().parents[2]
if str(_PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(_PKG / "scripts"))

import rules_registry  # noqa: E402

TEXT_SIZES = """(scope) => {
  const rows = [];
  const walker = document.createTreeWalker(document.querySelector(scope), NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent.trim();
    const el = node.parentElement;
    if (!text || !el || el.closest('script,style,[hidden]')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    rows.push({text: text.slice(0, 40), px: parseFloat(cs.fontSize),
               cjk: /[\\u3400-\\u9fff\\uff00-\\uffef]/.test(text),
               tag: el.tagName.toLowerCase() + '.' + (el.className || '')});
  }
  return rows;
}"""


def floors() -> tuple[float, float]:
    registry = _PKG / "skills" / "design-playbook" / "references" / "rules.md"
    entries = rules_registry.parse_registry(registry.read_text(encoding="utf-8"))
    return (rules_registry.threshold(entries, "A11Y-05", "latin-text-min").value,
            rules_registry.threshold(entries, "A11Y-05", "cjk-text-min").value)


def under_floor(rows: list[dict]) -> list[dict]:
    latin, cjk = floors()
    return [row for row in rows if row["px"] < (cjk if row["cjk"] else latin)]


@pytest.fixture(params=["en", "zh"])
def shell(request, tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "类型阶梯" if request.param == "zh" else "Type scale",
                                            ["确认" if request.param == "zh" else "Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            yield page
        finally:
            browser.close()


def test_shell_text_is_not_below_the_registry_floor(shell):
    rows = shell.evaluate(TEXT_SIZES, "#dpb-root")
    assert len(rows) > 10, "the shell rendered too little text to measure"
    assert under_floor(rows) == []


def test_shell_uses_at_most_six_text_sizes(shell):
    rows = shell.evaluate(TEXT_SIZES, "#dpb-root")
    assert len({row["px"] for row in rows}) <= 6
