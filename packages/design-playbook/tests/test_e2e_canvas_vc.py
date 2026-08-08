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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mcp" / "preview"))
import browser  # noqa: E402
import control as preview_control  # noqa: E402
from integrity import prototype_html_digest  # noqa: E402
import transaction  # noqa: E402
import versions  # noqa: E402
from i18n import default_options  # noqa: E402

try:
    from playwright.sync_api import sync_playwright  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - environment marker
    sync_playwright = None

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


def _serve(proto_html: str, summary: str, options: list[str], round_n: int):
    """Real preview HTTP server (mirrors browser._collect_via_browser assembly)."""
    control = preview_control._build_control(round_n, summary, options)
    token = browser._generate_decision_token()
    control = browser._inject_token_fields(control, token, round_n)
    page = browser._build_parent_page(proto_html, control)
    session = browser._DecisionSession(round_n, token)
    box: dict = {"result": None, "proto_hash": prototype_html_digest(
        proto_html.encode("utf-8"))}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            choice = (form.get("choice") or ["__abort__"])[0]
            feedback = (form.get("feedback") or [""])[0]
            try:
                posted_round = int((form.get("dpb_round") or [""])[0])
            except (ValueError, TypeError):
                posted_round = -1
            anchors = browser._parse_anchors(
                (form.get("anchors_json") or ["[]"])[0], posted_round)
            posted_token = (form.get("dpb_token") or [None])[0]
            if session.validate(posted_round, posted_token):
                box["result"] = {
                    "choice": choice,
                    "feedback": feedback,
                    "aborted": choice == "__abort__",
                    "anchors": anchors,
                    "prototype_html_hash": box["proto_hash"],
                }
            reply = b"<html><body>done</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(reply)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(reply)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1], box


class E2EFullFlowTests(unittest.TestCase):
    def test_real_browser_full_flow_and_vc(self) -> None:
        if sync_playwright is None:  # pragma: no cover
            self.skipTest("playwright not installed")
        server, port, box = _serve(PROTO, SUMMARY, OPTIONS, ROUND_N)

        def collect(prototype: Path, summary: str, options: list[str],
                    round_n: int) -> dict:
            with sync_playwright() as p:
                pw = p.chromium.launch(headless=True)
                try:
                    page = pw.new_page()
                    page.goto(f"http://127.0.0.1:{port}/")
                    page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                    # 1. open drawer -> pin mode
                    page.click("#dpb-open-drawer")
                    # 2. pin an element INSIDE the sandboxed prototype iframe
                    #    (G5 bridge path: iframe computes cssPath + postMessages)
                    proto = page.frame_locator("iframe.dpb-proto-frame")
                    proto.locator("#hdr").click()
                    page.wait_for_selector("#dpb-anchors .dpb-anchor")
                    # 3. comment + overall feedback
                    page.fill('#dpb-anchors input[data-i="0"]', "层级清晰")
                    page.fill('textarea[name="feedback"]', "整体不错，按钮再大一点")
                    # 4. confirm (drawer primary submit -> real POST)
                    page.click(".dpb-drawer .dpb-btn-primary")
                    page.wait_for_load_state("domcontentloaded")
                finally:
                    pw.close()
            assert box["result"] is not None, "server never received a valid POST"
            return dict(box["result"])

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

        server.shutdown()


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
                page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                page.click("#dpb-open-drawer")  # pin mode on
                page.click("#a")
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                page.evaluate(
                    """() => {
                        document.querySelector('#b').click();
                        document.querySelector('#dpb-close-drawer').focus();
                        return new Promise(resolve => setTimeout(resolve, 0));
                    }"""
                )
                page.wait_for_function(
                    "document.querySelectorAll('#dpb-anchors .dpb-anchor').length === 2")
                # Ctrl/Cmd+Z undoes the second pin
                self.assertEqual(
                    page.evaluate("document.activeElement.id"),
                    "dpb-close-drawer",
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
                page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                page.click("#dpb-open-drawer")
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
                page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                page.click("#dpb-open-drawer")
                page.click("#a")
                comment = page.locator('#dpb-anchors input[data-i="0"]')
                comment.fill("before")
                page.locator("#dpb-close-drawer").focus()
                comment.fill("after")
                page.locator("#dpb-close-drawer").focus()

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
                page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                page.click("#dpb-open-drawer")
                page.click("#a")
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                page.fill('#dpb-anchors input[data-i="0"]', "草稿评论")
                page.fill('textarea[name="feedback"]', "草稿反馈")
                # reload -> draft restored (per-run localStorage key)
                page.reload()
                page.wait_for_selector("#dpb-preview-bar .dpb-pill")
                restored = page.input_value('textarea[name="feedback"]')
                self.assertEqual(restored, "草稿反馈")
                page.click("#dpb-open-drawer")
                page.wait_for_selector("#dpb-anchors .dpb-anchor")
                self.assertEqual(
                    page.input_value('#dpb-anchors input[data-i="0"]'), "草稿评论")
            finally:
                pw.close()


if __name__ == "__main__":
    unittest.main()
