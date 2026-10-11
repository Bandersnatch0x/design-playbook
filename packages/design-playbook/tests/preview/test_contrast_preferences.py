"""U-02 (E-10): the Preview shell under light, dark and increased-contrast preferences."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

MORE_FLOOR = 4.5

SAMPLE = """() => {
  const parse = c => {
    const v = (c.match(/[\\d.]+/g) || []).map(Number);
    return c.startsWith('color(srgb') ? [v[0] * 255, v[1] * 255, v[2] * 255, ...v.slice(3)] : v;
  };
  const over = (top, back) => {
    const a = top.length > 3 ? top[3] : 1;
    return [0, 1, 2].map(i => top[i] * a + back[i] * (1 - a));
  };
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const backdrop = el => {
    const stack = [];
    for (let n = el; n; n = n.parentElement) stack.push(getComputedStyle(n).backgroundColor);
    let back = [255, 255, 255];
    for (const c of stack.reverse()) { const p = parse(c); if (p.length && (p[3] === undefined || p[3] > 0)) back = over(p, back); }
    return back;
  };
  const root = document.querySelector('#dpb-root');
  const rs = getComputedStyle(root);
  const resolve = name => {
    const probe = document.createElement('i');
    probe.style.color = `var(${name})`;
    root.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return parse(value);
  };
  const roles = {muted: resolve('--dpb-muted'), soft: resolve('--dpb-soft')};
  const ink = resolve('--dpb-ink');
  const same = (a, b) => a.length >= 3 && b.length >= 3 && [0, 1, 2].every(i => a[i] === b[i]);
  const rows = [];
  for (const el of root.querySelectorAll('*')) {
    if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.closest('[hidden]')) continue;
    if (el.disabled || el.closest('[aria-disabled="true"]')) continue;
    const fg = parse(cs.color);
    const role = same(fg, roles.muted) ? 'muted' : same(fg, roles.soft) ? 'soft' : null;
    if (!role) continue;
    const back = backdrop(el);
    const l1 = lum(over(fg, back)), l2 = lum(back);
    rows.push({role, ratio: (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05),
               tag: el.tagName.toLowerCase() + '.' + (el.className || '')});
  }
  return {rows, mutedIsInk: same(roles.muted, ink), softIsInk: same(roles.soft, ink),
          focusWidth: rs.getPropertyValue('--dpb-focus-width').trim()};
}"""


@pytest.fixture(params=[("light", "no-preference"), ("dark", "no-preference"),
                        ("light", "more"), ("dark", "more")],
                ids=lambda p: f"{p[0]}-{p[1]}")
def shell(request, tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    scheme, contrast = request.param
    control = review_session._build_control(1, "Contrast preferences", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}, color_scheme=scheme, contrast=contrast)
            page = context.new_page()
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            yield page, contrast
        finally:
            browser.close()


def test_secondary_text_meets_the_registry_floor(shell):
    page, contrast = shell
    sample = page.evaluate(SAMPLE)
    assert sample["rows"], "no muted or soft text on the shell to measure"
    low = [row for row in sample["rows"] if row["ratio"] < MORE_FLOOR]
    assert low == []
    if contrast == "more":
        assert sample["mutedIsInk"] and sample["softIsInk"]
        assert sample["focusWidth"] == "3px"
    else:
        assert not sample["mutedIsInk"]
        assert sample["focusWidth"] == "2px"


def test_keyboard_focus_ring_widens_under_increased_contrast(shell):
    page, contrast = shell
    seen = []
    for _ in range(14):
        page.keyboard.press("Tab")
        page.wait_for_timeout(450)  # outline-width may still be transitioning from the UA default
        ring = page.evaluate(
            """() => { const el = document.activeElement; const cs = getComputedStyle(el);
            return el.matches(':focus-visible') && cs.outlineStyle === 'solid' ? cs.outlineWidth : null; }""")
        if ring:
            seen.append(ring)
    assert seen, "no keyboard-focused control drew an outline"
    assert set(seen) == {"3px" if contrast == "more" else "2px"}
