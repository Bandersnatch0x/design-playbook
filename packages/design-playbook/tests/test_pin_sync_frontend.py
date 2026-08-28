#!/usr/bin/env python3
"""#56/#57/#58 preview control state-machine tests (headless playwright).

Covers the behaviors the ticket briefs call out on the real G5 sandbox path
(prototype inside ``<iframe sandbox="allow-scripts" srcdoc=...>``):

- #56 the parent owns pinOn and syncs it into the bridge via postMessage;
  the bridge starts passive (pin off) and prototype clicks pass through
  until the user turns picking on.
- #57 scheme A: locate scrolls/flashes the element inside the iframe and the
  numbered anchor badges render inside the iframe (cross-origin).
- #58 collapsing the drawer keeps pin on (anchors survive, picking continues
  from the pill) and the scrim drops to near-transparent while picking.

Static bridge-protocol assertions complement the unit tests in
test_browser_control.py (which pin G5 safety + structural contracts).
"""
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.preview.i18n import default_options  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

# Same directory; pytest's prepend import mode and direct `python <file>` runs
# both put this directory on sys.path.
from preview_e2e_helpers import dismiss_onboarding  # noqa: E402

ROUND_N = 1
SUMMARY = "pin sync e2e - collapse keeps pin"
OPTIONS = default_options()

proto = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>pin sync</title></head>
<body>
<h2 id="hdr">Run summary</h2>
<button id="action" class="btn-primary">Submit</button>
<p>some body text</p>
</body></html>"""


# --------------------------------------------------------------------------- #
# Static bridge protocol assertions (#56 sync, #57 scheme A channels)         #
# --------------------------------------------------------------------------- #


def _bridge_inner_js() -> str:
    raw = review_session.BRIDGE_SCRIPT
    m = re.search(r"<script[^>]*>(.*)</script>\s*$", raw, re.DOTALL)
    assert m, f"BRIDGE_SCRIPT is not a single <script> block: {raw[:80]!r}"
    return m.group(1)


class BridgePinSyncProtocolTests(unittest.TestCase):
    """#56: the bridge is passive until the parent tells it pin is on.

    The parent owns pinOn; the bridge learns it only via ``dpbPinState``
    messages (plus a ``dpbPinHello`` resend request after (re)load) and gates
    its capture listeners on that state. #57 scheme A: the parent can drive
    locate/flash/badges inside the iframe via dpbPinLocate/dpbPinFlash/
    dpbPinAnchors.
    """

    def test_bridge_starts_passive_and_gates_capture_on_pin_state(self) -> None:
        js = _bridge_inner_js()
        # passive initial state: no interception before the first sync
        self.assertRegex(
            js, r"var pinOn\s*=\s*false",
            "bridge must initialize pinOn=false (passive until parent syncs)",
        )
        # state channel + hello resend request
        self.assertIn("dpbPinState", js, "bridge must consume dpbPinState")
        self.assertIn("dpbPinHello", js,
                      "bridge must request a state resend after (re)load")
        # capture listeners gated on pinOn (click + hover)
        self.assertIn("if (!pinOn) return;", js,
                      "bridge capture handlers must be gated on pinOn")

    def test_bridge_scheme_a_channels_present(self) -> None:
        js = _bridge_inner_js()
        self.assertIn("dpbPinLocate", js, "#57: locate channel missing")
        self.assertIn("dpbPinFlash", js, "#57: flash channel missing")
        self.assertIn("dpbPinAnchors", js, "#57: numbered-badge channel missing")
        self.assertIn("dpbPinNote", js,
                      "#57: incremental badge-note channel missing")
        self.assertIn("dpb-pin-badge", js,
                      "#57: badge rendering markup/class missing from bridge")
        # C2: strict shape check — array-ish objects must not slip through
        self.assertIn("Array.isArray(data.dpbPinAnchors)", js,
                      "C2: dpbPinAnchors must be validated with Array.isArray")

    def test_bridge_inbound_messages_are_source_checked(self) -> None:
        # W3: only the parent window may drive the bridge; prototype scripts
        # sharing the iframe window must not be able to spoof pin state.
        js = _bridge_inner_js()
        self.assertIn("e.source !== window.parent", js,
                      "W3: bridge must reject messages not from window.parent")

    def test_bridge_injected_styles_respect_reduced_motion(self) -> None:
        # W5: the flash animation injected into the iframe must degrade under
        # prefers-reduced-motion (host control.css only covers the parent).
        js = _bridge_inner_js()
        self.assertIn("@media (prefers-reduced-motion:reduce)", js)
        self.assertIn(".dpb-pin-flash,.dpb-draw-flash{animation:none!important}", js)
        self.assertIn(".dpb-pin-badge.dpb-pin-drop", js)
        self.assertIn(".dpb-pin-badge.dpb-active::after", js)

    def test_parent_control_js_drives_sync_channels(self) -> None:
        # v9 splits the parent script into control.js + control.review.js and
        # stitches them at the DPB_REVIEW_INSERT marker. Assert the assembled
        # bundle — what actually ships into the page — so moving a channel
        # between the two files cannot fail this while the feature still works,
        # and dropping one still fails it.
        _, _, js, _ = preview_control._load_resources()
        # #56: parent pushes pin state on toggle/load/hello
        self.assertIn("dpbPinState", js)
        self.assertIn("dpbPinHello", js)
        self.assertIn("syncPinToFrame", js)
        # #57: parent mirrors anchors as badges + locate fallback
        self.assertIn("dpbPinAnchors", js)
        self.assertIn("dpbPinLocate", js)
        self.assertIn("dpbPinFlash", js)
        # W2: hello handshake must resend the badges too, not only the pin
        # state (v9: the bridge posts hello on every (re)load; the parent
        # answers with pin state + draw state + anchors).
        hello_idx = js.index("data.dpbPinHello")
        self.assertIn("syncAnchorsToFrame()", js[hello_idx:hello_idx + 400],
                      "W2: hello resend must include dpbPinAnchors")
        # W3: the parent only accepts messages from its own prototype iframe
        self.assertIn("e.source !== srcFrame.contentWindow", js,
                      "W3: parent must source-check inbound pin messages")
        # #58: collapsing the inspector must NOT turn the pick tool off
        drawer_fn = re.search(
            r"function setDrawer\(open[^)]*\)\s*\{(.*?)\n  \}", js, re.DOTALL)
        self.assertIsNotNone(drawer_fn, "setDrawer not found in control.js")
        self.assertNotIn("setTool(", drawer_fn.group(1),
                         "#58: setDrawer must keep the active tool on")


# --------------------------------------------------------------------------- #
# E2E: real sandbox path through review_session.collect_review                #
# --------------------------------------------------------------------------- #


class _PlaywrightPinSyncAdapter:
    """Drive one review session and retain per-step observations."""

    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None
        self.obs: dict[str, object] = {}

    def open(self, url: str) -> object:
        def drive() -> None:
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(url, wait_until="domcontentloaded")
                        page.wait_for_selector("#dpb-root")
                        page.wait_for_timeout(600)
                        # Real pointer clicks below (#dpb-mode-preview) are
                        # swallowed by the full-viewport onboarding scrim.
                        dismiss_onboarding(page)
                        proto_frame = page.frame_locator("iframe.dpb-proto-frame")

                        def hidden() -> list[dict]:
                            return page.evaluate(
                                "() => JSON.parse(document.getElementById("
                                "'dpb-anchors-json').value || '[]')"
                            )

                        # --- #56 passive bridge: pin off, click passes through
                        # v9 boots in annotate+select (pin ON); preview mode
                        # deactivates the pick channel for the passive check.
                        page.click("#dpb-mode-preview")
                        page.wait_for_timeout(200)
                        proto_frame.locator("#hdr").evaluate("el => el.click()")
                        page.wait_for_timeout(300)
                        self.obs["passive_rows"] = len(hidden())
                        self.obs["passive_highlight"] = bool(
                            proto_frame.locator("#hdr").evaluate(
                                "el => el.classList.contains('dpb-pin-target')")
                        )

                        # --- back to annotate: the pick channel re-engages
                        page.click("#dpb-mode-annotate")
                        page.wait_for_timeout(200)
                        self.obs["pin_aria"] = page.get_attribute(
                            "#dpb-pin-toggle", "aria-pressed")

                        # --- W3: spoofed dpbPinAnchor from the host page is dropped
                        page.evaluate(
                            "() => window.postMessage("
                            "{dpbPinAnchor: {selector: '#spoof', tag: 'div'}},"
                            " '*')")
                        page.wait_for_timeout(200)
                        self.obs["rows_after_spoof"] = len(hidden())

                        proto_frame.locator("#hdr").evaluate("el => el.click()")
                        page.wait_for_timeout(300)
                        self.obs["on_rows"] = len(hidden())

                        # --- #58 collapse the inspector; the pick tool stays on
                        page.click("#dpb-inspector-close")
                        page.wait_for_timeout(250)
                        self.obs["pin_after_collapse"] = page.evaluate(
                            "() => document.getElementById('dpb-pin-toggle')"
                            ".getAttribute('aria-pressed') === 'true'")
                        self.obs["drawer_open_after_collapse"] = page.evaluate(
                            "() => !document.getElementById('dpb-inspector')"
                            ".classList.contains('dpb-collapsed')")

                        # picking continues from the collapsed pill
                        proto_frame.locator("#action").evaluate("el => el.click()")
                        page.wait_for_timeout(300)
                        self.obs["rows_after_collapse_pick"] = len(hidden())

                        # --- reopen the inspector via the right-edge tab
                        page.click("#dpb-reopen-tab")
                        page.wait_for_timeout(250)

                        # --- #57 scheme A: badge mirrors into the iframe
                        page.wait_for_selector(
                            '.dpb-anchor input, .dpb-anchor textarea')
                        page.fill('#dpb-anchors input[data-i="0"]',
                                  "tighten header spacing")
                        page.fill('#dpb-anchors input[data-i="1"]',
                                  "clarify action label")
                        page.wait_for_timeout(250)
                        self.obs["badge_count"] = proto_frame.locator(
                            ".dpb-pin-badge").count()
                        self.obs["badge_first_text"] = (
                            proto_frame.locator(".dpb-pin-badge").first
                            .inner_text() if self.obs["badge_count"] else "")

                        # --- #57 scheme A: locate flashes inside the iframe
                        # (v9: clicking a card row focuses + locates the anchor)
                        page.click(
                            "#dpb-anchors .dpb-anchor:nth-of-type(2) "
                            ".dpb-anchor-meta")
                        page.wait_for_timeout(300)
                        self.obs["locate_flash"] = bool(
                            proto_frame.locator("#action").evaluate(
                                "el => el.classList.contains('dpb-pin-flash')")
                        )

                        # --- W4: live region stays mounted while drawer is open
                        self.obs["drawer_open_w4"] = page.evaluate(
                            "() => !document.getElementById('dpb-inspector')"
                            ".classList.contains('dpb-collapsed')")
                        self.obs["announce_mounted"] = page.evaluate(
                            "() => { const a = document.getElementById("
                            "'dpb-announce'); return !!(a && a.isConnected && "
                            "a.parentElement && a.parentElement.id === "
                            "'dpb-root'); }")

                        # --- W2: hello handshake rebuilds the iframe badges.
                        # A (re)loaded iframe boots with an empty bridge state;
                        # simulate that loss, then answer the hello resend.
                        proto_doc = next(
                            f for f in page.frames
                            if f is not page.main_frame)
                        proto_doc.evaluate(
                            "() => document.querySelectorAll('.dpb-pin-badge,"
                            ".dpb-pin-badge-note')"
                            ".forEach(n => n.remove())")
                        self.obs["badges_lost"] = bool(proto_doc.evaluate(
                            "() => !document.querySelector('.dpb-pin-badge')"))
                        proto_doc.evaluate(
                            "() => window.parent.postMessage("
                            "{dpbPinHello: true}, '*')")
                        page.wait_for_timeout(400)
                        self.obs["badge_count_after_reload"] = int(
                            proto_doc.evaluate(
                                "() => document.querySelectorAll("
                                "'.dpb-pin-badge').length"))

                        # --- #57: removing anchors must clear the in-iframe
                        # badges AND the highlight; the empty list must reach
                        # the bridge (not be swallowed by an early return).
                        page.click('.dpb-anchor-rm[data-rm="0"]')
                        page.wait_for_timeout(300)
                        self.obs["rows_after_rm1"] = len(hidden())
                        self.obs["badges_after_rm1"] = int(
                            proto_doc.evaluate(
                                "() => document.querySelectorAll("
                                "'.dpb-pin-badge').length"))
                        self.obs["highlight_after_rm1"] = bool(
                            proto_doc.evaluate(
                                "() => document.querySelector('#hdr')"
                                ".classList.contains('dpb-pin-target')"))
                        page.click('.dpb-anchor-rm[data-rm="0"]')
                        page.wait_for_timeout(300)
                        self.obs["rows_after_rm2"] = len(hidden())
                        self.obs["badges_after_rm2"] = int(
                            proto_doc.evaluate(
                                "() => document.querySelectorAll("
                                "'.dpb-pin-badge').length"))
                        self.obs["highlight_after_rm2"] = bool(
                            proto_doc.evaluate(
                                "() => document.querySelector('#action')"
                                ".classList.contains('dpb-pin-target')"))

                        # --- undo both removals: anchors, badges and the
                        # highlight come back through the full resync.
                        page.keyboard.press("Control+z")
                        page.wait_for_timeout(300)
                        page.keyboard.press("Control+z")
                        page.wait_for_timeout(400)
                        self.obs["rows_after_undo"] = len(hidden())
                        self.obs["badges_after_undo"] = int(
                            proto_doc.evaluate(
                                "() => document.querySelectorAll("
                                "'.dpb-pin-badge').length"))
                        self.obs["highlight_after_undo"] = bool(
                            proto_doc.evaluate(
                                "() => document.querySelector('#hdr')"
                                ".classList.contains('dpb-pin-target')"))

                        with page.expect_response(
                            lambda response: response.url.endswith("/decide")
                            and response.request.method == "POST"
                        ):
                            page.click("#dpb-btn-approve")
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
        self.thread.join(timeout=25)
        if self.thread.is_alive():
            raise AssertionError("Playwright pin-sync adapter did not finish")
        if self.error is not None:
            raise self.error


def main():
    failures = []
    adapter = _PlaywrightPinSyncAdapter()
    tmp = Path(tempfile.mkdtemp())
    prototype = tmp / "prototype.html"
    prototype.write_text(proto, encoding="utf-8")
    decision = review_session.collect_review(
        prototype, SUMMARY, OPTIONS, ROUND_N, adapter
    )
    obs = adapter.obs

    passive_ok = (obs.get("passive_rows") == 0
                  and obs.get("passive_highlight") is False)
    print(
        f"  S1 #56 passive bridge (pin off): rows={obs.get('passive_rows')} "
        f"highlight={obs.get('passive_highlight')} "
        f"-> {'OK' if passive_ok else 'FAIL'}")
    if not passive_ok:
        failures.append(
            "S1: with pin off the bridge must not intercept or highlight "
            "prototype clicks (passive start)")

    on_ok = obs.get("on_rows") == 1 and obs.get("pin_aria") == "true"
    print(
        f"  S2 #56 pin-on intercept: rows={obs.get('on_rows')} "
        f"aria-pressed={obs.get('pin_aria')} -> {'OK' if on_ok else 'FAIL'}")
    if not on_ok:
        failures.append(
            "S2: toggling pin on must sync into the bridge and intercept "
            "iframe clicks immediately")

    collapse_ok = (
        obs.get("pin_after_collapse") is True
        and obs.get("drawer_open_after_collapse") is False
    )
    print(
        f"  S3 #58 collapse keeps pin: pin={obs.get('pin_after_collapse')} "
        f"drawer_closed={not obs.get('drawer_open_after_collapse')} "
        f"-> {'OK' if collapse_ok else 'FAIL'}")
    if not collapse_ok:
        failures.append(
            "S3: collapsing the inspector must keep the pick tool on "
            "without closing the session")

    pick_ok = obs.get("rows_after_collapse_pick") == 2
    print(
        f"  S4 #58 picking from collapsed pill: "
        f"rows={obs.get('rows_after_collapse_pick')} "
        f"-> {'OK' if pick_ok else 'FAIL'}")
    if not pick_ok:
        failures.append(
            "S4: element picking must continue while the drawer is collapsed")

    badge_ok = (obs.get("badge_count") == 2
                and str(obs.get("badge_first_text", "")).strip().startswith("1"))
    print(
        f"  S6 #57 badges inside iframe: count={obs.get('badge_count')} "
        f"first={obs.get('badge_first_text')!r} "
        f"-> {'OK' if badge_ok else 'FAIL'}")
    if not badge_ok:
        failures.append(
            "S6: anchor list must mirror into the iframe as numbered badges")

    locate_ok = obs.get("locate_flash") is True
    print(
        f"  S7 #57 locate flashes in iframe: flash={obs.get('locate_flash')} "
        f"-> {'OK' if locate_ok else 'FAIL'}")
    if not locate_ok:
        failures.append(
            "S7: locate on a cross-origin anchor must flash the element "
            "inside the iframe")

    spoof_ok = (obs.get("rows_after_spoof") == 0)
    print(
        f"  S9 W3 spoofed message rejected: "
        f"rows={obs.get('rows_after_spoof')} "
        f"-> {'OK' if spoof_ok else 'FAIL'}")
    if not spoof_ok:
        failures.append(
            "S9: a dpbPinAnchor posted from outside the prototype iframe must "
            "be rejected (source check)")

    w4_ok = (obs.get("drawer_open_w4") is True
             and obs.get("announce_mounted") is True)
    print(
        f"  S10 W4 announce live region stays mounted: "
        f"drawer_open={obs.get('drawer_open_w4')} "
        f"mounted={obs.get('announce_mounted')} "
        f"-> {'OK' if w4_ok else 'FAIL'}")
    if not w4_ok:
        failures.append(
            "S10: #dpb-announce must stay in the accessibility tree while "
            "the inspector is open (direct child of #dpb-root)")

    reload_ok = (obs.get("badges_lost") is True
                 and obs.get("badge_count_after_reload") == 2)
    print(
        f"  S11 W2 badges rebuilt after iframe reload: "
        f"count={obs.get('badge_count_after_reload')} "
        f"-> {'OK' if reload_ok else 'FAIL'}")
    if not reload_ok:
        failures.append(
            "S11: the dpbPinHello resend must restore the numbered badges "
            "(dpbPinAnchors) after the iframe lost its bridge state")

    rm1_ok = (obs.get("rows_after_rm1") == 1
              and obs.get("badges_after_rm1") == 1
              and obs.get("highlight_after_rm1") is False)
    print(
        f"  S12 #57 removal clears badge + highlight: "
        f"rows={obs.get('rows_after_rm1')} "
        f"badges={obs.get('badges_after_rm1')} "
        f"highlight={obs.get('highlight_after_rm1')} "
        f"-> {'OK' if rm1_ok else 'FAIL'}")
    if not rm1_ok:
        failures.append(
            "S12: removing an anchor must clear its iframe badge and its "
            "dpb-pin-target highlight")

    rm2_ok = (obs.get("rows_after_rm2") == 0
              and obs.get("badges_after_rm2") == 0
              and obs.get("highlight_after_rm2") is False)
    print(
        f"  S13 #57 remove-to-empty clears all: "
        f"rows={obs.get('rows_after_rm2')} "
        f"badges={obs.get('badges_after_rm2')} "
        f"highlight={obs.get('highlight_after_rm2')} "
        f"-> {'OK' if rm2_ok else 'FAIL'}")
    if not rm2_ok:
        failures.append(
            "S13: removing the last anchor must clear every iframe badge "
            "and highlight (empty list reaches the bridge)")

    undo_ok = (obs.get("rows_after_undo") == 2
               and obs.get("badges_after_undo") == 2
               and obs.get("highlight_after_undo") is True)
    print(
        f"  S14 undo restores anchors + badges + highlight: "
        f"rows={obs.get('rows_after_undo')} "
        f"badges={obs.get('badges_after_undo')} "
        f"highlight={obs.get('highlight_after_undo')} "
        f"-> {'OK' if undo_ok else 'FAIL'}")
    if not undo_ok:
        failures.append(
            "S14: undoing the removals must restore the anchors, badges and "
            "highlights through the full resync")

    if adapter.error is not None:
        failures.append(f"adapter: {adapter.error}")
    if decision.get("aborted") or not decision.get("choice"):
        failures.append(f"review session did not confirm: {decision}")

    print()
    if failures:
        print("PIN SYNC E2E TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PIN SYNC E2E TEST PASSED")
    return 0


if __name__ == "__main__":
    # direct run: static protocol assertions first, then the playwright e2e
    suite_result = unittest.main(exit=False).result
    if not suite_result.wasSuccessful():
        sys.exit(1)
    sys.exit(main())
