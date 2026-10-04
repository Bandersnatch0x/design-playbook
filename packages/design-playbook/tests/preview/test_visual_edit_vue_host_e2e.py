"""Real offline Vue 3 rendering inside the plugin live-route bridge, not a proxy."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parents[2]
FIXTURE = PACKAGE / "tests" / "fixtures" / "visual-edit-vue-host"
for directory in (PACKAGE, PACKAGE / "tests"):
    sys.path.insert(0, str(directory))

from playwright.sync_api import expect, sync_playwright  # noqa: E402
from preview_e2e_helpers import dismiss_onboarding  # noqa: E402

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.live_route import observe_visual_source  # noqa: E402
from design_playbook.mcp.preview.transaction import run_preview_transaction  # noqa: E402

spec = importlib.util.spec_from_file_location("visual_edit_vue_host", FIXTURE / "server.py")
vue_host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vue_host)

COLOR = "rgb(40, 80, 120)"


class VueReviewBrowser:
    def __init__(self, route: str):
        self.route = route
        self.observed = {}

    def open(self, url: str) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                external = []

                def offline_only(request_route):
                    if urlsplit(request_route.request.url).hostname != "127.0.0.1":
                        external.append(request_route.request.url)
                        request_route.abort()
                    else:
                        request_route.continue_()

                context.route("**/*", offline_only)
                page = context.new_page()
                page.set_default_timeout(10000)
                errors, requests = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url))
                page.goto(url, wait_until="networkidle")
                dismiss_onboarding(page)
                iframe = page.locator("iframe.dpb-proto-frame")
                assert iframe.get_attribute("src") == self.route
                assert iframe.get_attribute("srcdoc") is None
                assert iframe.get_attribute("sandbox") == "allow-scripts"
                frame = page.frame_locator("iframe.dpb-proto-frame")
                title = frame.locator("#queue-title")
                expect(title).to_have_text("Reading queue - 0")
                runtime = title.evaluate("""() => ({
                    version: Vue.version,
                    mounted: !!document.querySelector('#app').__vue_app__,
                    react: typeof window.React
                })""")
                assert runtime == {"version": "3.5.39", "mounted": True, "react": "undefined"}
                assert self.route + "vendor/vue.global.prod.js" in requests
                assert self.route + "app.js" in requests
                assert title.evaluate("""() => {
                    try { return parent.document.body.tagName; }
                    catch (error) { return error.name; }
                }""") == "SecurityError"
                original_node = title.element_handle()
                initial_color = title.evaluate("el => getComputedStyle(el).color")
                assert initial_color == "rgb(32, 40, 48)"
                page.locator("#dpb-tab-visual").click()
                title.click(position={"x": 5, "y": 5})
                expect(page.locator(".dpb-react-selection")).to_have_text("#queue-title")
                page.locator('[data-property="color"] input').fill(COLOR)
                self.wait_batch(page, 1)
                self.assert_color(title, COLOR)
                batch = json.loads(page.locator("#dpb-visual-edits-json").input_value())
                assert batch["status"] == "pending"
                assert batch["routeUrl"] == self.route
                assert batch["sourceHash"]
                edit = batch["edits"][0]
                assert {key: edit[key] for key in
                        ("kind", "locator", "property", "oldValue", "newValue")} == {
                    "kind": "style", "locator": "#queue-title", "property": "color",
                    "oldValue": "", "newValue": COLOR,
                }
                self.advance_vue(page, frame, 1)
                self.assert_color(title, COLOR)
                assert self.batch(page) == batch
                undo = page.locator("#dpb-react-editor-root button").nth(0)
                redo = page.locator("#dpb-react-editor-root button").nth(1)
                expect(undo).to_be_enabled()
                expect(redo).to_be_disabled()
                undo.click()
                self.wait_batch(page, 0)
                assert title.evaluate("el => el.style.color") == ""
                self.assert_color(title, initial_color, inline=False)
                expect(undo).to_be_disabled()
                expect(redo).to_be_enabled()
                self.advance_vue(page, frame, 2)
                self.assert_color(title, initial_color, inline=False)
                assert self.batch(page)["edits"] == []
                redo.click()
                self.wait_batch(page, 1)
                self.assert_color(title, COLOR)
                assert self.batch(page) == batch
                expect(undo).to_be_enabled()
                expect(redo).to_be_disabled()
                self.advance_vue(page, frame, 3)
                self.assert_color(title, COLOR)
                assert self.batch(page) == batch
                assert original_node.evaluate(
                    "el => el.isConnected && el === document.querySelector('#queue-title')")
                self.observed = {"runtime": runtime, "batch": batch, "vueUpdates": 3,
                                 "sameDomNode": True, "undoEdits": 0, "redoEdits": 1,
                                 "sandbox": iframe.get_attribute("sandbox")}
                page.locator("#dpb-feedback").fill(
                    "Vue DOM preview only; source changes need a separate reviewed handoff.")
                with page.expect_response(lambda response: response.url.endswith("/decide")):
                    page.locator("#dpb-btn-approve").click()
                page.wait_for_load_state("domcontentloaded")
                assert external == [], external
                assert errors == [], errors
                self.observed.update({"externalRequests": external, "pageErrors": errors,
                                      "requests": requests})
            finally:
                browser.close()

    @staticmethod
    def batch(page) -> dict:
        return json.loads(page.locator("#dpb-visual-edits-json").input_value())

    @staticmethod
    def wait_batch(page, count: int) -> None:
        page.wait_for_function("""count => {
            const batch = JSON.parse(document.querySelector('#dpb-visual-edits-json').value);
            return batch.edits.length === count;
        }""", arg=count)

    @staticmethod
    def assert_color(title, value: str, *, inline: bool = True) -> None:
        if inline:
            assert title.evaluate("el => el.style.color") == value
        assert title.evaluate("el => getComputedStyle(el).color") == value

    @staticmethod
    def advance_vue(page, frame, count: int) -> None:
        # Exit selection mode so the actual Vue event handler receives the click.
        preview_mode = page.locator("#dpb-mode-preview")
        preview_mode.click()
        expect(preview_mode).to_have_attribute("aria-pressed", "true")
        frame.locator("#advance-queue").click()
        title = frame.locator("#queue-title")
        expect(title).to_have_text(f"Reading queue - {count}")
        expect(title).to_have_attribute("data-render-count", str(count))
        assert title.evaluate("el => el.style.letterSpacing") == f"{count}px"
        annotate_mode = page.locator("#dpb-mode-annotate")
        annotate_mode.click()
        expect(annotate_mode).to_have_attribute("aria-pressed", "true")

    def close(self, _handle: object) -> None:
        pass  # open owns browser teardown, including on assertion failure.


def test_vue_host_live_route_pending_edit_reactivity_undo_redo(tmp_path, monkeypatch):
    root = tmp_path / "host"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__"))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    preview = tmp_path / "preview"
    preview.mkdir()
    prototype = preview / "index.html"
    shutil.copyfile(root / "index.html", prototype)
    (preview / "visual-source.json").write_text(json.dumps({
        "sourceRoot": str(root.resolve()), "assetMap": "assets.json",
    }), encoding="utf-8")
    monkeypatch.setenv("DESIGN_PLAYBOOK_PREVIEW_LEDGER_DIR", str(preview / "ledger"))
    host = vue_host.create_server(root)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    route = f"http://127.0.0.1:{host.server_port}/"
    adapter = VueReviewBrowser(route)
    audit = {"active": True, "sourceWrites": []}

    def protect_source(event, args):
        if not audit["active"]:
            return
        paths = []
        if event == "open" and isinstance(args[0], (str, bytes)) and args[2] & (os.O_WRONLY | os.O_RDWR):
            paths = [args[0]]
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename"):
            paths = args[:2] if event == "os.rename" else args[:1]
        for raw in paths:
            path = Path(os.fsdecode(raw)).resolve()
            if path.is_relative_to(root.resolve()):
                audit["sourceWrites"].append(str(path))
                raise AssertionError(f"Plugin attempted a Vue host write: {event} {path}")

    sys.addaudithook(protect_source)
    try:
        source_hash = observe_visual_source(prototype, route)
        result = run_preview_transaction(
            path_arg=str(prototype), html=None, summary="Real offline Vue 3 bridge proof",
            round_n=1, report_ref="vue-host-review.md", options=["Confirm", "Revise"],
            live_route_url=route,
            collect=lambda *args, **kwargs: review_session.collect_review(
                *args, browser_adapter=adapter, **kwargs),
        )
        assert result["confirmed"] is True
        assert result["aborted"] is False
        record = json.loads(Path(result["confirm_record_path"]).read_text(encoding="utf-8"))
        assert record["confirmed"] is True
        assert record["report_ref"] == "vue-host-review.md"
        batch = record["visual_edits"]
        assert batch["sourceHash"] == source_hash == observe_visual_source(prototype, route)
        assert batch["edits"] == adapter.observed["batch"]["edits"]
        handoff = record["visual_handoff"]
        assert handoff == result["visual_handoff"]
        assert handoff["status"] == "pending-review"
        assert handoff["writesSource"] is False
        assert handoff["requiresUserConfirmation"] is True
        assert audit["sourceWrites"] == []
        assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        print("VUE-BRIDGE " + json.dumps(adapter.observed, sort_keys=True))
        print("BOUNDARY " + json.dumps({"writesSource": handoff["writesSource"],
              "status": handoff["status"], "pluginSourceWrites": audit["sourceWrites"],
              "hostFilesUnchanged": len(before), "confirmed": record["confirmed"]}))
    finally:
        audit["active"] = False
        host.shutdown()
        host.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
