#!/usr/bin/env python3
"""T-110 Phase 1 acceptance: browser edit -> transaction -> agent handoff.

Two halves:

1. ``VisualEditEndToEndTests`` (requires chromium) drives the real Preview page
   in a real browser, performs a direct visual edit, submits, and asserts the
   *transaction* result and *confirm record* carry a pending coding-agent
   handoff bound to the reviewed artifact hash.
2. ``VisualEditNegativeTests`` (pure Python) pins the fail-closed boundary:
   stale batches, tampered hashes, over-privileged locators, and the Phase 2
   rule that any future collaboration layer must not fork batch authority.

The Phase-1 report is `.agents/research/visual-edit-phase1-acceptance.md`.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from collections.abc import Callable

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
_TESTS_ROOT = _PKG_ROOT / "tests"
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from design_playbook.mcp.preview.transaction import run_preview_transaction  # noqa: E402
from design_playbook.mcp.preview.visual_batch import (  # noqa: E402
    VisualBatchError,
    normalize_visual_batch,
    validate_batch_current,
)
from design_playbook.mcp.preview.visual_handoff import (  # noqa: E402
    VisualHandoffError,
    build_agent_handoff,
    confirm_agent_handoff,
)

try:  # chromium is required only for the browser half
    from playwright.sync_api import sync_playwright  # noqa: E402
except Exception:  # noqa: BLE001
    sync_playwright = None  # type: ignore[assignment]

PROTOTYPE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>acceptance</title></head><body>
<h2 id="panel-title">Queue monitor</h2>
<p class="row">one</p>
</body></html>"""


class _PlaywrightEditAdapter:
    """Drive one review session: pick an element, edit it, then approve."""

    def __init__(self, *, viewport: str = "desktop", before_submit: Callable[[], None] | None = None) -> None:
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None
        self.obs: dict[str, object] = {}
        self.viewport = viewport
        self.before_submit = before_submit

    def open(self, url: str) -> object:
        def drive() -> None:
            try:
                with sync_playwright() as pw:  # type: ignore[misc]
                    browser = pw.chromium.launch(headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1280, "height": 900})
                        page.goto(url, wait_until="domcontentloaded")
                        page.wait_for_selector("#dpb-root")
                        page.wait_for_timeout(600)
                        from preview_e2e_helpers import dismiss_onboarding

                        dismiss_onboarding(page)
                        page.locator("#dpb-vp-" + self.viewport).click()
                        proto = page.frame_locator("iframe.dpb-proto-frame")
                        self.obs["frame_source"] = page.locator("iframe.dpb-proto-frame").evaluate(
                            "el => ({src: el.getAttribute('src'), srcdoc: el.hasAttribute('srcdoc'), sandbox: el.getAttribute('sandbox')})"
                        )

                        # pick the heading through the real sandbox bridge
                        proto.locator("#panel-title").evaluate("el => el.click()")
                        page.wait_for_timeout(300)

                        page.click("#dpb-tab-visual")
                        page.wait_for_timeout(200)
                        page.locator(
                            '#dpb-react-editor-root .dpb-react-field[data-property="background-color"] input'
                        ).fill("rgb(9, 9, 9)")
                        page.wait_for_timeout(300)
                        self.obs["selection"] = page.locator(
                            "#dpb-react-editor-root .dpb-react-selection"
                        ).inner_text()
                        self.obs["pending"] = page.locator(
                            "#dpb-react-editor-root .dpb-react-pending-count"
                        ).inner_text()
                        self.obs["batch"] = json.loads(
                            page.evaluate(
                                "() => document.getElementById('dpb-visual-edits-json').value"
                            )
                        )
                        self.obs["iframe_bg"] = proto.locator(
                            "#panel-title"
                        ).evaluate("el => el.style.backgroundColor")

                        if self.before_submit:
                            self.before_submit()
                        page.fill("#dpb-feedback", "visual edit staged for agent review")
                        with page.expect_response(
                            lambda r: r.url.endswith("/decide")
                            and r.request.method == "POST"
                        ):
                            page.click("#dpb-btn-approve")
                        page.wait_for_load_state("domcontentloaded")
                        self.obs["response_text"] = page.locator("body").inner_text()
                    finally:
                        browser.close()
            except Exception as exc:  # noqa: BLE001
                self.error = exc

        self.thread = threading.Thread(target=drive, daemon=True)
        self.thread.start()
        return self

    def close(self, handle: object) -> None:
        assert self.thread is not None
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise AssertionError("Playwright visual-edit adapter did not finish")
        if self.error is not None:
            raise self.error


@unittest.skipUnless(sync_playwright is not None, "playwright is not installed")
class VisualEditEndToEndTests(unittest.TestCase):
    """route -> React edit -> pending batch -> transaction -> handoff."""

    def test_browser_edit_reaches_confirm_record_as_pending_handoff(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        preview_dir = Path(temp.name)
        prototype = preview_dir / "round-1.html"
        prototype.write_text(PROTOTYPE, encoding="utf-8")
        adapter = _PlaywrightEditAdapter()

        result = run_preview_transaction(
            path_arg=str(prototype),
            html=None,
            summary="phase 1 acceptance",
            round_n=1,
            report_ref="report.md",
            options=["确认通过", "需要修改"],
            collect=lambda *a, **kw: review_session.collect_review(
                *a, browser_adapter=adapter, **kw
            ),
        )

        # The browser really applied the edit inside the sandboxed frame.
        self.assertEqual(adapter.obs.get("iframe_bg"), "rgb(9, 9, 9)")
        self.assertIn("#panel-title", str(adapter.obs.get("selection")))
        self.assertTrue(str(adapter.obs.get("pending", "")).startswith("1 "))

        # The batch the page produced is a valid, single-authority batch.
        batch = adapter.obs["batch"]
        self.assertEqual(batch["schemaVersion"], 1)
        self.assertEqual(batch["status"], "pending")
        self.assertEqual(len(batch["edits"]), 1)
        self.assertEqual(batch["edits"][0]["kind"], "style")
        self.assertEqual(batch["edits"][0]["viewport"], "desktop")
        self.assertEqual(batch["edits"][0]["locator"], "#panel-title")
        self.assertEqual(batch["edits"][0]["property"], "background-color")

        # The transaction projected it as review input, not as a write.
        self.assertTrue(result["confirmed"])
        handoff = result["visual_handoff"]
        self.assertEqual(handoff["status"], "pending-review")
        self.assertEqual(handoff["nextAction"], "coding-agent-review-diff")
        self.assertTrue(handoff["requiresUserConfirmation"])
        self.assertFalse(handoff["writesSource"])
        self.assertEqual(handoff["edits"], batch["edits"])

        # ... and the durable confirm record carries the same handoff.
        confirm = json.loads(
            (preview_dir / "confirm-round-1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(confirm["visual_handoff"]["status"], "pending-review")
        self.assertFalse(confirm["visual_handoff"]["writesSource"])
        self.assertEqual(
            confirm["visual_handoff"]["sourceHash"],
            prototype_html_digest(PROTOTYPE.encode("utf-8")),
        )

    def test_source_drift_invalidates_the_staged_batch(self) -> None:
        """A re-edited artifact makes the previous batch stale, not reusable."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        preview_dir = Path(temp.name)
        prototype = preview_dir / "round-1.html"
        prototype.write_text(PROTOTYPE, encoding="utf-8")
        adapter = _PlaywrightEditAdapter()

        result = run_preview_transaction(
            path_arg=str(prototype),
            html=None,
            summary="phase 1 drift",
            round_n=1,
            report_ref="report.md",
            options=["确认通过", "需要修改"],
            collect=lambda *a, **kw: review_session.collect_review(
                *a, browser_adapter=adapter, **kw
            ),
        )
        staged = result["visual_edits"]
        validate_batch_current(staged, prototype_html_digest(PROTOTYPE.encode("utf-8")))
        drifted = prototype_html_digest((PROTOTYPE + "<!-- changed -->").encode("utf-8"))

        with self.assertRaises(VisualBatchError):
            validate_batch_current(staged, drifted)
        with self.assertRaises(VisualHandoffError):
            build_agent_handoff(staged, current_source_hash=drifted)



    def test_changed_artifact_during_review_is_visibly_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "round-1.html"
            source.write_text(PROTOTYPE, encoding="utf-8")
            adapter = _PlaywrightEditAdapter(before_submit=lambda: source.write_text(
                PROTOTYPE + "<!-- changed during review -->", encoding="utf-8"))
            result = run_preview_transaction(
                path_arg=str(source), html=None, summary="stale during review", round_n=1,
                report_ref="report.md", options=["Confirm", "Revise"],
                collect=lambda *a, **kw: review_session.collect_review(*a, browser_adapter=adapter, **kw),
            )
            self.assertNotIn("visual_handoff", result)
            self.assertIn("stale", result["visual_edits_error"])
            self.assertIn("stale", adapter.obs["response_text"])

    def test_live_route_external_agent_diff_confirmation_and_refresh(self) -> None:
        """The only source writer here is the isolated HOST-side agent fixture."""
        import difflib
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from design_playbook.mcp.preview.live_route import observe_visual_source
        from design_playbook.mcp.preview.pin_bridge import build_visual_edit_bridge_script

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "host.html"
            source.write_text(PROTOTYPE, encoding="utf-8")
            class Host(BaseHTTPRequestHandler):
                def log_message(self, *_args) -> None:
                    pass

                def do_GET(self) -> None:
                    body = (source.read_text(encoding="utf-8") + build_visual_edit_bridge_script()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            host = ThreadingHTTPServer(("127.0.0.1", 0), Host)
            thread = threading.Thread(target=host.serve_forever, daemon=True)
            thread.start()
            route = f"http://127.0.0.1:{host.server_port}/app"
            try:
                adapter = _PlaywrightEditAdapter(viewport="mobile")
                result = run_preview_transaction(
                    path_arg=str(source), html=None, summary="live route host fixture",
                    round_n=1, report_ref="report.md", options=["Confirm", "Revise"],
                    live_route_url=route,
                    collect=lambda *a, **kw: review_session.collect_review(*a, browser_adapter=adapter, **kw),
                )
                self.assertEqual(adapter.obs["frame_source"],
                                 {"src": route, "srcdoc": False, "sandbox": "allow-scripts"})
                self.assertEqual(adapter.obs["iframe_bg"], "rgb(9, 9, 9)")
                self.assertEqual(source.read_text(encoding="utf-8"), PROTOTYPE)
                batch = result["visual_edits"]
                self.assertEqual(batch["edits"][0]["viewport"], "mobile")
                handoff = result["visual_handoff"]
                before_hash = observe_visual_source(source, route)
                validate_batch_current(batch, before_hash, current_route_url=route)
                with self.assertRaises(VisualBatchError):
                    validate_batch_current(batch, before_hash, current_route_url=route + "/other")
                self.assertFalse(handoff["writesSource"])
                self.assertTrue(handoff["requiresUserConfirmation"])
                self.assertEqual(handoff["edits"][0]["locator"], "#panel-title")
                # This deterministic fixture stands in for the external coding agent,
                # not a plugin source mapper or writer. It returns a reviewable diff.
                value = handoff["edits"][0]["newValue"]
                after = PROTOTYPE.replace('id="panel-title"',
                                          f'id="panel-title" style="background-color: {value}"')
                diff = "".join(difflib.unified_diff(PROTOTYPE.splitlines(True), after.splitlines(True),
                                                   fromfile="host.html", tofile="host.html"))
                self.assertIn("+<h2", diff)
                self.assertIn("rgb(9, 9, 9)", diff)

                def host_apply(*, user_confirmed: bool) -> None:
                    if not user_confirmed:
                        raise PermissionError("explicit host confirmation is required")
                    validate_batch_current(batch, observe_visual_source(source, route), current_route_url=route)
                    source.write_text(after, encoding="utf-8")

                with self.assertRaises(PermissionError):
                    host_apply(user_confirmed=False)
                self.assertEqual(source.read_text(encoding="utf-8"), PROTOTYPE)
                host_apply(user_confirmed=True)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(route)
                        self.assertEqual(page.locator("#panel-title").evaluate(
                            "el => getComputedStyle(el).backgroundColor"), "rgb(9, 9, 9)")
                    finally:
                        browser.close()
                with self.assertRaises(VisualBatchError):
                    validate_batch_current(batch, observe_visual_source(source, route), current_route_url=route)
                with self.assertRaises(VisualHandoffError):
                    build_agent_handoff(batch, current_source_hash=observe_visual_source(source, route), route_url=route)
            finally:
                host.shutdown()
                host.server_close()
                thread.join(timeout=5)


class VisualEditNegativeTests(unittest.TestCase):
    """Fail-closed boundary that does not need a browser."""

    def _batch(self) -> dict:
        return normalize_visual_batch(
            {"edits": [{"locator": "#panel-title", "property": "color",
                        "oldValue": "", "newValue": "red"}]},
            source_hash="artifact-v1",
        )

    def test_tampered_batch_hash_is_rejected(self) -> None:
        batch = self._batch()
        batch["edits"][0]["newValue"] = "blue"
        with self.assertRaises(VisualBatchError):
            validate_batch_current(batch, "artifact-v1")

    def test_unconfirmed_handoff_never_authorizes_a_write(self) -> None:
        handoff = build_agent_handoff(self._batch(), current_source_hash="artifact-v1")
        self.assertFalse(handoff["writesSource"])
        confirmed = confirm_agent_handoff(handoff, current_source_hash="artifact-v1")
        self.assertFalse(confirmed["writesSource"])

    def test_stale_confirmation_is_rejected(self) -> None:
        handoff = build_agent_handoff(self._batch(), current_source_hash="artifact-v1")
        with self.assertRaises(VisualHandoffError):
            confirm_agent_handoff(handoff, current_source_hash="artifact-v2")

    def test_unsupported_schema_version_is_rejected(self) -> None:
        with self.assertRaises(VisualBatchError):
            normalize_visual_batch(
                {"schemaVersion": 99, "edits": []}, source_hash="artifact-v1"
            )

    def test_single_batch_authority_for_phase_2_boundary(self) -> None:
        """Phase 2 collaboration must not fork the batch contract.

        The schema lives in exactly one module, and the browser channel writes
        that one shape into the one hidden field the transaction reads.
        """
        preview = _PKG_ROOT / "mcp" / "preview"
        owners = [
            path.name
            for path in sorted(preview.glob("*.py"))
            if "SCHEMA_VERSION = 1" in path.read_text(encoding="utf-8")
            and "batchHash" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(owners, ["visual_batch.py"])
        import ast
        def schema_owners(sources: dict[str, str]) -> list[str]:
            owners = []
            for name, text in sources.items():
                tree = ast.parse(text)
                keys = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                        and isinstance(node.value, str)}
                # A second complete batch declaration is a second authority even
                # when it avoids the existing SCHEMA_VERSION spelling.
                if {"schemaVersion", "sourceHash", "routeUrl", "edits", "batchHash", "status", "pending"} <= keys:
                    owners.append(name)
            return sorted(owners)
        sources = {path.name: path.read_text(encoding="utf-8") for path in preview.glob("*.py")}
        self.assertEqual(schema_owners(sources), ["visual_batch.py"])
        rogue = "batch = {'schemaVersion':1,'sourceHash':'x','routeUrl':'','edits':[],'batchHash':'x','status':'pending'}"
        self.assertEqual(schema_owners(dict(sources, shadow=rogue)), ["shadow", "visual_batch.py"])

        control_js = (preview / "control.react.js").read_text(encoding="utf-8")
        self.assertEqual(control_js.count("dpb-visual-edits-json"), 1)
        self.assertIn("schemaVersion: 1", control_js)
        self.assertNotIn("localStorage", control_js)



@unittest.skipUnless(sync_playwright is not None, "playwright is not installed")
class VisualEditorRegressionTests(unittest.TestCase):
    """Direct user input and tool calls share the same acknowledged edits."""

    def setUp(self) -> None:
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})

    def open_editor(self, *, tools: bool = False, delayed_receipts: bool = False,
                    loopback: bool = False, lifecycle: bool = False) -> None:
        from design_playbook.mcp.preview.control import _build_control
        from preview_e2e_helpers import dismiss_onboarding
        html = review_session._build_parent_page(
            '<html><body><h2 id="a" style="color:red">A</h2>'
            '<h2 id="b" style="color:blue">B</h2></body></html>',
            _build_control(1, "editor regression", ["Confirm", "Revise"],
                           criteria=[{"id": "AC-1", "title": "Title", "then": "Visible"}]),
        )
        if delayed_receipts:
            # Install before the editor listener so this really holds receipts.
            html = html.replace("<head>", """<head><script>
            window.addEventListener('message', e => {
              if (e.delayedReceipt || !(e.data.dpbVisualEditChange ||
                  e.data.dpbVisualEditSelection?.requestId)) return;
              e.stopImmediatePropagation();
              const receipt = new MessageEvent('message', {data: e.data, source: e.source, origin: e.origin});
              receipt.delayedReceipt = true;
              setTimeout(() => window.dispatchEvent(receipt), 500);
            }, true);
            </script>""")
        if tools:
            html = html.replace("<head>", """<head><script>
            window.tools = {}; window.registrations = []; window.unregistrations = [];
            document.modelContext = {
              registerTool(t) {
                if (window.tools[t.name]) throw Error('duplicate tool');
                window.tools[t.name] = t; window.registrations.push(t.name);
              },
              unregisterTool(name) { window.unregistrations.push(name); delete window.tools[name]; }
            };
            </script>""")
        if lifecycle:
            # Capture the real React root; do not simulate effect cleanup or rendering.
            boot = "window.ReactDOM.createRoot(mount).render(h(Editor));"
            self.assertEqual(html.count(boot), 1)
            html = html.replace(boot, """
            window.testEditorRoot = window.ReactDOM.createRoot(mount);
            window.testEditorElement = h(function LifecycleProbe(props) {
              React.useLayoutEffect(function () { window.testEditorRevision = props.revision; }, [props.revision]);
              return h(Editor);
            }, {revision: 0});
            window.testEditorRoot.render(window.testEditorElement);
            """)
        if loopback:
            from functools import partial
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            Path(directory.name, "index.html").write_text(html, encoding="utf-8")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=directory.name)
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(review_session._stop_http_server, server, thread)
            self.page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="domcontentloaded")
        else:
            self.page.set_content(html, wait_until="domcontentloaded")
        self.page.wait_for_timeout(350)
        dismiss_onboarding(self.page)
        # A normal pointer click is the regression boundary, not evaluate().
        self.page.locator("#dpb-tab-visual").click(timeout=1500)
        self.frame = self.page.frame_locator("iframe.dpb-proto-frame")

    def select(self, selector: str) -> None:
        self.frame.locator(selector).evaluate("el => el.click()")
        self.page.wait_for_timeout(100)
        # Pin selection opens the existing annotation draft; dismiss it normally
        # before testing inspector controls (never force-click through a dialog).
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(50)

    def edits(self) -> list:
        return self.page.evaluate("window.DPB_VISUAL_EDIT_BATCH.edits")

    def test_history_targets_recorded_element(self) -> None:
        self.open_editor()
        self.select("#a")
        self.page.locator("#dpb-react-editor-root input").first.fill("rgb(1, 2, 3)")
        self.page.wait_for_timeout(350)
        self.select("#b")
        self.page.locator("#dpb-react-editor-root button").nth(0).click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.color"), "red")
        self.assertEqual(self.frame.locator("#b").evaluate("el => el.style.color"), "blue")
        self.assertEqual(self.edits(), [])
        self.page.locator("#dpb-react-editor-root button").nth(1).click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.color"), "rgb(1, 2, 3)")
        self.assertEqual(self.frame.locator("#b").evaluate("el => el.style.color"), "blue")
        self.assertEqual([x["locator"] for x in self.edits()], ["#a"])

    def test_typing_and_rejected_css(self) -> None:
        self.open_editor()
        self.select("#a")
        field = self.page.locator("#dpb-react-editor-root input").nth(1)
        field.fill("")
        field.press_sequentially("red", delay=100)
        self.page.wait_for_timeout(350)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.backgroundColor"), "red")
        self.assertEqual(field.input_value(), "red")
        self.assertEqual(len(self.edits()), 1)
        field.fill("not-a-color")
        self.page.wait_for_timeout(350)
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.backgroundColor"), "red")
        self.assertTrue(self.page.locator(".dpb-react-diagnostic").inner_text())

    def test_paused_color_typing_keeps_focus_across_debounce(self) -> None:
        self.open_editor()
        self.select("#a")
        field = self.page.locator('[data-property="background-color"] input')
        field.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type("r")
        self.page.wait_for_timeout(450)
        self.page.keyboard.type("ed")
        self.page.wait_for_timeout(450)
        observed = {
            "draft": field.input_value(),
            "focused": field.evaluate("el => el === document.activeElement"),
            "background": self.frame.locator("#a").evaluate("el => el.style.backgroundColor"),
            "pending": len(self.edits()),
        }
        print("RP-1 paused color:", observed)
        self.assertEqual(observed, {"draft": "red", "focused": True, "background": "red", "pending": 1})

    def test_paused_numeric_typing_keeps_focus_across_debounce(self) -> None:
        self.open_editor()
        self.select("#a")
        field = self.page.locator('[data-property="font-weight"] input')
        field.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type("7")
        self.page.wait_for_timeout(450)
        self.page.keyboard.type("00")
        self.page.wait_for_timeout(450)
        observed = {
            "draft": field.input_value(),
            "focused": field.evaluate("el => el === document.activeElement"),
            "weight": self.frame.locator("#a").evaluate("el => el.style.fontWeight"),
        }
        print("RP-1 paused numeric:", observed)
        self.assertEqual(observed, {"draft": "700", "focused": True, "weight": "700"})

    def test_paused_font_size_preserves_draft_until_units_are_valid(self) -> None:
        self.open_editor()
        self.select("#a")
        field = self.page.locator('[data-property="font-size"] input')
        field.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type("7")
        self.page.wait_for_timeout(450)
        self.page.keyboard.type("00")
        self.page.wait_for_timeout(450)
        self.assertEqual(field.input_value(), "700")
        self.assertTrue(field.evaluate("el => el === document.activeElement"))
        self.assertEqual(self.edits(), [])
        self.assertTrue(self.page.locator(".dpb-react-diagnostic").inner_text())
        self.page.keyboard.type("px")
        self.page.wait_for_timeout(450)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.fontSize"), "700px")
        self.assertEqual(len(self.edits()), 1)
        print("RP-1 font-size: 7 + pause + 00 => 700 (focused); + px => 700px, pending=1")

    def test_inflight_receipt_preserves_newer_draft(self) -> None:
        self.open_editor(delayed_receipts=True)
        self.select("#a")
        field = self.page.locator('[data-property="font-weight"] input')
        field.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type("7")
        self.page.wait_for_timeout(250)
        self.assertEqual(self.edits(), [])  # The real first receipt is still held.
        self.page.keyboard.type("00")
        self.page.wait_for_timeout(550)
        self.assertEqual(field.input_value(), "700")
        self.assertTrue(field.evaluate("el => el === document.activeElement"))
        self.page.wait_for_timeout(850)
        self.assertEqual(field.input_value(), "700")
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.fontWeight"), "700")
        self.assertEqual([edit["newValue"] for edit in self.edits()], ["7", "700"])
        print("RP-1 delayed receipt: draft=700, focus retained, accepted edits=['7', '700']")

    def test_tab_after_accepted_edit_does_not_append_noop(self) -> None:
        self.open_editor()
        self.select("#a")
        field = self.page.locator('[data-property="background-color"] input')
        field.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type("red")
        self.page.wait_for_timeout(450)
        before = self.edits()
        self.assertEqual(len(before), 1)
        # Refocusing isolates no-op submission from RP-1's unintended blur.
        field.click()
        self.page.keyboard.press("Tab")
        self.page.wait_for_timeout(450)
        print("RP-2 Tab pending:", len(before), "->", len(self.edits()))
        self.assertEqual(self.edits(), before)
        self.page.locator("#dpb-react-editor-root button").nth(0).click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.edits(), [])

    def test_iframe_tool_shortcuts_use_parent_handlers(self) -> None:
        self.open_editor()
        self.page.locator("#dpb-ruler-toggle").click()
        self.frame.locator("#a").click(position={"x": 10, "y": 10})
        self.frame.locator("#b").click(position={"x": 80, "y": 10})
        self.assertEqual(self.frame.locator(".dpb-ruler-line").count(), 1)
        self.assertEqual(self.page.evaluate("document.activeElement.tagName"), "IFRAME")
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(150)
        lines = self.frame.locator(".dpb-ruler-line").count()
        print("IR-2 Escape from iframe: ruler lines =", lines)
        self.assertEqual(lines, 0)
        self.assertEqual(self.page.locator("#dpb-ruler-toggle").get_attribute("aria-pressed"), "false")
        self.page.keyboard.press("b")
        self.page.wait_for_timeout(150)
        box = self.page.locator("#dpb-box-toggle").get_attribute("aria-pressed")
        print("IR-2 B from iframe: box =", box)
        self.assertEqual(box, "true")
        self.page.keyboard.press("b")
        self.page.wait_for_timeout(150)
        self.assertEqual(self.page.locator("#dpb-box-toggle").get_attribute("aria-pressed"), "false")

    def test_iframe_shortcuts_reject_foreign_sources_and_editable_targets(self) -> None:
        self.open_editor()
        self.page.evaluate("""() => {
          window.dispatchEvent(new MessageEvent('message', {source: window, data: {dpbToolShortcut: 'b'}}));
        }""")
        self.assertEqual(self.page.locator("#dpb-box-toggle").get_attribute("aria-pressed"), "false")
        self.frame.locator("body").evaluate("""() => {
          parent.postMessage({dpbToolShortcut: 'Enter'}, '*');
          parent.postMessage({dpbToolShortcut: {key: 'Escape', shiftKey: true}}, '*');
          const input = document.createElement('input'); input.id = 'text';
          document.body.appendChild(input);
        }""")
        self.page.keyboard.press("v")
        self.page.wait_for_timeout(100)
        field = self.frame.locator("#text")
        field.click()
        self.page.keyboard.type("brdhpv")
        self.assertEqual(field.input_value(), "brdhpv")
        self.assertEqual(self.page.locator("#dpb-box-toggle").get_attribute("aria-pressed"), "false")
        self.assertEqual(self.page.locator("#dpb-ruler-toggle").get_attribute("aria-pressed"), "false")
        self.assertTrue(self.page.locator("#dpb-root").is_visible())

    def test_noop_tool_receipt_does_not_append_history(self) -> None:
        self.open_editor(tools=True)
        self.select("#a")
        for value in ("red", " red "):
            receipt = self.page.evaluate("""value => window.tools.preview_set_style.execute({
              property: 'background-color', value
            })""", value)
            self.assertTrue(receipt["accepted"])
        self.assertFalse(receipt["pending"])
        self.assertEqual(len(self.edits()), 1)

    def test_bridge_loss_disables_editor_without_changing_history(self) -> None:
        self.open_editor()
        self.select("#a")
        self.page.locator("#dpb-react-editor-root input").first.fill("green")
        self.page.wait_for_timeout(350)
        self.assertEqual(len(self.edits()), 1)
        self.page.locator("iframe").evaluate("el => el.srcdoc='<h2 id=a>A</h2>'")
        self.page.wait_for_timeout(500)
        self.assertEqual(self.page.locator("#dpb-react-editor-root input:enabled").count(), 0)
        self.assertEqual(self.page.evaluate("window.DPB_VISUAL_EDIT_BATCH.status"), "stale")
        self.assertTrue(self.page.locator(".dpb-react-diagnostic").inner_text())
        self.assertEqual(len(self.edits()), 1)

    def test_locale_and_all_rail_tabs_are_clickable(self) -> None:
        self.open_editor()
        for lang in ("zh-CN", "en"):
            if self.page.locator("#dpb-root").get_attribute("lang") != lang:
                self.page.keyboard.press("l")
                self.page.wait_for_timeout(100)
            for tab in ("#dpb-tab-spec", "#dpb-tab-annotations", "#dpb-tab-visual"):
                self.page.locator(tab).click(timeout=1500)
                self.assertEqual(self.page.locator(tab).get_attribute("aria-selected"), "true")
            title = "视觉编辑" if lang == "zh-CN" else "Visual editor"
            self.assertEqual(self.page.locator(".dpb-react-editor-head strong").inner_text(), title)
            undo = "撤销" if lang == "zh-CN" else "Undo"
            self.assertEqual(self.page.locator("#dpb-react-editor-root button").first.inner_text(), undo)


    def test_missing_replay_target_does_not_pop_pending_history(self) -> None:
        self.open_editor()
        self.select("#a")
        self.page.locator("#dpb-react-editor-root input").first.fill("green")
        self.page.wait_for_timeout(350)
        self.frame.locator("#a").evaluate("el => el.remove()")
        self.page.locator("#dpb-react-editor-root button").first.click()
        self.page.wait_for_timeout(150)
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.page.evaluate("window.DPB_VISUAL_EDIT_BATCH.status"), "stale")
        self.assertTrue(self.page.locator(".dpb-react-diagnostic").inner_text())

    def test_native_webmcp_registration_uses_the_same_batch(self) -> None:
        """Chromium 148 only exposes registerTool, not getTools/executeTool.

        The observer calls the real native method before recording success.
        Calling the captured execute callback tests our pipeline, NOT invocation
        by a real browser agent or a browser-provided executeTool API.
        """
        self.browser.close()
        self.browser = self.pw.chromium.launch(headless=True, args=["--enable-features=WebMCP"])
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.page.add_init_script("""(() => {
          if (window !== top) return;
          const context = navigator.modelContext;
          window.nativeSurface = {
            secure: isSecureContext,
            documentContext: typeof document.modelContext,
            navigatorContext: typeof context,
            detected: typeof context?.registerTool === 'function',
            methods: context ? Object.getOwnPropertyNames(Object.getPrototypeOf(context)) : [],
            getTools: typeof context?.getTools,
            executeTool: typeof context?.executeTool,
            provideContext: typeof context?.provideContext
          };
          window.tools = {}; window.registrations = [];
          if (!window.nativeSurface.detected) return;
          const register = context.registerTool;
          window.nativeSurface.native = Function.prototype.toString.call(register).includes('[native code]');
          context.registerTool = function (tool) {
            const result = register.call(this, tool);
            window.tools[tool.name] = tool;
            window.registrations.push({name: tool.name, inputSchema: tool.inputSchema, annotations: tool.annotations});
            return result;
          };
        })();""")
        self.open_editor(loopback=True)
        surface = self.page.evaluate("window.nativeSurface")
        print("Chromium", self.browser.version, "native WebMCP surface:", json.dumps(surface, sort_keys=True))
        self.assertEqual(surface, {
            "secure": True, "documentContext": "undefined", "navigatorContext": "object",
            "detected": True, "methods": ["registerTool", "constructor"], "native": True,
            "getTools": "undefined", "executeTool": "undefined", "provideContext": "undefined",
        })
        expected = [
            {"name": "preview_get_selection", "inputSchema": {"type": "object", "properties": {}},
             "annotations": {"readOnlyHint": True, "consequentialHint": False}},
            {"name": "preview_set_style", "inputSchema": {
                "type": "object", "properties": {"property": {"type": "string", "pattern": "^[A-Za-z-]{1,64}$"}, "value": {"type": "string"}},
                "required": ["property", "value"]},
             "annotations": {"readOnlyHint": False, "consequentialHint": False}},
            {"name": "preview_get_pending_edits", "inputSchema": {"type": "object", "properties": {}},
             "annotations": {"readOnlyHint": True, "consequentialHint": False}},
        ]
        registered = self.page.evaluate("window.registrations")
        print("Native registrations:", json.dumps(registered, sort_keys=True))
        self.assertEqual(registered, expected)
        self.assertEqual(self.page.locator(".dpb-react-badge").inner_text(), "WebMCP")
        self.assertNotIn("allow-same-origin", self.page.locator("iframe.dpb-proto-frame").get_attribute("sandbox"))
        self.select("#a")
        self.assertEqual(self.page.evaluate("window.tools.preview_get_selection.execute({}).selector"), "#a")
        self.page.locator('[data-property="color"] input').fill("green")
        self.page.wait_for_function("window.DPB_VISUAL_EDIT_BATCH.edits.length === 1")
        result = self.page.evaluate("window.tools.preview_set_style.execute({property:'padding',value:'17px'})")
        self.assertEqual(result, {"accepted": True, "pending": True})
        self.page.wait_for_function("window.DPB_VISUAL_EDIT_BATCH.edits.length === 2")
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "17px")
        self.assertEqual([edit["property"] for edit in self.edits()], ["color", "padding"])
        self.assertTrue(self.page.evaluate("window.tools.preview_get_pending_edits.execute({}) === window.DPB_VISUAL_EDIT_BATCH"))
        self.assertEqual(json.loads(self.page.locator("#dpb-visual-edits-json").input_value()),
                         self.page.evaluate("window.tools.preview_get_pending_edits.execute({})"))
        self.page.locator("#dpb-react-editor-root button").first.click()
        self.page.wait_for_function("window.DPB_VISUAL_EDIT_BATCH.edits.length === 1")
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "")
        self.assertEqual(self.page.evaluate("window.registrations"), expected)
        print("Registered callback + UI -> one pending batch; shared undo passed; registrations remain exactly three")

    def test_unflagged_loopback_editor_uses_bridge(self) -> None:
        self.open_editor(loopback=True)
        surface = self.page.evaluate("""() => ({secure: isSecureContext,
          documentContext: typeof document.modelContext, navigatorContext: typeof navigator.modelContext})""")
        self.assertEqual(surface, {"secure": True, "documentContext": "undefined", "navigatorContext": "undefined"})
        self.assertIn(self.page.locator(".dpb-react-badge").inner_text(), ("Bridge", "页面桥接"))
        self.select("#a")
        self.page.locator('[data-property="padding"] input').fill("19px")
        self.page.wait_for_function("window.DPB_VISUAL_EDIT_BATCH.edits.length === 1")
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "19px")
        self.assertEqual(json.loads(self.page.locator("#dpb-visual-edits-json").input_value())["edits"], self.edits())
        print("Chromium", self.browser.version, "unflagged surface:", json.dumps(surface, sort_keys=True),
              "bridge edit accepted; pending edits:", len(self.edits()))

    def test_optional_tools_unregister_on_react_unmount(self) -> None:
        self.open_editor(tools=True, lifecycle=True)
        names = ["preview_get_selection", "preview_set_style", "preview_get_pending_edits"]
        self.assertEqual(self.page.evaluate("window.registrations"), names)
        self.assertEqual(self.page.evaluate("window.unregistrations"), [])
        self.page.evaluate("window.testEditorRoot.unmount()")
        self.assertEqual(self.page.locator(".dpb-react-editor").count(), 0)
        self.assertEqual(self.page.evaluate("window.unregistrations"), names)
        self.assertEqual(self.page.evaluate("Object.keys(window.tools)"), [])

    def test_optional_tools_concurrent_rerender_does_not_double_register(self) -> None:
        self.open_editor(tools=True, lifecycle=True)
        self.select("#a")
        self.page.evaluate("""() => {
          window.originalTools = {...window.tools};
          for (let revision = 1; revision <= 20; revision++) {
            React.startTransition(() => window.testEditorRoot.render(React.cloneElement(
              window.testEditorElement, {revision}
            )));
          }
        }""")
        self.page.wait_for_function("window.testEditorRevision === 20")
        self.assertEqual(self.page.evaluate("window.unregistrations"), [])
        self.assertEqual(self.page.evaluate("window.registrations"),
                         ["preview_get_selection", "preview_set_style", "preview_get_pending_edits"])
        self.assertTrue(self.page.evaluate(
            "Object.keys(window.tools).every(name => window.tools[name] === window.originalTools[name])"))
        self.assertEqual(self.page.locator(".dpb-react-badge").inner_text(), "WebMCP")
        self.assertEqual(self.page.evaluate("window.tools.preview_get_selection.execute({}).selector"), "#a")
        self.assertEqual(self.page.evaluate(
            "window.tools.preview_set_style.execute({property:'padding',value:'23px'})"),
            {"accepted": True, "pending": True})
        self.page.wait_for_function("window.DPB_VISUAL_EDIT_BATCH.edits.length === 1")
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "23px")
        self.assertEqual(self.page.evaluate("window.tools.preview_get_pending_edits.execute({}).edits"), self.edits())
        self.assertEqual(len(self.page.evaluate("window.registrations")), 3)

    def test_optional_tool_execute_propagates_post_message_error(self) -> None:
        self.open_editor(tools=True)
        self.select("#a")
        result = self.page.evaluate("""async () => {
          const failure = new Error('bridge postMessage failed');
          const frame = document.querySelector('iframe.dpb-proto-frame');
          const contentWindow = frame.contentWindow;
          let calls = 0;
          Object.defineProperty(frame, 'contentWindow', {configurable: true, value: {
            postMessage() { calls++; throw failure; }
          }});
          try {
            const value = await window.tools.preview_set_style.execute({property: 'padding', value: '17px'});
            return {resolved: true, value, calls};
          } catch (error) {
            return {resolved: false, sameError: error === failure, message: error.message, calls};
          } finally {
            Object.defineProperty(frame, 'contentWindow', {configurable: true, value: contentWindow});
          }
        }""")
        self.assertEqual(result, {
            "resolved": False, "sameError": True, "message": "bridge postMessage failed", "calls": 1,
        })
        self.assertEqual(self.edits(), [])
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "")

    def test_optional_tool_schema_rejects_unsafe_properties(self) -> None:
        self.open_editor(tools=True)
        schema = self.page.evaluate("window.tools.preview_set_style.inputSchema")
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["property", "value"])
        property_schema = schema["properties"]["property"]
        self.assertEqual(property_schema["type"], "string")
        self.assertIn("pattern", property_schema)
        # JSON Schema patterns use ECMAScript regex semantics; exercise the
        # registered constraint in the browser, not a copied test-side rule.
        cases = [
            ("padding", True), ("background-color", True), ("font-size", True),
            ("a" * 64, True), ("a" * 65, False), ("", False),
            ("../padding", False), ("..", False), (r"..\padding", False),
            ("file:padding", False), ("about:blank", False),
            ("javascript:padding", False), ("C:/padding", False),
            ("/padding", False), ("padding;color", False),
        ]
        for property_name, allowed in cases:
            with self.subTest(property=property_name):
                self.assertEqual(self.page.evaluate(
                    "property => new RegExp(window.tools.preview_set_style.inputSchema.properties.property.pattern).test(property)",
                    property_name,
                ), allowed)
        # Direct callback callers can bypass host schema validation; the
        # existing bridge must still refuse traversal without creating edits.
        self.select("#a")
        result = self.page.evaluate(
            "window.tools.preview_set_style.execute({property:'../padding',value:'17px'})")
        self.assertEqual(result, {"accepted": False, "error": "visual_rejected"})
        self.assertEqual(self.edits(), [])
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "")

    def test_optional_tools_register_once_and_use_the_same_batch(self) -> None:
        self.open_editor(tools=True)
        self.select("#a")
        self.assertEqual(self.page.evaluate("window.registrations"),
                         ["preview_get_selection", "preview_set_style", "preview_get_pending_edits"])
        self.assertEqual(self.page.evaluate("window.tools.preview_get_selection.execute({}).selector"), "#a")
        self.assertEqual(self.page.evaluate("window.tools.preview_set_style.inputSchema.required"),
                         ["property", "value"])
        self.assertEqual(self.page.evaluate("window.tools.preview_set_style.annotations"),
                         {"readOnlyHint": False, "consequentialHint": False})
        for name in ("preview_get_selection", "preview_get_pending_edits"):
            self.assertEqual(self.page.evaluate("name => window.tools[name].inputSchema", name),
                             {"type": "object", "properties": {}})
            self.assertEqual(self.page.evaluate("name => window.tools[name].annotations", name),
                             {"readOnlyHint": True, "consequentialHint": False})
        self.assertEqual(self.page.evaluate("window.tools.preview_set_style.inputSchema.properties"),
                         {"property": {"type": "string", "pattern": "^[A-Za-z-]{1,64}$"}, "value": {"type": "string"}})
        self.page.evaluate("window.tools.preview_set_style.execute({property:'padding',value:'17px'})")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.frame.locator("#a").evaluate("el => el.style.padding"), "17px")
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual(self.page.evaluate("window.tools.preview_get_pending_edits.execute({}).edits"), self.edits())
        self.assertEqual(len(self.page.evaluate("window.registrations")), 3)


if __name__ == "__main__":
    unittest.main()
