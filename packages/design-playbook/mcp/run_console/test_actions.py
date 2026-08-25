#!/usr/bin/env python3
"""RCV1-009: the closed typed-action allowlist (RED first).

Unit level: the capability registry is closed — exactly the three base
typed capabilities (refresh, view-source, copy-agent-command) and
nothing else; the refresh action body is the fixed closed payload
(``{"schemaVersion": 1, "action": "refresh"}`` and nothing else); copy
eligibility is the known + non-null-command rule; and perform_refresh
rebuilds through the session instead of serving the cached document,
failing typed rather than ever serving a stale snapshot. The boundary
scan keeps actions.py free of outbound-network, exec, and persistence
primitives.

HTTP level (RefreshRouteTest, real loopback server): the one POST
action route sits behind the full policy pipeline (bounded body, Host,
exact Origin, bearer token, JSON content type, closed payload),
returns the complete rebuilt snapshot (a second refresh rebuilds
again), answers every negative with the fixed typed envelope and zero
partial effects, and gives forbidden action names no route at all.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mcp.run_console import test_http_server as harness  # noqa: E402

from design_playbook.mcp.run_console.actions import (  # noqa: E402
    ACTION_REFRESH,
    CAPABILITIES,
    CAPABILITY_BY_NAME,
    CONTENT_TYPE_UNSUPPORTED,
    REFRESH_ALLOWED_METHODS,
    REFRESH_ROUTE,
    ActionPayloadError,
    capability_names,
    content_type_is_json,
    copy_command_is_eligible,
    parse_json_action_body,
    perform_refresh,
    validate_refresh_payload,
)
from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.projection import SOURCE_HASH_MISMATCH  # noqa: E402
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ACTION_PAYLOAD_INVALID,
    METHOD_NOT_ALLOWED,
    ORIGIN_INVALID,
    REQUEST_TOO_LARGE,
    ROUTE_NOT_FOUND,
    SESSION_TOKEN_INVALID,
    SNAPSHOT_BUILD_FAILED,
)
from design_playbook.mcp.run_console.session import (  # noqa: E402
    SESSION_CLOSED,
    RunConsoleSession,
    RunConsoleSessionError,
)
from design_playbook.mcp.run_console.snapshot_builder import (  # noqa: E402
    SnapshotBuildError,
)

_VALID_PAYLOAD = {"schemaVersion": 1, "action": "refresh"}
_COMMAND = "qoder run --resume run_example --next ui-evaluator"


class TickingClock:
    """One ISO minute per call: every rebuild gets a distinct builtAt."""

    def __init__(self, start_minutes: int = 0) -> None:
        self.minute = start_minutes

    def __call__(self) -> str:
        now = f"2026-08-25T10:{self.minute:02d}:00Z"
        self.minute += 1
        return now


class ClosedCapabilityRegistryTest(unittest.TestCase):
    """The allowlist is closed: three capabilities, no generic dispatch."""

    def test_registry_exposes_exactly_the_three_base_capabilities(self) -> None:
        self.assertEqual(
            capability_names(), ("refresh", "view-source", "copy-agent-command")
        )

    def test_refresh_is_the_only_server_action(self) -> None:
        refresh = CAPABILITY_BY_NAME[ACTION_REFRESH]
        self.assertEqual(refresh.kind, "server-action")
        self.assertEqual(refresh.method, "POST")
        self.assertEqual(refresh.route, "/api/v1/actions/refresh")
        server_actions = [c for c in CAPABILITIES if c.kind == "server-action"]
        self.assertEqual([c.name for c in server_actions], [ACTION_REFRESH])

    def test_view_source_references_the_existing_hash_bound_read_route(self) -> None:
        view = CAPABILITY_BY_NAME["view-source"]
        self.assertEqual(view.kind, "read-route")
        self.assertEqual(view.method, "GET")
        self.assertTrue(view.route.startswith("/api/v1/sources/"))
        self.assertIn("expectedHash", view.route)

    def test_copy_is_browser_only_with_no_server_execution_route(self) -> None:
        copy = CAPABILITY_BY_NAME["copy-agent-command"]
        self.assertEqual(copy.kind, "browser-only")
        self.assertIsNone(copy.route)
        self.assertIsNone(copy.method)

    def test_forbidden_action_names_have_no_capability(self) -> None:
        for name in (
            "repair", "rerun", "run", "provider", "file-edit", "edit",
            "upload", "attest-role", "export-diagnostics", "execute",
            "contract", "manifest", "verdict", "acceptance", "shell",
            "copy", "refresh-all", "Refresh", "refresh ",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, CAPABILITY_BY_NAME)

    def test_every_capability_carries_a_description(self) -> None:
        for capability in CAPABILITIES:
            with self.subTest(name=capability.name):
                self.assertTrue(capability.description.strip())

    def test_actions_module_has_no_outbound_network_or_exec_primitive(self) -> None:
        path = Path(__file__).resolve().parent / "actions.py"
        self.assertTrue(path.exists(), str(path))
        source = path.read_text(encoding="utf-8")
        for token in (
            "urlopen",
            "urllib.request",
            "import requests",
            "requests.get",
            "requests.post",
            "create_connection",
            "subprocess",
            "os.system",
            "eval(",
            "exec(",
            "socket.connect",
            "telemetry",
        ):
            self.assertNotIn(token, source, f"actions.py: {token}")


class RefreshPayloadTest(unittest.TestCase):
    """The closed payload: exactly {"schemaVersion": 1, "action": "refresh"}."""

    def test_the_exact_closed_payload_is_accepted(self) -> None:
        self.assertIsNone(validate_refresh_payload(_VALID_PAYLOAD))
        parsed = parse_json_action_body(json.dumps(_VALID_PAYLOAD).encode("utf-8"))
        self.assertEqual(parsed, _VALID_PAYLOAD)
        self.assertIsNone(validate_refresh_payload(parsed))

    def test_non_dict_payloads_are_rejected(self) -> None:
        for payload in (None, True, False, 1, 1.0, "refresh", [], [_VALID_PAYLOAD], ()):
            with self.subTest(payload=payload):
                with self.assertRaises(ActionPayloadError) as ctx:
                    validate_refresh_payload(payload)
                self.assertEqual(ctx.exception.code, ACTION_PAYLOAD_INVALID)

    def test_wrong_schema_versions_are_rejected(self) -> None:
        for version in (2, 0, -1, "1", 1.0, True, False, None, [1]):
            with self.subTest(version=version):
                payload = {"schemaVersion": version, "action": "refresh"}
                with self.assertRaises(ActionPayloadError) as ctx:
                    validate_refresh_payload(payload)
                self.assertEqual(ctx.exception.code, ACTION_PAYLOAD_INVALID)

    def test_wrong_action_names_are_rejected(self) -> None:
        for action in (
            "rerun", "repair", "refresh ", " Refresh", "Refresh", "copy",
            "view-source", "", None, 1, True, ["refresh"],
        ):
            with self.subTest(action=action):
                payload = {"schemaVersion": 1, "action": action}
                with self.assertRaises(ActionPayloadError):
                    validate_refresh_payload(payload)

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        for extra in ("command", "expectedHash", "locator", "token", "force", "args"):
            with self.subTest(extra=extra):
                payload = dict(_VALID_PAYLOAD)
                payload[extra] = "x"
                with self.assertRaises(ActionPayloadError):
                    validate_refresh_payload(payload)
        for missing in ("schemaVersion", "action"):
            with self.subTest(missing=missing):
                payload = dict(_VALID_PAYLOAD)
                del payload[missing]
                with self.assertRaises(ActionPayloadError):
                    validate_refresh_payload(payload)

    def test_malformed_or_non_utf8_bodies_fail_to_parse(self) -> None:
        for raw in (b"", b"{", b'{"schemaVersion": 1,}', b"\x00", b"\xff\xfe{}", b"\x80"):
            with self.subTest(raw=raw):
                with self.assertRaises(ActionPayloadError) as ctx:
                    parse_json_action_body(raw)
                self.assertEqual(ctx.exception.code, ACTION_PAYLOAD_INVALID)

    def test_well_formed_json_that_is_not_the_closed_payload_is_rejected(self) -> None:
        bodies = (
            b"null",
            b"1",
            b'"refresh"',
            b"[1, 2]",
            b"{}",
            b'{"schemaVersion": 1}',
            b'{"action": "refresh"}',
            b'{"schemaVersion": 2, "action": "refresh"}',
            b'{"schemaVersion": 1, "action": "rerun"}',
            b'{"schemaVersion": 1, "action": "refresh", "command": "rm -rf /"}',
            b'{"schemaVersion": 1, "action": "refresh", "extra": true}',
            b'{"schemaVersion": true, "action": "refresh"}',
        )
        for raw in bodies:
            with self.subTest(raw=raw):
                parsed = parse_json_action_body(raw)
                with self.assertRaises(ActionPayloadError):
                    validate_refresh_payload(parsed)


class JsonContentTypeTest(unittest.TestCase):
    """Only application/json (with optional charset) carries an action."""

    def test_json_content_types_are_accepted(self) -> None:
        for value in (
            "application/json",
            "application/json; charset=utf-8",
            "application/json;charset=UTF-8",
            "APPLICATION/JSON",
            " Application/Json ",
            "application/json ; v=1",
        ):
            with self.subTest(value=value):
                self.assertTrue(content_type_is_json(value))

    def test_non_json_content_types_are_rejected(self) -> None:
        sentinel = object()
        for value in (
            None, "", "text/plain", "application/xml", "application/ld+json",
            "text/json", "multipart/form-data", "application/json {}",
            sentinel, 42, b"application/json",
        ):
            with self.subTest(value=value):
                self.assertFalse(content_type_is_json(value))


class CopyEligibilityTest(unittest.TestCase):
    """Copy is enabled only for a known action with a non-null command."""

    def test_known_action_with_an_exact_command_is_eligible(self) -> None:
        self.assertTrue(copy_command_is_eligible("known", _COMMAND))
        self.assertTrue(copy_command_is_eligible("known", "任意指令 --继续"))

    def test_null_or_missing_command_is_never_eligible(self) -> None:
        self.assertFalse(copy_command_is_eligible("known", None))
        self.assertFalse(copy_command_is_eligible("known", ""))

    def test_non_string_commands_are_never_eligible(self) -> None:
        for command in (42, True, ["qoder", "run"], {"command": _COMMAND}, b"qoder run"):
            with self.subTest(command=command):
                self.assertFalse(copy_command_is_eligible("known", command))

    def test_unavailable_action_states_are_never_eligible(self) -> None:
        for availability in ("stale", "unknown", "inconsistent", "unavailable", "", None):
            with self.subTest(availability=availability):
                self.assertFalse(copy_command_is_eligible(availability, _COMMAND))

    def test_prose_fields_are_never_a_substitute_for_the_command(self) -> None:
        # A next action may carry rich prose (label, summary), but only
        # the exact copyableAgentCommand value may be copied; with the
        # command null, prose must not make copy eligible.
        action = {
            "availability": "known",
            "result": {
                "label": "Repair from point-back findings and rerun the criteria.",
                "copyableAgentCommand": None,
            },
        }
        self.assertFalse(
            copy_command_is_eligible(
                action["availability"], action["result"]["copyableAgentCommand"]
            )
        )


class PerformRefreshTest(unittest.TestCase):
    """perform_refresh: one full rebuild, typed failures, no stale serving."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = harness._make_root(self.base)
        self.clock = TickingClock()
        self.session = RunConsoleSession(
            run_root=self.run_root, package_root=harness._PKG_ROOT, now_fn=self.clock
        )

    @staticmethod
    def _built_at(document: dict) -> str:
        return document["identity"]["snapshot"]["builtAt"]

    def test_refresh_rebuilds_instead_of_serving_the_cached_document(self) -> None:
        cached = self.session.build_snapshot()
        refreshed = perform_refresh(self.session)
        self.assertEqual(validate_snapshot(refreshed), refreshed)
        self.assertNotEqual(self._built_at(refreshed), self._built_at(cached))
        # The rebuilt document becomes the served one.
        self.assertIs(self.session.build_snapshot(), refreshed)

    def test_two_refreshes_in_a_row_each_return_a_full_valid_rebuild(self) -> None:
        first = perform_refresh(self.session)
        second = perform_refresh(self.session)
        for document in (first, second):
            self.assertEqual(validate_snapshot(document), document)
            self.assertEqual(document["schemaVersion"], 1)
        self.assertNotEqual(self._built_at(first), self._built_at(second))

    def test_refresh_picks_up_run_changes_and_preserves_the_session(self) -> None:
        token = self.session.token
        before = perform_refresh(self.session)
        record = harness._record(before, "source.specification")
        spec = self.run_root / "spec.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + "\nchanged after the first build\n",
            encoding="utf-8",
        )
        after = perform_refresh(self.session)
        self.assertEqual(validate_snapshot(after), after)
        self.assertEqual(self.session.token, token)
        self.assertEqual(
            self.session.run_id, after["identity"]["run"]["result"]["runId"]
        )
        changed = harness._record(after, "source.specification")
        self.assertNotEqual(changed["observedHash"], record["observedHash"])
        # The refreshed registry resolves the refreshed locator.
        view = self.session.resolve_source(changed["locator"])
        self.assertEqual(view.excerpt.content_hash, changed["observedHash"])

    def test_build_failure_is_typed_and_never_serves_the_prior_snapshot(self) -> None:
        self.session.build_snapshot()
        shutil.rmtree(self.run_root)
        with self.assertRaises(SnapshotBuildError):
            perform_refresh(self.session)
        # The cached document is gone: the next read rebuilds (and fails
        # typed) rather than serving the pre-refresh snapshot as current.
        self.assertFalse(self.session.built)
        with self.assertRaises(SnapshotBuildError):
            self.session.build_snapshot()

    def test_refresh_on_a_closed_session_is_the_typed_session_rejection(self) -> None:
        self.session.build_snapshot()
        self.session.close()
        with self.assertRaises(RunConsoleSessionError) as ctx:
            perform_refresh(self.session)
        self.assertEqual(ctx.exception.code, SESSION_CLOSED)


_CLOSED_BODY = b'{"schemaVersion": 1, "action": "refresh"}'
_VALID = object()  # helper default: the exact bound origin / valid token


class RefreshRouteTest(harness._ServerTestCase):
    """POST /api/v1/actions/refresh behind the full policy pipeline."""

    def _refresh(
        self,
        *,
        origin=_VALID,
        token=_VALID,
        content_type="application/json",
        body=_CLOSED_BODY,
        path=REFRESH_ROUTE,
    ):
        """One refresh POST; defaults are the exact origin and valid token.

        The body is sent with an explicit Content-Length, exactly like
        the browser fetch the UI issues (the low-level http.client
        putrequest/endheaders flow does not add one on its own).
        """
        if origin is _VALID:
            origin = self.server.origin
        if token is _VALID:
            token = harness._TOKEN
        headers = {} if content_type is None else {"Content-Type": content_type}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        return self._api(
            "POST", path, token=token, origin=origin, headers=headers, body=body
        )

    # -- the happy path --------------------------------------------------

    def test_post_refresh_returns_the_complete_rebuilt_snapshot(self) -> None:
        _, _, cached = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(
            json.loads(cached)["identity"]["snapshot"]["builtAt"], harness._NOW
        )
        self.clock.now = harness._LATER
        status, headers, payload = self._refresh()
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        document = json.loads(payload)
        self.assertEqual(validate_snapshot(document), document)
        self.assertEqual(document["schemaVersion"], 1)
        # A real rebuild, not the cached document: built at the new time.
        self.assertEqual(document["identity"]["snapshot"]["builtAt"], harness._LATER)
        # The rebuilt document becomes the served one.
        _, _, served = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(json.loads(served), document)

    def test_two_refreshes_in_a_row_each_return_a_full_valid_rebuild(self) -> None:
        _, _, first = self._refresh()
        self.clock.now = harness._LATER
        _, _, second = self._refresh()
        for payload in (first, second):
            document = json.loads(payload)
            self.assertEqual(validate_snapshot(document), document)
            self.assertEqual(document["schemaVersion"], 1)
        self.assertNotEqual(
            json.loads(first)["identity"]["snapshot"]["builtAt"],
            json.loads(second)["identity"]["snapshot"]["builtAt"],
        )

    def test_refresh_rebuild_picks_up_run_changes(self) -> None:
        _, _, first = self._api("GET", "/api/v1/snapshot")
        record = harness._record(json.loads(first), "source.specification")
        spec = self.run_root / "spec.md"
        spec.write_text(
            spec.read_text(encoding="utf-8") + "\nchanged after the build\n",
            encoding="utf-8",
        )
        self.clock.now = harness._LATER
        status, _, payload = self._refresh()
        self.assertEqual(status, 200)
        changed = harness._record(json.loads(payload), "source.specification")
        self.assertNotEqual(changed["observedHash"], record["observedHash"])
        # The hash bound at the old build is refused under the fresh
        # registry: a stale expectedHash never yields the old excerpt.
        status, _, payload = self._api(
            "GET",
            f"/api/v1/sources/{changed['locator']}?expectedHash={record['observedHash']}",
        )
        self.assertEqual(status, 409)
        harness._assert_error(payload, SOURCE_HASH_MISMATCH)

    # -- pipeline gates, in order ----------------------------------------

    def test_refresh_requires_the_exact_origin(self) -> None:
        status, _, payload = self._refresh(origin=harness._ORIGIN)
        self.assertEqual(status, 403)
        harness._assert_error(payload, ORIGIN_INVALID)
        status, _, payload = self._refresh(origin="http://evil.example")
        self.assertEqual(status, 403)
        harness._assert_error(payload, ORIGIN_INVALID)
        status, _, _ = self._refresh()
        self.assertEqual(status, 200)

    def test_refresh_requires_the_bearer_token(self) -> None:
        status, _, payload = self._refresh(token=None)
        self.assertEqual(status, 401)
        harness._assert_error(payload, SESSION_TOKEN_INVALID)
        status, _, payload = self._refresh(token="w" * 43)
        self.assertEqual(status, 401)
        harness._assert_error(payload, SESSION_TOKEN_INVALID)

    def test_refresh_rejects_query_parameters(self) -> None:
        status, _, payload = self._refresh(path=REFRESH_ROUTE + "?x=1")
        self.assertEqual(status, 400)
        harness._assert_error(payload, ACTION_PAYLOAD_INVALID)
        status, _, payload = self._refresh(
            path=REFRESH_ROUTE + f"?token={self.token}"
        )
        self.assertEqual(status, 401)
        harness._assert_error(payload, SESSION_TOKEN_INVALID)

    def test_refresh_requires_a_json_content_type(self) -> None:
        for content_type in (
            "text/plain",
            "application/x-www-form-urlencoded",
            "application/ld+json",
            "application/jsonx",
            "",
        ):
            with self.subTest(content_type=content_type):
                status, _, payload = self._refresh(content_type=content_type)
                self.assertEqual(status, 415)
                harness._assert_error(payload, CONTENT_TYPE_UNSUPPORTED)
        # A missing Content-Type header is equally unsupported.
        status, _, payload = self._refresh(content_type=None)
        self.assertEqual(status, 415)
        harness._assert_error(payload, CONTENT_TYPE_UNSUPPORTED)

    def test_refresh_with_a_duplicated_content_type_is_rejected(self) -> None:
        request = (
            f"POST {REFRESH_ROUTE} HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(_CLOSED_BODY)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + _CLOSED_BODY
        status, _ = self._raw(request)
        self.assertEqual(status, 415)

    def test_refresh_rejects_bodies_that_are_not_the_closed_payload(self) -> None:
        bodies = (
            b"",
            b"{",
            b"null",
            b"1",
            b'"refresh"',
            b"[1]",
            b"{}",
            b'{"schemaVersion": 1}',
            b'{"action": "refresh"}',
            b'{"schemaVersion": 2, "action": "refresh"}',
            b'{"schemaVersion": "1", "action": "refresh"}',
            b'{"schemaVersion": 1, "action": "rerun"}',
            b'{"schemaVersion": 1, "action": "refresh", "command": "rm -rf /"}',
            b'{"schemaVersion": 1, "action": "refresh", "extra": true}',
        )
        for body in bodies:
            with self.subTest(body=body):
                status, _, payload = self._refresh(body=body)
                self.assertEqual(status, 400)
                harness._assert_error(payload, ACTION_PAYLOAD_INVALID)
        # A POST with no body at all is not the closed payload either.
        status, _, payload = self._refresh(body=None)
        self.assertEqual(status, 400)
        harness._assert_error(payload, ACTION_PAYLOAD_INVALID)

    def test_refresh_rejects_a_body_without_a_content_length(self) -> None:
        # The route only ever reads a Content-Length-bounded body: bytes
        # that arrive without one are not the closed action payload.
        status, _, payload = self._api(
            "POST",
            REFRESH_ROUTE,
            origin=self.server.origin,
            headers={"Content-Type": "application/json"},
            body=_CLOSED_BODY,
        )
        self.assertEqual(status, 400)
        harness._assert_error(payload, ACTION_PAYLOAD_INVALID)

    def test_refresh_rejects_unbounded_bodies_before_routing(self) -> None:
        oversized = (
            f"POST {REFRESH_ROUTE} HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: 100000000\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, raw = self._raw(oversized)
        self.assertEqual(status, 413)
        harness._assert_error(raw.split(b"\r\n\r\n", 1)[1], REQUEST_TOO_LARGE)
        chunked = (
            f"POST {REFRESH_ROUTE} HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Type: application/json\r\n"
            f"Transfer-Encoding: chunked\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, raw = self._raw(chunked)
        self.assertEqual(status, 413)
        harness._assert_error(raw.split(b"\r\n\r\n", 1)[1], REQUEST_TOO_LARGE)

    # -- method policy and the closed route table -------------------------

    def test_refresh_route_accepts_only_post(self) -> None:
        for method in ("GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                status, headers, payload = self._api(
                    method, REFRESH_ROUTE, origin=self.server.origin
                )
                self.assertEqual(status, 405)
                self.assertEqual(headers["allow"], REFRESH_ALLOWED_METHODS)
                if method != "HEAD":
                    harness._assert_error(payload, METHOD_NOT_ALLOWED)

    def test_unknown_http_verb_on_refresh_route_has_accurate_allow(self) -> None:
        request = (
            f"PROPFIND {REFRESH_ROUTE} HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, raw = self._raw(request)
        self.assertEqual(status, 405)
        self.assertIn(b"Allow: POST", raw)
        self.assertNotIn(b"PROPFIND", raw.split(b"\r\n\r\n", 1)[1])

    def test_forbidden_action_names_have_no_route(self) -> None:
        for name in (
            "rerun", "repair", "provider", "file-edit", "upload",
            "attest-role", "export-diagnostics", "copy-agent-command",
            "view-source", "refresh/extra", "refreshx", "Refresh",
        ):
            with self.subTest(name=name):
                status, _, payload = self._refresh(path=f"/api/v1/actions/{name}")
                self.assertEqual(status, 404)
                harness._assert_error(payload, ROUTE_NOT_FOUND)
        for path in ("/api/v1/actions", "/api/v1/actions/"):
            with self.subTest(path=path):
                status, _, payload = self._api("GET", path)
                self.assertEqual(status, 404)
                harness._assert_error(payload, ROUTE_NOT_FOUND)

    # -- failures: typed, bounded, zero partial effects -------------------

    def test_failed_refreshes_leave_zero_partial_effects(self) -> None:
        before_tree = harness._tree_digest(self.run_root)
        _, _, cached = self._api("GET", "/api/v1/snapshot")
        failures = [
            self._refresh(origin=harness._ORIGIN),
            self._refresh(origin="http://evil.example"),
            self._refresh(token=None),
            self._refresh(token="w" * 43),
            self._refresh(content_type="text/plain"),
            self._refresh(content_type=None),
            self._refresh(body=b"{"),
            self._refresh(body=b'{"schemaVersion": 2, "action": "refresh"}'),
            self._refresh(body=b'{"schemaVersion": 1, "action": "rerun"}'),
            self._refresh(body=b'{"schemaVersion": 1, "action": "refresh", "x": 1}'),
            self._refresh(path=REFRESH_ROUTE + "?x=1"),
            self._refresh(path="/api/v1/actions/rerun"),
        ]
        self.assertTrue(failures)
        for status, _, payload in failures:
            self.assertLess(status, 500)
            envelope = json.loads(payload)
            self.assertEqual(set(envelope), {"schemaVersion", "error"})
        # Nothing was rebuilt and nothing was written.
        _, _, still = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(still, cached)
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)

    def test_build_failure_is_typed_500_and_never_serves_the_prior_snapshot(self) -> None:
        _, _, _ = self._api("GET", "/api/v1/snapshot")
        shutil.rmtree(self.run_root)
        status, _, payload = self._refresh()
        self.assertEqual(status, 500)
        harness._assert_error(payload, SNAPSHOT_BUILD_FAILED)
        # The next read rebuilds too: the prior snapshot is never current.
        status, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 500)
        harness._assert_error(payload, SNAPSHOT_BUILD_FAILED)

    def test_mocked_build_failure_is_typed_500(self) -> None:
        with mock.patch.object(
            self.session,
            "build_snapshot",
            side_effect=SnapshotBuildError("BUILD_FAILED"),
        ):
            status, _, payload = self._refresh()
        self.assertEqual(status, 500)
        harness._assert_error(payload, SNAPSHOT_BUILD_FAILED)

    def test_internal_failure_is_bounded_500_and_recoverable(self) -> None:
        boom = RuntimeError("boom " + str(self.run_root))
        with mock.patch.object(self.session, "build_snapshot", side_effect=boom):
            status, _, payload = self._refresh()
        self.assertEqual(status, 500)
        harness._assert_error(payload, SNAPSHOT_BUILD_FAILED)
        self.assertNotIn(b"boom", payload)
        # The session is left in a consistent state: the next read is a
        # full fresh build, not a broken or stale document.
        status, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)
        document = json.loads(payload)
        self.assertEqual(validate_snapshot(document), document)

    def test_successful_refresh_writes_nothing_to_the_run_tree(self) -> None:
        before_tree = harness._tree_digest(self.run_root)
        status, _, payload = self._refresh()
        self.assertEqual(status, 200)
        self.assertEqual(validate_snapshot(json.loads(payload)), json.loads(payload))
        self.assertEqual(harness._tree_digest(self.run_root), before_tree)


if __name__ == "__main__":
    unittest.main()
