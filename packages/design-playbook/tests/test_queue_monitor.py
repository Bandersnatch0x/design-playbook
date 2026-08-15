#!/usr/bin/env python3
"""Real-browser regression tests for queue-monitor dialog timer races."""
from __future__ import annotations

import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:  # pragma: no cover - environment marker
    sync_playwright = None

PACKAGE = Path(__file__).resolve().parents[1]
QUEUE_MONITOR_URL = (PACKAGE / "showcase" / "queue-monitor.html").as_uri()


class QueueMonitorRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if sync_playwright is None:  # pragma: no cover - explicit CI prerequisite
            raise unittest.SkipTest("Playwright is not installed")
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        if sync_playwright is None:  # pragma: no cover
            return
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.page = self.browser.new_page()
        self.page.goto(QUEUE_MONITOR_URL, wait_until="domcontentloaded")

    def tearDown(self) -> None:
        self.page.close()

    def _open_for_single_failure(self) -> None:
        self.page.check("#select-r-2203")
        self.page.click("#btn-batch-retry")
        self.assertTrue(
            self.page.locator("#retry-overlay").evaluate(
                "element => element.classList.contains('is-open')"
            )
        )

    def _assert_closed_and_ready(self) -> None:
        self.assertFalse(
            self.page.locator("#retry-overlay").evaluate(
                "element => element.classList.contains('is-open')"
            )
        )
        self.assertEqual(
            self.page.locator("body").get_attribute("data-state"),
            "queue-ready",
        )

    def test_cancel_during_skeleton_drops_delayed_render(self) -> None:
        self._open_for_single_failure()
        self.assertEqual(
            self.page.locator("body").get_attribute("data-state"),
            "retry-dialog-loading",
        )
        self.page.click("#dlg-cancel")
        self.page.wait_for_timeout(250)
        self._assert_closed_and_ready()

        # Reopen proves prior loading/timer state does not leak into next session.
        self.page.click("#btn-batch-retry")
        self.page.wait_for_function(
            "document.body.dataset.state === 'retry-dialog-open'"
        )
        self.assertFalse(self.page.locator("#dlg-cancel").is_disabled())
        self.assertNotIn(
            "is-loading",
            self.page.locator("#dlg-confirm").get_attribute("class") or "",
        )

    def test_overlay_cancel_during_skeleton_keeps_queue_ready(self) -> None:
        self._open_for_single_failure()
        self.page.dispatch_event("#retry-overlay", "click")
        self.page.wait_for_timeout(250)
        self._assert_closed_and_ready()

    def test_escape_and_cancel_cannot_interrupt_confirmed_retry(self) -> None:
        failed_before = int(self.page.locator("#cnt-failed").inner_text())
        queued_before = int(self.page.locator("#cnt-queued").inner_text())
        self._open_for_single_failure()
        self.page.wait_for_function(
            "document.body.dataset.state === 'retry-dialog-open'"
        )

        self.page.click("#dlg-confirm")
        self.assertTrue(self.page.locator("#dlg-cancel").is_disabled())
        self.page.keyboard.press("Escape")
        self.page.dispatch_event("#dlg-cancel", "click")
        self.page.wait_for_timeout(50)
        self.assertTrue(
            self.page.locator("#retry-overlay").evaluate(
                "element => element.classList.contains('is-open')"
            )
        )

        self.page.wait_for_function(
            "document.body.dataset.state === 'queue-post-confirm'"
        )
        self.assertFalse(
            self.page.locator("#retry-overlay").evaluate(
                "element => element.classList.contains('is-open')"
            )
        )
        self.assertEqual(
            int(self.page.locator("#cnt-failed").inner_text()), failed_before - 1
        )
        self.assertEqual(
            int(self.page.locator("#cnt-queued").inner_text()), queued_before + 1
        )
        self.assertEqual(self.page.locator("#sel-count").inner_text(), "0")

        # Extra wait catches duplicate/stale execute callbacks.
        self.page.wait_for_timeout(300)
        self.assertEqual(
            int(self.page.locator("#cnt-failed").inner_text()), failed_before - 1
        )
        self.assertEqual(
            int(self.page.locator("#cnt-queued").inner_text()), queued_before + 1
        )


if __name__ == "__main__":
    unittest.main()
