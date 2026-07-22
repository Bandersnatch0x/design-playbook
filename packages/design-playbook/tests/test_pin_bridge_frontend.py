#!/usr/bin/env python3
"""pin-to-annotate postMessage bridge e2e (headless playwright).

Verifies the G5 sandbox regression fix end-to-end. The prototype is isolated
inside ``<iframe sandbox="allow-scripts" srcdoc=...>`` (allow-same-origin
deliberately omitted), so the parent's ``document.click`` + ``cssPath`` can no
longer see clicks inside the iframe or traverse the iframe DOM (cross-origin,
opaque origin). The bridge injected into the srcdoc captures clicks inside the
iframe and postMessages ``{selector, tag}`` to the parent; the parent records
the anchor only while pin mode is on.

This drives the real sandbox path via ``browser._build_parent_page`` (not the
same-origin direct-embed path covered by test_floor_frontend.py, which builds
``proto.replace("</body>", control + "</body>")`` and exercises the parent's
own document.click listener).
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mcp" / "preview"))
import browser  # noqa: E402
import server  # noqa: E402
from i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROUND_N = 1
SUMMARY = "pin bridge e2e - sandbox iframe"
OPTIONS = default_options()

control = server._build_control(ROUND_N, SUMMARY, OPTIONS)

# Prototype with distinct anchorable elements (each has an id so cssPath
# short-circuits to a stable selector).
proto = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>pin bridge</title></head>
<body>
<h2 id="hdr">Run summary</h2>
<button id="action" class="btn-primary">Submit</button>
<p>some body text</p>
</body></html>"""

# Real sandbox path: prototype + bridge live inside the srcdoc of a sandboxed
# iframe; the control bar lives in the trusted parent.
full = browser._build_parent_page(proto, control)

tmp = Path(tempfile.mkdtemp())
page_path = tmp / "page.html"
page_path.write_text(full, encoding="utf-8")
file_url = page_path.as_uri()


def _hidden_anchors(page):
    return page.evaluate(
        "() => JSON.parse(document.getElementById('dpb-anchors-json').value || '[]')"
    )


def main():
    failures = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(file_url, wait_until="domcontentloaded")
        page.wait_for_selector("#dpb-preview-bar")

        # Frame locator into the sandboxed prototype iframe (opaque origin).
        proto_frame = page.frame_locator("iframe.dpb-proto-frame")

        def click_in_frame(sel):
            # Dispatch the click programmatically inside the iframe. The bridge
            # is a capture-phase document listener, so a synthetic el.click()
            # fires it. A real Playwright click() would instead resolve screen
            # coordinates that the parent's drawer overlay can intercept (the
            # drawer sits above the iframe); a human user simply clicks a
            # visible iframe element, so the overlay is a harness artifact, not
            # a bridge defect. Synthetic dispatch tests the actual bridge logic.
            proto_frame.locator(sel).evaluate("el => el.click()")

        # --- S1: pin on + click iframe element -> anchor collected in parent ---
        page.click("#dpb-open-primary")  # not substantive -> opens drawer
        page.wait_for_timeout(200)
        page.click("#dpb-pin-toggle")    # enable pin mode
        page.wait_for_timeout(150)
        click_in_frame("#hdr")        # click INSIDE the iframe
        page.wait_for_timeout(350)

        n_rows = page.eval_on_selector_all(
            "#dpb-anchors .dpb-anchor", "els => els.length"
        )
        hidden = _hidden_anchors(page)
        s1_ok = (
            n_rows == 1
            and len(hidden) == 1
            and hidden[0].get("selector") == "#hdr"
            and hidden[0].get("tag") == "h2"
            and hidden[0].get("label")  # labelForTag produced something
        )
        print(
            f"  S1 iframe click -> anchor: rows={n_rows} hidden={hidden} "
            f"-> {'OK' if s1_ok else 'FAIL'}"
        )
        if not s1_ok:
            failures.append(
                "S1: pin-on iframe click must produce one anchor "
                "(selector=#hdr, tag=h2, non-empty label) in the parent list"
            )

        # --- S2: el is null cross-origin; comment input still works + serializes
        comment_sel = ".dpb-anchor input, .dpb-anchor textarea"
        page.wait_for_selector(comment_sel)
        page.fill(comment_sel, "fix spacing on header")
        page.wait_for_timeout(150)
        hidden2 = _hidden_anchors(page)
        s2_ok = (
            len(hidden2) == 1
            and hidden2[0].get("comment") == "fix spacing on header"
        )
        print(
            f"  S2 comment on bridge anchor: comment="
            f"{hidden2[0].get('comment') if hidden2 else None!r} "
            f"-> {'OK' if s2_ok else 'FAIL'}"
        )
        if not s2_ok:
            failures.append(
                "S2: comment typed on a cross-origin anchor (el=null) must "
                "serialize into anchors_json"
            )

        # --- S3: second distinct iframe element -> second anchor ---
        click_in_frame("#action")
        page.wait_for_timeout(350)
        n3 = page.eval_on_selector_all(
            "#dpb-anchors .dpb-anchor", "els => els.length"
        )
        hidden3 = _hidden_anchors(page)
        s3_ok = (
            n3 == 2
            and len(hidden3) == 2
            and hidden3[1].get("selector") == "#action"
            and hidden3[1].get("tag") == "button"
        )
        print(
            f"  S3 second iframe element: rows={n3} "
            f"sel2={hidden3[1].get('selector') if len(hidden3) > 1 else None!r} "
            f"-> {'OK' if s3_ok else 'FAIL'}"
        )
        if not s3_ok:
            failures.append(
                "S3: second distinct iframe click must add a second anchor "
                "(selector=#action, tag=button)"
            )

        # --- S4: clicking the SAME element again de-dupes (no third row) ---
        click_in_frame("#action")
        page.wait_for_timeout(350)
        n4 = page.eval_on_selector_all(
            "#dpb-anchors .dpb-anchor", "els => els.length"
        )
        s4_ok = n4 == 2
        print(
            f"  S4 de-dupe same selector: rows={n4} "
            f"-> {'OK' if s4_ok else 'FAIL'}"
        )
        if not s4_ok:
            failures.append(
                "S4: clicking the same iframe element again must not duplicate "
                "the anchor (de-dupe by selector)"
            )

        # --- S5: pin OFF -> bridge message ignored (no new anchor) ---
        page.click("#dpb-pin-toggle")  # disable pin
        page.wait_for_timeout(150)
        click_in_frame("#hdr")
        page.wait_for_timeout(350)
        n5 = page.eval_on_selector_all(
            "#dpb-anchors .dpb-anchor", "els => els.length"
        )
        s5_ok = n5 == 2
        print(
            f"  S5 pin-off ignores bridge: rows={n5} "
            f"-> {'OK' if s5_ok else 'FAIL'}"
        )
        if not s5_ok:
            failures.append(
                "S5: with pin off, bridge postMessages must not add anchors "
                "(parent filters on pinOn)"
            )

        # --- S6: highlight CSS injected into iframe (dpb-pin-target on el) ---
        page.click("#dpb-pin-toggle")  # pin back on
        page.wait_for_timeout(150)
        click_in_frame("#hdr")
        page.wait_for_timeout(250)
        highlighted = proto_frame.locator("#hdr").evaluate(
            "el => el.classList.contains('dpb-pin-target')"
        )
        s6_ok = bool(highlighted)
        print(
            f"  S6 iframe self-highlight: dpb-pin-target={highlighted} "
            f"-> {'OK' if s6_ok else 'FAIL'}"
        )
        if not s6_ok:
            failures.append(
                "S6: bridge must add dpb-pin-target to the clicked element "
                "inside the iframe (in-frame highlight)"
            )

        b.close()

    print()
    if failures:
        print("PIN BRIDGE E2E TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PIN BRIDGE E2E TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
