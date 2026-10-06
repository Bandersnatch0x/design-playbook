"""HOST-only presence and fail-closed conflicts; no collaborative source editor."""
from __future__ import annotations

import http.client
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

import pytest
from playwright.sync_api import expect, sync_playwright

from .test_visual_edit_host_e2e import FIXTURE, LiveReviewBrowser, create_server, stage_review
from .test_visual_edit_host_multifile import host_case as host_case, read_source

from preview_e2e_helpers import dismiss_onboarding  # noqa: E402
from presence import Presence  # noqa: E402


# Presence visibility depends on a loopback SSE join racing the browser under test.
# The default 5s Playwright expect window is too tight when the suite runs under CPU
# contention, so presence waits use a load-tolerant window. Assertions are unchanged;
# only the time allowed for the same condition to become true is wider.
PRESENCE_WAIT = 20000


@pytest.fixture
def presence_host(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("index.html", "styles.css"):
        shutil.copyfile(FIXTURE / name, root / name)
    server = create_server(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def presence_path(server, **query):
    token = server.RequestHandlerClass.keywords["presence"].token
    return "/_presence?" + urlencode({"token": token, **query})


class Subscriber:
    def __init__(self, server, user):
        self.connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.connection.request("GET", presence_path(server, user=user, name=user))
        self.socket = self.connection.sock
        self.response = self.connection.getresponse()
        assert self.response.status == 200
        assert self.response.getheader("Content-Type").startswith("text/event-stream")

    def event(self, kind):
        while True:
            line = self.response.readline()
            assert line, "SSE ended before expected event"
            if line.startswith(b"data: "):
                event = json.loads(line[6:])
                if event["type"] == kind:
                    print("SSE", json.dumps(event, sort_keys=True))
                    return event

    def close(self):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.response.close()
        self.connection.close()


def send_event(server, user, kind="user-editing-element", **headers):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("POST", presence_path(server), json.dumps({"userId": user, "type": kind,
                           "selector": "#next-read", "property": "padding"}),
                           {"Content-Type": "application/json", **headers})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_sse_broadcasts_join_edit_commit_leave_and_survivor_continues(presence_host):
    root, server = presence_host
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    alice = Subscriber(server, "alice")
    bob = None
    try:
        assert [u["userId"] for u in alice.event("user-join")["users"]] == ["alice"]
        bob = Subscriber(server, "bob")
        for subscriber in (alice, bob):
            event = subscriber.event("user-join")
            assert [u["userId"] for u in event["users"]] == ["alice", "bob"]
        assert send_event(server, "alice") == 204
        for subscriber in (alice, bob):
            event = subscriber.event("user-editing-element")
            assert event["user"] == {"userId": "alice", "name": "alice",
                                     "selector": "#next-read", "property": "padding"}
        assert send_event(server, "bob", "user-committed-edit") == 204
        for subscriber in (alice, bob):
            event = subscriber.event("user-committed-edit")
            assert event["user"]["userId"] == "bob"
            assert event["scope"] == "preview-only"
        alice.close()
        alice = None
        left = bob.event("user-leave")
        assert left["user"]["userId"] == "alice"
        assert [u["userId"] for u in left["users"]] == ["bob"]
        assert send_event(server, "alice") == 400
        assert send_event(server, "bob") == 204
        assert bob.event("user-editing-element")["user"]["userId"] == "bob"
        assert {p.name: p.read_bytes() for p in root.iterdir()} == before
        print("SURVIVOR continues; host source byte-identical")
    finally:
        if alice:
            alice.close()
        if bob:
            bob.close()


@pytest.mark.parametrize("origin", ["https://example.com", "null", "http://127.0.0.1.evil.test",
                                    "http://[::1", "http://127.0.0.1:invalid"])
def test_presence_rejects_non_loopback_origins(presence_host, origin):
    _, server = presence_host
    assert send_event(server, "alice", Origin=origin) == 403
    assert not server.RequestHandlerClass.keywords["presence"].users
    print("REFUSED origin", origin)


def test_presence_requires_capability_and_valid_payload(presence_host):
    _, server = presence_host
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/_presence?user=alice&name=alice")
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request("POST", presence_path(server), '{"type":"user-join"}',
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 400
        response.read()
    finally:
        connection.close()
    print("REFUSED missing capability and malformed event")


def test_presence_connection_and_backlog_limits_are_explicit():
    presence = Presence()
    for index in range(8):
        presence.join(f"user-{index}", f"User {index}")
    with pytest.raises(ValueError, match="already connected"):
        presence.join("user-0", "Duplicate")
    with pytest.raises(ValueError, match="at most eight"):
        presence.join("user-8", "Ninth user")
    for _ in range(65):
        presence.edit({"type": "user-editing-element", "userId": "user-0",
                       "selector": "#next-read", "property": "padding"})
    assert len(presence.events) == 64
    with pytest.raises(ValueError, match="fell behind; reconnect required"):
        presence.after(0)
    presence.leave("user-0")
    cursor = presence.join("user-0", "Reconnected")
    assert len(presence.after(cursor)) == 1
    print("BOUNDS duplicate/ninth/slow subscriber refused; reconnect gets current membership")


@pytest.mark.parametrize("identity", ["", "../alice", "a" * 65])
def test_presence_rejects_invalid_identity(identity):
    with pytest.raises(ValueError, match="user identity"):
        Presence().join(identity, "User")
    print("REFUSED invalid display identity", repr(identity))


@contextmanager
def waiting_applier(argv):
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8")
    output = queue.Queue()
    lines = []

    def read():
        for line in process.stdout:
            lines.append(line)
            output.put(line)
        output.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while True:
            line = output.get(timeout=20)
            assert line is not None, "first applier exited before confirmation"
            if line.startswith("Type exactly: "):
                yield process, line.removeprefix("Type exactly: ")
                break
    finally:
        if process.poll() is None:
            process.stdin.close()  # EOF withdraws approval and releases only its own marker.
            process.wait(timeout=10)
        reader.join(timeout=5)
        assert not reader.is_alive()
        print("FIRST", process.returncode, "".join(lines), process.stderr.read())
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()


def test_named_applier_conflict_then_owner_disconnect_allows_apply(host_case):
    case = host_case
    argv = [sys.executable, "-X", "utf8", str(FIXTURE / "applier.py"), "apply",
            "--root", str(case.root), "--handoff", str(case.handoff),
            "--candidate", str(case.candidate), "--route-url", case.route, "--user-id"]
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    with waiting_applier([*argv, "alice"]) as (first, confirmation):
        marker = lock.read_bytes()
        owner = json.loads(marker)
        assert owner["userId"] == "alice"
        assert owner["pid"] == first.pid
        assert owner["selectors"] == ["#next-read", "#queue-title"]
        second = subprocess.run([*argv, "bob"], input=confirmation, capture_output=True,
                                text=True, encoding="utf-8", timeout=20)
        print("CONFLICT", second.returncode, second.stdout, second.stderr)
        assert second.returncode == 2
        error = json.loads(second.stderr.removeprefix("REFUSED: "))
        assert error["phase"] == "lock"
        assert error["requestedBy"] == "bob"
        assert error["lockOwner"] == owner
        assert error["pluginWritesSource"] is False
        assert error["conflicts"] == owner["pendingEdits"]
        assert any(e["locator"] == "#next-read" and e["property"] == "padding"
                   and e["newValue"] == "24px" for e in error["conflicts"])
        assert all(text in error["error"] for text in ("alice", "pending edits", "#next-read", "padding", "24px"))
        assert lock.read_bytes() == marker
        assert read_source(case) == case.before
        assert first.poll() is None
    assert first.returncode == 2
    assert not lock.exists()
    survivor = subprocess.run([*argv, "bob"], input=confirmation, capture_output=True,
                              text=True, encoding="utf-8", timeout=20)
    print("SURVIVOR APPLY", survivor.returncode, survivor.stdout, survivor.stderr)
    assert survivor.returncode == 0
    assert json.loads(survivor.stdout.splitlines()[-1])["pluginWritesSource"] is False
    assert read_source(case) == case.contents
    assert not lock.exists()


def test_two_browser_presence_no_style_sync_and_disconnect_recovery(presence_host, tmp_path):
    root, server = presence_host
    route = f"http://127.0.0.1:{server.server_port}/"

    def open_two(adapter, url):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                first_context = browser.new_context(viewport={"width": 1280, "height": 900})
                first = first_context.new_page()
                first.goto(url, wait_until="domcontentloaded")
                dismiss_onboarding(first)
                first.locator("#dpb-tab-visual").click()
                expect(first.locator(".dpb-react-presence li")).to_have_count(1, timeout=PRESENCE_WAIT)
                alice = first.locator(".dpb-react-presence li").get_attribute("data-user-id")
                second_context = browser.new_context(viewport={"width": 1280, "height": 900})
                second = second_context.new_page()
                second.goto(url, wait_until="domcontentloaded")
                dismiss_onboarding(second)
                second.locator("#dpb-tab-visual").click()
                for page in (first, second):
                    expect(page.locator(".dpb-react-presence li")).to_have_count(2, timeout=PRESENCE_WAIT)
                    assert page.locator("iframe.dpb-proto-frame").get_attribute("sandbox") == "allow-scripts"
                first.frame_locator("iframe").locator("#next-read").click(position={"x": 5, "y": 5})
                first.locator('.dpb-react-field[data-property="padding"] input').fill("32px")
                expect(first.locator("#dpb-visual-count")).to_have_text("1")
                expect(second.locator(f'.dpb-react-presence [data-user-id="{alice}"]')).to_contain_text("#next-read · padding", timeout=PRESENCE_WAIT)
                assert second.frame_locator("iframe").locator("#next-read").evaluate("el => el.style.padding") == ""
                assert json.loads(second.locator("#dpb-visual-edits-json").input_value())["edits"] == []
                evidence = os.environ.get("DPB_PRESENCE_EVIDENCE_DIR")
                if evidence:
                    second.screenshot(path=str(Path(evidence) / "f5-presence-two-users.png"))
                print("BROWSER two users visible; remote preview style and batch unchanged")
                first_context.close()
                expect(second.locator(".dpb-react-presence li")).to_have_count(1, timeout=PRESENCE_WAIT)
                second_context.set_offline(True)
                second.frame_locator("iframe").locator("#next-read").click(position={"x": 5, "y": 5})
                expect(second.locator(".dpb-react-presence")).to_have_attribute("data-state", "unavailable", timeout=PRESENCE_WAIT)
                second.locator('.dpb-react-field[data-property="padding"] input').fill("40px")
                expect(second.locator("#dpb-visual-count")).to_have_text("1")
                second_context.set_offline(False)
                second.locator('.dpb-react-field[data-property="padding"] input').fill("41px")
                expect(second.locator("#dpb-visual-count")).to_have_text("2")
                expect(second.locator(".dpb-react-presence")).to_have_attribute("data-state", "connected", timeout=PRESENCE_WAIT)
                print("BROWSER survivor edits normally after peer disconnect and presence POST outage; delivery recovers")
                second.locator("#dpb-feedback").fill("Presence is advisory; source changes still need separate confirmation.")
                with second.expect_response(lambda response: response.url.endswith("/decide")):
                    second.locator("#dpb-btn-approve").click()
            finally:
                browser.close()

    with patch.object(LiveReviewBrowser, "open", open_two):
        result, observation = stage_review(root, tmp_path / "preview", route)
    assert result["confirmed"] is True
    assert result["visual_handoff"]["writesSource"] is False
    assert observation["pluginSourceWrites"] == []
