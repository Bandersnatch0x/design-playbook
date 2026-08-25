#!/usr/bin/env python3
"""RCV1-009: real-browser tests for the base typed action allowlist UI.

Covers the one server-action control the closed allowlist adds to the
read-only console: a header refresh control for
``POST /api/v1/actions/refresh``. The control is distinct from the reload
button (which stays a GET re-fetch of the current document): clicking it or
pressing R sends exactly the closed payload
``{"schemaVersion":1,"action":"refresh"}`` under the bearer token, the page
re-renders the fully rebuilt snapshot, a failed rebuild shows the
build-error view (never the prior snapshot as current), and the strict
request audit proves no other network access happens.

The other two allowed capabilities already have coverage elsewhere and are
not duplicated here: the hash-bound source view (test_ui_browser.py source
tests) and the browser-only copy control (test_ui_browser.py copy tests).
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mcp.run_console import test_ui_browser as browser_harness  # noqa: E402
from design_playbook.mcp.run_console.snapshot_builder import SnapshotBuildError  # noqa: E402

_PLAYWRIGHT = None
_BROWSER = None


def setUpModule() -> None:
    global _PLAYWRIGHT, _BROWSER
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch()
    # BrowserTestCase (reused from test_ui_browser) reads its browser from
    # its own module globals; this module owns the live instance.
    browser_harness._BROWSER = _BROWSER


def tearDownModule() -> None:
    _BROWSER.close()
    _PLAYWRIGHT.stop()
    browser_harness._BROWSER = None


_REFRESH_BODY = '{"schemaVersion":1,"action":"refresh"}'
_BUILT_AT = "2026-08-25T10:00:00Z"
_LATER = "2026-08-25T11:00:00Z"
_LATER_STILL = "2026-08-25T12:00:00Z"


def _swap_to_recirculate(console) -> None:
    """Change a run source after the initial (cached) snapshot load."""
    (console.run_root / "point-back.md").write_text(
        (Path(__file__).parent / "fixtures" / "point-back-recirculate.md").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )


class RefreshControlTest(browser_harness.BrowserTestCase):
    """The one typed action control: full snapshot refresh."""

    def _record(self, bucket: list) -> None:
        """Record every request; used for the strict network audit."""

        def record(route):
            bucket.append({
                "method": route.request.method,
                "url": route.request.url,
                "authorization": route.request.headers.get("authorization"),
                "content_type": route.request.headers.get("content-type"),
                "body": route.request.post_data,
            })
            route.continue_()

        self.context.route("**/*", record)

    def test_refresh_control_is_present_distinct_and_labeled(self) -> None:
        self.open()
        button = self.page.locator("#refresh-button")
        expect(button).to_be_visible()
        self.assertTrue(button.evaluate(
            "b => b.closest('#header-actions') !== null"))
        self.assertEqual(button.get_attribute("type"), "button")
        expect(button).to_contain_text("Refresh snapshot")
        expect(button.locator("kbd")).to_have_text("R")
        self.assertIn("(R)", button.get_attribute("title"))
        # The reload control stays a distinct GET re-fetch button.
        reload_button = self.page.locator("#reload-button")
        expect(reload_button).to_be_visible()
        expect(reload_button).to_contain_text("Reload snapshot")

    def test_click_posts_the_closed_payload_and_renders_the_rebuild(self) -> None:
        requests: list[dict] = []
        self._record(requests)
        self.open()
        run_line = self.page.locator("#run-id-line")
        self.assertIn(_BUILT_AT, run_line.inner_text())
        self.assertIn("Pass", self.fact(2).inner_text())
        # Change the run after the initial cached load: only a full
        # rebuild can surface this, a GET re-fetch cannot.
        _swap_to_recirculate(self.console)
        self.console.session._now_fn = lambda: _LATER
        self.page.locator("#refresh-button").click()
        self.expect_ready()
        self.assertIn(_LATER, run_line.inner_text())
        self.assertIn("Recirculate", self.fact(2).inner_text())
        self.assertIn("destructive action has no confirmation",
                      self.fact(3).inner_text())
        # Exactly one typed POST with the closed payload and the token.
        posts = [r for r in requests if "/api/v1/actions/refresh" in r["url"]]
        self.assertEqual(len(posts), 1, requests)
        self.assertEqual(posts[0]["method"], "POST")
        self.assertEqual(posts[0]["body"], _REFRESH_BODY)
        self.assertEqual(posts[0]["content_type"], "application/json")
        self.assertEqual(posts[0]["authorization"],
                         "Bearer " + self.console.token)
        # Strict audit: same-origin only, token never in a URL, and the
        # only API traffic is the initial GET plus the one typed POST.
        for request in requests:
            self.assertTrue(request["url"].startswith(self.console.origin),
                            request["url"])
            self.assertNotIn(self.console.token, request["url"])
        api = [(r["method"], r["url"][len(self.console.origin):])
               for r in requests if "/api/v1/" in r["url"]]
        self.assertEqual(api, [
            ("GET", "/api/v1/snapshot"),
            ("POST", "/api/v1/actions/refresh"),
        ])

    def test_rebuild_shows_loading_and_hides_the_control(self) -> None:
        self.open()
        real_build = self.console.session.build_snapshot

        def slow_build():
            time.sleep(0.8)
            return real_build()

        with mock.patch.object(
            self.console.session, "build_snapshot", side_effect=slow_build
        ):
            self.page.locator("#refresh-button").click()
            expect(self.page.locator("#view-loading")).to_be_visible()
            expect(self.page.locator("#view-ready")).to_be_hidden()
            # The control is unreachable while a rebuild is in flight.
            expect(self.page.locator("#refresh-button")).to_be_hidden()
        self.expect_ready()

    def test_failed_rebuild_shows_build_error_never_the_stale_snapshot(self) -> None:
        self.open()
        self.assertIn("Pass", self.fact(2).inner_text())
        with mock.patch.object(
            self.console.session, "build_snapshot",
            side_effect=SnapshotBuildError("SOURCE_ROOT_MISSING"),
        ):
            self.page.locator("#refresh-button").click()
            expect(self.page.locator("#view-build-error")).to_be_visible()
            expect(self.page.locator("#view-ready")).to_be_hidden()
            detail = self.page.locator("#build-error-detail").inner_text()
        self.assertGreater(len(detail.strip()), 10)
        # Recovery: the error view's own reload re-request a build, and
        # the previous document is never served as current in between.
        self.page.locator("#build-error-reload-btn").click()
        self.expect_ready()
        self.assertIn("Pass", self.fact(2).inner_text())

    def test_rejected_action_shows_the_closed_view(self) -> None:
        seen: list[dict] = []

        def reject(route):
            seen.append({
                "method": route.request.method,
                "body": route.request.post_data,
                "authorization": route.request.headers.get("authorization"),
            })
            route.fulfill(
                status=401,
                content_type="application/json",
                body=json.dumps({
                    "schemaVersion": 1,
                    "error": {
                        "code": "SESSION_TOKEN_INVALID",
                        "message": "The console session has closed.",
                        "requestId": "req-ui-action-test",
                        "retryable": False,
                    },
                }),
            )

        self.page.route("**/api/v1/actions/refresh", reject)
        self.open()
        self.page.locator("#refresh-button").click()
        expect(self.page.locator("#view-closed")).to_be_visible()
        expect(self.page.locator("#view-ready")).to_be_hidden()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["method"], "POST")
        self.assertEqual(seen[0]["body"], _REFRESH_BODY)
        self.assertEqual(seen[0]["authorization"],
                         "Bearer " + self.console.token)

    def test_keyboard_shortcut_r_triggers_exactly_one_refresh(self) -> None:
        posts: list[str] = []

        def record(route):
            if "/api/v1/actions/refresh" in route.request.url:
                posts.append(route.request.post_data)
            route.continue_()

        self.context.route("**/*", record)
        self.open()
        _swap_to_recirculate(self.console)
        self.page.keyboard.press("r")
        self.expect_ready()
        self.assertIn("Recirculate", self.fact(2).inner_text())
        self.assertEqual(posts, [_REFRESH_BODY])

    def test_keyboard_shortcut_is_inactive_without_a_rendered_snapshot(self) -> None:
        action_requests: list[str] = []

        def record(route):
            if "/api/v1/actions/" in route.request.url:
                action_requests.append(route.request.url)
            route.continue_()

        self.context.route("**/*", record)
        self.page.goto(self.console.url())  # no token: no-token view
        expect(self.page.locator("#view-no-token")).to_be_visible()
        self.page.keyboard.press("r")
        self.page.keyboard.press("R")
        self.assertEqual(action_requests, [])

    def test_keyboard_shortcut_ignores_modifier_keys(self) -> None:
        posts: list[str] = []

        def record(route):
            if "/api/v1/actions/refresh" in route.request.url:
                posts.append(route.request.post_data)
            route.continue_()

        self.context.route("**/*", record)
        self.open()
        # Ctrl/Cmd+R stays the browser's page reload, not the action.
        self.page.keyboard.press("Control+r")
        self.page.wait_for_load_state("load")
        self.expect_ready()
        self.assertEqual(posts, [])

    def test_refresh_labels_follow_the_language_toggle(self) -> None:
        self.open()
        button = self.page.locator("#refresh-button")
        expect(button).to_contain_text("Refresh snapshot")
        self.assertIn("(R)", button.get_attribute("title"))
        self.page.locator("#lang-toggle-button").click()
        expect(button).to_contain_text("刷新快照")
        self.assertIn("(R)", button.get_attribute("title"))
        self.page.locator("#lang-toggle-button").click()
        expect(button).to_contain_text("Refresh snapshot")

    def test_two_refreshes_in_a_row_each_rebuild(self) -> None:
        posts: list[str] = []

        def record(route):
            if "/api/v1/actions/refresh" in route.request.url:
                posts.append(route.request.post_data)
            route.continue_()

        self.context.route("**/*", record)
        self.open()
        clock = {"now": _LATER}
        self.console.session._now_fn = lambda: clock["now"]
        run_line = self.page.locator("#run-id-line")
        self.page.locator("#refresh-button").click()
        self.expect_ready()
        self.assertIn(_LATER, run_line.inner_text())
        clock["now"] = _LATER_STILL
        self.page.locator("#refresh-button").click()
        self.expect_ready()
        self.assertIn(_LATER_STILL, run_line.inner_text())
        self.assertNotIn(_LATER, run_line.inner_text())
        self.assertEqual(posts, [_REFRESH_BODY, _REFRESH_BODY])


if __name__ == "__main__":
    unittest.main()
