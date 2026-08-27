#!/usr/bin/env python3
"""G5 trust-boundary isolation tests for the preview browser control.

Covers the secure-ship 0.4.4 ticket 01 acceptance:

- prototype HTML isolated inside ``<iframe sandbox="allow-scripts" srcdoc="...">``
  with ``allow-same-origin`` deliberately omitted (parent DOM unreachable by
  prototype scripts, so the hidden decision token stays secret).
- one-time decision token generated via ``secrets.token_urlsafe(32)`` and bound
  to the preview round + a first-decision-wins session.
- ``do_POST`` fails closed (``confirmed=False``, ``floor_pass=False``) on the
  three rejection paths: token missing, token reused, round mismatch.
- a normal human confirm with the token still records ``confirmed=True`` and
  ``floor_pass=True``; the durable decision transaction records ``prototype_html_hash``.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


# --------------------------------------------------------------------------- #
# HTTP client helpers (raw sockets, mirroring test_server_stdio.py)            #
# --------------------------------------------------------------------------- #


def _http_round_trip(port: int, raw_request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        sock.sendall(raw_request)
        sock.settimeout(3)
        chunks: list[bytes] = []
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
        return b"".join(chunks)


def _get_page(port: int) -> str:
    req = (
        f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    return _http_round_trip(port, req).decode("utf-8", errors="replace")


def _post_form(port: int, fields: dict[str, str]) -> bytes:
    body = urlencode(fields).encode("ascii")
    req = (
        f"POST /decide HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii") + body
    return _http_round_trip(port, req)


def _extract_token(page: str) -> str | None:
    m = re.search(r'name="dpb_token"\s+value="([^"]+)"', page)
    return m.group(1) if m else None


SPEC_FIXTURE = """# Spec

## L1 Goal
- Outcome summary: Review a queue monitor UI.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
1. Queue cards: Given jobs exist, When the monitor renders, Then active and queued counts are visible.
2. Failure affordance: Given failed jobs exist, When a reviewer scans the table, Then retry guidance is visible.
"""


def _write_spec_fixture(root: Path) -> Path:
    report = root / "report.md"
    report.write_text("# Decision report\n", encoding="utf-8")
    (root / "spec.md").write_text(SPEC_FIXTURE, encoding="utf-8")
    return report


def _write_control_page(root: Path, criteria: list[dict[str, str]]) -> str:
    control = preview_control._build_control(
        1, "Spec matrix workbench", ["确认通过", "需要修改"], criteria=criteria
    )
    page_path = root / "workbench.html"
    page_path.write_text(
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"></head>"
        "<body><section id=\"prototype\"><h1>Prototype</h1></section>"
        + control
        + "</body></html>",
        encoding="utf-8",
    )
    return page_path.as_uri()


def _hide_onboarding(page: Any) -> None:
    page.wait_for_timeout(80)
    page.evaluate(
        """() => {
          const modal = document.getElementById('dpb-onboarding-modal');
          if (modal) {
            modal.hidden = true;
            modal.setAttribute('aria-hidden', 'true');
          }
          try { localStorage.setItem('dpb.onboarding.v1', '1'); } catch (e) {}
        }"""
    )


# How long a deliberately stuck /export-zip handler is held, and the ceiling
# collect_review must return within while that handler is still in flight.
STUCK_HANDLER_HOLD_S = 8.0
TEARDOWN_CEILING_S = 5.0


class _FakeBrowserAdapter:
    """One fake owned-browser adapter (US-4 / Slice 4).

    Replaces the old process/profile monkeypatch cluster: the real collector
    and local HTTP exchange still run, while the owned-browser lifecycle is
    faked so no OS browser launches and no process/profile internals are
    patched. The interface mirrors ``BrowserInteraction`` (open/close only);
    it owns no executable, PID, profile, or subprocess.
    """

    def __init__(self, client_fn: Any | None = None) -> None:
        self.opened_urls: list[str] = []
        self.closed_handles: list[object] = []
        self.client_fn = client_fn
        self.client_thread: threading.Thread | None = None
        self.client_error: Exception | None = None

    def open(self, url: str) -> object:
        self.opened_urls.append(url)
        if self.client_fn is not None:
            port = int(url.split(":")[2].split("/")[0])

            def run_client() -> None:
                try:
                    self.client_fn(port)
                except Exception as exc:  # noqa: BLE001
                    self.client_error = exc

            self.client_thread = threading.Thread(target=run_client, daemon=True)
            self.client_thread.start()
        # Opaque handle; the real adapter returns a (proc, profile) tuple.
        return ("fake-owned-handle", None)

    def close(self, handle: object) -> None:
        self.closed_handles.append(handle)
        if self.client_thread is not None:
            self.client_thread.join(timeout=3)


def _run_collect(
    proto_html: str,
    client_fn: Any,
    *,
    summary: str = "summary",
    options: list[str] | None = None,
    round_n: int = 1,
    fake_adapter: _FakeBrowserAdapter | None = None,
) -> dict[str, Any]:
    """Drive review_session.collect_review through one fake owned-browser
    adapter (US-4).

    ``client_fn(port)`` runs in a thread and is expected to POST something to
    /decide so the collect call terminates. The real collector and local HTTP
    exchange run; the owned browser lifecycle is faked so no OS browser
    launches and no process/profile internals are patched.
    """
    if options is None:
        options = ["确认通过", "需要修改"]
    if fake_adapter is None:
        fake_adapter = _FakeBrowserAdapter(client_fn)
    elif fake_adapter.client_fn is None:
        fake_adapter.client_fn = client_fn

    with tempfile.TemporaryDirectory() as tmp:
        proto = Path(tmp) / "proto.html"
        proto.write_text(proto_html, encoding="utf-8")
        decision = review_session.collect_review(
            proto, summary, options, round_n, fake_adapter
        )

    assert fake_adapter.client_thread is not None
    assert not fake_adapter.client_thread.is_alive(), "client thread still alive"
    assert fake_adapter.client_error is None, fake_adapter.client_error
    return decision


def _collect_submitted_anchors(
    submitted: list[dict[str, Any]], round_n: int
) -> list[dict[str, Any]]:
    def client(port: int) -> None:
        page = _get_page(port)
        token = _extract_token(page) or ""
        _post_form(
            port,
            {
                "choice": "确认通过",
                "feedback": "anchor compatibility",
                "anchors_json": json.dumps(submitted),
                "dpb_token": token,
                "dpb_round": str(round_n),
            },
        )

    decision = _run_collect(
        "<html><body>anchor compatibility</body></html>",
        client,
        round_n=round_n,
    )
    return decision["anchors"]


# --------------------------------------------------------------------------- #
# Unit tests: external control resources                                      #
# --------------------------------------------------------------------------- #


class ControlResourceAssemblyTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("node"), "node is required for JavaScript syntax check"
    )
    def test_javascript_resource_is_valid_before_assembly(self) -> None:
        result = subprocess.run(
            [
                "node",
                "--check",
                str(Path(preview_control.__file__).with_name("control.js")),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_build_control_assembles_complete_external_resources(self) -> None:
        control = preview_control._build_control(
            2,
            "Review <unsafe> summary",
            ["Confirm", "Revise"],
        )

        self.assertIn("<style>", control)
        self.assertIn("#dpb-root", control)
        self.assertIn('id="dpb-decide-form"', control)
        self.assertIn("window.DPB_I18N =", control)
        self.assertNotIn("reviseLabels", control)
        self.assertIn("isSubstantive()", control)
        self.assertNotIn("<unsafe>", control)
        self.assertNotRegex(
            control, r"\{(?:t_|summary_safe|primary_|secondary_|pill_)[^}]*\}"
        )

    def test_build_control_scheme_a_prime_surface(self) -> None:
        """Scheme A′ control chrome contracts (abort popover, header revise submit)."""
        control = preview_control._build_control(
            1,
            "A-prime surface",
            ["Confirm", "Needs changes"],
        )
        # Abort: button opens popover; real submit lives on #dpb-abort-confirm
        self.assertIn('id="dpb-abort"', control)
        self.assertIn('id="dpb-abort-popover"', control)
        self.assertIn('id="dpb-abort-confirm"', control)
        self.assertIn('id="dpb-abort-cancel"', control)
        self.assertRegex(
            control,
            r'<button type="submit" name="choice" value="__abort__"[^>]*id="dpb-abort-confirm"',
        )
        self.assertNotRegex(
            control,
            r'<button type="submit" name="choice" value="__abort__"[^>]*id="dpb-abort"',
        )
        # v9: the revise option renders as a header submit (secondary)
        self.assertRegex(
            control,
            r'<button type="submit" name="choice" value="Needs changes"[^>]*class="[^"]*dpb-btn-secondary[^"]*"',
        )
        # v9 shell chrome: status pill + feedback field + announce region
        self.assertIn('id="dpb-status-pill"', control)
        self.assertIn('id="dpb-feedback"', control)
        self.assertIn('id="dpb-announce"', control)
        self.assertIn("z-index: 999", control)


class SpecMatrixWorkbenchTests(unittest.TestCase):
    def test_spec_matrix_renders_criteria_and_updates_hidden_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = _write_spec_fixture(root)
            criteria = transaction._criteria_from_report_ref(str(report))
            file_url = _write_control_page(root, criteria)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(file_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#dpb-spec-panel")
                    _hide_onboarding(page)

                    self.assertIn(
                        "验收准则 (Spec Matrix)",
                        page.locator("#dpb-spec-title").inner_text(),
                    )
                    self.assertEqual(page.locator(".dpb-spec-card").count(), 2)
                    self.assertIn(
                        "L6.1: Queue cards",
                        page.locator(".dpb-spec-card").first.inner_text(),
                    )
                    self.assertIn(
                        "active and queued counts are visible.",
                        page.locator(".dpb-spec-card").first.inner_text(),
                    )
                    self.assertEqual(
                        page.locator("#dpb-criteria-count").inner_text(),
                        "准则 0/2",
                    )

                    pane_text = page.locator("#dpb-spec-panel").inner_text()
                    self.assertNotIn("G1", pane_text)
                    self.assertNotIn("待整改", pane_text)
                    self.assertNotIn("通过", pane_text)

                    page.check('.dpb-criterion-check[data-criterion-id="L6.1"]')
                    self.assertEqual(
                        page.locator("#dpb-criteria-count").inner_text(),
                        "准则 1/2",
                    )
                    payload = page.evaluate(
                        "() => JSON.parse(document.getElementById('dpb-criteria-json').value)"
                    )
                    self.assertEqual(
                        payload,
                        [
                            {"id": "L6.1", "title": "Queue cards", "checked": True},
                            {"id": "L6.2", "title": "Failure affordance", "checked": False},
                        ],
                    )

                    page.click("#dpb-criteria-toggle")
                    self.assertIn(
                        "dpb-collapsed",
                        page.locator("#dpb-spec-panel").get_attribute("class") or "",
                    )
                finally:
                    browser.close()

    def test_spec_matrix_empty_state_without_spec_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.md"
            report.write_text("# Decision report\n", encoding="utf-8")
            criteria = transaction._criteria_from_report_ref(str(report))
            file_url = _write_control_page(root, criteria)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(file_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#dpb-spec-panel")
                    _hide_onboarding(page)

                    self.assertEqual(page.locator(".dpb-spec-card").count(), 0)
                    self.assertIn(
                        "无 spec 判据来源",
                        page.locator("#dpb-spec-list").inner_text(),
                    )
                    self.assertTrue(page.locator("#dpb-criteria-toggle").is_hidden())
                    self.assertEqual(
                        page.evaluate(
                            "() => document.getElementById('dpb-criteria-json').value"
                        ),
                        "[]",
                    )
                finally:
                    browser.close()

    def test_dark_toggle_flips_root_theme_and_persists_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = _write_spec_fixture(root)
            criteria = transaction._criteria_from_report_ref(str(report))
            file_url = _write_control_page(root, criteria)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(file_url, wait_until="domcontentloaded")
                    page.wait_for_selector("#dpb-root")
                    _hide_onboarding(page)
                    before = page.locator("#dpb-root").get_attribute("data-theme")
                    page.click("#dpb-theme-toggle")
                    after = page.locator("#dpb-root").get_attribute("data-theme")
                    stored = page.evaluate(
                        "() => localStorage.getItem('dpb.preview.theme')"
                    )
                    icon = page.locator("#dpb-theme-icon").inner_text()

                    self.assertIn(before, ("light", "dark"))
                    self.assertEqual(after, "dark" if before == "light" else "light")
                    self.assertEqual(stored, after)
                    self.assertEqual(icon, "☀" if after == "dark" else "☾")
                finally:
                    browser.close()

    def test_confirm_roundtrip_contains_criteria_review(self) -> None:
        criteria = [
            {
                "id": "L6.1",
                "title": "Queue cards",
                "then": "active and queued counts are visible.",
            },
            {
                "id": "L6.2",
                "title": "Failure affordance",
                "then": "retry guidance is visible.",
            },
        ]

        class Adapter:
            def __init__(self) -> None:
                self.thread: threading.Thread | None = None
                self.error: Exception | None = None

            def open(self, url: str) -> object:
                def drive() -> None:
                    try:
                        with sync_playwright() as pw:
                            browser = pw.chromium.launch(headless=True)
                            try:
                                page = browser.new_page()
                                page.goto(url, wait_until="domcontentloaded")
                                page.wait_for_selector("#dpb-root")
                                _hide_onboarding(page)
                                page.check(
                                    '.dpb-criterion-check[data-criterion-id="L6.2"]'
                                )
                                page.fill("#dpb-feedback", "criteria checked")
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
                self.thread.join(timeout=20)
                if self.thread.is_alive():
                    raise AssertionError("Playwright criteria adapter did not finish")
                if self.error is not None:
                    raise self.error

        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "prototype.html"
            prototype.write_text("<html><body>criteria</body></html>", encoding="utf-8")
            decision = review_session.collect_review(
                prototype,
                "criteria roundtrip",
                ["确认通过", "需要修改"],
                1,
                Adapter(),
                criteria=criteria,
            )

        self.assertEqual(
            decision["criteria_review"],
            [
                {"id": "L6.1", "title": "Queue cards", "checked": False},
                {"id": "L6.2", "title": "Failure affordance", "checked": True},
            ],
        )


# --------------------------------------------------------------------------- #
# Integration tests: parent-page rendering + HTTP decide flow                 #
# --------------------------------------------------------------------------- #


class TrustBoundaryIntegrationTests(unittest.TestCase):
    def test_iframe_sandbox_excludes_allow_same_origin(self) -> None:
        page_box: dict[str, str] = {"page": ""}

        def client(port: int) -> None:
            page = _get_page(port)
            page_box["page"] = page
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        _run_collect("<html><body><h1>proto-marker-123</h1></body></html>", client)
        page = page_box["page"]
        self.assertIn("srcdoc=", page)
        m = re.search(r'<iframe[^>]*\bsandbox="([^"]*)"', page)
        self.assertIsNotNone(m, f"no sandboxed iframe in page head: {page[:240]!r}")
        sandbox_attr = m.group(1)
        self.assertIn("allow-scripts", sandbox_attr)
        self.assertNotIn(
            "allow-same-origin",
            sandbox_attr,
            "allow-same-origin would re-same-origin the iframe and defeat G5",
        )
        # The prototype body must NOT be rendered inline in the parent document;
        # it lives escaped inside the iframe srcdoc attribute.
        self.assertNotIn("<h1>proto-marker-123</h1>", page)
        self.assertIn("proto-marker-123", page)

    def test_control_form_carries_hidden_token_and_round(self) -> None:
        page_box: dict[str, str] = {"page": ""}

        def client(port: int) -> None:
            page_box["page"] = _get_page(port)
            token = _extract_token(page_box["page"]) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        _run_collect("<html><body>x</body></html>", client)
        page = page_box["page"]
        token = _extract_token(page)
        self.assertIsNotNone(token, "hidden dpb_token field missing from control form")
        self.assertGreaterEqual(len(token), 32)
        self.assertRegex(
            page,
            r'name="dpb_round"\s+value="1"',
            "hidden dpb_round field missing or wrong round",
        )

    def test_malicious_post_without_token_does_not_hijack_session(self) -> None:
        """MEDIUM-1 (secure-ship-0.4.4): a forged no-token POST must NOT
        terminate the preview session.

        A sandboxed prototype forging ``fetch('/decide', ...)`` arrives
        without ``dpb_token`` (the hidden field lives in the trusted parent,
        unreachable from the iframe). The server still fail-closes the
        result internally (``confirmed=False``, ``rejected=True``) AND
        responds 200, but it must keep the session alive so the real user
        can still click confirm. Before MEDIUM-1, ``done.set()`` fired
        unconditionally and one forged POST aborted every preview before
        the user clicked anything (DoS on the gate).
        """

        def client(port: int) -> None:
            # 1) Forged cross-origin POST: no dpb_token, no dpb_round.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "forged",
                    "anchors_json": "[]",
                },
            )
            # 2) Real user then submits via the trusted control form, which
            #    is the path that should terminate the session.
            page = _get_page(port)
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "real user clicked confirm",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect(
            "<html><body><script>fetch('/decide',{method:'POST',"
            "body:new URLSearchParams({choice:'CONFIRM',feedback:'ok'})})"
            "</script></body></html>",
            client,
        )
        # Forged POST did not hijack: real user's authenticated submission wins.
        self.assertEqual(decision["choice"], "确认通过")
        self.assertEqual(decision["feedback"], "real user clicked confirm")
        self.assertFalse(decision["aborted"])
        self.assertNotIn("confirmed", decision)
        self.assertNotIn("floor_pass", decision)
        self.assertNotIn("rejected", decision)

    def test_round_mismatch_rejected_at_http(self) -> None:
        # A POST whose dpb_round does not match the session round is rejected
        # (validate -> round_mismatch) and, per MEDIUM-1, must NOT end the
        # session - the real user can still confirm afterward. The mismatch
        # POST is fail closed internally; the subsequent valid POST wins,
        # proving the mismatch neither consumed nor hijacked the session.
        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page) or ""
            # 1) Mismatched-round POST: rejected, must not terminate.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "99",
                },
            )
            # 2) Real user's valid-round POST: must still confirm.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "real user",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect("<html><body>x</body></html>", client)
        # Mismatch did not hijack: the real user's valid POST wins.
        self.assertEqual(decision["choice"], "确认通过")
        self.assertEqual(decision["feedback"], "real user")
        self.assertFalse(decision["aborted"])
        self.assertNotIn("rejected", decision)

    def test_normal_confirm_with_token_passes(self) -> None:
        submitted = [
            {
                "selector": "div.card > h2",
                "label": 'h2 "Title"',
                "comment": "tighten spacing",
                "tag": "h2",
            }
        ]

        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page)
            assert token, "token not rendered in control form"
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "looks good, ship it",
                    "anchors_json": json.dumps(submitted),
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect(
            "<html><body><h1>real prototype</h1></body></html>", client
        )
        self.assertEqual(decision["choice"], "确认通过")
        self.assertEqual(decision["feedback"], "looks good, ship it")
        self.assertFalse(decision["aborted"])
        self.assertEqual(decision["anchors"][0]["selector"], "div.card > h2")
        self.assertEqual(decision["anchors"][0]["features"]["tag"], "h2")
        self.assertEqual(decision["anchors"][0]["features"]["text"], "Title")
        self.assertEqual(decision["anchors"][0]["features"]["classes"], ["card"])
        self.assertRegex(decision["anchors"][0]["node_id"], r"^[0-9a-f]{8}$")
        self.assertEqual(
            decision["prototype_html_hash"],
            prototype_html_digest(b"<html><body><h1>real prototype</h1></body></html>"),
        )
        self.assertNotIn("confirmed", decision)
        self.assertNotIn("floor_pass", decision)
        self.assertNotIn("rejected", decision)

    def test_anchor_node_ids_are_deterministic_and_round_scoped(self) -> None:
        submitted = [
            {
                "selector": "div.card > h2",
                "label": 'h2 "Title"',
                "comment": "first",
                "tag": "h2",
            },
            {
                "selector": "div.card > h2",
                "label": 'h2 "Title"',
                "comment": "second",
                "tag": "h2",
            },
        ]

        round_three = _collect_submitted_anchors(submitted, 3)
        repeated = _collect_submitted_anchors(submitted, 3)
        round_four = _collect_submitted_anchors(submitted, 4)

        self.assertEqual(
            [anchor["node_id"] for anchor in round_three],
            [anchor["node_id"] for anchor in repeated],
        )
        self.assertNotEqual(round_three[0]["node_id"], round_three[1]["node_id"])
        self.assertNotEqual(round_three[0]["node_id"], round_four[0]["node_id"])

    def test_resolved_flag_survives_submission(self) -> None:
        """A reviewer's resolved marks must reach the decision, not evaporate.

        The resolve toggle is real UI state and the draft channel already
        round-trips it, but syncHidden() — the channel the decision is actually
        submitted through — used to drop it, so every resolved mark vanished at
        submit time with no trace in the decision record.
        """
        anchors = _collect_submitted_anchors(
            [
                {"selector": "#a", "label": "a", "comment": "", "tag": "h2",
                 "resolved": True},
                {"selector": "#b", "label": "b", "comment": "", "tag": "p"},
                # Only the exact boolean counts — a truthy string must not
                # silently close a reviewer's open item.
                {"selector": "#c", "label": "c", "comment": "", "tag": "p",
                 "resolved": "yes"},
            ],
            1,
        )

        self.assertTrue(anchors[0].get("resolved"))
        self.assertNotIn("resolved", anchors[1])
        self.assertNotIn("resolved", anchors[2])

    def test_round_zero_omits_anchor_v2_fields(self) -> None:
        anchors = _collect_submitted_anchors(
            [
                {
                    "selector": "p",
                    "label": 'p "x"',
                    "comment": "y",
                    "tag": "p",
                }
            ],
            0,
        )

        self.assertNotIn("node_id", anchors[0])
        self.assertNotIn("features", anchors[0])

    def test_submitted_compatibility_fields_preserve_base_anchor_fields(self) -> None:
        anchors = _collect_submitted_anchors(
            [
                {
                    "selector": "p",
                    "label": "p",
                    "comment": "y",
                    "tag": "p",
                    "node_id": "legacy-node",
                    "features": {"tag": "legacy"},
                }
            ],
            1,
        )

        self.assertEqual(
            {key: anchors[0][key] for key in ("selector", "comment", "label", "tag")},
            {"selector": "p", "comment": "y", "label": "p", "tag": "p"},
        )

    def test_draw_anchor_points_are_sanitized_and_capped(self) -> None:
        anchors = _collect_submitted_anchors(
            [
                {
                    "selector": "@draw-1",
                    "label": "draw 1",
                    "comment": "circled",
                    "tag": "draw",
                    # malformed entries (short, non-list, non-numeric) sit
                    # between valid ones and must be skipped, never fatal
                    "points": (
                        [[0, 0], ["bad", 1], [1], "nope", [10, 20], [None, 2]]
                        + [[i, i] for i in range(600)]
                    ),
                },
                {
                    "selector": "@draw-2",
                    "label": "draw 2",
                    "comment": "all malformed",
                    "tag": "draw",
                    "points": [["x", "y"], [1], "z"],
                },
            ],
            1,
        )

        self.assertEqual(anchors[0]["selector"], "@draw-1")
        self.assertEqual(anchors[0]["tag"], "draw")
        self.assertEqual(anchors[0]["points"][:2], [[0.0, 0.0], [10.0, 20.0]])
        self.assertEqual(len(anchors[0]["points"]), 512)  # _DRAW_POINTS_MAX
        # all-malformed points carry no key at all (an empty list would be
        # a truthy "has points" for the JS renderers)
        self.assertNotIn("points", anchors[1])

    def test_abort_with_token_is_recorded(self) -> None:
        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "__abort__",
                    "feedback": "",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect("<html><body>x</body></html>", client)
        self.assertEqual(decision["choice"], "__abort__")
        self.assertEqual(decision["feedback"], "")
        self.assertTrue(decision["aborted"])
        self.assertNotIn("confirmed", decision)
        self.assertNotIn("rejected", decision)


# --------------------------------------------------------------------------- #
# Stage 9 static-handoff delivery endpoints (/export-zip, /disclosure-review) #
# --------------------------------------------------------------------------- #


def _bridge_inner_js() -> str:
    """Return the raw JS inside the bridge <script> tag (no <script> wrappers).

    Used by syntax + string assertions so they reason about the executable JS
    rather than the HTML wrapper. Strips the leading ``<script ...>`` and
    trailing ``</script>`` of the first script block in BRIDGE_SCRIPT.
    """
    raw = review_session.BRIDGE_SCRIPT
    m = re.search(r"<script[^>]*>(.*)</script>\s*$", raw, re.DOTALL)
    assert m, f"BRIDGE_SCRIPT is not a single <script>...</script> block: {raw[:80]!r}"
    return m.group(1)


class PinAnnotationBridgeTests(unittest.TestCase):
    """G5 introduced ``<iframe sandbox="allow-scripts" srcdoc=...>`` (no
    allow-same-origin, opaque origin) to keep the prototype away from the
    parent DOM where the decision token lives. That isolation also broke
    pin-to-annotate: the parent's ``document.click`` + ``cssPath(e.target)``
    can no longer see iframe clicks or traverse the iframe DOM.

    The fix is a postMessage bridge: a script injected into the srcdoc captures
    clicks inside the iframe and postMessages ``{dpbPinAnchor:{selector,tag}}``
    to the parent; the parent records the anchor only while pin mode is on.

    These tests pin the bridge's presence, structure, and G5 safety (it must
    never touch the parent DOM or the token) at the unit level. End-to-end
    DOM correctness is covered by the playwright bridge test.
    """

    def test_bridge_script_constant_is_single_script_block(self) -> None:
        # The bridge is a self-contained <script>...</script> appended to the
        # prototype before escaping into srcdoc. It must be exactly one block
        # so _build_parent_page can concatenate it as a trailer.
        self.assertTrue(review_session.BRIDGE_SCRIPT.startswith("<script"))
        self.assertTrue(review_session.BRIDGE_SCRIPT.rstrip().endswith("</script>"))
        # exactly one <script...> open + one </script> close
        self.assertEqual(
            len(re.findall(r"<script\b", review_session.BRIDGE_SCRIPT)),
            1,
            "bridge must be a single <script> block",
        )
        self.assertEqual(
            len(re.findall(r"</script>", review_session.BRIDGE_SCRIPT)),
            1,
            "bridge must close exactly one <script> block",
        )

    def test_bridge_script_is_valid_javascript(self) -> None:
        # node --check proves the injected JS parses (catches copy/format
        # errors that string assertions cannot). Skipped if node is absent.
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node not available; JS syntax check skipped")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(_bridge_inner_js())
            tmp_path = fh.name
        try:
            completed = subprocess.run(
                [node, "--check", tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
        self.assertEqual(
            completed.returncode,
            0,
            f"bridge script is not valid JS: "
            f"{completed.stderr.decode('utf-8', 'replace')}",
        )

    def test_bridge_draw_style_matches_the_parent_theme_tokens(self) -> None:
        """The iframe's inlined draw style must track control.css.

        The sandboxed frame cannot read the parent's custom properties, so the
        bridge inlines literal values. That copy is the production path — when
        it drifts, the dashed #E11D48 stroke in control.css is not what any
        reviewer ever sees, and nothing else catches it.
        """
        css = (
            Path(preview_control.__file__)
            .with_name("control.css")
            .read_text(encoding="utf-8")
        )
        bridge = review_session.BRIDGE_SCRIPT

        for token, expected in (("--dpb-draw-stroke", "#E11D48"),
                                ("--dpb-draw-ink", "#FFFFFF")):
            self.assertIn(
                f"{token}: {expected}", css,
                f"control.css light-theme {token} changed; update the bridge copy",
            )
            self.assertIn(
                expected, bridge,
                f"bridge must inline the light-theme {token} value {expected}",
            )
        # spec §3.1: strokes are dashed. The parent dashes them; so must the
        # frame that actually renders them.
        self.assertIn("stroke-dasharray: 8 4", css)
        self.assertIn("stroke-dasharray:8 4", bridge)

    def test_bridge_contains_postMessage_with_dpbPinAnchor(self) -> None:
        js = _bridge_inner_js()
        self.assertIn(
            "postMessage", js, "bridge must postMessage the anchor to the parent"
        )
        self.assertIn(
            "dpbPinAnchor", js, "bridge must tag its messages with the dpbPinAnchor key"
        )
        # postMessage target must be the parent window
        self.assertRegex(
            js,
            r"parent\.postMessage\s*\(",
            "bridge must postMessage to parent (not top/opener)",
        )

    def test_bridge_contains_cssPath_logic(self) -> None:
        # The bridge duplicates cssPath (from control.py) so the iframe can
        # compute a selector for the clicked element on its own side of the
        # trust boundary. Assert the key branches are present.
        js = _bridge_inner_js()
        self.assertIn("function cssPath", js, "cssPath function missing from bridge")
        self.assertIn("CSS.escape", js, "cssPath must escape id/class via CSS.escape")
        # id fast path
        self.assertRegex(
            js, r'el\.id\b.*#"', "cssPath must short-circuit on element id"
        )
        # nth-of-type branch (disambiguate siblings)
        self.assertIn(
            ":nth-of-type(",
            js,
            "cssPath must include :nth-of-type for sibling disambig",
        )
        # tag fallback
        self.assertIn(
            "tagName.toLowerCase()", js, "cssPath must fall back to lowercased tagName"
        )
        # the click listener that fires cssPath + postMessage
        self.assertIn('"click"', js, "bridge must register a click listener")
        self.assertIn(
            "dpb-pin-target", js, "bridge must highlight the clicked element in-iframe"
        )

    def test_bridge_does_not_reach_parent_dom_or_token(self) -> None:
        # G5 security contract: the bridge runs inside the sandboxed opaque-
        # origin iframe. It must NOT touch parent.document, parent.location,
        # or the decision token. It may only postMessage anchor data.
        js = _bridge_inner_js()
        self.assertNotIn(
            "parent.document", js, "bridge must not read parent.document (G5 boundary)"
        )
        self.assertNotIn(
            "parent.location", js, "bridge must not read parent.location (G5 boundary)"
        )
        self.assertNotIn(
            "dpb_token", js, "bridge must not reference the decision token"
        )
        self.assertNotIn(
            "dpb_round", js, "bridge must not reference the decision round"
        )
        self.assertNotIn(
            "/decide", js, "bridge must not POST to /decide (parent-only path)"
        )
        self.assertNotIn(
            "localStorage", js, "bridge must not touch storage (no exfil channel)"
        )
        # no fetch/XHR — the bridge's only outbound channel is postMessage
        self.assertNotRegex(
            js,
            r"\bfetch\s*\(",
            "bridge must not use fetch (postMessage is its only channel)",
        )
        self.assertNotIn(
            "XMLHttpRequest",
            js,
            "bridge must not use XHR (postMessage is its only channel)",
        )

    def test_collect_routes_through_browser_adapter(self) -> None:
        """The public interface uses the supplied adapter end to end."""
        fake = _FakeBrowserAdapter()

        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        _run_collect("<html><body>x</body></html>", client, fake_adapter=fake)
        self.assertEqual(len(fake.opened_urls), 1)
        self.assertEqual(len(fake.closed_handles), 1)


if __name__ == "__main__":
    unittest.main()
