#!/usr/bin/env python3
"""A01/A02 (browser half): the real project-entry journey in Chromium.

Drives the served shell against the real loopback service: the one-time
bootstrap exchange and fragment clearing, adding a folder through probe
and confirmation, keyboard reachability, renaming, granting, the
disconnected state after the folder disappears, rebinding, removal, and
the security negatives a browser can actually demonstrate -- no storage
of the credential, no project data in the unauthenticated shell, a
replayed bootstrap refused, and no path echoed in a rejection.
"""
from __future__ import annotations

import json
import re
import time
import unittest
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from tests.harness import WorkbenchHarness, http_request

_PLAYWRIGHT = None
_BROWSER = None


def setUpModule() -> None:
    global _PLAYWRIGHT, _BROWSER
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch()


def tearDownModule() -> None:
    _BROWSER.close()
    _PLAYWRIGHT.stop()


class ProjectEntryJourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page()
        self.addCleanup(self.page.close)
        self.origin = self.h.runtime.origin

    def _open_session(self) -> None:
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def _add_project(self, path: Path, name: str = "") -> None:
        self.page.fill("#project-path", str(path))
        self.page.click("#probe-button")
        expect(self.page.locator("#candidate")).to_be_visible()
        if name:
            self.page.fill("#project-name", name)
        self.page.click("#register-button")
        expect(self.page.locator("#project-rows tr")).to_have_count(1)

    def test_bootstrap_is_exchanged_once_and_cleared_from_the_url(self) -> None:
        self._open_session()
        # The one-time secret is gone from the address bar as soon as the
        # exchange starts, so it cannot be bookmarked or replayed by reload.
        expect(self.page).to_have_url(self.origin + "/")
        self.page.reload()
        expect(self.page.locator("#session-error")).to_be_visible()
        expect(self.page.locator("#session-state")).to_contain_text("会话不可用")

    def test_shell_without_bootstrap_shows_no_project_data_or_credential(self) -> None:
        self.page.goto(self.origin + "/")
        expect(self.page.locator("#session-error")).to_be_visible()
        body = self.page.inner_text("body")
        self.assertNotIn(self.h.workspace.name, body)
        self.assertNotIn("bootstrap=", body)

    def test_add_project_confirm_switch_and_rename_with_the_keyboard(self) -> None:
        self._open_session()
        directory = self.h.make_directory("设计 项目 alpha")

        # Both steps of registration are completable from the keyboard:
        # Enter submits the path, and focus moves to the confirm control so
        # Enter registers without a pointer.
        self.page.fill("#project-path", str(directory))
        self.page.press("#project-path", "Enter")
        expect(self.page.locator("#candidate")).to_be_visible()
        expect(self.page.locator("#candidate-path")).to_have_text(
            str(directory.resolve())
        )
        expect(self.page.locator("#candidate-identity")).not_to_be_empty()
        expect(self.page.locator("#candidate-scope")).to_contain_text("只读")
        expect(self.page.locator("#register-button")).to_be_focused()

        self.page.keyboard.press("Enter")
        row = self.page.locator("#project-rows tr").first
        expect(row).to_be_visible()
        expect(row.locator(".project-name")).to_have_text("设计 项目 alpha")
        expect(row.locator(".state-badge")).to_have_text("已连接")
        expect(row.locator(".grant-list")).to_have_text("只读")
        expect(self.page.locator("#list-empty")).to_be_hidden()

        row.locator(".open-button").click()
        expect(row.locator(".current-flag")).to_be_visible()

        self.page.once("dialog", lambda dialog: dialog.accept("重命名后的项目"))
        row.locator(".rename-button").click()
        expect(row.locator(".project-name")).to_have_text("重命名后的项目")

        self.page.once("dialog", lambda dialog: dialog.accept("read, write"))
        row.locator(".grants-button").click()
        expect(row.locator(".grant-list")).to_contain_text("写入")

    def test_disconnected_rebind_and_removal_journey(self) -> None:
        self._open_session()
        directory = self.h.make_directory("vanish")
        self._add_project(directory, name="Vanish")
        row = self.page.locator("#project-rows tr").first

        # The folder disappears: the UI must say disconnected on the next
        # probe instead of pretending the project is still usable.
        directory.rmdir()
        self.page.click("#refresh-button")
        expect(row.locator(".state-badge")).to_have_text("已断开")
        expect(row.locator(".rebind-button")).to_be_visible()

        replacement = self.h.make_directory("vanish-moved")
        # One handler for the whole flow: Playwright delivers each dialog to
        # every registered listener, so the prompt and the confirmation
        # cannot be answered by two separate handlers.
        self.page.on(
            "dialog",
            lambda dialog: dialog.accept(str(replacement))
            if dialog.type == "prompt"
            else dialog.accept(),
        )
        row.locator(".rebind-button").click()
        expect(row.locator(".state-badge")).to_have_text("已连接")
        expect(row.locator(".cell-path code")).to_have_text(
            str(replacement.resolve())
        )

        # Removal unregisters only; the folder itself stays on disk.
        row.locator(".remove-button").click()
        expect(self.page.locator("#project-rows tr")).to_have_count(0)
        expect(self.page.locator("#list-empty")).to_be_visible()
        self.assertTrue(replacement.exists())

    def test_credential_is_never_persisted_in_the_browser(self) -> None:
        self._open_session()
        self._add_project(self.h.make_directory("storage"), name="Storage")
        self.assertEqual(self.page.evaluate("() => localStorage.length"), 0)
        self.assertEqual(self.page.evaluate("() => sessionStorage.length"), 0)
        self.assertEqual(self.page.evaluate("() => document.cookie"), "")
        # The live session token never appears in the served document either.
        self.assertNotIn(self.h.runtime.session.token, self.page.content())

    def test_rejections_shown_to_the_maintainer_do_not_leak_paths(self) -> None:
        self._open_session()
        secret = self.h.workspace / "confidential-plans"
        self.page.fill("#project-path", str(secret))
        self.page.click("#probe-button")
        error = self.page.locator("#list-error")
        expect(error).to_be_visible()
        self.assertNotIn("confidential-plans", error.inner_text())

    def test_credential_record_is_not_reachable_over_http(self) -> None:
        self._open_session()
        result = self.page.evaluate(
            "async () => { const r = await fetch('/session/session.json');"
            " return { status: r.status, body: await r.text() }; }"
        )
        # Unauthenticated, so the file is not a route at all: never 200.
        self.assertIn(result["status"], (401, 404))
        self.assertNotIn("bootId", result["body"])
        self.assertNotIn("bootstrap", result["body"])

    def test_static_shell_is_reachable_without_a_session(self) -> None:
        # A second page with no credential can load the shell (browser
        # navigation cannot carry a header), and it shows the error state
        # rather than any project data.
        other = _BROWSER.new_page()
        self.addCleanup(other.close)
        other.goto(self.origin + "/app.html")
        expect(other.locator("#session-error")).to_be_visible()
        self.assertEqual(
            other.evaluate("() => document.querySelectorAll('#project-rows tr').length"),
            0,
        )


class AssetsPanelJourneyTest(unittest.TestCase):
    """WB-03 in the browser: find, inspect, and preview an imported asset."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.token = self.h.runtime.session.token
        self.page = _BROWSER.new_page()
        self.addCleanup(self.page.close)
        self.origin = self.h.runtime.origin
        self.directory = self.h.make_directory("assets-ui")
        (self.directory / "site").mkdir()
        (self.directory / "site" / "index.html").write_text(
            "<!doctype html><h1>Imported page</h1><script>document.title='ran'</script>",
            encoding="utf-8",
        )
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Assets")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        granted = self.h.grant(self.project_id, ["read", "write"], expected_counter=0)
        assert granted.status == 200, granted.text
        self.page_asset = self.h.import_assets(self.project_id, ["site"]).json["result"]["asset"]
        self.markdown_asset = self.h.import_assets(self.project_id, ["brand.md"]).json["result"]["asset"]
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def _open_panel(self) -> None:
        self.page.locator("#project-rows tr .assets-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_visible()
        expect(self.page.locator(".asset-item")).to_have_count(2)

    def test_search_detail_and_capabilities_are_visible(self) -> None:
        self._open_panel()
        # Search narrows the list and says why an item matched.
        self.page.fill("#assets-query", "brand")
        self.page.click("#assets-search-button")
        expect(self.page.locator(".asset-item")).to_have_count(1)
        expect(self.page.locator(".asset-name").first).to_have_text("brand.md")
        self.page.fill("#assets-query", "")
        self.page.select_option("#assets-kind", "static-package")
        self.page.click("#assets-search-button")
        expect(self.page.locator(".asset-item")).to_have_count(1)
        row = self.page.locator(".asset-item").first
        expect(row.locator(".asset-meta")).to_contain_text("静态预览")

        row.locator(".asset-select").click()
        expect(self.page.locator("#asset-detail")).to_be_visible()
        expect(self.page.locator("#asset-detail-heading")).to_have_text("site")
        expect(self.page.locator("#asset-detail-capabilities")).to_contain_text("参考")
        expect(self.page.locator("#asset-detail-capabilities")).to_contain_text(
            "静态预览"
        )
        expect(self.page.locator("#asset-detail-lifecycle")).to_have_text("草稿")
        expect(self.page.locator("#asset-manifest li")).to_have_count(1)
        expect(self.page.locator("#asset-locators li").first).to_contain_text(
            "site/index.html"
        )

    def _wait_for_preview_frame(self, timeout_ms: int = 10000):
        """The loaded preview frame, located by origin (it loads asynchronously)."""
        deadline = timeout_ms
        waited = 0
        while waited < deadline:
            for candidate in self.page.frames:
                if candidate.url.startswith(self.h.preview_origin):
                    return candidate
            self.page.wait_for_timeout(100)
            waited += 100
        raise AssertionError("the preview frame did not load")

    def _open_static_package(self) -> None:
        """Filter to the static package before selecting it.

        Both assets are imported within the same second, so the list order
        inside one match rank is the stable-id tie-break, not import order:
        the test must name what it wants instead of assuming position.
        """
        self._open_panel()
        self.page.select_option("#assets-kind", "static-package")
        self.page.click("#assets-search-button")
        expect(self.page.locator(".asset-item")).to_have_count(1)
        self.page.locator(".asset-item").first.locator(".asset-select").click()
        expect(self.page.locator("#asset-detail-kind")).to_have_text("静态页面包")

    def test_static_preview_blocks_the_page_script(self) -> None:
        self._open_static_package()
        self.page.click("#asset-preview-static")
        frame = self.page.frame_locator("#asset-preview-frame")
        expect(frame.locator("h1")).to_have_text("Imported page")
        handle = self._wait_for_preview_frame()
        self.assertNotEqual(handle.evaluate("() => document.title"), "ran")
        note = self.page.locator("#asset-preview-note")
        expect(note).to_contain_text("脚本已被禁止")

    def test_dynamic_preview_is_explicit_and_stays_isolated(self) -> None:
        self._open_static_package()
        self.page.click("#asset-preview-static")
        expect(self.page.locator("#asset-preview-enable")).to_be_visible()
        self.page.on("dialog", lambda dialog: dialog.accept())
        self.page.click("#asset-preview-enable")
        expect(self.page.locator("#asset-preview-enable")).to_be_hidden()
        self.page.click("#asset-preview-dynamic")
        expect(self.page.locator("#asset-preview-frame")).to_have_attribute(
            "sandbox", "allow-scripts"
        )
        expect(self.page.locator("#asset-preview-note")).to_contain_text("无凭证")
        handle = self._wait_for_preview_frame()
        # Enabling already switched to dynamic, so the click above re-selects
        # the same mode and may reload the frame once more. Wait for the title
        # instead of reading it back, so the check does not race that reload.
        handle.wait_for_function("() => document.title === 'ran'", timeout=10000)

    def test_a_carrier_without_preview_capability_shows_no_dynamic_button(self) -> None:
        self._open_panel()
        self.page.select_option("#assets-kind", "markdown")
        self.page.click("#assets-search-button")
        expect(self.page.locator(".asset-item")).to_have_count(1)
        self.page.locator(".asset-item").first.locator(".asset-select").click()
        self.page.click("#asset-preview-static")
        expect(self.page.locator("#asset-preview-enable")).to_be_hidden()



class DesignSystemJourneyTest(unittest.TestCase):
    """WB-05 in the browser: edit tokens, see real errors, publish, preview."""

    TOKENS = {
        "color": {"brand": "#1f4fd8", "ink": "#16181d"},
        "space": {"gap": "8px"},
        "theme": {"dark": {"color": {"ink": "#eceff4"}}},
    }

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page()
        self.addCleanup(self.page.close)
        self.origin = self.h.runtime.origin
        self.directory = self.h.make_directory("design-system-ui")
        (self.directory / "tokens").mkdir()
        self.baseline = self.directory / "tokens" / "brand.json"
        self.baseline.write_text(
            json.dumps(self.TOKENS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status == 200
        self.markdown = self.h.import_assets(self.project_id, ["brand.md"]).json["result"][
            "asset"
        ]
        imported = self.h.import_assets(self.project_id, ["tokens/brand.json"])
        assert imported.status == 200, imported.text
        self.tokens = imported.json["result"]["asset"]
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def _open_asset(self, kind: str) -> None:
        self.page.locator("#project-rows tr .assets-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_visible()
        self.page.select_option("#assets-kind", kind)
        self.page.click("#assets-search-button")
        expect(self.page.locator(".asset-item")).to_have_count(1)
        self.page.locator(".asset-item").first.locator(".asset-select").click()
        expect(self.page.locator("#asset-detail")).to_be_visible()

    def _open_design_system(self) -> None:
        self._open_asset("tokens")
        expect(self.page.locator("#asset-design-system-controls")).to_be_visible()
        self.page.click("#asset-design-system")
        expect(self.page.locator("#tokens-panel")).to_be_visible()
        expect(self.page.locator("#tokens-heading")).to_contain_text(self.tokens["name"])

    def _preview_frame(self, timeout_ms: int = 10000):
        waited = 0
        while waited < timeout_ms:
            for candidate in self.page.frames:
                if candidate.url.startswith(self.h.preview_origin):
                    return candidate
            self.page.wait_for_timeout(100)
            waited += 100
        raise AssertionError("the design-system sample frame did not load")

    def _edit(self, document: dict) -> None:
        self.page.fill(
            "#tokens-document", json.dumps(document, ensure_ascii=False, indent=2)
        )

    def _save(self) -> None:
        self.page.click("#tokens-save")
        # Wait for the real outcome instead of racing the next request.
        expect(self.page.locator("#tokens-status")).to_contain_text("草稿已保存")

    def _publish(self, number: int) -> None:
        self.page.click("#tokens-publish")
        expect(self.page.locator("#tokens-status")).to_contain_text(
            f"已发布第 {number} 次修订"
        )

    def test_a_non_token_asset_has_no_design_system_entry(self) -> None:
        self._open_asset("markdown")
        expect(self.page.locator("#asset-design-system-controls")).to_be_hidden()
        expect(self.page.locator("#asset-design-system-hint")).to_be_hidden()

    def test_edit_publish_diff_preview_and_baseline_proposal(self) -> None:
        self._open_design_system()
        expect(self.page.locator("#tokens-validation")).to_contain_text("校验通过")
        expect(self.page.locator("#tokens-document")).to_have_value(
            re.compile(r"#1f4fd8")
        )
        expect(self.page.locator("#tokens-status")).to_contain_text("草稿")

        # A broken document is refused with the real reason, and no revision
        # appears: the refusal is not a UI decoration.
        self._edit({"color": {"a": {"$ref": "color.b"}, "b": {"$ref": "color.a"}}})
        self.page.click("#tokens-save")
        expect(self.page.locator("#tokens-error")).to_be_visible()
        expect(self.page.locator("#tokens-error")).to_contain_text("invalid-input")
        self.assertEqual(self.h.runtime.store.asset_revisions(self.tokens["assetId"]), [])

        # A valid edit saves as a draft and then publishes a fixed revision.
        first = {
            "color": {"brand": "#1f4fd8", "ink": "#16181d"},
            "space": {"gap": "8px"},
            "theme": {"dark": {"color": {"ink": "#eceff4"}}},
        }
        self._edit(first)
        self._save()
        self._publish(1)
        self.assertEqual(
            len(self.h.runtime.store.asset_revisions(self.tokens["assetId"])), 1
        )

        second = {
            "color": {"brand": "#0b5fce", "ink": "#16181d"},
            "space": {"gap": "12px"},
            "theme": {"dark": {"color": {"ink": "#eceff4"}}},
        }
        self._edit(second)
        self._save()
        self._publish(2)
        self.page.click("#tokens-diff-button")
        expect(self.page.locator("#tokens-diff-counts")).to_contain_text("变更 2")
        expect(self.page.locator("#tokens-diff")).to_contain_text("color.brand")
        expect(self.page.locator("#tokens-diff")).to_contain_text("#0b5fce")

        # The theme switch is a real render from the stored values.
        expect(self.page.locator("#tokens-theme")).to_contain_text("dark")
        self.page.select_option("#tokens-theme", "dark")
        self.page.click("#tokens-preview-refresh")
        expect(self.page.locator("#tokens-preview-note")).to_contain_text("主题：dark")
        frame = self._preview_frame()
        frame.wait_for_selector("h1", timeout=10000)
        self.assertIn("#eceff4", frame.inner_text("body"))

        # Replacing the project baseline stays a maintainer decision.
        before = self.baseline.read_bytes()
        expect(self.page.locator("#tokens-baseline-path")).to_have_value(
            "tokens/brand.json"
        )
        self.page.click("#tokens-baseline-button")
        expect(self.page.locator("#tokens-baseline-result")).to_contain_text(
            "等待授权"
        )
        expect(self.page.locator("#tokens-baseline-result")).to_contain_text(
            "本操作没有写入项目文件"
        )
        self.assertEqual(self.baseline.read_bytes(), before)

        # The proposal is the ordinary R06 proposal, reviewed elsewhere.
        self.page.locator("#project-rows tr .proposals-button").first.click()
        expect(self.page.locator("#proposals-panel")).to_be_visible()
        expect(self.page.locator(".proposal-item")).to_have_count(1)
        expect(self.page.locator(".proposal-summary").first).to_contain_text(
            "设计系统基线替换"
        )

    def test_the_affected_list_names_real_dependent_components(self) -> None:
        self._open_design_system()
        self._publish(1)
        # A component published against this revision is a real dependent.
        revision = self.h.runtime.store.latest_revision(self.tokens["assetId"])
        (self.directory / "button.md").write_text("# Button\n", encoding="utf-8")
        component = self.h.import_assets(self.project_id, ["button.md"]).json["result"][
            "asset"
        ]
        published = self.h.asset_action(
            self.project_id,
            component["assetId"],
            "publish-with-deps",
            payload={
                "dependencies": [
                    {
                        "assetId": self.tokens["assetId"],
                        "revisionId": revision["revision_id"],
                    }
                ]
            },
        )
        self.assertEqual(published.status, 200, published.text)
        self.page.click("#tokens-close")
        self._open_design_system()
        expect(self.page.locator("#tokens-affected")).to_contain_text("button.md")
        expect(self.page.locator("#tokens-affected-note")).to_contain_text("不会自动升级")


class ComponentDocumentJourneyTest(unittest.TestCase):
    """WB-06 in the browser: define, publish, instantiate, distill."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page()
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("documents-ui")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")
        self.page.locator("#project-rows tr .assets-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_visible()

    def _assets(self, kind: str | None = None) -> list[dict]:
        rows = self.h.runtime.store.project_assets(self.project_id)
        return [row for row in rows if kind is None or row["kind"] == kind]

    def _instance_frame(self, timeout_ms: int = 10000):
        waited = 0
        while waited < timeout_ms:
            for candidate in self.page.frames:
                if candidate.url.startswith(self.h.preview_origin):
                    return candidate
            self.page.wait_for_timeout(100)
            waited += 100
        raise AssertionError("the component sample frame did not load")

    def test_create_edit_publish_and_instantiate_a_component(self) -> None:
        self.page.click("#create-component")
        expect(self.page.locator("#document-panel")).to_be_visible()
        expect(self.page.locator("#document-heading")).to_contain_text("组件")
        expect(self.page.locator("#document-validation")).to_contain_text("校验通过")
        expect(self.page.locator("#document-text")).to_have_value(
            re.compile(r'"label"')
        )
        # Creating a workbench document writes no project file.
        self.assertEqual(list(self.directory.iterdir()), [])
        component = self._assets("component")[0]
        component_id = component["asset_id"]

        definition = {
            "name": "按钮",
            "description": "主要操作",
            "props": [
                {"name": "label", "type": "string", "default": "确定"},
                {"name": "tone", "type": "enum", "values": ["primary", "ghost"],
                 "default": "primary"},
            ],
            "variants": [{"name": "size", "values": ["s", "m"]}],
            "states": ["default", "hover"],
            "slots": [{"name": "icon"}],
            "constraints": {"minWidth": "4rem"},
            "dependencies": {"tokens": [], "components": []},
        }
        self.page.fill("#document-text", json.dumps(definition, ensure_ascii=False))
        self.page.click("#document-save")
        expect(self.page.locator("#document-status")).to_contain_text("草稿已保存")

        # The instance sample renders the declared surface with real values.
        self.page.fill("#instance-params", json.dumps({"label": "保存"}, ensure_ascii=False))
        self.page.click("#instance-render")
        expect(self.page.locator("#instance-slots")).to_have_text("icon")
        expect(self.page.locator("#instance-note")).to_contain_text("组件源码未执行")
        frame = self._instance_frame()
        frame.wait_for_selector("h1", timeout=10000)
        body = frame.inner_text("body")
        self.assertIn("保存", body)
        self.assertIn("primary", body)

        # An unknown property type is refused with the real reason and
        # produces no revision.
        broken = dict(definition, props=[{"name": "tone", "type": "colour"}])
        self.page.fill("#document-text", json.dumps(broken, ensure_ascii=False))
        self.page.click("#document-save")
        expect(self.page.locator("#document-error")).to_be_visible()
        self.assertEqual(
            self.h.runtime.store.asset_revisions(component_id), []
        )

        self.page.fill("#document-text", json.dumps(definition, ensure_ascii=False))
        self.page.click("#document-save")
        expect(self.page.locator("#document-status")).to_contain_text("草稿已保存")
        self.page.click("#document-publish")
        expect(self.page.locator("#document-status")).to_contain_text("已发布第 1 次修订")
        self.assertEqual(
            len(self.h.runtime.store.asset_revisions(component_id)), 1
        )
        expect(self.page.locator("#document-validation-errors")).to_be_empty()

    def test_create_a_page_and_distill_a_candidate_without_touching_it(self) -> None:
        self.page.click("#create-page")
        expect(self.page.locator("#document-panel")).to_be_visible()
        expect(self.page.locator("#page-distill")).to_be_visible()
        expect(self.page.locator("#component-instance")).to_be_hidden()
        self.page.click("#document-publish")
        expect(self.page.locator("#document-status")).to_contain_text("已发布第 1 次修订")
        page_asset = self._assets("page")[0]
        page_id = page_asset["asset_id"]
        before = self.page.input_value("#document-text")

        self.page.fill("#distill-nodes", "title")
        self.page.click("#distill-button")
        expect(self.page.locator("#distill-result")).to_contain_text("候选")
        expect(self.page.locator("#distill-result")).to_contain_text("complete=false")
        candidates = [
            row for row in self._assets("component") if "区块" in row["name"] or "新页面" in row["name"]
        ]
        self.assertEqual(len(candidates), 1)
        # The source page keeps its layout and its single revision.
        self.assertEqual(
            len(self.h.runtime.store.asset_revisions(page_id)), 1
        )
        self.page.click("#document-reload")
        expect(self.page.locator("#document-text")).to_have_value(before)


class CanvasJourneyTest(unittest.TestCase):
    """WB-07 in the browser: boards, gestures, saves, undo, snapshot."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        # The canvas panel is tall: a taller window keeps the board and the
        # asset list reachable by real pointer coordinates.
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("canvas-ui")
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        imported = self.h.import_assets(self.project_id, ["brand.md"])
        self.asset = imported.json["result"]["asset"]
        published = self.h.asset_action(self.project_id, self.asset["assetId"], "publish")
        assert published.status == 200, published.text
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()

    # -- helpers ---------------------------------------------------------

    def create_canvas(self, name: str = "首页方案") -> None:
        self.page.fill("#canvas-name", name)
        self.page.click("#canvas-create")
        expect(self.page.locator("#canvas-save-state")).to_contain_text("已保存")
        expect(self.page.locator(".canvas-node")).to_have_count(1)

    def test_round3_canvas_dark_theme(self) -> None:
        self.create_canvas()
        self.page.emulate_media(color_scheme="dark")
        node = self.page.locator(".canvas-node").first
        self.assertNotEqual(node.evaluate("el => getComputedStyle(el).backgroundColor"),
                            "rgb(247, 249, 252)")
        for token in ("--canvas-grid-1", "--canvas-grid-2", "--canvas-node-bg",
                      "--canvas-node-text-bg", "--canvas-node-instance-bg"):
            self.assertTrue(self.page.locator("html").evaluate(
                "(el, token) => getComputedStyle(el).getPropertyValue(token).trim()", token))
        expect(node).to_have_css("background-color", "rgb(43, 49, 61)")
        expect(self.page.locator("#canvas-stage")).to_have_css(
            "background-color", "rgb(28, 31, 37)")
        self.page.emulate_media(color_scheme="light")
        expect(node).to_have_css("background-color", "rgb(255, 255, 255)")
        css = (Path(__file__).parents[1] / "design_playbook_workbench" /
               "web" / "app.css").read_text(encoding="utf-8")
        for selector in (".canvas-node", ".canvas-node-text", ".canvas-node-instance"):
            body = re.search(re.escape(selector) + r"\s*\{([^}]+)", css)[1]
            self.assertNotRegex(body, r"background:\s*#")

    def test_round3_scheme_fields_are_grouped_and_compact(self) -> None:
        for selector in ("#scheme-rules", "#scheme-acceptance"):
            expect(self.page.locator(selector)).to_have_css("min-height", "80px")
        self.assertEqual(self.page.locator("#scheme-regions").evaluate(
            "el => el.parentElement.querySelector('label').htmlFor"), "scheme-regions")

    def test_round3_canvas_node_selection_focuses_shortcut_scope(self) -> None:
        self.create_canvas()
        node = self.page.locator(".canvas-node").first
        node.click()
        expect(self.page.locator("#canvas-viewport")).to_be_focused()
        x = float(self.page.locator("#prop-x").input_value())
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#prop-x")).to_have_value(str(int(x + 1)))
        self.page.locator("#canvas-heading").focus()
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#prop-x")).to_have_value(str(int(x + 2)))
        self.page.locator("#prop-content").focus()
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#prop-x")).to_have_value(str(int(x + 2)))

        self.page.locator("#canvas-board").focus()
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#prop-x")).to_have_value(str(int(x + 2)))

    def canvas_id(self) -> str:
        return self.page.evaluate(
            "() => document.querySelector('#canvas-select').value"
        )

    def server_document(self) -> dict:
        listing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{self.canvas_id()}",
            token=self.h.token,
        )
        assert listing.status == 200, listing.text
        return listing.json["document"]

    def server_nodes(self) -> list[dict]:
        return self.server_document()["boards"][0]["nodes"]

    def node(self, node_id: str) -> dict:
        return next(node for node in self.server_nodes() if node["id"] == node_id)

    def wait_saved(self) -> None:
        expect(self.page.locator("#canvas-save-state")).to_contain_text("已保存")

    def wait_for(self, check, label: str, timeout: float = 8.0):
        """Poll the service until the confirmed state satisfies ``check``.

        The save label alone is not a barrier (it also reads "saved" right
        after loading), so the assertions wait on the stored result.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                value = check()
            except (AssertionError, StopIteration):
                value = None
            if value:
                return value
            self.page.wait_for_timeout(120)
        raise AssertionError(f"timed out waiting for {label}")

    def wait_node_layout(self, node_id: str, predicate, label: str):
        return self.wait_for(
            lambda: predicate(self.node(node_id)["layout"]) and True, label
        )

    def wait_node_count(self, count: int):
        self.wait_for(lambda: len(self.server_nodes()) == count, f"{count} nodes")
        self.assertEqual(len(self.server_nodes()), count)
        # 服务端确认早于渲染它的响应回到页面。键盘操作读的是内存中的画布
        # （Ctrl+A 全选、Ctrl+D 复制），此刻继续会作用在过期的节点集合上——
        # 慢 I/O 下这正好让随后的对齐落空。
        self.page.wait_for_function(
            "n => document.querySelectorAll('.canvas-node').length === n", arg=count
        )

    def canvas_scale(self) -> float:
        return int(self.page.inner_text("#canvas-zoom-label").rstrip("%")) / 100

    def drag_node(self, node_id: str, dx: int, dy: int) -> None:
        """Drag a node by board units, not by screen pixels."""
        self.page.locator("#canvas-viewport").scroll_into_view_if_needed()
        scale = self.canvas_scale()
        box = self.page.locator(f'.canvas-node[data-node-id="{node_id}"]').bounding_box()
        assert box is not None
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 12)
        self.page.mouse.down()
        self.page.mouse.move(
            box["x"] + box["width"] / 2 + dx * scale,
            box["y"] + 12 + dy * scale,
            steps=6,
        )
        self.page.mouse.up()

    def only_node_id(self) -> str:
        return self.page.locator(".canvas-node").first.get_attribute("data-node-id")

    def canvas_action(self, verb: str, *, payload=None, expected=0):
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id()}/{verb}",
            method="POST",
            body={
                "operation": {
                    "operationId": f"op_ui_{verb}_{expected}",
                    "payload": {"action": verb, **(payload or {})},
                    "expectedCounter": expected,
                },
                **(payload or {}),
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )

    # -- journeys --------------------------------------------------------

    def test_mouse_and_keyboard_editing_saves_confirmed_state(self) -> None:
        self.create_canvas()
        node_id = self.only_node_id()
        start = self.node(node_id)["layout"]

        # One drag gesture is one transaction, confirmed by the service. The
        # exact landing point depends on the fitted zoom, so the assertion is
        # about the acknowledged movement, not a pixel count.
        self.drag_node(node_id, 60, 40)
        self.wait_node_layout(
            node_id, lambda layout: layout["x"] > start["x"] + 50, "the dragged position"
        )
        self.wait_saved()
        dragged = self.node(node_id)["layout"]
        self.assertAlmostEqual(dragged["x"] - start["x"], 60, delta=2)
        self.assertAlmostEqual(dragged["y"] - start["y"], 40, delta=2)

        # Keyboard alternatives move the same selection.
        self.page.locator(f'.canvas-node[data-node-id="{node_id}"]').click()
        self.page.locator("#canvas-viewport").press("ArrowRight")
        self.wait_node_layout(
            node_id, lambda layout: layout["x"] > dragged["x"] + 0.5, "the keyboard move"
        )
        self.page.locator("#canvas-viewport").press("ArrowDown")
        self.wait_node_layout(
            node_id,
            lambda layout: layout["y"] > dragged["y"] + 0.5,
            "the keyboard move down",
        )
        self.wait_saved()
        after_keys = self.node(node_id)["layout"]
        self.assertAlmostEqual(after_keys["x"] - dragged["x"], 1, delta=0.5)
        self.assertAlmostEqual(after_keys["y"] - dragged["y"], 1, delta=0.5)
        self.page.locator("#canvas-viewport").press("Shift+ArrowRight")
        self.wait_node_layout(
            node_id,
            lambda layout: layout["x"] > after_keys["x"] + 9,
            "the shifted keyboard move",
        )
        self.wait_saved()
        self.assertAlmostEqual(
            self.node(node_id)["layout"]["x"] - after_keys["x"], 10, delta=0.5
        )

        # Duplicate, undo, redo, and delete round-trip through the server.
        self.page.locator("#canvas-viewport").press("Control+d")
        self.wait_node_count(2)
        self.page.locator("#canvas-viewport").press("Control+z")
        self.wait_node_count(1)
        self.page.locator("#canvas-viewport").press("Control+Shift+z")
        self.wait_node_count(2)
        self.wait_saved()

        # Align is a real command, not a preview.
        self.page.locator("#canvas-viewport").press("Control+a")
        self.page.locator('.canvas-align[data-align="left"]').click()
        self.wait_for(
            lambda: len({node["layout"]["x"] for node in self.server_nodes()}) == 1,
            "the aligned column",
        )

        # A resize handle drag is one gesture too.
        self.page.locator("#canvas-viewport").press("Escape")
        self.page.locator(".canvas-node").last.click()
        target = self.page.locator(".canvas-node[data-selected='true']").first
        resized_id = target.get_attribute("data-node-id")
        before_width = self.node(resized_id)["layout"]["width"]
        target.scroll_into_view_if_needed()
        scale = self.canvas_scale()
        handle = target.locator(".canvas-resize-handle")
        box = handle.bounding_box()
        assert box is not None
        self.page.mouse.move(box["x"] + 4, box["y"] + 4)
        self.page.mouse.down()
        self.page.mouse.move(
            box["x"] + 4 + 40 * scale, box["y"] + 4 + 24 * scale, steps=5
        )
        self.page.mouse.up()
        self.wait_for(
            lambda: self.node(resized_id)["layout"]["width"] > before_width + 30,
            "the resized node",
        )
        self.wait_saved()

        # Node content and token references are real properties too.
        self.page.fill("#prop-content", "新的标题")
        self.page.click("#prop-content-apply")
        self.wait_for(
            lambda: self.node(resized_id)["props"].get("text") == "新的标题",
            "the edited text",
        )
        self.page.fill("#prop-token", "color.brand")
        self.page.click("#prop-token-apply")
        self.wait_for(
            lambda: self.node(resized_id)["props"].get("tokenRef") == "color.brand",
            "the token reference",
        )
        self.wait_saved()

        # A second board is a real board, and the snapshot renders layout.
        self.page.click("#canvas-board-add")
        expect(self.page.locator("#canvas-board option")).to_have_count(2)
        self.wait_for(
            lambda: len(self.server_document()["boards"]) == 2, "the second board"
        )
        self.wait_saved()
        self.page.click("#canvas-snapshot")
        expect(self.page.locator("#canvas-snapshot-note")).to_contain_text(
            "静态布局快照"
        )
        expect(self.page.locator("#canvas-snapshot-frame")).to_be_visible()
        frame_url = self.page.locator("#canvas-snapshot-frame").get_attribute("src")
        self.assertTrue(frame_url.startswith(self.h.preview_origin))

        # Reopening the panel reads the persisted state, not a UI guess.
        boards_before = len(self.server_document()["boards"])
        self.page.click("#canvas-close")
        expect(self.page.locator("#canvas-panel")).to_be_hidden()
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        expect(self.page.locator("#canvas-board option")).to_have_count(boards_before)
        self.page.locator("#canvas-undo").click()
        expect(self.page.locator("#canvas-save-state")).to_contain_text("已保存")

    def test_placing_an_asset_creates_a_fixed_revision_instance(self) -> None:
        self.create_canvas()
        self.page.locator("#project-rows tr .assets-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_visible()
        self.page.select_option("#assets-kind", "markdown")
        self.page.click("#assets-search-button")
        self.page.locator(".asset-item").first.locator(".asset-select").click()
        expect(self.page.locator("#asset-detail")).to_be_visible()
        self.page.click("#asset-into-canvas")
        self.wait_for(
            lambda: len([n for n in self.server_nodes() if n["type"] == "instance"])
            == 1,
            "the instance node",
        )
        self.wait_saved()
        expect(self.page.locator(".canvas-node-instance")).to_have_count(1)
        instances = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/instances",
            token=self.h.token,
        ).json["instances"]
        self.assertEqual(len(instances), 1)
        nodes = self.server_nodes()
        instance_node = next(node for node in nodes if node["type"] == "instance")
        self.assertEqual(
            instance_node["props"]["instanceId"], instances[0]["instanceId"]
        )
        self.assertIn("实例", self.page.locator(".canvas-node-instance").inner_text())

        # The canvas names the instance; the revision move stays WB-04's.
        (self.directory / "brand.md").write_text("# Brand v2\n", encoding="utf-8")
        assert (
            self.h.asset_action(self.project_id, self.asset["assetId"], "refresh-draft").status
            == 200
        )
        published = self.h.asset_action(self.project_id, self.asset["assetId"], "publish")
        self.assertEqual(published.status, 200, published.text)
        self.page.locator(".canvas-node-instance").click()
        expect(self.page.locator("#canvas-instance-props")).to_be_visible()
        self.page.click("#canvas-instance-upgrade")
        expect(self.page.locator("#canvas-instance-info")).to_contain_text(
            "第 2 次修订"
        )
        upgraded = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/instances",
            token=self.h.token,
        ).json["instances"]
        self.assertEqual(upgraded[0]["revisionNumber"], 2)
        # Upgrading an instance never rewrites the canvas document itself.
        self.assertEqual(len(self.server_nodes()), 2)

    def test_a_failed_flush_keeps_the_draft_and_never_claims_saved(self) -> None:
        self.create_canvas()
        node_id = self.only_node_id()
        self.page.route(
            "**/actions/canvases/**",
            lambda route: route.abort("failed"),
        )
        self.page.locator(f'.canvas-node[data-node-id="{node_id}"]').click()
        self.page.locator("#canvas-viewport").press("ArrowRight")
        expect(self.page.locator("#canvas-save-state")).to_contain_text("保存失败")
        expect(self.page.locator("#canvas-retry")).to_be_visible()
        expect(self.page.locator("#canvas-dirty-note")).to_be_visible()
        self.page.unroute("**/actions/canvases/**")
        self.page.click("#canvas-retry")
        self.wait_node_layout(
            node_id, lambda layout: layout["x"] == 49, "the retried draft"
        )
        self.wait_saved()

    def test_a_conflicting_write_is_offered_as_a_branch(self) -> None:
        self.create_canvas()
        node_id = self.only_node_id()
        original_id = self.canvas_id()
        # Another writer (window or Agent) commits first.
        other = self.canvas_action(
            "commands",
            payload={
                "commands": [
                    {
                        "kind": "node-move",
                        "boardId": self.server_document()["boards"][0]["id"],
                        "nodeIds": [node_id],
                        "dx": 200,
                        "dy": 0,
                    }
                ]
            },
            expected=0,
        )
        self.assertEqual(other.status, 200, other.text)
        self.page.locator(f'.canvas-node[data-node-id="{node_id}"]').click()
        self.page.locator("#canvas-viewport").press("ArrowDown")
        expect(self.page.locator("#canvas-save-state")).to_contain_text("保存冲突")
        expect(self.page.locator("#canvas-fork")).to_be_visible()
        self.page.once("dialog", lambda dialog: dialog.accept("本页草稿"))
        self.page.click("#canvas-fork")
        expect(self.page.locator("#canvas-save-state")).to_contain_text("已保存")
        names = self.page.locator("#canvas-select option")
        expect(names).to_have_count(2)
        branch_id = self.canvas_id()
        self.assertNotEqual(branch_id, original_id)
        # The other writer's state is intact; the draft is a separate canvas.
        original = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{original_id}",
            token=self.h.token,
        ).json["document"]
        self.assertEqual(original["boards"][0]["nodes"][0]["layout"]["x"], 248)
        branch = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{branch_id}",
            token=self.h.token,
        ).json["document"]
        branch_node = branch["boards"][0]["nodes"][0]
        self.assertEqual(branch_node["layout"]["y"], 49)
        canvases = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases",
            token=self.h.token,
        ).json["canvases"]
        self.assertEqual(len(canvases), 2)

    def test_the_201st_instance_is_refused_in_the_ui(self) -> None:
        created = self.h.action(
            self.project_id,
            "instances",
            payload={"assetId": self.asset["assetId"]},
        )
        self.assertEqual(created.status, 200, created.text)
        instance_id = created.json["result"]["instanceId"]
        nodes = [
            {
                "id": f"i{index}",
                "type": "instance",
                "children": [],
                "props": {"instanceId": instance_id, "params": {}},
                "layout": {"x": (index % 20) * 30, "y": (index // 20) * 30,
                           "width": 20, "height": 20, "z": index},
            }
            for index in range(200)
        ]
        document = {
            "name": "满画布",
            "boards": [
                {"id": "b_full", "name": "满", "width": 1200, "height": 800,
                 "nodes": nodes, "flowEdges": []}
            ],
        }
        created_canvas = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_ui_full_canvas",
                    "payload": {"action": "canvases"},
                },
                "name": "满画布",
                "document": document,
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(created_canvas.status, 200, created_canvas.text)
        new_canvas_id = created_canvas.json["result"]["canvas"]["canvasId"]
        self.page.click("#canvas-reload")
        expect(self.page.locator("#canvas-select option")).to_have_count(1)
        self.page.select_option("#canvas-select", new_canvas_id)
        expect(self.page.locator(".canvas-node")).to_have_count(200)

        self.page.locator("#project-rows tr .assets-button").first.click()
        self.page.select_option("#assets-kind", "markdown")
        self.page.click("#assets-search-button")
        self.page.locator(".asset-item").first.locator(".asset-select").click()
        self.page.click("#asset-into-canvas")
        expect(self.page.locator("#canvas-error")).to_contain_text("limit-exceeded")
        expect(self.page.locator("#canvas-retry")).to_be_visible()
        # The whole operation was refused: the stored document still has 200.
        stored = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{new_canvas_id}",
            token=self.h.token,
        ).json
        self.assertEqual(stored["validation"]["instanceCount"], 200)
        self.assertEqual(len(stored["document"]["boards"][0]["nodes"]), 200)


class OrchestrationJourneyTest(unittest.TestCase):
    """WB-08 in the browser: flows, schemes, snapshots, context consent."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("orchestration-ui")
        (self.directory / "notes.md").write_text("notes\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        self.page.fill("#canvas-name", "编排方案")
        self.page.click("#canvas-create")
        expect(self.page.locator(".canvas-node")).to_have_count(1)

    def canvas_id(self) -> str:
        return self.page.evaluate(
            "() => document.querySelector('#canvas-select').value"
        )

    def server_document(self) -> dict:
        response = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{self.canvas_id()}",
            token=self.h.token,
        )
        assert response.status == 200, response.text
        return response.json["document"]

    def wait_for(self, check, label: str, timeout: float = 8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                value = check()
            except (AssertionError, StopIteration):
                value = None
            if value:
                return value
            self.page.wait_for_timeout(120)
        raise AssertionError(f"timed out waiting for {label}")

    def select_node(self, node_id: str) -> None:
        """Select a specific node by clicking a corner the duplicate cannot cover."""
        self.page.locator(f'.canvas-node[data-node-id="{node_id}"]').click(
            position={"x": 4, "y": 4}
        )

    def add_second_node(self) -> None:
        """A second node makes flow endpoints and multi-select meaningful."""
        self.page.locator("#canvas-viewport").press("Control+a")
        self.page.locator("#canvas-viewport").press("Control+d")
        self.wait_for(
            lambda: len(self.server_document()["boards"][0]["nodes"]) == 2,
            "the duplicated node",
        )

    def test_flows_scheme_snapshots_and_context_consent(self) -> None:
        self.add_second_node()
        board = self.server_document()["boards"][0]
        node_ids = [node["id"] for node in board["nodes"]]

        # Flow edges: a loop between two nodes is a normal user flow.
        self.page.select_option("#flow-from", node_ids[0])
        self.page.select_option("#flow-to", node_ids[1])
        self.page.click("#flow-add")
        self.wait_for(
            lambda: len(self.server_document()["boards"][0]["flowEdges"]) == 1,
            "the first flow edge",
        )
        self.page.select_option("#flow-from", node_ids[1])
        self.page.select_option("#flow-to", node_ids[0])
        self.page.select_option("#flow-kind", "back")
        self.page.fill("#flow-label", "返回")
        self.page.click("#flow-add")
        self.wait_for(
            lambda: len(self.server_document()["boards"][0]["flowEdges"]) == 2,
            "the looping flow edge",
        )
        expect(self.page.locator("#flow-list li")).to_have_count(2)
        # Navigation is not lineage: adding flow edges created no asset and
        # wrote no derived-from relation (canvas nodes are not assets).
        self.assertEqual(self.h.runtime.store.project_assets(self.project_id), [])

        # Scheme constraints describe the scheme.
        self.page.fill("#scheme-width", "1440")
        self.page.fill("#scheme-height", "900")
        self.page.fill("#scheme-device", "desktop")
        self.page.fill("#scheme-rules", "使用 8pt 间距\n主色仅用于主操作")
        self.page.fill("#scheme-regions", node_ids[1])
        self.page.fill("#scheme-acceptance", "首屏一次点击到达详情")
        self.page.click("#scheme-save")
        self.wait_for(
            lambda: (self.server_document()["boards"][0]["scheme"] or {}).get(
                "viewport", {}
            ).get("width")
            == 1440,
            "the saved scheme",
        )
        expect(self.page.locator("#scheme-note")).to_contain_text("已声明方案约束")

        # A derived scheme is a separate board with recorded lineage.
        self.page.once("dialog", lambda dialog: dialog.accept("方案 B"))
        self.page.click("#scheme-derive")
        self.wait_for(
            lambda: len(self.server_document()["boards"]) == 2,
            "the derived board",
        )
        derived = self.server_document()["boards"][1]
        self.assertEqual(derived["scheme"]["derivedFrom"]["boardId"], board["id"])
        expect(self.page.locator("#canvas-board option")).to_have_count(2)
        expect(self.page.locator("#scheme-note")).to_contain_text("派生自画板")
        # The panel switched to the derived board: later steps select from it.
        node_ids = [node["id"] for node in derived["nodes"]]

        # Fixed snapshot, then a later edit must not move it.
        self.page.click("#snapshot-create")
        snapshot = self.wait_for(
            lambda: self.h.runtime.store.canvas_scheme_snapshots(self.canvas_id()) or None,
            "the frozen snapshot",
        )[0]
        frozen_hash = snapshot["content_hash"]
        self.select_node(node_ids[0])
        self.page.locator("#canvas-viewport").press("ArrowRight")
        self.wait_for(
            lambda: self.h.runtime.store.canvas(
                self.canvas_id()
            )["counter"]
            > snapshot["counter"],
            "the canvas edit",
        )
        again = self.h.runtime.store.scheme_snapshot(snapshot["snapshot_id"])
        self.assertEqual(again["content_hash"], frozen_hash)

        # Compare two snapshots side by side without crowning a winner.
        self.page.click("#canvas-board-add")
        self.wait_for(
            lambda: len(self.server_document()["boards"]) == 3, "the third board"
        )
        self.page.click("#snapshot-create")
        self.wait_for(
            lambda: len(self.h.runtime.store.canvas_scheme_snapshots(self.canvas_id())) == 2,
            "the second snapshot",
        )
        options = self.page.locator("#compare-left option")
        expect(options).to_have_count(2)
        self.page.click("#compare-run")
        expect(self.page.locator("#compare-grid")).to_be_visible()
        note = self.page.locator("#compare-note")
        expect(note).to_contain_text("不选择赢家")
        left_src = self.page.locator("#compare-left-frame").get_attribute("src")
        right_src = self.page.locator("#compare-right-frame").get_attribute("src")
        self.assertTrue(left_src.startswith(self.h.preview_origin))
        self.assertTrue(right_src.startswith(self.h.preview_origin))

        # Context: only the selected node and the named file are included.
        # Switch back to the derived board (adding a board selected the new one).
        self.page.select_option("#canvas-board", derived["id"])
        expect(self.page.locator(".canvas-node")).to_have_count(2)
        self.select_node(node_ids[1])
        self.page.fill("#context-files", "notes.md")
        self.page.click("#context-build")
        expect(self.page.locator("#context-content")).to_contain_text("合计")
        expect(self.page.locator("#context-content")).to_contain_text("notes.md")
        expect(self.page.locator("#context-exclusions")).to_contain_text("credentials")
        expect(self.page.locator("#context-exclusions")).to_contain_text("run-and-evidence-logs")
        expect(self.page.locator("#context-state")).to_contain_text("草稿")
        first_digest = self.page.evaluate(
            "() => document.querySelector('#context-state').textContent"
        )
        self.page.click("#context-confirm")
        expect(self.page.locator("#context-state")).to_contain_text("已确认")
        expect(self.page.locator("#context-stale")).to_be_hidden()

        # Changing the selection invalidates the confirmation.
        self.page.locator("#canvas-viewport").press("Control+a")
        self.page.click("#context-build")
        expect(self.page.locator("#context-stale")).to_be_visible()
        expect(self.page.locator("#context-state")).to_contain_text("草稿")
        self.assertNotEqual(
            first_digest,
            self.page.evaluate(
                "() => document.querySelector('#context-state').textContent"
            ),
        )
        selections = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{self.canvas_id()}/contexts",
            token=self.h.token,
        ).json["selections"]
        self.assertEqual(len(selections), 1)
        stale = selections[0]
        self.assertTrue(stale["staleConfirmation"])
        refused = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id()}/confirm",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_ui_stale_confirm",
                    "payload": {"action": "confirm"},
                },
                "selectionId": stale["selectionId"],
                "digest": stale["confirmed"]["digest"],
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(refused.status, 409)
        # The fresh digest still confirms.
        self.page.click("#context-confirm")
        expect(self.page.locator("#context-state")).to_contain_text("已确认")
        expect(self.page.locator("#context-stale")).to_be_hidden()


class WorkRequestJourneyTest(unittest.TestCase):
    """WB-10 in the browser: consent, real agent traffic, cancel honesty."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("work-ui")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    # -- helpers ---------------------------------------------------------

    def canvas_id(self) -> str:
        return self.page.evaluate(
            "() => document.querySelector('#canvas-select').value"
        )

    def request_id(self) -> str:
        return self.page.evaluate(
            """() => {
              const button = document.querySelector('#work-list button');
              return button ? button.dataset.requestId : '';
            }"""
        )

    def wait_for(self, check, label: str, timeout: float = 8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                value = check()
            except (AssertionError, StopIteration):
                value = None
            if value:
                return value
            self.page.wait_for_timeout(120)
        raise AssertionError(f"timed out waiting for {label}")

    def confirmed_context(self) -> str:
        """Build and confirm a context through the canvas panel."""
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        self.page.fill("#canvas-name", "任务画布")
        self.page.click("#canvas-create")
        expect(self.page.locator(".canvas-node")).to_have_count(1)
        self.page.locator(".canvas-node").first.click()
        self.page.click("#context-build")
        expect(self.page.locator("#context-state")).to_contain_text("草稿")
        self.page.click("#context-confirm")
        expect(self.page.locator("#context-state")).to_contain_text("已确认")
        return self.page.evaluate(
            "() => document.querySelector('#context-state').textContent"
        )

    def agent_call(self, verb: str, request_id: str, payload: dict):
        record = json.loads(
            (
                self.h.runtime.data_dir.session_dir / f"claim-{request_id}.json"
            ).read_text(encoding="utf-8")
        )
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/requests/{request_id}/{verb}",
            method="POST",
            body={
                "operation": {
                    "operationId": f"op_ui_agent_{verb}_{request_id[:8]}",
                    "payload": {"action": verb},
                },
                **payload,
            },
            capability=record["token"],
        )

    # -- journeys --------------------------------------------------------

    def test_consent_handoff_and_real_agent_events(self) -> None:
        self.confirmed_context()
        self.page.locator("#project-rows tr .work-button").first.click()
        expect(self.page.locator("#work-panel")).to_be_visible()
        expect(self.page.locator("#work-context-note")).to_contain_text("已确认")

        self.page.fill("#work-title", "首页静态改版")
        self.page.fill("#work-goal", "改写首页标题并保持既有布局")
        self.page.fill("#work-reuse", "首页布局")
        self.page.fill("#work-new", "标题文案")
        # The result below reports a dependency change; the request must grant
        # add-dependency or the agent's submit is refused (work.py gate).
        self.page.check('input.work-action[value="add-dependency"]')
        self.page.click("#work-create")
        expect(self.page.locator("#work-detail-state")).to_contain_text("等待确认发送范围")
        # Nothing is sent and no credential exists before consent.
        expect(self.page.locator("#work-detail-capability")).to_have_text("尚未生成")
        expect(self.page.locator("#work-attempt")).to_contain_text("不推测进度")
        request_id = self.request_id()
        self.assertTrue(request_id)

        self.page.click("#work-consent")
        expect(self.page.locator("#work-detail-state")).to_contain_text("等待 Agent 接手")
        handoff = self.page.locator("#work-handoff")
        expect(handoff).to_contain_text("/design-playbook:run-handoff")
        expect(handoff).to_contain_text(request_id)
        # The credential never appears on screen or in a response.
        token = json.loads(
            (
                self.h.runtime.data_dir.session_dir / f"claim-{request_id}.json"
            ).read_text(encoding="utf-8")
        )["token"]
        self.assertNotIn(token, self.page.content())
        # No fake progress while nobody has claimed the task.
        expect(self.page.locator("#work-attempt")).to_contain_text("不推测进度")

        claimed = self.agent_call("claim", request_id, {})
        self.assertEqual(claimed.status, 200, claimed.text)
        lease = claimed.json["result"]["lease"]
        self.page.click("#work-reload")
        expect(self.page.locator("#work-detail-state")).to_contain_text("执行中")
        expect(self.page.locator("#work-attempt")).to_contain_text(
            f"attempt #{lease['sequence']}"
        )

        beat = self.agent_call(
            "heartbeat",
            request_id,
            {
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "progress": {"phase": "editing", "files": 1},
            },
        )
        self.assertEqual(beat.status, 200, beat.text)
        self.page.click("#work-reload")
        expect(self.page.locator("#work-attempt")).to_contain_text("editing")

        submitted = self.agent_call(
            "result",
            request_id,
            {
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "result": {
                    "summary": "改写标题",
                    "targetStack": "static-html",
                    "changes": [
                        {"path": "index.html", "operation": "create",
                         "content": "<h1>新标题</h1>\n"}
                    ],
                    "dependencies": [{"name": "none", "path": "package.json"}],
                    "entrypoints": {"preview": "index.html", "build": None, "test": None},
                    "artifacts": [{"path": "index.html", "hash": "sha256:" + "b" * 64}],
                    "runReceipt": {"command": "python -m http.server", "exitCode": 0},
                },
            },
        )
        self.assertEqual(submitted.status, 200, submitted.text)
        self.page.click("#work-reload")
        expect(self.page.locator("#work-detail-state")).to_contain_text("已收到结果提案")
        expect(self.page.locator("#work-detail-state")).to_contain_text("未验证")
        expect(self.page.locator("#work-result-list")).to_contain_text("index.html")
        expect(self.page.locator("#work-result-list")).to_contain_text("退出码 0")
        expect(self.page.locator("#work-attempts")).to_contain_text("result-submitted")
        # The result is a proposal: approving it is not this panel's action.
        expect(self.page.locator("#work-result-list")).to_contain_text("需维护者批准")
        self.assertNotIn("已验证", self.page.locator("#work-detail-state").inner_text())

    def test_cancel_is_not_a_fake_stop_and_a_late_result_is_refused(self) -> None:
        self.confirmed_context()
        self.page.locator("#project-rows tr .work-button").first.click()
        self.page.fill("#work-title", "取消演示")
        self.page.fill("#work-goal", "演示取消语义")
        self.page.click("#work-create")
        expect(self.page.locator("#work-detail-state")).to_contain_text("等待确认发送范围")
        self.page.click("#work-consent")
        expect(self.page.locator("#work-detail-state")).to_contain_text("等待 Agent 接手")
        request_id = self.request_id()
        claimed = self.agent_call("claim", request_id, {})
        self.assertEqual(claimed.status, 200, claimed.text)
        lease = claimed.json["result"]["lease"]

        self.page.click("#work-cancel")
        expect(self.page.locator("#work-detail-state")).to_contain_text("已请求取消")
        # The UI does not claim the Agent stopped.
        self.assertNotIn(
            "已取消（宿主确认）",
            self.page.locator("#work-detail-state").inner_text(),
        )
        late = self.agent_call(
            "result",
            request_id,
            {
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "result": {"summary": "太晚了", "targetStack": "static-html",
                           "changes": []},
            },
        )
        self.assertEqual(late.status, 409, late.text)

        self.page.click("#work-confirm-cancel")
        expect(self.page.locator("#work-detail-state")).to_contain_text("已取消（宿主确认）")
        # The retired credential and its record are gone.
        self.assertFalse(
            (
                self.h.runtime.data_dir.session_dir / f"claim-{request_id}.json"
            ).exists()
        )
        expect(self.page.locator("#work-detail-capability")).not_to_have_text("尚未生成")


class OwnerBackflowJourneyTest(unittest.TestCase):
    """WB-11 in the browser: owner facts shown, confirmed, backflowed."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("owner-ui")
        self.publish_projection(
            "run-1",
            {
                "version": "owner-projection/v1",
                "runId": "run-1",
                "owner": "run-console",
                "runner": "design-playbook run-console",
                "generatedAt": "2026-09-26T12:00:00Z",
                "criteria": [
                    {"criterionId": "c-1", "role": "owner-verified", "verdict": "fail",
                     "sourceHash": "sha256:" + "1" * 64,
                     "evidenceHashes": ["sha256:" + "a" * 64]},
                ],
                "evidence": [
                    {"evidenceId": "e-1", "kind": "screenshot",
                     "hash": "sha256:" + "a" * 64, "criterionId": "c-1"},
                ],
                "findings": [
                    {"findingId": "f-1", "severity": "blocker",
                     "summary": "主操作不可键盘到达",
                     "sourceHash": "sha256:" + "2" * 64,
                     "pointBack": {"kind": "source", "path": "index.html",
                                   "repairOwner": "craft-guard"}},
                ],
            },
        )
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def publish_projection(self, run_id: str, document: dict) -> None:
        path = self.directory / ".design-playbook" / "runs" / run_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "projection.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_facts_shown_confirmed_and_backflowed_without_a_second_verdict(self) -> None:
        expect(self.page.locator("#project-rows tr")).to_have_count(1)
        self.page.locator("#project-rows tr .owner-button").first.click()
        expect(self.page.locator("#owner-panel")).to_be_visible()
        expect(self.page.locator("#owner-run-note")).to_contain_text("run-console")
        expect(self.page.locator("#owner-run-note")).to_contain_text("不重新裁决")
        # The owner's own verdicts are shown, not re-decided.
        expect(self.page.locator("#owner-criteria")).to_contain_text("c-1 · fail")
        expect(self.page.locator("#owner-evidence")).to_contain_text("screenshot")
        expect(self.page.locator("#owner-findings")).to_contain_text("craft-guard")

        # Confirming binds the object hash; the record shows it.
        self.page.once("dialog", lambda dialog: dialog.accept("人工核对后确认"))
        self.page.locator("#owner-criteria button").first.click()
        expect(self.page.locator("#owner-confirmations")).to_contain_text("owner-verified")
        expect(self.page.locator("#owner-criteria")).to_contain_text("已确认")
        stored = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/confirmations",
            token=self.h.token,
        ).json["confirmations"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["role"], "owner-verified")
        self.assertEqual(stored[0]["objectId"], "c-1")

        # A finding backflows into a draft candidate; the run is untouched.
        self.page.once("dialog", lambda dialog: dialog.accept("键盘可达候选"))
        self.page.locator("#owner-findings button").first.click()
        self.page.wait_for_timeout(400)
        components = [
            row
            for row in self.h.runtime.store.project_assets(self.project_id)
            if row["kind"] == "component"
        ]
        self.assertEqual(len(components), 1)
        detail = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/runs/run-1",
            token=self.h.token,
        ).json
        # The run's own facts did not change because a candidate was made.
        self.assertEqual(detail["criteria"][0]["verdict"], "fail")
        self.assertEqual(detail["findings"][0]["summary"], "主操作不可键盘到达")

    def test_a_changed_object_shows_stale_and_the_old_confirmation_lapses(self) -> None:
        expect(self.page.locator("#project-rows tr")).to_have_count(1)
        self.page.locator("#project-rows tr .owner-button").first.click()
        expect(self.page.locator("#owner-panel")).to_be_visible()
        self.page.once("dialog", lambda dialog: dialog.accept(""))
        self.page.locator("#owner-criteria button").first.click()
        expect(self.page.locator("#owner-criteria")).to_contain_text("已确认")

        # The owner re-runs and the criterion changes.
        self.publish_projection(
            "run-1",
            {
                "version": "owner-projection/v1",
                "runId": "run-1",
                "owner": "run-console",
                "criteria": [
                    {"criterionId": "c-1", "role": "owner-verified", "verdict": "pass",
                     "sourceHash": "sha256:" + "9" * 64},
                ],
                "evidence": [],
                "findings": [],
            },
        )
        self.page.click("#owner-reload")
        # The verdict is now the owner's new one, and the old confirmation no
        # longer applies to the changed object.
        expect(self.page.locator("#owner-criteria")).to_contain_text("c-1 · pass")
        criteria_text = self.page.locator("#owner-criteria").inner_text()
        self.assertNotIn("已确认", criteria_text)
        freshness = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/runs/run-1/freshness"
            f"?objectType=criterion&objectId=c-1&sourceHash=sha256:{'1' * 64}",
            token=self.h.token,
        ).json
        self.assertEqual(freshness["state"], "stale")


class LifecycleJourneyTest(unittest.TestCase):
    """WB-12 in the browser: archive, recycle bin, reference-safe delete."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("lifecycle-ui")
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.asset = self.h.import_assets(self.project_id, ["brand.md"]).json["result"]["asset"]
        published = self.h.asset_action(self.project_id, self.asset["assetId"], "publish")
        assert published.status == 200, published.text
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")
        self.page.locator("#project-rows tr .life-button").first.click()
        expect(self.page.locator("#life-panel")).to_be_visible()

    def wait_for(self, check, label, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                value = check()
            except (AssertionError, StopIteration):
                value = None
            if value:
                return value
            self.page.wait_for_timeout(120)
        raise AssertionError(f"timed out waiting for {label}")

    def select_asset(self) -> None:
        self.page.locator("#life-list button").first.click()
        expect(self.page.locator("#life-detail")).to_be_visible()

    def test_round3_lifecycle_actions_match_state(self) -> None:
        for lifecycle, action, visible in (
            ("published", None, {"archive", "trash", "references", "delete"}),
            ("archived", "archive", {"unarchive", "trash", "references", "delete"}),
            ("trashed", "trash", {"restore", "references", "delete"}),
            ("published", "restore", {"archive", "trash", "references", "delete"}),
        ):
            if action:
                self.page.click("#life-" + action)
                self.wait_for(lambda: self.h.runtime.store.asset(self.asset["assetId"])
                              ["lifecycle"] == lifecycle, lifecycle)
            self.select_asset()
            for verb in ("archive", "unarchive", "trash", "restore", "references", "delete"):
                button = self.page.locator("#life-" + verb)
                if verb in visible:
                    expect(button).to_be_visible()
                    expect(button).to_be_enabled()
                else:
                    expect(button).to_be_hidden()
                    expect(button).to_be_disabled()

    def test_archive_trash_restore_and_reference_safe_delete(self) -> None:
        # Archive then unarchive: discovery state only.
        self.select_asset()
        self.page.click("#life-archive")
        expect(self.page.locator("#life-project-note")).to_contain_text("归档 1")
        self.assertEqual(
            self.h.runtime.store.asset(self.asset["assetId"])["lifecycle"], "archived"
        )
        # The published revision is still readable while archived.
        self.assertIsNotNone(self.h.runtime.store.latest_revision(self.asset["assetId"]))
        self.select_asset()
        self.page.click("#life-unarchive")
        self.wait_for(
            lambda: self.h.runtime.store.asset(self.asset["assetId"])["lifecycle"]
            == "published",
            "unarchived",
        )

        # Trash then restore keeps the id.
        self.select_asset()
        self.page.click("#life-trash")
        self.wait_for(
            lambda: self.h.runtime.store.asset(self.asset["assetId"])["lifecycle"]
            == "trashed",
            "trashed",
        )
        self.page.select_option("#life-filter", "trashed")
        self.select_asset()
        self.page.click("#life-restore")
        self.wait_for(
            lambda: self.h.runtime.store.asset(self.asset["assetId"])["lifecycle"]
            == "published",
            "restored",
        )

        # A reference blocks deletion; the report is shown.
        instance = self.h.action(
            self.project_id, "instances", payload={"assetId": self.asset["assetId"]}
        )
        self.assertEqual(instance.status, 200, instance.text)
        self.page.select_option("#life-filter", "all")
        self.select_asset()
        self.page.click("#life-references")
        expect(self.page.locator("#life-refs-note")).to_contain_text("可删除：否")
        # Attempting delete does not remove it while referenced.
        self.page.click("#life-delete")
        self.page.wait_for_timeout(400)
        self.assertIsNotNone(self.h.runtime.store.asset(self.asset["assetId"]))

        # Detach, then permanent delete succeeds through the in-surface
        # confirmation: revealing it deletes nothing by itself, and only
        # the explicit second step removes the record.
        self.h.runtime.store.delete_instance(instance.json["result"]["instanceId"])
        self.select_asset()
        self.page.click("#life-delete")
        confirm = self.page.locator("#life-delete-confirm")
        expect(confirm).to_be_visible()
        # The impact report the maintainer just loaded is carried in.
        expect(self.page.locator("#life-delete-confirm-body")).to_contain_text(
            self.asset["name"]
        )
        self.assertIsNotNone(
            self.h.runtime.store.asset(self.asset["assetId"]),
            "revealing the confirmation must not delete anything",
        )
        # Escape cancels, and the asset survives.
        self.page.locator("#life-panel").press("Escape")
        expect(confirm).to_be_hidden()
        self.assertIsNotNone(self.h.runtime.store.asset(self.asset["assetId"]))
        self.page.click("#life-delete")
        self.page.click("#life-delete-confirm-button")
        self.wait_for(
            lambda: self.h.runtime.store.asset(self.asset["assetId"]) is None,
            "deleted",
        )
        self.assertTrue((self.directory / "brand.md").exists())


class BackupSettingsJourneyTest(unittest.TestCase):
    """WB-13 in the browser: create, verify, and restore a backup."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("backup-ui")
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Design")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        asset = self.h.import_assets(self.project_id, ["brand.md"]).json["result"]["asset"]
        assert self.h.asset_action(self.project_id, asset["assetId"], "publish").status == 200
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def test_create_verify_and_restore_from_the_settings_panel(self) -> None:
        self.page.click("#settings-open")
        expect(self.page.locator("#settings-panel")).to_be_visible()
        dest = str(self.h.base / "ui-backup.dpwb.zip")
        self.page.fill("#backup-dest", dest)
        self.page.click("#backup-create")
        expect(self.page.locator("#backup-note")).to_contain_text("已创建备份")
        expect(self.page.locator("#backup-note")).to_contain_text("含凭证：否")
        self.assertTrue(Path(dest).is_file())

        # Verify auto-filled the path; run it.
        self.page.click("#backup-verify")
        expect(self.page.locator("#backup-verify-note")).to_contain_text("校验通过")

        # Restore to a new empty directory; the original stays active.
        restore_dir = str(self.h.base / "ui-restored")
        self.page.fill("#restore-target", restore_dir)
        self.page.click("#restore-run")
        expect(self.page.locator("#restore-note")).to_contain_text("已恢复到")
        expect(self.page.locator("#restore-note")).to_contain_text("需重新授权：是")
        self.assertTrue((Path(restore_dir) / "workbench.db").is_file())
        # The active data directory is untouched.
        self.assertTrue(self.h.runtime.data_dir.database_path.is_file())


class ProposalJourneyTest(unittest.TestCase):
    """WB-09 in the browser: review a diff, authorize, revert, recover."""

    def setUp(self) -> None:
        # The page needs the pristine bootstrap, so the harness must not
        # consume it; maintainer-side API calls go through session.token.
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.token = self.h.runtime.session.token
        self.page = _BROWSER.new_page()
        self.addCleanup(self.page.close)
        self.origin = self.h.runtime.origin
        self.directory = self.h.make_directory("proposal-ui")
        self.file = self.directory / "index.html"
        self.file.write_bytes(b"<h1>hello</h1>\n")
        registered = self.h.register(self.directory, name="Proposals")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        granted = self.h.grant(
            self.project_id, ["read", "write"], expected_counter=0
        )
        assert granted.status == 200, granted.text
        self.counter = granted.json["counter"]
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def _propose(self, content: str, path: str = "index.html") -> dict:
        import hashlib

        changes = [
            {
                "path": path,
                "operation": "update" if path == "index.html" else "create",
                "content": content,
            }
        ]
        if path == "index.html":
            changes[0]["baseHash"] = (
                "sha256:" + hashlib.sha256(self.file.read_bytes()).hexdigest()
            )
        response = self.h.create_proposal(self.project_id, changes)
        assert response.status == 200, response.text
        return response.json["result"]

    def _open_panel(self) -> None:
        self.page.locator("#project-rows tr .proposals-button").first.click()
        expect(self.page.locator("#proposals-panel")).to_be_visible()

    def test_review_diff_apply_and_revert(self) -> None:
        self._propose("<h1>from proposal</h1>\n")
        self._open_panel()
        item = self.page.locator(".proposal-item").first
        expect(item).to_be_visible()
        expect(item.locator(".proposal-state")).to_have_text("等待授权")

        # The diff is on demand, and it shows both sides of the change.
        item.locator(".diff-button").click()
        diff = item.locator(".proposal-diff")
        expect(diff).to_be_visible()
        self.assertIn("-<h1>hello</h1>", diff.inner_text())
        self.assertIn("+<h1>from proposal</h1>", diff.inner_text())

        # Nothing is written until the maintainer authorizes the digest.
        self.assertEqual(self.file.read_bytes(), b"<h1>hello</h1>\n")
        self.page.on("dialog", lambda dialog: dialog.accept())
        item.locator(".apply-button").click()
        expect(self.page.locator(".proposal-item").first.locator(".proposal-state")).to_have_text(
            "已应用"
        )
        self.assertEqual(self.file.read_bytes(), b"<h1>from proposal</h1>\n")

        # Reverting produces a new proposal, listed first, that still needs
        # the maintainer's authorization.
        self.page.locator(".proposal-item").first.locator(".revert-button").click()
        expect(self.page.locator(".proposal-item")).to_have_count(2)
        newest = self.page.locator(".proposal-item").nth(0)
        expect(newest.locator(".proposal-state")).to_have_text("等待授权")
        self.assertEqual(self.file.read_bytes(), b"<h1>from proposal</h1>\n")
        newest.locator(".apply-button").click()
        expect(newest.locator(".proposal-state")).to_have_text("已应用")
        self.assertEqual(self.file.read_bytes(), b"<h1>hello</h1>\n")
        # The original proposal is still visible as applied history.
        expect(
            self.page.locator(".proposal-item").nth(1).locator(".proposal-state")
        ).to_have_text("已应用")

    def test_reject_leaves_the_source_untouched(self) -> None:
        self._propose("<h1>never applied</h1>\n")
        self._open_panel()
        item = self.page.locator(".proposal-item").first
        self.page.on("dialog", lambda dialog: dialog.accept())
        item.locator(".reject-button").click()
        expect(item.locator(".proposal-state")).to_have_text("已拒绝")
        self.assertEqual(self.file.read_bytes(), b"<h1>hello</h1>\n")
        expect(item.locator(".apply-button")).to_be_hidden()

    def test_recovery_required_is_shown_and_rollback_restores(self) -> None:
        from unittest import mock

        from design_playbook_workbench import proposals as module

        proposal = self._propose("<h1>partial</h1>\n")
        with mock.patch.object(
            module, "_atomic_replace", side_effect=OSError("injected")
        ):
            failed = self.h.proposal_action(
                self.project_id,
                proposal["proposalId"],
                "apply",
                digest=proposal["digest"],
            )
        self.assertEqual(failed.status, 503, failed.text)
        self.assertEqual(failed.error_code, "recovery-required")

        self._open_panel()
        item = self.page.locator(".proposal-item").first
        expect(item.locator(".proposal-state")).to_have_text("需要恢复")
        expect(item.locator(".proposal-recovery")).to_be_visible()
        expect(item.locator(".apply-button")).to_be_hidden()

        self.page.on("dialog", lambda dialog: dialog.accept())
        item.locator(".recover-rollback-button").click()
        expect(item.locator(".proposal-state")).to_have_text("已回滚")
        self.assertEqual(self.file.read_bytes(), b"<h1>hello</h1>\n")

    def test_apply_button_is_absent_when_the_project_only_has_read_scope(self) -> None:
        # Without the write scope the API refuses the proposal outright, so
        # the panel reports the real reason instead of offering a dead button.
        self.h.grant(self.project_id, ["read"], expected_counter=self.counter)
        self._open_panel()
        expect(self.page.locator("#proposals-empty")).to_be_visible()
        response = self.h.create_proposal(
            self.project_id,
            [{"path": "new.txt", "operation": "create", "content": "x"}],
        )
        self.assertEqual(response.status, 401)
        self.assertEqual(response.error_code, "unauthorized")


class UiReviewRegressionTest(unittest.TestCase):
    """Regressions for the UI/UX review findings, locked in the browser suite.

    Each test names the finding it holds: an accessible name for every control,
    icon-position actions that still announce themselves, a localized session
    clock, the authored font on native selects, and an actionable empty state.
    """

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("review-ui")
        (self.directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
        registered = self.h.register(self.directory, name="Review")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def test_round3_mobile_project_labels_and_no_overflow(self) -> None:
        self.page.set_viewport_size({"width": 320, "height": 800})
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
        headers = self.page.locator(".project-table th").all_text_contents()
        cells = self.page.locator("#project-rows tr").first.locator("td")
        self.assertEqual(cells.count(), len(headers))
        for cell, label in zip(cells.all(), headers):
            expect(cell).to_have_attribute("data-label", label)
            self.assertIn(label, cell.evaluate("el => getComputedStyle(el, '::before').content"))

    def test_round3_panel_siblings_close_and_nested_focus_returns(self) -> None:
        self.page.locator(".assets-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_visible()
        self.page.locator("#create-component").click()
        expect(self.page.locator("#document-panel")).to_be_visible()
        expect(self.page.locator("#assets-panel")).to_be_hidden()
        self.page.locator("#document-close").click()
        expect(self.page.locator("#assets-panel")).to_be_visible()
        expect(self.page.locator("#create-component")).to_be_focused()
        self.page.locator("#assets-close").click()
        expect(self.page.locator(".assets-button").first).to_be_focused()
        self.page.locator(".assets-button").first.click()
        self.page.locator(".life-button").first.click()
        expect(self.page.locator("#assets-panel")).to_be_hidden()
        expect(self.page.locator("#life-panel")).to_be_visible()
        self.page.locator("#life-close").click()
        expect(self.page.locator(".life-button").first).to_be_focused()
        expect(self.page.locator("#assets-panel")).to_be_hidden()

    def test_the_flow_edge_note_has_an_accessible_name(self) -> None:
        # F1: every control in the flow row announces what it is; the note was
        # the only one relying on a placeholder, which is not a name.
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        # exact=True: the canvas viewport's own aria-label mentions these
        # words, so a substring lookup would match it too.
        expect(
            self.page.get_by_label("流程边说明（可选）", exact=True)
        ).to_have_count(1)
        for label in ("当前画板", "流程边类型"):
            with self.subTest(label=label):
                expect(self.page.get_by_label(label, exact=True)).to_have_count(1)

    def test_icon_position_actions_keep_an_accessible_name(self) -> None:
        # F5: undo/redo/zoom use glyphs, so their name must come from aria-label
        # rather than the glyph itself.
        self.page.locator("#project-rows tr .canvas-button").first.click()
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        for button_id, label in (
            ("#canvas-undo", "撤销"),
            ("#canvas-redo", "重做"),
            ("#canvas-zoom-in", "放大"),
            ("#canvas-zoom-out", "缩小"),
        ):
            with self.subTest(button_id=button_id):
                button = self.page.locator(button_id)
                self.assertEqual(button.get_attribute("aria-label"), label)
                self.assertNotEqual(button.get_attribute("title"), None)
                expect(self.page.get_by_label(label, exact=True)).to_have_count(1)

    def test_session_state_shows_a_local_clock_and_keeps_the_raw_stamp(self) -> None:
        # F4: a Chinese console must not show a bare ISO stamp as its label, but
        # the exact server time stays available for audit.
        state = self.page.locator("#session-state")
        expect(state).to_contain_text("会话有效 · 至")
        text = state.inner_text()
        self.assertNotRegex(text, r"\d{4}-\d{2}-\d{2}T")
        title = state.get_attribute("title") or ""
        self.assertRegex(title, r"\d{4}-\d{2}-\d{2}T")

    def test_native_selects_use_the_authored_font(self) -> None:
        # F7: selects were the only controls on the UA default (13.3333px/Arial).
        measured = self.page.evaluate(
            "() => { const s = document.querySelector('select');"
            " const cs = getComputedStyle(s);"
            " return {size: cs.fontSize, family: cs.fontFamily}; }"
        )
        self.assertNotIn("13.3333", measured["size"])
        self.assertNotIn("Arial", measured["family"])
        self.assertIn("system-ui", measured["family"])

    def test_a_filtered_empty_lifecycle_list_offers_the_next_action(self) -> None:
        # F2 (downgraded): the empty branch existed but lacked the next action
        # every sibling collection surface provides.
        self.page.locator("#project-rows tr .life-button").first.click()
        expect(self.page.locator("#life-panel")).to_be_visible()
        self.page.select_option("#life-filter", "trashed")
        empty = self.page.locator("#life-list li").first
        expect(empty).to_contain_text("没有资产")
        expect(empty).to_contain_text("全部")


class IndependentReviewRegressionTest(unittest.TestCase):
    """Regressions for the independent (agy) review findings C-01, H-01, H-02."""

    def setUp(self) -> None:
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.page = _BROWSER.new_page(viewport={"width": 1440, "height": 1200})
        self.addCleanup(self.page.close)
        self.directories = []
        for name in ("alpha", "beta"):
            directory = self.h.make_directory(name)
            (directory / "brand.md").write_text("# Brand\n", encoding="utf-8")
            registered = self.h.register(directory, name=name)
            assert registered.status == 200, registered.text
            project_id = registered.json["result"]["projectId"]
            self.h.grant(project_id, ["read", "write"], expected_counter=0)
            self.directories.append(directory)
        self.page.goto(self.h.runtime.bootstrap_url)
        expect(self.page.locator("#session-state")).to_contain_text("会话有效")

    def test_only_the_current_project_shows_the_current_badge(self) -> None:
        # C-01: an author `display` rule outranked `[hidden]`, so every row
        # rendered the badge and the state was unreadable.
        expect(self.page.locator("#project-rows tr")).to_have_count(2)
        # Nothing is current until the maintainer picks one: zero visible.
        # Before the [hidden] fix every row rendered the badge instead.
        self.assertEqual(
            self.page.evaluate(
                "() => Array.from(document.querySelectorAll('#project-rows .current-flag'))"
                ".filter((el) => el.offsetParent !== null).length"
            ),
            0,
        )
        # 设为当前 really opens the project now: `open` is a setting write whose
        # guard counter is 0, not the project's own counter. The chosen row's
        # badge must appear and no other row may claim to be current.
        self.page.locator("#project-rows tr").last.locator(
            ".open-button"
        ).click()
        expect(
            self.page.locator("#project-rows tr").last.locator(".current-flag")
        ).to_be_visible()
        per_row = self.page.evaluate(
            "() => Array.from(document.querySelectorAll('#project-rows tr')).map("
            "(row) => Array.from(row.querySelectorAll('.current-flag'))"
            ".filter((el) => el.offsetParent !== null).length)"
        )
        self.assertEqual(per_row, [0, 1], "only the chosen row may be current")

    def test_each_project_row_offers_a_single_primary_action(self) -> None:
        # H-01: the row had two filled primaries (设为当前 plus 画布).
        # `danger` is its own role, not a competing primary, so only the
        # filled-accent (neither secondary nor danger) buttons count.
        expect(self.page.locator("#project-rows tr")).to_have_count(2)
        primaries = self.page.evaluate(
            "() => { const row = document.querySelector('#project-rows tr');"
            " return Array.from(row.querySelectorAll('button'))"
            ".filter((b) => !b.classList.contains('secondary')"
            " && !b.classList.contains('danger'))"
            ".map((b) => (b.textContent || '').trim()); }"
        )
        self.assertEqual(primaries, ["设为当前"], primaries)

    def test_opening_a_panel_moves_focus_in_and_closing_hands_it_back(self) -> None:
        # H-02: five panels never received focus, and no close returned it.
        trigger = self.page.locator("#project-rows tr .canvas-button").first
        trigger.focus()
        trigger.press("Enter")
        expect(self.page.locator("#canvas-panel")).to_be_visible()
        focused = self.page.evaluate(
            "() => document.activeElement ? document.activeElement.id : null"
        )
        self.assertEqual(focused, "canvas-heading", "focus must enter the panel")

        self.page.locator("#canvas-close").click()
        expect(self.page.locator("#canvas-panel")).to_be_hidden()
        returned = self.page.evaluate(
            "() => { const a = document.activeElement;"
            " return a ? (a.className || a.tagName) : null; }"
        )
        self.assertIn("canvas-button", returned, "focus must return to the opener")

    def test_settings_panel_also_receives_focus(self) -> None:
        # H-02 covered settings too; it has no heading reference, so the panel
        # itself is the labelled focus target.
        trigger = self.page.locator("#settings-open")
        trigger.focus()
        trigger.press("Enter")
        expect(self.page.locator("#settings-panel")).to_be_visible()
        self.assertEqual(
            self.page.evaluate(
                "() => document.activeElement ? document.activeElement.id : null"
            ),
            "settings-panel",
        )
        self.page.locator("#settings-close").click()
        expect(self.page.locator("#settings-panel")).to_be_hidden()
        self.assertEqual(
            self.page.evaluate(
                "() => document.activeElement ? document.activeElement.id : null"
            ),
            "settings-open",
        )


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
