#!/usr/bin/env python3
"""pin-to-annotate postMessage bridge e2e (headless playwright).

Verifies the G5 sandbox regression fix end-to-end. The prototype is isolated
inside ``<iframe sandbox="allow-scripts" srcdoc=...>`` (allow-same-origin
deliberately omitted), so the parent's ``document.click`` + ``cssPath`` can no
longer see clicks inside the iframe or traverse the iframe DOM (cross-origin,
opaque origin). The bridge injected into the srcdoc captures clicks inside the
iframe and postMessages ``{selector, tag}`` to the parent; the parent records
the anchor only while pin mode is on.

This drives the real sandbox path through ``review_session.collect_review``
with a Playwright ``BrowserInteraction`` adapter. The same-origin direct-embed
path covered by test_floor_frontend.py remains a separate frontend test.
"""
import sys
import tempfile
import threading
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ROUND_N = 1
SUMMARY = "pin bridge e2e - sandbox iframe"
OPTIONS = default_options()

# Prototype with distinct anchorable elements (each has an id so cssPath
# short-circuits to a stable selector).
proto = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>pin bridge</title></head>
<body>
<h2 id="hdr">Run summary</h2>
<button id="action" class="btn-primary">Submit</button>
<p>some body text</p>
</body></html>"""

class _PlaywrightPinAdapter:
    """Drive the public review session and retain bridge observations."""

    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None
        self.snapshots: dict[str, list[dict]] = {}
        self.comment = ""
        self.highlighted = False

    def open(self, url: str) -> object:
        def drive() -> None:
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(url, wait_until="domcontentloaded")
                        page.wait_for_selector("#dpb-preview-bar")
                        proto_frame = page.frame_locator("iframe.dpb-proto-frame")

                        def hidden() -> list[dict]:
                            return page.evaluate(
                                "() => JSON.parse(document.getElementById('dpb-anchors-json').value || '[]')"
                            )

                        def record(name: str) -> None:
                            self.snapshots[name] = hidden()

                        page.click("#dpb-open-primary")
                        page.wait_for_timeout(200)
                        page.click("#dpb-pin-toggle")
                        page.wait_for_timeout(150)
                        proto_frame.locator("#hdr").evaluate("el => el.click()")
                        page.wait_for_timeout(350)
                        record("s1")

                        page.wait_for_selector(".dpb-anchor input, .dpb-anchor textarea")
                        page.fill(".dpb-anchor input, .dpb-anchor textarea", "fix spacing on header")
                        page.wait_for_timeout(150)
                        self.comment = hidden()[0].get("comment", "")

                        proto_frame.locator("#action").evaluate("el => el.click()")
                        page.wait_for_timeout(350)
                        record("s3")
                        page.fill(
                            '#dpb-anchors input[data-i="1"]',
                            "clarify action label",
                        )
                        proto_frame.locator("#action").evaluate("el => el.click()")
                        page.wait_for_timeout(350)
                        record("s4")

                        page.click("#dpb-pin-toggle")
                        page.wait_for_timeout(150)
                        proto_frame.locator("#hdr").evaluate("el => el.click()")
                        page.wait_for_timeout(350)
                        record("s5")

                        page.click("#dpb-pin-toggle")
                        page.wait_for_timeout(150)
                        proto_frame.locator("#hdr").evaluate("el => el.click()")
                        page.wait_for_timeout(250)
                        self.highlighted = bool(
                            proto_frame.locator("#hdr").evaluate(
                                "el => el.classList.contains('dpb-pin-target')"
                            )
                        )
                        record("s6")
                        with page.expect_response(
                            lambda response: response.url.endswith("/decide")
                            and response.request.method == "POST"
                        ):
                            page.click(".dpb-drawer .dpb-btn-primary")
                    finally:
                        browser.close()
            except Exception as exc:  # noqa: BLE001
                self.error = exc

        self.thread = threading.Thread(target=drive, daemon=True)
        self.thread.start()
        return self

    def close(self, handle: object) -> None:
        assert handle is self
        assert self.thread is not None
        self.thread.join(timeout=20)
        if self.thread.is_alive():
            raise AssertionError("Playwright pin adapter did not finish")
        if self.error is not None:
            raise self.error


def main():
    failures = []
    adapter = _PlaywrightPinAdapter()
    tmp = Path(tempfile.mkdtemp())
    prototype = tmp / "prototype.html"
    prototype.write_text(proto, encoding="utf-8")
    decision = review_session.collect_review(
        prototype, SUMMARY, OPTIONS, ROUND_N, adapter
    )

    hidden = adapter.snapshots.get("s1", [])
    n_rows = len(hidden)
    s1_ok = (
        n_rows == 1
        and hidden[0].get("selector") == "#hdr"
        and hidden[0].get("tag") == "h2"
        and hidden[0].get("label")
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

    s2_ok = adapter.comment == "fix spacing on header"
    print(
        f"  S2 comment on bridge anchor: comment={adapter.comment!r} "
        f"-> {'OK' if s2_ok else 'FAIL'}"
    )
    if not s2_ok:
        failures.append(
            "S2: comment typed on a cross-origin anchor must serialize"
        )

    hidden3 = adapter.snapshots.get("s3", [])
    n3 = len(hidden3)
    s3_ok = (
        n3 == 2
        and hidden3[1].get("selector") == "#action"
        and hidden3[1].get("tag") == "button"
    )
    print(
        f"  S3 second iframe element: rows={n3} "
        f"sel2={hidden3[1].get('selector') if len(hidden3) > 1 else None!r} "
        f"-> {'OK' if s3_ok else 'FAIL'}"
    )
    if not s3_ok:
        failures.append("S3: second distinct iframe click must add a second anchor")

    n4 = len(adapter.snapshots.get("s4", []))
    s4_ok = n4 == 2
    print(f"  S4 de-dupe same selector: rows={n4} -> {'OK' if s4_ok else 'FAIL'}")
    if not s4_ok:
        failures.append("S4: clicking the same iframe element again must not duplicate")

    n5 = len(adapter.snapshots.get("s5", []))
    s5_ok = n5 == 2
    print(f"  S5 pin-off ignores bridge: rows={n5} -> {'OK' if s5_ok else 'FAIL'}")
    if not s5_ok:
        failures.append("S5: pin-off bridge messages must not add anchors")

    s6_ok = adapter.highlighted
    print(
        f"  S6 iframe self-highlight: dpb-pin-target={adapter.highlighted} "
        f"-> {'OK' if s6_ok else 'FAIL'}"
    )
    if not s6_ok:
        failures.append("S6: bridge must add dpb-pin-target to the clicked element")

    return_code = 0
    if adapter.error is not None:
        failures.append(f"adapter: {adapter.error}")
    if decision.get("aborted") or not decision.get("choice"):
        failures.append(f"review session did not confirm: {decision}")

    print()
    if failures:
        print("PIN BRIDGE E2E TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PIN BRIDGE E2E TEST PASSED")
    return return_code


if __name__ == "__main__":
    sys.exit(main())
