#!/usr/bin/env python3
"""Process-boundary tests for the preview MCP stdio transport."""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


SERVER = Path(__file__).with_name("server.py")


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
        with mock.patch.object(server, "_screen_size", return_value=(1920, 1080)), mock.patch.object(
            server, "_browser_candidates", return_value=["browser.exe"]
        ), mock.patch.object(server.tempfile, "mkdtemp", return_value="profile-dir"), mock.patch.object(
            server.subprocess, "Popen", return_value=fake_proc
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
            body = (
                "choice=%E7%A1%AE%E8%AE%A4%E9%80%9A%E8%BF%87"
                "&feedback="
                "&anchors_json=%5B%5D"
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
            with mock.patch.object(server, "HTTPServer", StashingHTTPServer), mock.patch.object(
                server, "_open_preview_window", return_value=(None, None)
            ), mock.patch.object(server, "_request_browser_window_close") as close_window, mock.patch.object(
                server, "_kill_browser_proc"
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
            body = (
                "choice=%E9%9C%80%E8%A6%81%E4%BF%AE%E6%94%B9"
                "&feedback=%E8%AF%B7%E8%B0%83%E6%95%B4"
                "&anchors_json="
                + quote(json.dumps([anchor], ensure_ascii=False))
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
            with mock.patch.object(server, "HTTPServer", StashingHTTPServer), mock.patch.object(
                server, "_open_preview_window", return_value=(mock.sentinel.proc, "profile")
            ), mock.patch.object(server, "_request_browser_window_close") as close_window, mock.patch.object(
                server, "_kill_browser_proc"
            ) as kill_browser, mock.patch.object(server, "_rm_tree"):
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

    def test_stop_http_server_joins_serve_thread(self) -> None:
        server_mod = _load_server_module()
        http = server_mod.HTTPServer(("127.0.0.1", 0), server_mod.BaseHTTPRequestHandler)
        serve_thread = threading.Thread(target=http.serve_forever, daemon=True)
        serve_thread.start()

        server_mod._stop_http_server(http, serve_thread, timeout_s=0.4)

        self.assertFalse(serve_thread.is_alive())


if __name__ == "__main__":
    unittest.main()
