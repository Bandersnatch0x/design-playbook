#!/usr/bin/env python3
"""RCV1-007: real-browser tests for the read-only Run Console UI.

Drives the real UI served by the real loopback server (RCV1-006 harness)
with Playwright/Chromium against `#token=...` URLs. Covers the four
comprehension facts on Pass and Recirculate fixtures, the complete state
machine (loading, ready, empty-in-section, degraded, stale, inconsistent,
unsupported version, build error, closed session, network failure,
no-token), keyboard navigation and focus visibility, reduced motion,
320px and 200%-zoom layouts, zero layout shift, CJK/long/control-character
text, and the security negatives (script-in-label rendering, token/stack/
path leak scans, storage scan, same-origin-only request scan, disabled
unavailable controls, source hash mismatch).

States a real server cannot produce (stale, inconsistent, unsupported
schemaVersion, empty criteria, a generic 422) are produced by same-origin
route interception in the page context: the test intercepts the
`/api/v1/snapshot` fetch and fulfills it with a mutated copy of a real
snapshot. This is documented here as the chosen approach; every other
state uses the real server, including the build error (instance-level
patch of the session's build method) and the network failure (server
stopped, then reload clicked).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mcp.run_console import test_http_server as harness  # noqa: E402
from design_playbook.mcp.run_console.http_server import serve_run_console  # noqa: E402
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402
from design_playbook.mcp.run_console.snapshot_builder import SnapshotBuildError  # noqa: E402

_PLAYWRIGHT = None
_BROWSER = None

_LONG_SUMMARY = (
    "一句话定义：控制字符\x07与超长文本混合压力测试。" + "队列监控页设计基线与验收标准说明。" * 12 +
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" * 6 +
    "路径样例 evidence/L6.3-error.png ../../run_root\\win.ini 完成。"
)


def setUpModule() -> None:
    global _PLAYWRIGHT, _BROWSER
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch()


def tearDownModule() -> None:
    _BROWSER.close()
    _PLAYWRIGHT.stop()


class ConsoleHarness:
    """One real run root, session, and loopback server.

    The session is constructed exactly like the launcher constructs it
    (default package root), so the fixtures mirror the operator's real
    experience.
    """

    def __init__(self, *, point_back: str = "point-back-pass-closed.md",
                 spec: str | None = None,
                 drop: tuple[str, ...] = ()) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.run_root = harness._make_root(self.base)
        if point_back is not None:
            (self.run_root / "point-back.md").write_text(
                (Path(__file__).parent / "fixtures" / point_back).read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
        if spec is not None:
            (self.run_root / "spec.md").write_text(spec, encoding="utf-8")
        for name in drop:
            (self.run_root / name).unlink()
        self.session = RunConsoleSession(
            run_root=self.run_root,
            now_fn=lambda: "2026-08-25T10:00:00Z",
        )
        self.server = serve_run_console(self.session, bind_host="127.0.0.1", port=0)

    @property
    def origin(self) -> str:
        return self.server.origin

    @property
    def token(self) -> str:
        return self.session.token

    def url(self, fragment: str = "") -> str:
        return self.origin + "/" + fragment

    def snapshot(self) -> dict:
        return self.session.build_snapshot()

    def close(self) -> None:
        self.server.stop()
        self._tmp.cleanup()


class BrowserTestCase(unittest.TestCase):
    """One harness and one fresh browser context per test."""

    def setUp(self) -> None:
        self.console = ConsoleHarness()
        self.addCleanup(self.console.close)
        self.context = _BROWSER.new_context(viewport={"width": 1280, "height": 800})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.dialogs = []
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)
        dialog.dismiss()

    def open(self, fragment: str | None = None) -> None:
        """Open the console the way the operator does: hash-carried token."""
        token = fragment if fragment is not None else self.console.token
        self.page.goto(self.console.url(f"#token={token}"))
        self.expect_ready()

    def expect_ready(self) -> None:
        expect(self.page.locator("#view-ready")).to_be_visible()
        expect(self.page.locator("#view-loading")).to_be_hidden()

    def fact(self, number: int):
        return self.page.locator(f"#fact-grid .fact:nth-child({number})")

    def body_text(self) -> str:
        return self.page.locator("body").inner_text()


class ComprehensionFactsTest(BrowserTestCase):
    """The four facts, in snapshot order, on one validated page."""

    def test_pass_fixture_shows_all_four_facts(self) -> None:
        self.open()
        headings = self.page.locator("#fact-grid h3").all_text_contents()
        self.assertEqual(
            headings, ["1. Intent", "2. Verdict", "3. Blocker", "4. Next action"]
        )
        # 1 — intent summary, exactly the snapshot string, as text.
        intent = self.fact(1).inner_text()
        self.assertIn("查看所有模拟运行的队列监控页", intent)
        self.assertIn("<script>alert(1)</script>", intent)
        # 2 — verdict.
        self.assertIn("Pass", self.fact(2).inner_text())
        # 3 — blocker source/limitation.
        blocker = self.fact(3).inner_text()
        self.assertIn("No blocking findings", blocker)
        self.assertIn("2 recorded limitations", blocker)
        # 4 — next owner/action.
        action = self.fact(4).inner_text()
        self.assertIn("Run complete (Pass). Ship or start a new run.", action)
        self.assertIn("run-operator", action)
        self.assertIn("kind: stop", action)
        # All four on one page: the detail sections also render, with
        # term/value pairs correctly aligned (regression: shifted kv rows).
        identity_text = self.page.locator("#section-identity").inner_text()
        self.assertIn("Run id", identity_text)
        run_id = self.console.snapshot()["identity"]["run"]["result"]["runId"]
        self.assertIn(run_id, identity_text)
        self.assertIn("Built at", identity_text)
        for section_id in (
            "section-identity", "section-intent", "section-execution",
            "section-evaluation", "section-next-actions", "section-limitations",
            "section-sources",
        ):
            expect(self.page.locator(f"#{section_id}")).to_be_visible()

    def test_recirculate_fixture_shows_blocker_and_next_owner(self) -> None:
        self.console.close()
        self.console = ConsoleHarness(point_back="point-back-recirculate.md")
        self.addCleanup(self.console.close)
        self.open()
        self.assertIn("Recirculate", self.fact(2).inner_text())
        blocker = self.fact(3).inner_text()
        self.assertIn("destructive action has no confirmation", blocker)
        self.assertIn("1 blocking finding", blocker)
        action = self.fact(4).inner_text()
        self.assertIn("repair from point-back findings", action)
        self.assertIn("agent", action)
        self.assertIn("kind: continue", action)

    def test_degraded_build_with_missing_source_is_explicit(self) -> None:
        self.console.close()
        self.console = ConsoleHarness(drop=("contract-bind.json",))
        self.addCleanup(self.console.close)
        self.open()
        expect(self.page.locator("#build-state-banner")).to_contain_text("degraded")
        contract = self.page.locator("#section-intent").inner_text()
        self.assertIn("Unknown", contract)
        self.assertIn("source-missing", contract)
        self.assertIn("The source bound to this assertion is missing.", contract)
        # Known values still render; nothing is blanked by the degradation.
        self.assertIn("Pass", self.fact(2).inner_text())

    def test_current_build_state_is_stated_too(self) -> None:
        self.open()
        expect(self.page.locator("#build-state-banner")).to_contain_text("current")

    def test_hash_token_stripped_immediately(self) -> None:
        self.open()
        self.assertEqual(self.page.evaluate("() => location.hash"), "")
        self.assertEqual(self.page.evaluate("() => location.href"), self.console.url())
        self.assertNotIn("#token=", self.page.url)


class StateMachineTest(BrowserTestCase):
    """Every state is explicit, accessible, and reachable."""

    def test_loading_state_is_skeleton_not_blank(self) -> None:
        real_build = self.console.session.build_snapshot

        def slow_build():
            time.sleep(1.0)
            return real_build()

        with mock.patch.object(
            self.console.session, "build_snapshot", side_effect=slow_build
        ):
            self.page.goto(self.console.url(f"#token={self.console.token}"),
                           wait_until="commit")
            expect(self.page.locator("#view-loading")).to_be_visible()
            expect(self.page.locator(".skeleton")).to_be_visible()
            self.assertEqual(
                self.page.locator("#main").get_attribute("aria-busy"), "true"
            )
            background = self.page.evaluate(
                "() => getComputedStyle(document.body).backgroundColor"
            )
            self.assertNotIn("rgba(0, 0, 0, 0)", background)  # no white flash
        self.expect_ready()  # the delayed response still resolves

    def test_no_token_state(self) -> None:
        self.page.goto(self.console.url())
        expect(self.page.locator("#view-no-token")).to_be_visible()
        expect(self.page.locator("#view-no-token")).to_contain_text("No session token")
        self.assertEqual(self.page.locator("#view-no-token").get_attribute("role"),
                         "alert")

    def test_closed_session_state_on_invalid_token(self) -> None:
        self.page.goto(self.console.url("#token=this-token-is-not-valid-000000000"))
        expect(self.page.locator("#view-closed")).to_be_visible()
        expect(self.page.locator("#view-closed")).to_contain_text("Session closed")

    def test_network_failure_state_when_server_is_unreachable(self) -> None:
        self.open()
        # Deterministic unreachable-server: the API fetch cannot connect.
        self.page.route(
            "**/api/v1/snapshot", lambda route: route.abort("connectionrefused")
        )
        self.page.locator("#reload-button").click()
        expect(self.page.locator("#view-network")).to_be_visible()
        expect(self.page.locator("#view-network")).to_contain_text("unreachable")
        self.assertEqual(
            self.page.locator("#view-network").get_attribute("role"), "alert"
        )
        # The old content never stays on screen as if current.
        expect(self.page.locator("#view-ready")).to_be_hidden()

    def test_real_server_stop_while_open_fails_closed(self) -> None:
        self.open()
        self.console.server.stop()
        self.page.locator("#reload-button").click()
        # The listener is closed and the session invalidated; the browser
        # may reuse its still-open keep-alive connection (the server then
        # answers the closed session with 401) or open a new one (refused).
        # Either way an explicit error view replaces the snapshot view.
        expect(self.page.locator("#view-ready")).to_be_hidden()
        explicit = [
            name for name in ("#view-network", "#view-closed")
            if self.page.locator(name).is_visible()
        ]
        self.assertTrue(explicit, "no explicit error state after server stop")

    def test_build_error_state_is_real_500(self) -> None:
        with mock.patch.object(
            self.console.session, "build_snapshot",
            side_effect=SnapshotBuildError("source-missing"),
        ):
            self.page.goto(self.console.url(f"#token={self.console.token}"))
            expect(self.page.locator("#view-build-error")).to_be_visible()
            expect(self.page.locator("#view-build-error")).to_contain_text(
                "could not be built"
            )
            expect(self.page.locator("#view-build-error")).to_contain_text("retryable")

    def test_unsupported_version_state_via_intercepted_fetch(self) -> None:
        snapshot = self.console.snapshot()
        snapshot["schemaVersion"] = 2

        def fulfill(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(snapshot))

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-unsupported")).to_be_visible()
        expect(self.page.locator("#view-unsupported")).to_contain_text("version 2")
        expect(self.page.locator("#view-unsupported")).to_contain_text("only version 1")
        # No partial rendering of the v2 document.
        self.assertEqual(self.page.locator("#fact-grid .fact").count(), 0)

    def test_generic_api_error_state(self) -> None:
        envelope = {
            "schemaVersion": 1,
            "error": {"code": "SNAPSHOT_CONTRACT_INVALID",
                      "message": "bounded detail", "requestId": "req_test_001",
                      "retryable": False},
        }

        def fulfill(route):
            route.fulfill(status=422, content_type="application/json",
                          body=json.dumps(envelope))

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-error")).to_be_visible()
        expect(self.page.locator("#view-error")).to_contain_text(
            "SNAPSHOT_CONTRACT_INVALID"
        )

    def test_stale_and_inconsistent_assertions_are_explicit(self) -> None:
        snapshot = self.console.snapshot()
        snapshot["intent"]["summary"]["availability"] = "stale"
        snapshot["intent"]["summary"]["reason"] = {
            "code": "source-changed-during-build",
            "message": "The specification changed while the snapshot was built.",
            "sourceRefs": ["source.specification"],
            "observedHashes": [], "verifiedHashes": [], "conflicts": [],
        }
        verdict = snapshot["evaluation"]["verdict"]
        verdict["availability"] = "inconsistent"
        verdict["result"] = None
        verdict["reason"] = {
            "code": "conflicting-authorities",
            "message": "Two authorities disagree about the verdict.",
            "sourceRefs": ["source.evaluator-report"],
            "observedHashes": [], "verifiedHashes": [],
            "conflicts": [{
                "sourceRef": "source.evaluator-report",
                "hash": "sha256:" + "a" * 64,
                "summary": "verdict contradicts the findings ledger",
            }],
        }

        def fulfill(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(snapshot))

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        intent_fact = self.fact(1).inner_text()
        self.assertIn("Stale", intent_fact)
        self.assertIn("source-changed-during-build", intent_fact)
        self.assertIn("not be read as current", intent_fact)
        self.assertIn("stale context", self.fact(1).inner_text())
        verdict_fact = self.fact(2).inner_text()
        self.assertIn("Inconsistent", verdict_fact)
        self.assertIn("conflicting-authorities", verdict_fact)
        self.assertIn("verdict contradicts the findings ledger", verdict_fact)
        self.assertNotIn("Pass", verdict_fact)

    def test_empty_sections_render_explicit_notes(self) -> None:
        snapshot = self.console.snapshot()
        snapshot["intent"]["criteria"] = []
        snapshot["evaluation"]["findings"] = []
        snapshot["nextActions"]["alternatives"] = []
        snapshot["limitations"]["items"] = []
        snapshot["execution"]["progress"]["result"]["observedStages"] = []

        def fulfill(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(snapshot))

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        body = self.body_text()
        self.assertIn("No acceptance criteria are declared", body)
        self.assertIn("No findings are recorded", body)
        self.assertIn("No alternative actions are recorded", body)
        self.assertIn("No limitations are recorded", body)
        self.assertIn("No stages are observed", body)
        # Blocker fact names the emptiness, never a blank card.
        self.assertIn("No blocking findings", self.fact(3).inner_text())
        self.assertIn("No limitations recorded", self.fact(3).inner_text())


class AccessibilityTest(BrowserTestCase):
    """Keyboard-first navigation, focus visibility, layout resilience."""

    def test_keyboard_navigation_and_roving_focus(self) -> None:
        self.open()
        # The app moves initial focus to the main status region; Tab from
        # there enters the fact grid, Shift+Tab walks back through the
        # reload control to the skip link: the full DOM tab order.
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate(
            "() => document.activeElement.closest('.fact').querySelector('h3').textContent"),
            "1. Intent")
        self.page.keyboard.press("Shift+Tab")
        self.assertEqual(self.page.evaluate("() => document.activeElement.id"),
                         "reload-button")
        self.page.keyboard.press("Shift+Tab")
        self.assertEqual(self.page.evaluate("() => document.activeElement.id"),
                         "lang-toggle-button")
        self.page.keyboard.press("Shift+Tab")
        self.assertTrue(self.page.evaluate(
            "() => document.activeElement.classList.contains('skip-link')"))
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate(
            "() => document.activeElement.closest('.fact').querySelector('h3').textContent"),
            "1. Intent")
        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate(
            "() => document.activeElement.closest('.fact').querySelector('h3').textContent"),
                         "2. Verdict")
        self.page.keyboard.press("End")
        self.assertEqual(self.page.evaluate(
            "() => document.activeElement.closest('.fact').querySelector('h3').textContent"),
                         "4. Next action")
        self.page.keyboard.press("Home")
        self.assertEqual(self.page.evaluate(
            "() => document.activeElement.closest('.fact').querySelector('h3').textContent"),
                         "1. Intent")
        # Only one card is a tab stop at a time.
        tabstops = self.page.evaluate(
            "() => Array.from(document.querySelectorAll('#fact-grid .fact'))"
            ".filter(c => c.tabIndex === 0).length")
        self.assertEqual(tabstops, 1)

    def test_focus_ring_is_visible_with_keyboard_focus(self) -> None:
        self.open()
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Tab")
        style = self.page.evaluate(
            "() => { const e = document.activeElement;"
            " const s = getComputedStyle(e);"
            " return {style: s.outlineStyle, width: s.outlineWidth}; }")
        self.assertEqual(style["style"], "solid")
        self.assertGreaterEqual(float(style["width"].rstrip("px")), 2)

    def test_semantic_structure_and_status_roles(self) -> None:
        self.open()
        self.assertEqual(self.page.locator("h1").count(), 1)
        headings = self.page.locator("#view-ready h2").all_inner_texts()
        for expected in ("At a glance", "Identity", "Intent", "Execution",
                         "Evaluation", "Next actions", "Limitations", "Sources"):
            self.assertIn(expected, headings)
        self.assertEqual(self.page.locator("#main").get_attribute("role"), "status")
        self.assertEqual(self.page.locator("#main").get_attribute("aria-live"),
                         "polite")
        # Error views are alerts.
        self.page.goto(self.console.url())
        self.assertEqual(self.page.locator("#view-no-token").get_attribute("role"),
                         "alert")

    def test_reduced_motion_disables_skeleton_animation(self) -> None:
        self.page.emulate_media(reduced_motion="reduce")
        real_build = self.console.session.build_snapshot

        def slow_build():
            time.sleep(0.8)
            return real_build()

        with mock.patch.object(
            self.console.session, "build_snapshot", side_effect=slow_build
        ):
            self.page.goto(self.console.url(f"#token={self.console.token}"),
                           wait_until="commit")
            expect(self.page.locator("#view-loading")).to_be_visible()
            animation = self.page.evaluate(
                "() => getComputedStyle(document.querySelector('.skeleton-block'))"
                ".animationName")
            self.assertEqual(animation, "none")

    def test_narrow_viewport_320px_no_horizontal_scroll(self) -> None:
        self.page.set_viewport_size({"width": 320, "height": 600})
        self.open()
        overflow = self.page.evaluate(
            "() => document.documentElement.scrollWidth - "
            "document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 0)
        # Fact cards stack in one column.
        boxes = [self.fact(i).bounding_box() for i in range(1, 5)]
        xs = {round(b["x"]) for b in boxes}
        self.assertEqual(len(xs), 1)

    def test_200_percent_zoom_keeps_all_four_facts_visible(self) -> None:
        self.open()
        cdp = self.context.new_cdp_session(self.page)
        cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        try:
            for i in range(1, 5):
                box = self.fact(i).bounding_box()
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box["x"], 0)
            # No horizontal layout overflow at the zoomed size.
            overflow = self.page.evaluate(
                "() => document.documentElement.scrollWidth - window.innerWidth")
            self.assertLessEqual(overflow, 0)
        finally:
            cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})

    def test_zero_layout_shift_loading_to_ready(self) -> None:
        self.open()
        self.page.wait_for_timeout(150)
        cls = self.page.evaluate(
            "() => performance.getEntriesByType('layout-shift')"
            ".filter(e => !e.hadRecentInput)"
            ".reduce((sum, e) => sum + e.value, 0)")
        self.assertEqual(cls, 0)

    def test_cjk_long_and_control_characters_wrap_without_breaking_layout(self) -> None:
        fixture = (Path(__file__).parent / "fixtures" /
                   "spec-script-summary.md").read_text(encoding="utf-8")
        spec = fixture.replace(
            "- 一句话定义：<script>alert(1)</script> 查看所有模拟运行的队列监控页。",
            "- 一句话定义：" + _LONG_SUMMARY,
        )
        self.console.close()
        self.console = ConsoleHarness(spec=spec)
        self.addCleanup(self.console.close)
        self.open()
        value = self.fact(1).locator(".fact-value")
        expect(value).to_be_visible()
        text = value.inner_text()
        self.assertIn("路径样例", text)
        # Long unbroken strings are clamped visually, full text in title.
        self.assertTrue(value.evaluate("e => e.classList.contains('is-clamped')"))
        title = value.get_attribute("title")
        assert title is not None
        self.assertIn("win.ini", title)
        overflow = self.page.evaluate(
            "() => document.documentElement.scrollWidth - "
            "document.documentElement.clientWidth")
        self.assertLessEqual(overflow, 0)
        detail = self.page.locator("#section-intent").inner_text()
        self.assertIn("win.ini", detail)  # full text in the detail section


class SecurityTest(BrowserTestCase):
    """Rendering negatives and the storage/request scans."""

    def test_script_in_label_renders_as_text_and_never_executes(self) -> None:
        self.open()
        intent = self.fact(1).inner_text()
        self.assertIn("<script>alert(1)</script>", intent)
        self.assertEqual(self.dialogs, [])
        self.assertEqual(self.page.locator("#view-ready script").count(), 0)

    def test_no_anchors_and_no_javascript_urls_are_created(self) -> None:
        self.open()
        javascript_anchors = self.page.evaluate(
            "() => document.querySelectorAll('a[href^=\"javascript:\"]').length")
        self.assertEqual(javascript_anchors, 0)
        # Only the static skip link exists; data never becomes links.
        self.assertEqual(self.page.locator("a").count(), 1)

    def test_token_paths_and_stacks_never_appear_in_the_dom(self) -> None:
        self.open()
        html = self.page.content()
        self.assertNotIn(self.console.token, html)
        self.assertNotIn(str(self.console.run_root), html)
        self.assertNotIn("Traceback", html)
        self.assertNotIn(".py", self.page.locator("#fact-grid").inner_text())

    def test_no_storage_is_ever_written(self) -> None:
        self.open()
        # Interact: reload, open a source excerpt, exercise copy fallback.
        self.page.locator("#reload-button").click()
        self.expect_ready()
        self.page.locator("details.source").first.locator("summary").click()
        expect(self.page.locator("pre.excerpt")).to_be_visible(timeout=10000)
        storage = self.page.evaluate(
            """async () => ({
                local: window.localStorage.length,
                session: window.sessionStorage.length,
                cookie: document.cookie,
                databases: (await window.indexedDB.databases()).length,
                workers: (await navigator.serviceWorker.getRegistrations()).length,
            })"""
        )
        self.assertEqual(storage, {
            "local": 0, "session": 0, "cookie": "",
            "databases": 0, "workers": 0,
        })

    def test_all_requests_are_same_origin_and_authenticated(self) -> None:
        requests = []

        def record(route):
            requests.append({
                "url": route.request.url,
                "authorization": route.request.headers.get("authorization"),
            })
            route.continue_()

        self.context.route("**/*", record)
        self.open()
        self.page.locator("details.source").first.locator("summary").click()
        expect(self.page.locator("pre.excerpt")).to_be_visible(timeout=10000)
        self.assertTrue(requests, "no requests were recorded")
        for request in requests:
            self.assertTrue(request["url"].startswith(self.console.origin),
                            request["url"])
            self.assertNotIn(self.console.token, request["url"])
        api = [r for r in requests if "/api/v1/" in r["url"]]
        self.assertTrue(api)
        for request in api:
            self.assertEqual(request["authorization"],
                             "Bearer " + self.console.token)

    def test_unavailable_controls_are_disabled_with_reasons(self) -> None:
        self.open()
        disabled = self.page.locator("#view-ready button[disabled]")
        labels = {disabled.nth(i).inner_text() for i in range(disabled.count())}
        self.assertIn("Copy agent command", labels)
        self.assertIn("Attest role", labels)
        self.assertIn("Export diagnostics", labels)
        for i in range(disabled.count()):
            button = disabled.nth(i)
            described = button.get_attribute("aria-describedby")
            self.assertIsNotNone(described)
            reason = self.page.locator("#" + described).inner_text()
            self.assertGreater(len(reason.strip()), 10)
        body = self.body_text()
        self.assertIn("no copyable agent command", body)
        self.assertIn("Role attestation", body)
        self.assertIn("Diagnostic export", body)

    def test_copyable_command_copies_plaintext_when_known(self) -> None:
        self.context.grant_permissions(["clipboard-read", "clipboard-write"])
        snapshot = self.console.snapshot()
        snapshot["nextActions"]["primary"]["result"]["copyableAgentCommand"] = \
            "qoder run --resume run_example --next ui-evaluator"

        def fulfill(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(snapshot))

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        self.page.get_by_role("button", name="Copy agent command (plain text)").click()
        expect(self.page.locator(".copy-status")).to_contain_text("plain text")
        clip = self.page.evaluate("() => navigator.clipboard.readText()")
        self.assertEqual(clip, "qoder run --resume run_example --next ui-evaluator")
        self.assertEqual(self.dialogs, [])

    def test_source_excerpt_renders_as_text(self) -> None:
        self.open()
        # The evidence artifact is an HTML file; its excerpt must be text.
        html_source = self.page.locator(
            "details.source", has_text="source.evidence-artifact"
        )
        html_source.locator("summary").click()
        excerpt = html_source.locator("pre.excerpt")
        expect(excerpt).to_be_visible(timeout=10000)
        text = excerpt.inner_text()
        # The server escapes markup in excerpts and the UI renders text
        # only: the hostile artifact appears as inert characters.
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertIn("plain evidence text", text)
        self.assertEqual(html_source.locator("script").count(), 0)
        self.assertEqual(
            html_source.locator("pre.excerpt").evaluate(
                "e => getComputedStyle(e).whiteSpace"),
            "pre-wrap",
        )

    def test_source_hash_mismatch_after_file_change(self) -> None:
        self.open()
        spec = self.console.run_root / "spec.md"
        original = spec.read_text(encoding="utf-8")
        self.addCleanup(lambda: spec.write_text(original, encoding="utf-8"))
        # The page's snapshot is cached by the session, so its recorded
        # verified hash is the pre-change one; the excerpt route re-reads
        # the file and must refuse to serve the changed content (S22).
        spec.write_text(
            original + "\nchanged after the snapshot was built\n", encoding="utf-8"
        )
        stale = self.page.locator("details.source", has_text="source.specification")
        stale.locator("summary").click()
        expect(stale.locator(".excerpt-state")).to_contain_text(
            "changed after the snapshot", timeout=10000
        )
        self.assertEqual(stale.locator("pre.excerpt").count(), 0)


class LanguageToggleTest(BrowserTestCase):
    """Tests language toggle button, shortcut key, bilingual dictionary, and memory persistence."""

    def test_language_toggle_button_switches_labels_in_place(self) -> None:
        self.open()
        # Default is English
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "en")
        self.assertEqual(self.page.locator("h1").inner_text(), "Run Console")
        self.assertIn("1. Intent", self.fact(1).inner_text())
        self.assertIn("2. Verdict", self.fact(2).inner_text())
        self.assertIn("3. Blocker", self.fact(3).inner_text())
        self.assertIn("4. Next action", self.fact(4).inner_text())

        # Click language toggle button
        lang_btn = self.page.locator("#lang-toggle-button")
        lang_btn.click()

        # Switched to Chinese
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "zh-CN")
        self.assertEqual(self.page.locator("h1").inner_text(), "运行控制台")
        self.assertIn("1. 意图", self.fact(1).inner_text())
        self.assertIn("2. 结论", self.fact(2).inner_text())
        self.assertIn("3. 阻塞项", self.fact(3).inner_text())
        self.assertIn("4. 下一动作", self.fact(4).inner_text())

        # Detail section headings in Chinese
        self.assertEqual(
            self.page.locator("#section-identity h2").inner_text(), "身份标识"
        )
        self.assertEqual(
            self.page.locator("#section-intent h2").inner_text(), "意图"
        )
        self.assertEqual(
            self.page.locator("#section-execution h2").inner_text(), "执行"
        )
        self.assertEqual(
            self.page.locator("#section-evaluation h2").inner_text(), "评估"
        )
        self.assertEqual(
            self.page.locator("#section-next-actions h2").inner_text(), "后续动作"
        )
        self.assertEqual(
            self.page.locator("#section-limitations h2").inner_text(), "局限性"
        )
        self.assertEqual(
            self.page.locator("#section-sources h2").inner_text(), "源数据"
        )

        # Toggle back to English
        lang_btn.click()
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "en")
        self.assertEqual(self.page.locator("h1").inner_text(), "Run Console")
        self.assertIn("1. Intent", self.fact(1).inner_text())

    def test_keyboard_shortcut_l_toggles_language(self) -> None:
        self.open()
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "en")

        # Press 'l' key
        self.page.keyboard.press("l")
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "zh-CN")
        self.assertEqual(self.page.locator("h1").inner_text(), "运行控制台")

        # Press 'L' key (Shift+l)
        self.page.keyboard.press("Shift+L")
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "en")
        self.assertEqual(self.page.locator("h1").inner_text(), "Run Console")

    def test_language_persists_only_in_memory_no_storage_apis(self) -> None:
        self.open()
        self.page.locator("#lang-toggle-button").click()
        self.assertEqual(self.page.evaluate("() => document.documentElement.lang"), "zh-CN")

        # Zero storage usage
        local_len = self.page.evaluate("() => window.localStorage.length")
        session_len = self.page.evaluate("() => window.sessionStorage.length")
        cookies = self.page.evaluate("() => document.cookie")
        self.assertEqual(local_len, 0)
        self.assertEqual(session_len, 0)
        self.assertEqual(cookies, "")


if __name__ == "__main__":
    unittest.main()
