#!/usr/bin/env python3
"""Process-boundary tests for the preview MCP stdio transport."""
from __future__ import annotations

import importlib.util
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# Sibling modules live next to this file. pytest's default prepend mode only
# puts this dir on sys.path[0] when it has no __init__.py; mcp/preview/ is now
# a package (see __init__.py) so the two same-named test_server_stdio.py files
# in preview/ and evidence/ collect under package-qualified names without an
# import-mismatch — so make the sibling dir importable explicitly here.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# After server.py was split, the browser/HTTP helpers moved to browser.py;
# _collect_via_browser resolves them from the ``browser`` namespace, so the
# patches must target ``browser``. ``server`` re-exports the same names, which
# keeps the call sites (server._collect_via_browser, server.HTTPServer, ...)
# working unchanged.
import browser  # noqa: E402


SERVER = Path(__file__).with_name("server.py")


# G5: the parent page embeds a one-time dpb_token + dpb_round as hidden fields.
# Tests that POST /decide must GET / first and lift them — the same path a real
# human submit takes through the trusted control form (not a forged fetch).
_TOKEN_RE = re.compile(r'name="dpb_token"\s+value="([^"]*)"')
_ROUND_RE = re.compile(r'name="dpb_round"\s+value="([^"]*)"')


def _fetch_decision_token(port: int, timeout: float = 3.0) -> tuple[str, int]:
    """GET / and extract the one-time dpb_token + dpb_round from the parent form."""
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
                sock.sendall(
                    f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                    "Connection: close\r\n\r\n".encode("ascii")
                )
                chunks: list[bytes] = []
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
                body = b"".join(chunks).decode("utf-8", errors="replace")
            m_tok = _TOKEN_RE.search(body)
            m_round = _ROUND_RE.search(body)
            if m_tok and m_round:
                return m_tok.group(1), int(m_round.group(1))
        except OSError:
            pass
        time.sleep(0.02)
    raise AssertionError("could not fetch dpb_token/dpb_round from parent page")


def _load_server_module():
    spec = importlib.util.spec_from_file_location("dpb_preview_server", SERVER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PreviewMcpStdioTests(unittest.TestCase):
    def test_claude_code_newline_json_can_initialize_and_list_tools(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        wire_input = "".join(
            json.dumps(request, ensure_ascii=False) + "\n" for request in requests
        )

        completed = subprocess.run(
            [sys.executable, str(SERVER)],
            input=wire_input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"],
            "design-playbook-preview",
        )
        self.assertEqual(
            [tool["name"] for tool in responses[1]["result"]["tools"]],
            ["preview_prototype"],
        )


class PreviewWindowTests(unittest.TestCase):
    def test_open_preview_window_uses_centered_app_window_not_fullscreen(self) -> None:
        server = _load_server_module()
        fake_proc = mock.Mock(pid=4242)
        with mock.patch.object(browser, "_screen_size", return_value=(1920, 1080)), mock.patch.object(
            browser, "_browser_candidates", return_value=["browser.exe"]
        ), mock.patch.object(browser.tempfile, "mkdtemp", return_value="profile-dir"), mock.patch.object(
            browser.subprocess, "Popen", return_value=fake_proc
        ) as popen:
            proc, profile = server._open_preview_window(
                "http://127.0.0.1:4321/", width=1100, height=780
            )

        self.assertIs(proc, fake_proc)
        self.assertEqual(profile, "profile-dir")
        command = popen.call_args.args[0]
        self.assertIn("--app=http://127.0.0.1:4321/", command)
        self.assertIn("--window-size=1100,780", command)
        self.assertIn("--window-position=410,150", command)
        self.assertNotIn("--start-maximized", command)
        self.assertNotIn("--start-fullscreen", command)
        self.assertNotIn("--kiosk", command)


class PreviewCollectShutdownTests(unittest.TestCase):
    def test_collect_returns_when_client_keeps_connection_open(self) -> None:
        """POST /decide must not hang MCP on HTTP keep-alive (dogfood 006 hang)."""
        server = _load_server_module()
        port_box: dict[str, int] = {}
        sticky_done = threading.Event()

        def sticky_client() -> None:
            deadline = time.time() + 5
            port = None
            while time.time() < deadline:
                port = port_box.get("port")
                if port:
                    break
                time.sleep(0.02)
            if not port:
                sticky_done.set()
                return
            from urllib.parse import quote

            token, round_n = _fetch_decision_token(port)
            body = (
                "choice=%E7%A1%AE%E8%AE%A4%E9%80%9A%E8%BF%87"
                "&feedback="
                "&anchors_json=%5B%5D"
                + f"&dpb_token={quote(token)}"
                + f"&dpb_round={round_n}"
            )
            payload = body.encode("ascii")
            req = (
                f"POST /decide HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
            ).encode("ascii") + payload
            sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            try:
                sock.sendall(req)
                sock.settimeout(3)
                try:
                    data = sock.recv(65536)
                    # Response must request close so Chromium cannot pin serve_forever.
                    self.assertIn(b"Connection: close", data)
                except socket.timeout:
                    pass
                time.sleep(3)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
                sticky_done.set()

        real_http = server.HTTPServer

        class StashingHTTPServer(real_http):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                port_box["port"] = self.server_address[1]

        client_thread = threading.Thread(target=sticky_client, daemon=True)
        client_thread.start()

        with tempfile.TemporaryDirectory() as tmp:
            proto = Path(tmp) / "proto.html"
            proto.write_text(
                "<html><body><h1>proto</h1></body></html>",
                encoding="utf-8",
            )
            with mock.patch.object(browser, "HTTPServer", StashingHTTPServer), mock.patch.object(
                browser, "_open_preview_window", return_value=(None, None)
            ), mock.patch.object(browser, "_request_browser_window_close") as close_window, mock.patch.object(
                browser, "_kill_browser_proc"
            ) as kill_browser:
                started = time.monotonic()
                decision = server._collect_via_browser(
                    proto,
                    "summary for test",
                    ["\u786e\u8ba4\u901a\u8fc7", "\u9700\u8981\u4fee\u6539"],
                    1,
                )
                elapsed = time.monotonic() - started

        close_window.assert_called_once_with(None)
        kill_browser.assert_called_once_with(None, None)
        sticky_done.wait(timeout=5)
        self.assertLess(
            elapsed,
            2.5,
            f"collect hung under keep-alive client: {elapsed:.2f}s",
        )
        self.assertTrue(decision["confirmed"])
        self.assertEqual(decision["selected_options"], ["确认通过"])
        self.assertFalse(decision["aborted"])

    def test_modify_submission_returns_dom_anchor_and_closes_owned_window(self) -> None:
        server = _load_server_module()
        port_box: dict[str, int] = {}
        anchor = {"selector": "#submit", "comment": "\u6309\u94ae\u5c42\u7ea7\u4e0d\u6e05\u6670", "label": "Retry", "tag": ""}

        def submit_modify() -> None:
            from urllib.parse import quote

            deadline = time.time() + 5
            while time.time() < deadline and not port_box.get("port"):
                time.sleep(0.02)
            port = port_box["port"]
            token, round_n = _fetch_decision_token(port)
            body = (
                "choice=%E9%9C%80%E8%A6%81%E4%BF%AE%E6%94%B9"
                "&feedback=%E8%AF%B7%E8%B0%83%E6%95%B4"
                "&anchors_json="
                + quote(json.dumps([anchor], ensure_ascii=False))
                + f"&dpb_token={quote(token)}"
                + f"&dpb_round={round_n}"
            )
            payload = body.encode("ascii")
            request = (
                f"POST /decide HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                sock.sendall(request)
                sock.recv(65536)

        real_http = server.HTTPServer

        class StashingHTTPServer(real_http):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                port_box["port"] = self.server_address[1]

        client_thread = threading.Thread(target=submit_modify, daemon=True)
        client_thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            proto = Path(tmp) / "proto.html"
            proto.write_text(
                "<html><body><button id='submit'>Retry</button></body></html>",
                encoding="utf-8",
            )
            with mock.patch.object(browser, "HTTPServer", StashingHTTPServer), mock.patch.object(
                browser, "_open_preview_window", return_value=(mock.sentinel.proc, "profile")
            ), mock.patch.object(browser, "_request_browser_window_close") as close_window, mock.patch.object(
                browser, "_kill_browser_proc"
            ) as kill_browser, mock.patch.object(browser, "_rm_tree"):
                decision = server._collect_via_browser(
                    proto, "summary", ["\u786e\u8ba4\u901a\u8fc7", "\u9700\u8981\u4fee\u6539"], 1
                )

        client_thread.join(timeout=3)
        self.assertFalse(client_thread.is_alive())
        self.assertFalse(decision["confirmed"])
        self.assertEqual(decision["selected_options"], ["\u9700\u8981\u4fee\u6539"])
        self.assertEqual(decision["anchors"], [anchor])
        self.assertIn("#submit", decision["feedback"])
        self.assertIn("\u6309\u94ae\u5c42\u7ea7\u4e0d\u6e05\u6670", decision["feedback"])
        close_window.assert_called_once_with(mock.sentinel.proc)
        kill_browser.assert_called_once_with(mock.sentinel.proc, "profile")

    def test_post_with_bogus_token_is_rejected(self) -> None:
        """G5 stdio e2e: a forged POST carrying an arbitrary dpb_token (which
        an attacker controls in the POST body) must NOT abort the session -
        only a genuinely validated decision ends it. The bogus POST is fail
        closed (confirmed=False), then the real user's valid-token POST still
        confirms, proving the session was not hijacked.
        """
        server = _load_server_module()
        port_box: dict[str, int] = {}

        def bogus_then_valid_client() -> None:
            deadline = time.time() + 5
            port = None
            while time.time() < deadline:
                port = port_box.get("port")
                if port:
                    break
                time.sleep(0.02)
            if not port:
                return
            from urllib.parse import quote

            # Lift the real token + round from the parent page.
            token, round_n = _fetch_decision_token(port)
            # 1) Forged POST: attacker-controlled arbitrary dpb_token. Must be
            #    fail closed AND must not end the session.
            forged_body = (
                "choice=%E7%A1%AE%E8%AE%A4%E9%80%9A%E8%BF%87"
                "&feedback=forged"
                "&anchors_json=%5B%5D"
                "&dpb_token=bogus-not-the-real-token"
                + f"&dpb_round={round_n}"
            )
            for body in (forged_body,):
                payload = body.encode("ascii")
                req = (
                    f"POST /decide HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    "Content-Type: application/x-www-form-urlencoded\r\n"
                    f"Content-Length: {len(payload)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii") + payload
                with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                    sock.sendall(req)
                    sock.settimeout(3)
                    try:
                        sock.recv(65536)
                    except socket.timeout:
                        pass
            # 2) Real user's valid-token POST: must still confirm (session was
            #    not hijacked by the forged POST).
            valid_body = (
                "choice=%E7%A1%AE%E8%AE%A4%E9%80%9A%E8%BF%87"
                "&feedback=ok"
                "&anchors_json=%5B%5D"
                + f"&dpb_token={quote(token)}"
                + f"&dpb_round={round_n}"
            )
            payload = valid_body.encode("ascii")
            req = (
                f"POST /decide HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                sock.sendall(req)
                sock.settimeout(3)
                try:
                    sock.recv(65536)
                except socket.timeout:
                    pass

        real_http = server.HTTPServer

        class StashingHTTPServer(real_http):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                port_box["port"] = self.server_address[1]

        client_thread = threading.Thread(target=bogus_then_valid_client, daemon=True)
        client_thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            proto = Path(tmp) / "proto.html"
            proto.write_text(
                "<html><body><h1>proto</h1></body></html>",
                encoding="utf-8",
            )
            with mock.patch.object(browser, "HTTPServer", StashingHTTPServer), mock.patch.object(
                browser, "_open_preview_window", return_value=(None, None)
            ), mock.patch.object(browser, "_request_browser_window_close"), mock.patch.object(
                browser, "_kill_browser_proc"
            ):
                decision = server._collect_via_browser(
                    proto,
                    "summary",
                    ["确认通过", "需要修改"],
                    1,
                )

        client_thread.join(timeout=3)
        self.assertFalse(client_thread.is_alive())
        # The forged POST did not hijack: the real user's valid POST wins.
        self.assertTrue(decision["confirmed"])
        self.assertFalse(decision.get("aborted"))
    def test_replay_same_token_is_rejected(self) -> None:
        """G5 stdio e2e: first-decision-wins. The first valid POST locks the
        session and sets the confirmed result; a replayed second POST with
        the same token must NOT overwrite that result - the legitimate
        confirmed decision survives.
        """
        server = _load_server_module()
        port_box: dict[str, int] = {}

        def replay_client() -> None:
            deadline = time.time() + 5
            port = None
            while time.time() < deadline:
                port = port_box.get("port")
                if port:
                    break
                time.sleep(0.02)
            if not port:
                return
            from urllib.parse import quote

            token, round_n = _fetch_decision_token(port)
            body = (
                "choice=%E7%A1%AE%E8%AE%A4%E9%80%9A%E8%BF%87"
                "&feedback=ok"
                "&anchors_json=%5B%5D"
                + f"&dpb_token={quote(token)}"
                + f"&dpb_round={round_n}"
            )
            payload = body.encode("ascii")
            req = (
                f"POST /decide HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            # POST 1: first valid use of the token - locks the session and
            # ends it (done.set()). result is confirmed=True.
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                sock.sendall(req)
                sock.settimeout(3)
                try:
                    sock.recv(65536)
                except socket.timeout:
                    pass
            # POST 2: same token - rejected as reuse by the session. It must
            # not change the confirmed result already set by POST 1. (This
            # POST may or may not be processed before shutdown; the assertion
            # is that result stays confirmed regardless.)
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
                    sock.sendall(req)
                    sock.settimeout(1)
                    try:
                        sock.recv(65536)
                    except socket.timeout:
                        pass
            except OSError:
                # Server already shut down after POST 1 - acceptable; the
                # replay never reached the handler, result is intact.
                pass

        real_http = server.HTTPServer

        class StashingHTTPServer(real_http):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                port_box["port"] = self.server_address[1]

        client_thread = threading.Thread(target=replay_client, daemon=True)
        client_thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            proto = Path(tmp) / "proto.html"
            proto.write_text(
                "<html><body><h1>proto</h1></body></html>",
                encoding="utf-8",
            )
            with mock.patch.object(browser, "HTTPServer", StashingHTTPServer), mock.patch.object(
                browser, "_open_preview_window", return_value=(None, None)
            ), mock.patch.object(browser, "_request_browser_window_close"), mock.patch.object(
                browser, "_kill_browser_proc"
            ):
                decision = server._collect_via_browser(
                    proto,
                    "summary",
                    ["确认通过", "需要修改"],
                    1,
                )

        client_thread.join(timeout=3)
        self.assertFalse(client_thread.is_alive())
        # First-decision-wins: the legitimate confirmed result survives the
        # replay attempt - it was not overwritten with a rejected one.
        self.assertTrue(decision["confirmed"])
        self.assertFalse(decision.get("aborted"))

    def test_stop_http_server_joins_serve_thread(self) -> None:
        server_mod = _load_server_module()
        http = server_mod.HTTPServer(("127.0.0.1", 0), server_mod.BaseHTTPRequestHandler)
        serve_thread = threading.Thread(target=http.serve_forever, daemon=True)
        serve_thread.start()

        server_mod._stop_http_server(http, serve_thread, timeout_s=0.4)

        self.assertFalse(serve_thread.is_alive())


class PreviewLogRejectionTests(unittest.TestCase):
    """LOW-4 (secure-ship-0.4.4): a rejected decision's rejection reason
    must persist to preview_dir/log.md so a fail-closed G5 event (forged
    token / replay / round mismatch) is auditable on disk, not just in the
    in-memory MCP payload that vanishes when the call returns.
    """

    def _run_handle(self, server_mod: object, tmp: str, decision: dict) -> dict:
        proto = Path(tmp) / "proto.html"
        proto.write_text("<html></html>", encoding="utf-8")
        with mock.patch.object(server_mod, "_collect_via_browser",
                               return_value=decision):
            return server_mod.handle_preview_prototype(
                {
                    "path": str(proto),
                    "summary": "summary",
                    "round": 1,
                    "report_ref": "report-1",
                }
            )

    def test_rejected_decision_writes_rejection_line_to_log(self) -> None:
        server_mod = _load_server_module()
        rejected_decision = {
            "confirmed": False,
            "selected_options": [],
            "feedback": "forged",
            "aborted": True,
            "anchors": [],
            "rejected": True,
            "rejection": "invalid_token",
            "floor_pass": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._run_handle(server_mod, tmp, rejected_decision)
            log_text = (Path(tmp) / "log.md").read_text(encoding="utf-8")

        self.assertFalse(payload["confirmed"])
        self.assertIn("- rejected: true", log_text)
        self.assertIn("- rejection: invalid_token", log_text)

    def test_confirmed_decision_does_not_write_rejection_line(self) -> None:
        server_mod = _load_server_module()
        confirmed_decision = {
            "confirmed": True,
            "selected_options": ["确认通过"],
            "feedback": "ok",
            "aborted": False,
            "anchors": [],
            "floor_pass": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._run_handle(server_mod, tmp, confirmed_decision)
            log_text = (Path(tmp) / "log.md").read_text(encoding="utf-8")

        self.assertTrue(payload["confirmed"])
        self.assertNotIn("rejected:", log_text)
        self.assertNotIn("rejection:", log_text)


if __name__ == "__main__":
    unittest.main()
