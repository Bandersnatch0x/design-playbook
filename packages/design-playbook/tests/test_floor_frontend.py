#!/usr/bin/env python3
"""ADR-0008 frontend JS floor-intercept verification (headless).

Renders the adapter confirm page (prototype + injected control bar) and
drives multiple HITL-equivalent scenarios with playwright to verify the
frontend submit handler + readiness logic blocks non-substantive feedback
(empty, whitespace-only, incomplete anchors) and allows valid cases
(non-empty feedback incl. short CJK, complete anchors). Mirrors the
adapter floor's structural semantics — no minimum length (ADR-0008). Also
verifies the injected control follows live host/system color-scheme changes.
"""
import sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mcp" / "preview"))
import control as preview_control  # noqa: E402
from i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402


def wait_submit_navigated(page, timeout_ms=3000) -> bool:
    """Wait until the confirm POST has committed (URL left file:).

    The submit lands on a chrome-error page (no server behind /decide); a
    fixed sleep can race the next scenario's ``page.goto`` ("interrupted by
    another navigation to chrome-error://chromewebdata/"). Poll the URL so
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
# submitted. Shared by S10 + S15.
CAPTURE_SUBMITTER_JS = """() => {
  const f = document.getElementById('dpb-decide-form');
  f.addEventListener('submit', (e) => {
    window.__capturedSubmitter = (e.submitter && e.submitter.value) || null;
    e.preventDefault();
  }, true);
}"""

control = preview_control._build_control(ROUND_N, SUMMARY, OPTIONS)

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
        nav_ok = wait_submit_navigated(page)
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
        nav_ok = wait_submit_navigated(page)
        s3_ok = nav_ok
        print(f"  S3 anchor+comment: submit_allowed={nav_ok} url={page.url[:40]} -> {'OK' if s3_ok else 'FAIL'}")
        if not s3_ok:
            failures.append("S3: anchor+comment confirm not allowed through")

        # --- Scenario 4: short feedback is allowed (structural floor, no min length) ---
        # CJK-first: 3-char "太挤了" is substantive feedback; semantic junk is G6's
        # job, not the floor's (ADR-0008).
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', '太挤了')  # 3 chars, substantive
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        nav_ok = wait_submit_navigated(page)
        s4_ok = nav_ok
        print(f"  S4 short CJK feedback (3 chars): submit_allowed={nav_ok} -> {'OK' if s4_ok else 'FAIL'}")
        if not s4_ok:
            failures.append("S4: short CJK feedback must be allowed (no min-length floor)")

        # --- Scenario 5: whitespace-only feedback is blocked (trimmed before non-empty check) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', '   ')  # whitespace only
        page.click('.dpb-drawer .dpb-btn-primary', timeout=2000)
        page.wait_for_timeout(200)
        blocked = page.url.startswith('file:')
        s5_ok = blocked
        print(f"  S5 whitespace-only feedback: blocked={blocked} -> {'OK' if s5_ok else 'FAIL'}")
        if not s5_ok:
            failures.append("S5: whitespace-only feedback must be blocked")

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
        nav_ok = wait_submit_navigated(page)
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
        # leave everything empty and capture the submitted revise choice without
        # depending on file:// -> 404 navigation timing.
        revise_label = SECONDARY[0]
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.click('.dpb-drawer .dpb-btn-secondary', timeout=1000)
        page.wait_for_timeout(100)
        captured_revise = page.evaluate("() => window.__capturedSubmitter")
        s9_ok = captured_revise == revise_label
        print(
            f"  S9 empty + revise: captured={captured_revise!r} "
            f"(want {revise_label!r}) -> {'OK' if s9_ok else 'FAIL'}"
        )
        if not s9_ok:
            failures.append("S9: revise should allow submit even with no substantive feedback")

        # --- S10: pill primary direct-confirm is two-step arm→submit when ready ---
        # 二级保护: first click arms (no submit), second click submits confirm.
        # Guards the "null"-choice regression + accidental one-click confirm.
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
        page.evaluate(CAPTURE_SUBMITTER_JS)
        # First click: arm only
        page.click('#dpb-open-primary')
        page.wait_for_timeout(100)
        armed = page.evaluate(
            "() => document.getElementById('dpb-open-primary').classList.contains('is-armed')")
        captured_after_arm = page.evaluate("() => window.__capturedSubmitter")
        drawer_open_after_arm = page.evaluate(
            "() => { const d = document.getElementById('dpb-drawer'); return !!(d && d.open); }")
        # Second click: submit confirm
        page.click('#dpb-open-primary')
        page.wait_for_timeout(300)
        captured = page.evaluate("() => window.__capturedSubmitter")
        drawer_open = page.evaluate(
            "() => { const d = document.getElementById('dpb-drawer'); return !!(d && d.open); }")
        s10_ok = (
            ready and armed and captured_after_arm is None
            and not drawer_open_after_arm
            and captured == PRIMARY_OPT and not drawer_open
        )
        print(
            f"  S10 pill arm→confirm: ready={ready} armed_1st={armed} "
            f"captured_after_arm={captured_after_arm} captured_2nd='{captured}' "
            f"(want '{PRIMARY_OPT}') drawer_open={drawer_open} -> {'OK' if s10_ok else 'FAIL'}"
        )
        if not s10_ok:
            failures.append(
                "S10: pill primary must arm on 1st click and submit confirm on 2nd when ready"
            )

        # --- S11: draft button keeps notes and closes without deciding (no submit) ---
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

        # --- S13: pill primary label restores when readiness flips back (I13) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        original_label = page.evaluate("() => document.getElementById('dpb-open-primary').textContent")
        page.fill('textarea[name="feedback"]', 'enough text to be ready')
        page.wait_for_timeout(100)
        ready_label = page.evaluate("() => document.getElementById('dpb-open-primary').textContent")
        # clear feedback -> readiness flips back, label must restore
        page.fill('textarea[name="feedback"]', '')
        page.wait_for_timeout(100)
        restored_label = page.evaluate("() => document.getElementById('dpb-open-primary').textContent")
        s13_ok = (ready_label != original_label) and (restored_label == original_label)
        print(f"  S13 label restore on flip-back: orig='{original_label}' ready='{ready_label}' restored='{restored_label}' -> {'OK' if s13_ok else 'FAIL'}")
        if not s13_ok:
            failures.append("S13: pill primary label should restore when readiness flips back to not-ready")

        # --- S14: abort requires a second click (I18 two-step confirm) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        abort_btn = page.query_selector('#dpb-abort')
        abort_armed_before = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        abort_btn.click()  # first click should arm, not submit
        page.wait_for_timeout(100)
        stayed_after_arm = page.url.startswith('file:')
        abort_armed_after = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        # close+reopen should reset arming (I18 leak fix); then first click arms, second submits
        abort_btn.click()  # second click while armed -> should submit __abort__ (navigate)
        page.wait_for_timeout(300)
        aborted_nav = not page.url.startswith('file:')
        s14_ok = (not abort_armed_before) and stayed_after_arm and abort_armed_after and aborted_nav
        print(f"  S14 abort two-step: armed_before={abort_armed_before} armed_after_1st={abort_armed_after} aborted_on_2nd={aborted_nav} -> {'OK' if s14_ok else 'FAIL'}")
        if not s14_ok:
            failures.append("S14: abort needs arm(1st)+submit(2nd); first must not navigate")

        # --- S14b: arming resets when drawer closes (I18 leak fix) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.click('#dpb-abort')  # arm
        page.wait_for_timeout(50)
        armed_before_close = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        page.click('#dpb-close-drawer')  # collapse drawer -> should reset arming
        page.wait_for_timeout(50)
        armed_after_close = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        s14b_ok = armed_before_close and (not armed_after_close)
        print(f"  S14b abort reset on close: armed_before={armed_before_close} armed_after={armed_after_close} -> {'OK' if s14b_ok else 'FAIL'}")
        if not s14b_ok:
            failures.append("S14b: abort arming should reset when drawer closes")

        # --- S15: Ctrl+Enter in feedback submits the CONFIRM (I8) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'enough text to be ready')
        page.wait_for_timeout(100)
        # capture the submitter value (shared listener) so the form does not
        # navigate and we can assert WHICH action was submitted.
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.focus('textarea[name="feedback"]')
        page.keyboard.press('Control+Enter')
        page.wait_for_timeout(200)
        captured = page.evaluate("() => window.__capturedSubmitter")
        s15_ok = captured == PRIMARY_OPT  # must be the confirm, not abort/revise
        # S15b: Ctrl+Enter with drawer CLOSED must NOT submit (handler only on textarea)
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.keyboard.press('Control+Enter')
        page.wait_for_timeout(200)
        stayed_closed = page.url.startswith('file:')
        s15_ok = s15_ok and stayed_closed
        print(f"  S15 Ctrl+Enter: captured_submitter='{captured}' (want '{PRIMARY_OPT}') no_submit_when_closed={stayed_closed} -> {'OK' if s15_ok else 'FAIL'}")
        if not s15_ok:
            failures.append("S15: Ctrl+Enter should submit the CONFIRM (not abort/revise) when open; nothing when closed")

        # --- S16: clicking elsewhere in drawer cancels abort arming (8b34387) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.click('#dpb-abort')  # first click arms
        page.wait_for_timeout(100)
        armed = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        page.click('textarea[name="feedback"]')  # click elsewhere in drawer -> cancel arm
        page.wait_for_timeout(100)
        armed_after_cancel = page.evaluate("() => document.getElementById('dpb-abort').classList.contains('is-armed')")
        stayed = page.url.startswith('file:')
        s16_ok = armed and not armed_after_cancel and stayed
        print(f"  S16 drawer-click cancels abort arm: armed={armed} after_cancel={armed_after_cancel} stayed={stayed} -> {'OK' if s16_ok else 'FAIL'}")
        if not s16_ok:
            failures.append("S16: clicking elsewhere in drawer must cancel abort arming")

        # --- S17: pill confirm arm undoes without submit (timeout / annotate click) ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        page.fill('textarea[name="feedback"]', 'ready then undo arm')
        page.wait_for_timeout(100)
        page.click('#dpb-close-drawer')
        page.wait_for_timeout(200)
        page.evaluate(CAPTURE_SUBMITTER_JS)
        page.click('#dpb-open-primary')  # arm
        page.wait_for_timeout(100)
        armed = page.evaluate(
            "() => document.getElementById('dpb-open-primary').classList.contains('is-armed')")
        # Click annotate -> must undo arm, no submit
        page.click('#dpb-open-drawer')
        page.wait_for_timeout(150)
        armed_after_undo = page.evaluate(
            "() => document.getElementById('dpb-open-primary').classList.contains('is-armed')")
        captured_undo = page.evaluate("() => window.__capturedSubmitter")
        # Re-close, re-arm, wait past CONFIRM_ARM_MS (4000) for timeout undo
        page.click('#dpb-close-drawer')
        page.wait_for_timeout(200)
        page.click('#dpb-open-primary')  # arm again
        page.wait_for_timeout(100)
        armed_again = page.evaluate(
            "() => document.getElementById('dpb-open-primary').classList.contains('is-armed')")
        page.wait_for_timeout(4100)
        armed_after_timeout = page.evaluate(
            "() => document.getElementById('dpb-open-primary').classList.contains('is-armed')")
        captured_timeout = page.evaluate("() => window.__capturedSubmitter")
        stayed = page.url.startswith('file:')
        s17_ok = (
            armed and not armed_after_undo and captured_undo is None
            and armed_again and not armed_after_timeout
            and captured_timeout is None and stayed
        )
        print(
            f"  S17 pill arm undo: arm={armed} after_annotate={armed_after_undo} "
            f"rearm={armed_again} after_timeout={armed_after_timeout} "
            f"no_submit={captured_undo is None and captured_timeout is None} "
            f"-> {'OK' if s17_ok else 'FAIL'}"
        )
        if not s17_ok:
            failures.append(
                "S17: pill confirm arm must undo via annotate click and 4s timeout without submit"
            )

        # --- S18: footer decision controls expose non-empty consequence descriptions ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')
        page.click('#dpb-open-primary')
        page.wait_for_timeout(200)
        descs = page.evaluate("""() => {
          const pick = (sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            return (el.getAttribute('aria-description') || el.getAttribute('title') || '').trim();
          };
          return {
            abort: pick('#dpb-abort'),
            draft: pick('#dpb-draft'),
            confirm: pick('.dpb-drawer-foot .dpb-btn-primary'),
            revise: pick('.dpb-drawer-foot .dpb-btn-secondary'),
          };
        }""")
        s18_ok = all(
            isinstance(descs.get(k), str) and len(descs[k]) > 0
            for k in ("abort", "draft", "confirm", "revise")
        )
        # Descriptions must be pairwise distinct (different outcomes, not copy-paste)
        vals = [descs[k] for k in ("abort", "draft", "confirm", "revise")]
        s18_ok = s18_ok and len(set(vals)) == 4
        print(
            f"  S18 footer descs: abort={bool(descs.get('abort'))} "
            f"draft={bool(descs.get('draft'))} confirm={bool(descs.get('confirm'))} "
            f"revise={bool(descs.get('revise'))} distinct={len(set(vals)) == 4} "
            f"-> {'OK' if s18_ok else 'FAIL'}"
        )
        if not s18_ok:
            failures.append(
                "S18: abort/draft/confirm/revise must each expose a non-empty, distinct title/aria-description"
            )

        # --- S19: familiar control text is not prefixed by platform emoji ---
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-open-drawer')
        annotate_text = page.locator('#dpb-open-drawer').inner_text()
        annotate_html = page.locator('#dpb-open-drawer').inner_html()
        s19_ok = '💬' not in annotate_text and '💬' not in annotate_html
        print(
            "  S19 annotate control avoids platform emoji: "
            f"text={ascii(annotate_text)} -> {'OK' if s19_ok else 'FAIL'}"
        )
        if not s19_ok:
            failures.append("S19: annotate control should use stable text/control language, not platform emoji")

        # --- S20: control theme follows live host overrides and system changes ---
        page.emulate_media(color_scheme='dark')
        page.goto(file_url, wait_until='domcontentloaded')
        page.wait_for_selector('#dpb-preview-bar')

        def control_theme():
            return page.get_attribute('#dpb-preview-bar', 'data-theme')

        initial_theme = control_theme()
        page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        page.wait_for_timeout(100)
        host_light = control_theme()
        page.click('#dpb-open-primary')
        page.click('#dpb-pin-toggle')
        page.click('#hdr')
        page.wait_for_timeout(100)
        light_surface = page.evaluate("""() => ({
          barBg: getComputedStyle(document.getElementById('dpb-preview-bar'))
            .getPropertyValue('--dpb-bg').trim(),
          headerBg: getComputedStyle(document.querySelector('.dpb-drawer-head')).backgroundImage,
          floatTheme: document.getElementById('dpb-float-root')?.getAttribute('data-theme'),
        })""")
        page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        page.wait_for_timeout(100)
        host_dark = control_theme()
        float_dark = page.get_attribute('#dpb-float-root', 'data-theme')
        page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
        page.emulate_media(color_scheme='light')
        page.wait_for_timeout(100)
        system_light = control_theme()
        float_system_light = page.get_attribute('#dpb-float-root', 'data-theme')
        s20_ok = (
            initial_theme == 'dark'
            and host_light == 'light'
            and light_surface['barBg'] == '#ffffff'
            and 'rgb(243, 244, 246)' in light_surface['headerBg']
            and light_surface['floatTheme'] == 'light'
            and host_dark == 'dark'
            and float_dark == 'dark'
            and system_light == 'light'
            and float_system_light == 'light'
        )
        print(
            "  S20 live theme sync: "
            f"initial={initial_theme!r} host_light={host_light!r} "
            f"light_bg={light_surface['barBg']!r} "
            f"float={light_surface['floatTheme']!r}/{float_dark!r}/{float_system_light!r} "
            f"host_dark={host_dark!r} system_light={system_light!r} "
            f"-> {'OK' if s20_ok else 'FAIL'}"
        )
        if not s20_ok:
            failures.append(
                "S20: control surfaces and annotations must follow live host/system themes"
            )

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
