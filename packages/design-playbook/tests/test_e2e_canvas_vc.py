#!/usr/bin/env python3
"""E2E: real-browser full flow for the canvas-upgrade (wayfinder 08).

Playwright drives a real Chromium against a real preview HTTP server; the
human-equivalent confirm lands in ``transaction.run_preview_transaction``
(html mode, preview_dir pinned to a temp dir) so the durable artifacts are
real. The version-control APIs (versions.py) then consume those artifacts:

    canvas open -> pin anchor -> feedback -> confirm (floor pass) ->
    named version -> timeline -> state_at -> fork

plus frontend interaction improvements (07): Ctrl/Cmd+Z undo and draft
persistence across reload (file:// scenarios, mirroring test_floor_frontend).
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview import versions  # noqa: E402
from design_playbook.mcp.preview.i18n import default_options  # noqa: E402

try:
    from playwright.sync_api import sync_playwright  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - environment marker
    sync_playwright = None

# Same directory; pytest's prepend import mode and direct `python <file>` runs
# both put this directory on sys.path.
from preview_e2e_helpers import dismiss_onboarding as _dismiss_onboarding  # noqa: E402

SUMMARY = "e2e full flow"
ROUND_N = 1
OPTIONS = default_options()


PROTO = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>e2e canvas</title></head>
<body>
<h2 id="hdr">Run summary</h2>
<p class="card">An anchorable paragraph</p>
<button id="act">Do it</button>
</body></html>"""


class _PlaywrightReviewAdapter:
    """BrowserInteraction adapter that drives the real review interface."""

    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None

    def open(self, url: str) -> object:
        def drive() -> None:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(url)
                        page.wait_for_selector("#dpb-root")
                        _dismiss_onboarding(page)
                        page.frame_locator("iframe.dpb-proto-frame").locator("#hdr").click()
                        page.wait_for_selector("#dpb-anchors .dpb-anchor")
                        page.fill('#dpb-anchors input[data-i="0"]', "tighten spacing")
                        page.fill('textarea[name="feedback"]', "looks good, ship it")
                        page.click("#dpb-btn-approve")
                        page.wait_for_load_state("domcontentloaded")
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
            raise AssertionError("Playwright review adapter did not finish")
        if self.error is not None:
            raise self.error


class E2EFullFlowTests(unittest.TestCase):
    def test_real_browser_full_flow_and_vc(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        def collect(
            prototype: Path,
            summary: str,
            options: list[str],
            round_n: int,
            *,
            criteria: list[dict[str, str]],
        ) -> dict:
            return review_session.collect_review(
                prototype,
                summary,
                options,
                round_n,
                _PlaywrightReviewAdapter(),
                criteria=criteria,
            )
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            with mock.patch.object(
                transaction, "_preview_dir_for", return_value=preview_dir
            ):
                decision = transaction.run_preview_transaction(
                    path_arg=None, html=PROTO, summary=SUMMARY, round_n=ROUND_N,
                    report_ref="r.md", options=OPTIONS, collect=collect)

            # durable artifacts are real
            entry = json.loads(
                (preview_dir / "decision-round-1.json").read_text(encoding="utf-8"))
            confirm = json.loads(
                (preview_dir / "confirm-round-1.json").read_text(encoding="utf-8"))
            self.assertTrue(decision["confirmed"])
            self.assertTrue(decision["floor_pass"])
            self.assertEqual(entry["outcome"]["confirmed"], True)
            self.assertEqual(confirm["confirmed"], True)
            self.assertTrue((preview_dir / "round-1.html").is_file())
            log = (preview_dir / "log.md").read_text(encoding="utf-8")
            self.assertIn("## round 1", log)

            # anchors carry v2 node_id/features (05b)
            anchor = decision["anchors"][0]
            self.assertEqual(anchor["selector"], "#hdr")
            self.assertIn("node_id", anchor)
            self.assertEqual(anchor["features"]["tag"], "h2")

            # 5. named version (05a) -> version-1.json + log section
            v1 = versions.create_named_version(
                preview_dir, round_n=1, name="确认版·e2e", kind="confirmed")
            self.assertEqual(v1["seq"], 1)
            log2 = (preview_dir / "log.md").read_text(encoding="utf-8")
            self.assertIn("## versions", log2)
            self.assertIn("确认版·e2e", log2)

            # 6. timeline = decision + version
            items = versions.timeline(preview_dir)
            self.assertEqual([i["event_type"] for i in items],
                             ["decision", "version"])

            # 7. state_at replay (html mode)
            state = versions.state_at(preview_dir, 1)
            self.assertEqual(state["prototype_html"], PROTO)
            self.assertEqual([v["name"] for v in state["versions"]],
                             ["确认版·e2e"])

            # 8. fork from round 1 -> independent chain
            fork_dir = preview_dir / "fork-alt"
            fork = versions.fork(
                preview_dir, branch="alt", from_round=1, new_dir=fork_dir,
                report_ref="alt.md", summary="备选方案")
            self.assertEqual(fork["fork"]["forked_from_round"], 1)
            self.assertEqual(
                (fork_dir / "round-1.html").read_text(encoding="utf-8"), PROTO)
            self.assertTrue((fork_dir / "fork.json").is_file())
class FrontendInteractionTests(unittest.TestCase):
    """Undo (07) and draft persistence (07) — file:// scenarios."""

    def _page(self, p):
        control = preview_control._build_control(1, "interaction", OPTIONS)
        proto = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
        <title>i</title></head><body>
        <h2 id="a">Alpha</h2><p id="b">Beta</p></body></html>"""
        full = proto.replace("</body>", control + "</body>", 1)
        # mkdtemp (not TemporaryDirectory): the dir must outlive the page for
        # reload-based draft persistence tests.
        tmp = Path(tempfile.mkdtemp(prefix="dpb-e2e-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = tmp / "page.html"
        path.write_text(full, encoding="utf-8")
        page = p.new_page()
        page.goto(path.as_uri())
        return page

    def test_undo_removes_last_anchor(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        with sync_playwright() as p:
            pw = p.chromium.launch(headless=True)
            try:
                page = self._page(pw)
                page.wait_for_selector("#dpb-root")
                _dismiss_onboarding(page)
                page.click("#a")
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                page.evaluate(
                    """() => {
                        document.querySelector('#b').click();
                        document.querySelector('#dpb-undo-btn').focus();
                        return new Promise(resolve => setTimeout(resolve, 0));
                    }"""
                )
                page.wait_for_function(
                    "document.querySelectorAll('#dpb-anchors .dpb-anchor').length === 2")
                # Ctrl/Cmd+Z undoes the second pin
                self.assertEqual(
                    page.evaluate("document.activeElement.id"),
                    "dpb-undo-btn",
                )
                page.keyboard.press("Control+Z")
                page.wait_for_function(
                    "document.querySelectorAll('#dpb-anchors .dpb-anchor').length === 1")
                self.assertEqual(
                    page.locator("#dpb-anchors .dpb-anchor").count(), 1)
                self.assertTrue(page.locator("#a").evaluate(
                    "el => el.classList.contains('dpb-pin-target')"))
                self.assertFalse(page.locator("#b").evaluate(
                    "el => el.classList.contains('dpb-pin-target')"))
            finally:
                pw.close()

    def test_comment_input_uses_native_undo_without_removing_anchor(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        with sync_playwright() as p:
            pw = p.chromium.launch(headless=True)
            try:
                page = self._page(pw)
                page.wait_for_selector("#dpb-root")
                _dismiss_onboarding(page)
                page.click("#a")
                comment = page.locator('#dpb-anchors input[data-i="0"]')
                comment.press_sequentially("draft comment")

                page.keyboard.press("Control+Z")

                self.assertEqual(
                    page.locator("#dpb-anchors .dpb-anchor").count(), 1)
                self.assertNotEqual(comment.input_value(), "draft comment")
            finally:
                pw.close()

    def test_undo_restores_committed_comment_without_removing_anchor(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        with sync_playwright() as p:
            pw = p.chromium.launch(headless=True)
            try:
                page = self._page(pw)
                page.wait_for_selector("#dpb-root")
                _dismiss_onboarding(page)
                page.click("#a")
                comment = page.locator('#dpb-anchors input[data-i="0"]')
                comment.fill("before")
                page.locator("#dpb-undo-btn").focus()
                comment.fill("after")
                page.locator("#dpb-undo-btn").focus()

                page.keyboard.press("Control+Z")

                self.assertEqual(
                    page.locator("#dpb-anchors .dpb-anchor").count(), 1)
                self.assertEqual(
                    page.input_value('#dpb-anchors input[data-i="0"]'),
                    "before",
                )
            finally:
                pw.close()

    def test_draft_persists_across_reload(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        with sync_playwright() as p:
            pw = p.chromium.launch(headless=True)
            try:
                page = self._page(pw)
                page.wait_for_selector("#dpb-root")
                _dismiss_onboarding(page)
                page.click("#a")
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                page.fill('#dpb-anchors input[data-i="0"]', "草稿评论")
                page.fill('textarea[name="feedback"]', "草稿反馈")
                # reload -> draft restored (per-run localStorage key)
                page.reload()
                page.wait_for_selector("#dpb-root")
                restored = page.input_value('textarea[name="feedback"]')
                self.assertEqual(restored, "草稿反馈")
                _dismiss_onboarding(page)
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                self.assertEqual(
                    page.input_value('#dpb-anchors input[data-i="0"]'), "草稿评论")
            finally:
                pw.close()

    def test_draw_mode_records_stroke_anchor(self) -> None:
        """Same-doc draw: stroke on the parent layer -> draw anchor + points."""
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        with sync_playwright() as p:
            pw = p.chromium.launch(headless=True)
            try:
                page = self._page(pw)
                _dismiss_onboarding(page)
                page.click("#dpb-draw-toggle")  # draw mode on (pin off)
                self.assertTrue(
                    page.evaluate("() => document.body.classList.contains('dpb-tool-draw')"))
                # freehand stroke over the prototype area (clear of the
                # onboarding card at top-left and the right drawer rail)
                page.mouse.move(440, 320)
                page.mouse.down()
                page.mouse.move(560, 360, steps=3)
                page.mouse.move(500, 420, steps=3)
                page.mouse.move(440, 320, steps=3)
                page.mouse.up()
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                anchors = page.evaluate(
                    "() => JSON.parse(document.getElementById('dpb-anchors-json').value || '[]')")
                self.assertEqual(len(anchors), 1)
                self.assertEqual(anchors[0]["tag"], "draw")
                self.assertTrue(anchors[0]["selector"].startswith("@draw-"))
                self.assertGreaterEqual(len(anchors[0]["points"]), 4)
                # stroke + numbered badge rendered on the parent SVG layer
                self.assertGreaterEqual(
                    page.locator("#dpb-draw-layer .dpb-draw-path").count(), 1)
                self.assertGreaterEqual(
                    page.locator("#dpb-draw-layer .dpb-draw-badge").count(), 1)
                # comment flows through the ordinary anchor row
                page.fill('#dpb-anchors input[data-i="0"]', "圈出标题区域")
                anchors2 = page.evaluate(
                    "() => JSON.parse(document.getElementById('dpb-anchors-json').value || '[]')")
                self.assertEqual(anchors2[0]["comment"], "圈出标题区域")
                # Esc exits draw mode; the stroke stays
                page.locator("#dpb-undo-btn").focus()
                page.keyboard.press("Escape")
                self.assertFalse(
                    page.evaluate("() => document.body.classList.contains('dpb-tool-draw')"))
                self.assertGreaterEqual(
                    page.locator("#dpb-draw-layer .dpb-draw-path").count(), 1)
            finally:
                pw.close()

    def test_draw_mode_bridge_stroke_in_iframe(self) -> None:
        """Sandbox path: the bridge captures the stroke, the anchor round-trips
        through the transaction with its points."""
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")

        class _DrawAdapter:
            def __init__(self) -> None:
                self.thread = None
                self.error = None

            def open(self, url: str) -> object:
                def drive() -> None:
                    try:
                        with sync_playwright() as q:
                            browser = q.chromium.launch(headless=True)
                            try:
                                page = browser.new_page()
                                page.goto(url)
                                page.wait_for_selector("#dpb-root")
                                _dismiss_onboarding(page)
                                page.click("#dpb-draw-toggle")
                                page.wait_for_timeout(200)
                                # stroke over the iframe area (bridge captures);
                                # clear of the onboarding card and drawer rail
                                page.mouse.move(440, 320)
                                page.mouse.down()
                                page.mouse.move(560, 360, steps=3)
                                page.mouse.move(500, 420, steps=3)
                                page.mouse.move(440, 320, steps=3)
                                page.mouse.up()
                                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                                page.fill('#dpb-anchors input[data-i="0"]', "圈出主区域")
                                page.fill('textarea[name="feedback"]', "整体走查通过")
                                page.click("#dpb-btn-approve")
                                page.wait_for_load_state("domcontentloaded")
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
                self.thread.join(timeout=30)
                if self.thread.is_alive():
                    raise AssertionError("draw adapter did not finish")
                if self.error is not None:
                    raise self.error

        def collect(
            prototype: Path,
            summary: str,
            options: list[str],
            round_n: int,
            *,
            criteria: list[dict[str, str]],
        ) -> dict:
            return review_session.collect_review(
                prototype,
                summary,
                options,
                round_n,
                _DrawAdapter(),
                criteria=criteria,
            )

        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            with mock.patch.object(
                transaction, "_preview_dir_for", return_value=preview_dir
            ):
                decision = transaction.run_preview_transaction(
                    path_arg=None, html=PROTO, summary=SUMMARY, round_n=ROUND_N,
                    report_ref="r.md", options=OPTIONS, collect=collect)
            self.assertTrue(decision["confirmed"])
            anchor = decision["anchors"][0]
            self.assertEqual(anchor["tag"], "draw")
            self.assertTrue(anchor["selector"].startswith("@draw-"))
            self.assertGreaterEqual(len(anchor["points"]), 4)
            self.assertEqual(anchor["comment"], "圈出主区域")
            self.assertIn("@draw-", decision["feedback"])


if __name__ == "__main__":
    unittest.main()
