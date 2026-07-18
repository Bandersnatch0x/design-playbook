#!/usr/bin/env python3
"""ADR-0008 frontend JS floor-intercept verification (headless).

Renders the adapter confirm page (prototype + injected control bar) and
drives three HITL-equivalent scenarios with playwright to verify the frontend
submit handler blocks empty confirms and allows substantive ones.
"""
import sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "design-playbook-preview"))
import server  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROUND_N = 1
SUMMARY = "verify run summary - list scene"
PRIMARY_OPT = "确认通过"
SECONDARY = ["需要修改"]
OPTIONS = [PRIMARY_OPT] + SECONDARY

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
