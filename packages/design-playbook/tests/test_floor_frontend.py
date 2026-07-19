#!/usr/bin/env python3
"""ADR-0008 frontend JS floor-intercept verification (headless).

Renders the adapter confirm page (prototype + injected control bar) and
drives multiple HITL-equivalent scenarios with playwright to verify the
frontend submit handler + readiness logic blocks non-substantive feedback
(short text, empty, incomplete anchors) and allows valid cases (4+ chars,
complete anchors). Covers all feedback operation scenarios post floor
hardening (min 4 chars for pure text).
"""
import sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "design-playbook-preview"))
import server  # noqa: E402
from i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROUND_N = 1
SUMMARY = "verify run summary - list scene"
OPTIONS = default_options()
PRIMARY_OPT = OPTIONS[0]
SECONDARY = [OPTIONS[1]]
OPTIONS = [PRIMARY_OPT] + SECONDARY  # ensure order if needed, but default_options already gives [confirm, revise]

control = server._build_control(ROUND_N, SUMMARY, OPTIONS)

# Prototype body with an anchorable element
proto = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
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


def click_primary(page):
    """Click the pill primary submit button."""
    return page.click('#dpb-preview-bar .dpb-pill .dpb-btn-primary')


def main():
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # capture console + the POST (form action /decide will 404 but we
        # only care whether submit was prevented: if prevented, URL stays
        # file://; if allowed, browser navigates to /decide and errors).
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')

        # --- Scenario 1 (I1): pill primary opens the drawer, does NOT submit ---
        # After I1 the pill has no confirm submit; its primary opens the drawer.
        page.click('#dpb-open-primary')
        page.wait_for_timeout(300)
        drawer_open = page.evaluate(
            "() => { const d = document.getElementById('dpb-drawer'); "
            "  return !!(d && d.open); }")
        # URL must stay file:// (no submit/navigation from the pill)
        s1_ok = drawer_open and page.url.startswith('file:')
        print(f"  S1 pill opens drawer (no submit): drawer_open={drawer_open} "
              f"stayed={page.url.startswith('file:')} -> {'OK' if s1_ok else 'FAIL'}")
        if not s1_ok:
            failures.append("S1: pill primary must open drawer, not submit")
        # then an empty in-drawer confirm is still blocked by the floor
        page.wait_for_selector('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(200)
        blocked = page.url.startswith('file:')
        if not blocked:
            failures.append("S1b: empty in-drawer confirm must be blocked")

        # --- Scenario 2: feedback text -> submit allowed ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', '确认通过,摘要列清晰')
        # submit allowed -> browser navigates to /decide (404 chrome-error)
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        s2_ok = nav_ok
        print(f"  S2 feedback text: submit_allowed={nav_ok} url={page.url[:40]} -> {'OK' if s2_ok else 'FAIL'}")
        if not s2_ok:
            failures.append("S2: feedback-text confirm not allowed through")

        # --- Scenario 3: anchor with comment -> submit allowed ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        # enable pin (点选批注)
        page.click('#dpb-pin-toggle')
        # click the h2 to add an anchor
        page.click('#hdr')
        page.wait_for_timeout(200)
        # find the anchor comment input and type
        comment_sel = '.dpb-anchor input, .dpb-anchor textarea, .dpb-anchor [contenteditable]'
        page.wait_for_selector(comment_sel)
        page.fill(comment_sel, 'fix spacing on this header')
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        s3_ok = nav_ok
        print(f"  S3 anchor+comment: submit_allowed={nav_ok} url={page.url[:40]} -> {'OK' if s3_ok else 'FAIL'}")
        if not s3_ok:
            failures.append("S3: anchor+comment confirm not allowed through")

        # --- Scenario 4: short feedback (<4 chars, e.g. "ok") is blocked (new min-length rule) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'ok')  # 2 chars
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(200)
        blocked = page.url.startswith('file:')
        s4_ok = blocked
        print(f"  S4 short feedback (2 chars): blocked={blocked} -> {'OK' if s4_ok else 'FAIL'}")
        if not s4_ok:
            failures.append("S4: short feedback (<4) must be blocked")

        # --- Scenario 5: exactly 4 chars feedback allowed ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'fixx')  # 4 chars
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        s5_ok = nav_ok
        print(f"  S5 4-char feedback: submit_allowed={nav_ok} -> {'OK' if s5_ok else 'FAIL'}")
        if not s5_ok:
            failures.append("S5: 4-char feedback must be allowed through")

        # --- Scenario 6: feedback present + incomplete anchor (no comment) still blocked ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'some text here')
        page.click('#dpb-pin-toggle')
        page.click('#hdr')
        page.wait_for_timeout(200)
        # do NOT fill the comment input for the anchor
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(200)
        blocked = page.url.startswith('file:')
        s6_ok = blocked
        print(f"  S6 feedback + incomplete anchor: blocked={blocked} -> {'OK' if s6_ok else 'FAIL'}")
        if not s6_ok:
            failures.append("S6: feedback + incomplete anchor must be blocked")

        # --- Scenario 7: complete anchor only (no feedback text) is allowed ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.click('#dpb-pin-toggle')
        page.click('#hdr')
        page.wait_for_timeout(200)
        comment_sel = '.dpb-anchor input, .dpb-anchor textarea, .dpb-anchor [contenteditable]'
        page.wait_for_selector(comment_sel)
        page.fill(comment_sel, 'valid anchor note')
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        s7_ok = nav_ok
        print(f"  S7 anchor-only (complete): submit_allowed={nav_ok} -> {'OK' if s7_ok else 'FAIL'}")
        if not s7_ok:
            failures.append("S7: complete anchor without text must be allowed")

        # --- Scenario 8: live readiness indicator + multiple anchors edge cases ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        # initially not ready
        ready_initial = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        page.fill('textarea[name="feedback"]', 'ready now')
        page.wait_for_timeout(100)
        ready_after_text = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        # add one anchor but leave comment empty -> should go back to not ready
        page.click('#dpb-pin-toggle')
        page.click('#hdr')
        page.wait_for_timeout(150)
        ready_with_bad_anchor = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        # fill the anchor comment -> ready again
        page.fill(comment_sel, 'good note')
        page.wait_for_timeout(100)
        ready_final = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        s8_ok = (not ready_initial) and ready_after_text and (not ready_with_bad_anchor) and ready_final
        print(f"  S8 readiness indicator: initial={ready_initial} text={ready_after_text} bad_anchor={ready_with_bad_anchor} final={ready_final} -> {'OK' if s8_ok else 'FAIL'}")
        if not s8_ok:
            failures.append("S8: readiness indicator must react correctly to feedback/anchors")

        # --- Scenario 9: revise (e.g. "需要修改") should be allowed even with empty/no feedback ---
        # Revise is for requesting changes; floor enforcement is mainly for confirm.
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        # leave everything empty, click the revise/secondary button
        # Use the actual label from i18n
        revise_label = SECONDARY[0]
        try:
            page.click('.dpb-drawer .dpb-btn-secondary', timeout=1000)
        except:
            page.click(f'button[value="{revise_label}"]', timeout=1000)
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        s9_ok = nav_ok
        print(f"  S9 empty + revise: submit_allowed={nav_ok} -> {'OK' if s9_ok else 'FAIL'}")
        if not s9_ok:
            failures.append("S9: revise should allow submit even with no substantive feedback")

        # --- S10: pill primary directly submits confirm when ready (no drawer forced open) ---
        # Per button flow debate: when isSubstantive(), pill primary should direct confirm.
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'ready to confirm directly from pill')
        page.wait_for_timeout(100)
        # Close drawer to make pill visible again
        page.click('#dpb-close-drawer')
        page.wait_for_timeout(200)
        # Check readiness on now-visible pill
        ready = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        # Click the pill primary (should now direct submit because ready)
        page.click('#dpb-open-primary')
        page.wait_for_timeout(300)
        nav_ok = not page.url.startswith('file:')
        # Drawer should be closed
        drawer_open = page.evaluate("() => { const d = document.getElementById('dpb-drawer'); return !!(d && d.open); }")
        s10_ok = nav_ok and ready and not drawer_open
        print(f"  S10 pill primary direct confirm when ready: ready={ready} nav={nav_ok} drawer_open={drawer_open} -> {'OK' if s10_ok else 'FAIL'}")
        if not s10_ok:
            failures.append("S10: pill primary must direct submit when ready, without forcing drawer")

        # --- S11: draft button records without deciding (closes without submit) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'just drafting notes')
        page.wait_for_timeout(100)
        # Click draft
        draft_clicked = False
        try:
            page.click('#dpb-draft', timeout=1000)
            draft_clicked = True
        except:
            pass
        page.wait_for_timeout(200)
        drawer_open_after = page.evaluate("() => { const d = document.getElementById('dpb-drawer'); return !!(d && d.open); }")
        no_nav = page.url.startswith('file:')
        s11_ok = draft_clicked and not drawer_open_after and no_nav
        print(f"  S11 draft button: clicked={draft_clicked} drawer_closed={not drawer_open_after} no_nav={no_nav} -> {'OK' if s11_ok else 'FAIL'}")
        if not s11_ok:
            failures.append("S11: draft button should close drawer without triggering submit")

        # --- S12: pill primary label switches to confirm label when ready ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        initial_label = page.evaluate("() => document.getElementById('dpb-open-primary').textContent")
        page.fill('textarea[name="feedback"]', 'enough text to be ready')
        page.wait_for_timeout(100)
        ready = page.evaluate("() => document.getElementById('dpb-pill-ready').classList.contains('is-ready')")
        final_label = page.evaluate("() => document.getElementById('dpb-open-primary').textContent")
        # final should be the confirm/primary label (not the original t_pill_open)
        s12_ok = ready and final_label != initial_label
        print(f"  S12 pill label switch on ready: initial='{initial_label}' final='{final_label}' ready={ready} -> {'OK' if s12_ok else 'FAIL'}")
        if not s12_ok:
            failures.append("S12: pill primary label should update to confirm label when ready")

        browser.close()

    print()
    if failures:
        print("FRONTEND FLOOR TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("FRONTEND FLOOR TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
