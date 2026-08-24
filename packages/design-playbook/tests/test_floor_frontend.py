#!/usr/bin/env python3
"""ADR-0008 frontend JS floor-intercept verification (headless, v9 shell).

Renders the adapter confirm page (prototype + injected v9 app shell) and
drives HITL-equivalent scenarios with playwright to verify the frontend
submit handler + readiness logic blocks non-substantive feedback (empty,
whitespace-only, incomplete anchors) and allows valid cases (non-empty
feedback incl. short CJK, complete anchors). Mirrors the adapter floor's
structural semantics - no minimum length (ADR-0008). Also covers the v9
chrome: status pill readiness, drawer collapse, abort popover (Scheme A'),
Ctrl+Enter routing, and theme sync.
"""
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.preview.i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

# Same directory; pytest's prepend import mode and direct `python <file>` runs
# both put this directory on sys.path.
from preview_e2e_helpers import dismiss_onboarding  # noqa: E402


def wait_submit_navigated(page, timeout_ms=3000) -> bool:
    """Wait until the confirm POST has committed (URL left file:).

    The submit lands on a chrome-error page (no server behind /decide); a
    fixed sleep can race the next scenario's ``page.goto``. Poll the URL so
    the navigation commits before the next page load.
    """
    import time
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if not page.url.startswith("file:"):
            return True
        page.wait_for_timeout(50)
    return not page.url.startswith("file:")


ROUND_N = 1
SUMMARY = "verify run summary - list scene"
OPTIONS = default_options()  # [confirm, revise] in the active locale
PRIMARY_OPT = OPTIONS[0]
SECONDARY = [OPTIONS[1]]

# Capture-phase listener that records the submitter value and preventDefaults,
# so the form does not navigate and tests can assert WHICH action was
# submitted. Shared by S10 + S14 + S15.
CAPTURE_SUBMITTER_JS = """() => {
  const f = document.getElementById('dpb-decide-form');
  f.addEventListener('submit', (e) => {
    window.__capturedSubmitter = (e.submitter && e.submitter.value) || null;
    e.preventDefault();
  }, true);
}"""

control = preview_control._build_control(ROUND_N, SUMMARY, OPTIONS)

# Prototype body with an anchorable element
proto = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>verify floor</title></head>
<body>
<h2 id="hdr">Run summary</h2>
<table><tbody><tr><td>row1</td></tr></tbody></table>
</body></html>"""
full = proto.replace("</body>", control + "</body>", 1)

tmp = Path(tempfile.mkdtemp())
page_path = tmp / "page.html"
page_path.write_text(full, encoding="utf-8")
file_url = page_path.as_uri()


def fresh(page):
    page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
    page.goto(file_url, wait_until="domcontentloaded")
    page.wait_for_selector("#dpb-root")
    page.wait_for_timeout(250)
    # The production shell intentionally blocks the canvas on first use until
    # onboarding is dismissed.  Complete that initialization before driving a
    # floor scenario so the scenario clicks target the underlying controls.
    dismiss_onboarding(page)


def main():
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        # --- S1: empty confirm is blocked; feedback gate engages ---
        fresh(page)
        page.click("#dpb-btn-approve")
        page.wait_for_timeout(300)
        blocked = page.url.startswith("file:")
        hint_on = page.evaluate(
            "() => document.getElementById('dpb-feedback-hint')"
            ".classList.contains('is-on')")
        focused = page.evaluate(
            "() => document.activeElement === document.getElementById('dpb-feedback')")
        s1_ok = blocked and hint_on and focused
        print(f"  S1 empty confirm blocked: blocked={blocked} hint={hint_on} "
              f"focused={focused} -> {'OK' if s1_ok else 'FAIL'}")
        if not s1_ok:
            failures.append("S1: empty confirm must be blocked with hint + focus")

        # --- S2: feedback text -> submit allowed ---
        fresh(page)
        page.fill('textarea[name="feedback"]', '确认通过,摘要列清晰')
        page.click("#dpb-btn-approve")
        nav_ok = wait_submit_navigated(page)
        print(f"  S2 feedback text: submit_allowed={nav_ok} -> "
              f"{'OK' if nav_ok else 'FAIL'}")
        if not nav_ok:
            failures.append("S2: feedback-text confirm not allowed through")

        # --- S3: element pin + comment -> submit allowed ---
        fresh(page)
        page.click("#hdr")  # default tool: select/pin, mode: annotate
        page.wait_for_selector("#dpb-anchors .dpb-anchor")
        sel = page.evaluate(
            "() => JSON.parse(document.getElementById('dpb-anchors-json')"
            ".value || '[]')[0].selector")
        page.fill('#dpb-anchors input[data-i="0"]', 'fix spacing on this header')
        page.click("#dpb-btn-approve")
        nav_ok = wait_submit_navigated(page)
        s3_ok = nav_ok and sel == "#hdr"
        print(f"  S3 pin+comment: selector={sel} submit_allowed={nav_ok} -> "
              f"{'OK' if s3_ok else 'FAIL'}")
        if not s3_ok:
            failures.append("S3: element pin anchor + comment must confirm")

        # --- S4: short CJK feedback (3 chars) -> allowed (no min length) ---
        fresh(page)
        page.fill('textarea[name="feedback"]', '层级清晰')
        page.click("#dpb-btn-approve")
        nav_ok = wait_submit_navigated(page)
        print(f"  S4 short CJK: submit_allowed={nav_ok} -> "
              f"{'OK' if nav_ok else 'FAIL'}")
        if not nav_ok:
            failures.append("S4: short CJK feedback must confirm (no min length)")

        # --- S5: whitespace-only -> blocked ---
        fresh(page)
        page.fill('textarea[name="feedback"]', '   \n\t  ')
        page.click("#dpb-btn-approve")
        page.wait_for_timeout(300)
        blocked = page.url.startswith("file:")
        print(f"  S5 whitespace-only: blocked={blocked} -> "
              f"{'OK' if blocked else 'FAIL'}")
        if not blocked:
            failures.append("S5: whitespace-only feedback must be blocked")

        # --- S6: feedback + incomplete anchor (no comment) -> blocked ---
        fresh(page)
        page.click("#hdr")
        page.wait_for_selector("#dpb-anchors .dpb-anchor")
        page.fill('textarea[name="feedback"]', 'some text here')
        page.click("#dpb-btn-approve")
        page.wait_for_timeout(300)
        blocked = page.url.startswith("file:")
        print(f"  S6 incomplete anchor: blocked={blocked} -> "
              f"{'OK' if blocked else 'FAIL'}")
        if not blocked:
            failures.append("S6: incomplete anchor must block confirm")

        # --- S7: anchor-only (complete) -> allowed ---
        fresh(page)
        page.click("#hdr")
        page.wait_for_selector("#dpb-anchors .dpb-anchor")
        page.fill('#dpb-anchors input[data-i="0"]', 'fix spacing')
        page.click("#dpb-btn-approve")
        nav_ok = wait_submit_navigated(page)
        print(f"  S7 anchor-only complete: submit_allowed={nav_ok} -> "
              f"{'OK' if nav_ok else 'FAIL'}")
        if not nav_ok:
            failures.append("S7: complete anchor-only must confirm")

        # --- S8: status pill readiness flips ---
        fresh(page)
        initial = page.evaluate(
            "() => document.getElementById('dpb-status-pill')"
            ".classList.contains('dpb-is-ready')")
        page.fill('textarea[name="feedback"]', 'ready now')
        page.wait_for_timeout(150)
        ready = page.evaluate(
            "() => document.getElementById('dpb-status-pill')"
            ".classList.contains('dpb-is-ready')")
        s8_ok = (not initial) and ready
        print(f"  S8 readiness pill: initial={initial} after_text={ready} -> "
              f"{'OK' if s8_ok else 'FAIL'}")
        if not s8_ok:
            failures.append("S8: status pill readiness must track substantive state")

        # --- S9: empty revise is blocked with gate ---
        fresh(page)
        page.evaluate(CAPTURE_SUBMITTER_JS)
        revise_btn = page.locator("#dpb-decide-form button.dpb-btn-secondary").first
        revise_btn.click()
        page.wait_for_timeout(300)
        captured = page.evaluate("() => window.__capturedSubmitter")
        hint_on = page.evaluate(
            "() => document.getElementById('dpb-feedback-hint')"
            ".classList.contains('is-on')")
        focused = page.evaluate(
            "() => document.activeElement === document.getElementById('dpb-feedback')")
        s9_ok = captured == SECONDARY[0] and hint_on and focused
        print(f"  S9 empty revise blocked: captured={captured!r} hint={hint_on} "
              f"focused={focused} -> {'OK' if s9_ok else 'FAIL'}")
        if not s9_ok:
            failures.append("S9: revise must be blocked until feedback is substantive")

        # --- S10: single-click approve when ready ---
        fresh(page)
        page.fill('textarea[name="feedback"]', 'ready to confirm directly')
        page.wait_for_timeout(100)
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.click("#dpb-btn-approve")
        page.wait_for_timeout(300)
        captured = page.evaluate("() => window.__capturedSubmitter")
        s10_ok = captured == PRIMARY_OPT
        print(f"  S10 single-click approve: captured={captured!r} "
              f"(want {PRIMARY_OPT!r}) -> {'OK' if s10_ok else 'FAIL'}")
        if not s10_ok:
            failures.append("S10: ready approve must submit the CONFIRM choice")

        # --- S11: status-approve button gates when not ready ---
        fresh(page)
        page.click("#dpb-status-approve")
        page.wait_for_timeout(300)
        blocked = page.url.startswith("file:")
        hint_on = page.evaluate(
            "() => document.getElementById('dpb-feedback-hint')"
            ".classList.contains('is-on')")
        s11_ok = blocked and hint_on
        print(f"  S11 status pill gate: blocked={blocked} hint={hint_on} -> "
              f"{'OK' if s11_ok else 'FAIL'}")
        if not s11_ok:
            failures.append("S11: status quick-approve must gate when not ready")

        # --- S12: drawer collapse + reopen tab + [ shortcut ---
        fresh(page)
        page.click("#dpb-inspector-close")
        page.wait_for_timeout(300)
        collapsed = page.evaluate(
            "() => document.getElementById('dpb-inspector')"
            ".classList.contains('dpb-collapsed')")
        tab_visible = page.evaluate(
            "() => !document.getElementById('dpb-reopen-tab').hidden")
        page.keyboard.press("[")
        page.wait_for_timeout(300)
        reopened = not page.evaluate(
            "() => document.getElementById('dpb-inspector')"
            ".classList.contains('dpb-collapsed')")
        s12_ok = collapsed and tab_visible and reopened
        print(f"  S12 drawer collapse: collapsed={collapsed} tab={tab_visible} "
              f"reopened={reopened} -> {'OK' if s12_ok else 'FAIL'}")
        if not s12_ok:
            failures.append("S12: drawer must collapse with a reopen tab and [ shortcut")

        # --- S14: abort popover (Scheme A') ---
        fresh(page)
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.click("#dpb-abort")
        page.wait_for_timeout(200)
        open_before = page.evaluate(
            "() => !document.getElementById('dpb-abort-popover').hidden")
        page.click("#dpb-abort-confirm")
        page.wait_for_timeout(200)
        captured = page.evaluate("() => window.__capturedSubmitter")
        s14_ok = open_before and captured == "__abort__"
        print(f"  S14 abort popover: open={open_before} captured={captured!r} -> "
              f"{'OK' if s14_ok else 'FAIL'}")
        if not s14_ok:
            failures.append("S14: abort popover must submit __abort__ after confirm")

        # --- S14b: popover resets when drawer/chrome clicked elsewhere ---
        fresh(page)
        page.click("#dpb-abort")
        page.wait_for_timeout(150)
        open_before = page.evaluate(
            "() => !document.getElementById('dpb-abort-popover').hidden")
        page.click("#dpb-toolbar")
        page.wait_for_timeout(200)
        open_after = page.evaluate(
            "() => !document.getElementById('dpb-abort-popover').hidden")
        s14b_ok = open_before and not open_after
        print(f"  S14b popover dismiss: open={open_before} after={open_after} -> "
              f"{'OK' if s14b_ok else 'FAIL'}")
        if not s14b_ok:
            failures.append("S14b: clicking chrome elsewhere must dismiss the popover")

        # --- S15: Ctrl+Enter routes the CONFIRM; blocked when not ready ---
        fresh(page)
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(300)
        blocked_empty = page.url.startswith("file:")
        page.fill('textarea[name="feedback"]', 'ctrl enter works')
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(250)
        captured_filled = page.evaluate("() => window.__capturedSubmitter")
        s15_ok = blocked_empty and captured_filled == PRIMARY_OPT
        print(f"  S15 Ctrl+Enter: blocked_empty={blocked_empty} "
              f"filled={captured_filled!r} -> {'OK' if s15_ok else 'FAIL'}")
        if not s15_ok:
            failures.append("S15: Ctrl+Enter must confirm only when substantive")

        # --- S16: header buttons carry decision titles ---
        descs = page.evaluate("""() => ({
          skip: !!(document.getElementById('dpb-btn-skip').getAttribute('title') || ''),
          abort: !!(document.getElementById('dpb-abort').getAttribute('title') || ''),
          approve: !!(document.getElementById('dpb-btn-approve').getAttribute('title') || ''),
        })""")
        s16_ok = all(descs.values())
        print(f"  S16 header descs: {descs} -> {'OK' if s16_ok else 'FAIL'}")
        if not s16_ok:
            failures.append("S16: header decision buttons must carry titles")

        # --- S17: free pin drops on canvas padding ---
        fresh(page)
        page.evaluate("""() => {
          const c = document.getElementById('dpb-canvas');
          const b = c.getBoundingClientRect();
          c.dispatchEvent(new MouseEvent('click', {bubbles: true,
            clientX: b.x + 30, clientY: b.y + 30}));
        }""")
        page.wait_for_timeout(250)
        free = page.evaluate(
            "() => JSON.parse(document.getElementById('dpb-anchors-json')"
            ".value || '[]').filter(a => String(a.selector).startsWith('@pin-')).length")
        print(f"  S17 free pin on canvas: count={free} -> "
              f"{'OK' if free == 1 else 'FAIL'}")
        if free != 1:
            failures.append("S17: canvas click must drop a free position pin")

        # --- S18: theme attribute syncs ---
        theme = page.evaluate(
            "() => document.getElementById('dpb-root').getAttribute('data-theme')")
        s18_ok = theme in ("light", "dark")
        print(f"  S18 theme sync: {theme!r} -> {'OK' if s18_ok else 'FAIL'}")
        if not s18_ok:
            failures.append("S18: root must carry a resolved data-theme")

        # --- S19: draw tool records a stroke anchor ---
        fresh(page)
        page.click("#dpb-draw-toggle")
        page.wait_for_timeout(150)
        r = page.evaluate("""() => {
          const a = document.getElementById('dpb-artboard').getBoundingClientRect();
          return {x: a.x + a.width / 2, y: a.y + a.height / 2};
        }""")
        page.mouse.move(r["x"], r["y"])
        page.mouse.down()
        page.mouse.move(r["x"] + 60, r["y"] + 40, steps=3)
        page.mouse.move(r["x"] - 10, r["y"] + 80, steps=3)
        page.mouse.move(r["x"], r["y"], steps=3)
        page.mouse.up()
        page.wait_for_timeout(300)
        draw = page.evaluate(
            "() => JSON.parse(document.getElementById('dpb-anchors-json')"
            ".value || '[]').filter(a => a.tag === 'draw').length")
        print(f"  S19 draw stroke anchor: count={draw} -> "
              f"{'OK' if draw == 1 else 'FAIL'}")
        if draw != 1:
            failures.append("S19: draw tool must record a stroke anchor")

        # --- S20: shortcut modal opens and closes ---
        fresh(page)
        page.keyboard.press("?")
        page.wait_for_timeout(200)
        modal_open = page.evaluate(
            "() => !document.getElementById('dpb-shortcut-modal').hidden")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        modal_closed = page.evaluate(
            "() => document.getElementById('dpb-shortcut-modal').hidden")
        s20_ok = modal_open and modal_closed
        print(f"  S20 shortcut modal: open={modal_open} closed={modal_closed} -> "
              f"{'OK' if s20_ok else 'FAIL'}")
        if not s20_ok:
            failures.append("S20: shortcut modal must open on ? and close on Esc")

        # --- S21: Esc submits the skip channel when idle ---
        fresh(page)
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        captured = page.evaluate("() => window.__capturedSubmitter")
        skip_val = page.evaluate(
            "() => document.getElementById('dpb-btn-skip').getAttribute('value')")
        s21_ok = captured == skip_val
        print(f"  S21 Esc skip: captured={captured!r} skip_val={skip_val!r} -> "
              f"{'OK' if s21_ok else 'FAIL'}")
        if not s21_ok:
            failures.append("S21: Esc must submit the skip choice when idle")

        browser.close()

        if errors:
            failures.append(f"page errors during scenarios: {errors[:3]}")

    if failures:
        print("FRONTEND FLOOR TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("FRONTEND FLOOR TEST PASSED")
    return 0


def test_floor_frontend_scenarios() -> None:
    """pytest entry point for the main()-style harness above.

    Same gap as test_pin_bridge_frontend: without a ``test_*`` name pytest
    collected nothing here, so these floor scenarios only ever ran when
    someone invoked the file by hand. main() prints per-scenario diagnostics
    and returns non-zero on failure.
    """
    assert main() == 0, "frontend floor scenarios reported failures (see stdout)"


if __name__ == "__main__":
    sys.exit(main())
