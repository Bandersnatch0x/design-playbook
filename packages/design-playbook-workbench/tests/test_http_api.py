#!/usr/bin/env python3
"""A01/A02 over the real HTTP surface: the negative journeys.

Every check drives a real loopback listener. The tests here are the ones
the browser cannot easily prove: forged Host/Origin, non-loopback binds,
replayed bootstrap secrets, credentials in a query string, cross-project
capabilities, restarts that must invalidate old credentials, path and
secret leakage in rejections, and credential-record permissions.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import contextlib
from pathlib import Path

from design_playbook_workbench.errors import WorkbenchError
from design_playbook_workbench.credentials import (
    current_user_principal,
    is_private,
    write_private_json,
)
from design_playbook_workbench.http_server import (
    WorkbenchHTTPServer,
)
from design_playbook_workbench.launcher import start_runtime

from tests.harness import (
    WorkbenchHarness,
    http_request,
    make_directory_link,
    make_runtime,
)

UNKNOWN_PROJECT = "00000000-0000-4000-8000-000000000000"


def _ipv6_loopback_available() -> bool:
    """Whether this host can actually bind the IPv6 loopback.

    The bind policy allows a bare ``::1``; a container or kernel without an
    IPv6 loopback interface reports OSError (EADDRNOTAVAIL) before any policy
    check runs, so the bind assertion is only meaningful where the kernel
    provides the address.
    """
    import socket

    if not socket.has_ipv6:
        return False
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.bind(("::1", 0))
    except OSError:
        return False
    finally:
        probe.close()
    return True


class BindPolicyTest(unittest.TestCase):
    def test_non_loopback_binds_are_refused(self) -> None:
        for host in ("0.0.0.0", "localhost", "192.168.1.10", "::", "[::1]", ""):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    WorkbenchHTTPServer(bind_host=host)

    @unittest.skipUnless(_ipv6_loopback_available(), "host has no IPv6 loopback")
    def test_ipv6_loopback_bind_is_available(self) -> None:
        server = WorkbenchHTTPServer(bind_host="::1")
        try:
            self.assertEqual(server.bind_host, "::1")
            self.assertTrue(server.origin.startswith("http://[::1]:"))
        finally:
            server.server_close()

    def test_port_collision_reports_an_explicit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = start_runtime(data_dir=Path(tmp) / "one", port=0)
            try:
                with self.assertRaises(OSError):
                    WorkbenchHTTPServer(port=first.server.port)
            finally:
                first.stop()


class TransportPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)

    def test_host_must_equal_the_bound_authority(self) -> None:
        for host in (
            "localhost:1234",
            "127.0.0.2",
            "evil.example",
            f"127.0.0.1:{self.h.runtime.server.port + 1}",
            "http://127.0.0.1",
        ):
            with self.subTest(host=host):
                response = http_request(
                    self.h.runtime, "/api/v1/projects", token=self.h.token, host=host
                )
                self.assertEqual(response.status, 403, host)
                self.assertEqual(response.error_code, "origin-invalid")

    def test_reads_may_omit_origin_but_writes_may_not(self) -> None:
        allowed = http_request(self.h.runtime, "/api/v1/projects", token=self.h.token)
        self.assertEqual(allowed.status, 200)

        directory = self.h.make_directory("origin")
        missing = http_request(
            self.h.runtime,
            "/api/v1/projects/probe",
            method="POST",
            body={"path": str(directory)},
            token=self.h.token,
        )
        self.assertEqual(missing.status, 403)
        self.assertEqual(missing.error_code, "origin-invalid")

        wrong = http_request(
            self.h.runtime,
            "/api/v1/projects/probe",
            method="POST",
            body={"path": str(directory)},
            token=self.h.token,
            origin="http://localhost:1234",
        )
        self.assertEqual(wrong.status, 403)
        self.assertEqual(wrong.error_code, "origin-invalid")

        for method, path in (
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/session"),
        ):
            with self.subTest(method=method, path=path):
                response = http_request(
                    self.h.runtime,
                    path,
                    method=method,
                    body={} if method == "POST" else None,
                    token=self.h.token,
                    origin="https://evil.example",
                )
                self.assertEqual(response.status, 403)

    def test_bootstrap_exchange_is_one_time_and_origin_bound(self) -> None:
        secret = self.h.bootstrap_secret()
        # The harness already consumed the original bootstrap; a fresh
        # runtime gives a clean one-time secret to exercise.
        self.h.stop()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = start_runtime(data_dir=Path(tmp) / "data")
            try:
                secret = runtime.bootstrap_url.split("#bootstrap=", 1)[1]
                no_origin = http_request(
                    runtime,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": secret},
                )
                self.assertEqual(no_origin.status, 403)

                wrong = http_request(
                    runtime,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": "z" * 43},
                    origin=runtime.origin,
                )
                self.assertEqual(wrong.status, 401)
                self.assertEqual(wrong.error_code, "unauthorized")

                first = http_request(
                    runtime,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": secret},
                    origin=runtime.origin,
                )
                self.assertEqual(first.status, 200)
                self.assertTrue(first.json["token"])

                replay = http_request(
                    runtime,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": secret},
                    origin=runtime.origin,
                )
                self.assertEqual(replay.status, 401)
                self.assertEqual(replay.headers.get("Cache-Control"), "no-store")
            finally:
                runtime.stop()

    def test_credentials_never_travel_in_a_query_string(self) -> None:
        for query in (
            "?token=" + self.h.token,
            "?bootstrap=abc",
            "?session_token=abc",
            "?api_key=abc",
        ):
            with self.subTest(query=query):
                response = http_request(
                    self.h.runtime, "/api/v1/projects" + query, token=self.h.token
                )
                self.assertEqual(response.status, 401)
                self.assertEqual(response.error_code, "unauthorized")

    def test_static_shell_needs_no_token_but_carries_no_project_data(self) -> None:
        for path in ("/", "/app.html", "/app.css", "/app.js"):
            with self.subTest(path=path):
                response = http_request(self.h.runtime, path)
                self.assertEqual(response.status, 200)
                self.assertIn("frame-ancestors 'none'", response.headers[
                    "Content-Security-Policy"
                ])
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        shell = http_request(self.h.runtime, "/").text
        self.assertNotIn("bootstrap=", shell)
        self.assertNotIn(self.h.token, shell)

    def test_resource_paths_outside_the_shell_are_never_served(self) -> None:
        target = self.h.runtime.data_dir.session_record_path
        response = http_request(
            self.h.runtime, "/session/session.json", token=self.h.token
        )
        self.assertEqual(response.status, 404)
        self.assertEqual(response.error_code, "route-not-found")
        unauthenticated = http_request(self.h.runtime, "/api/v1/anything")
        self.assertEqual(unauthenticated.status, 401)
        self.assertNotIn(str(target), unauthenticated.text)

    def test_unsupported_methods_are_rejected_with_allow(self) -> None:
        for method in ("PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                response = http_request(
                    self.h.runtime,
                    "/api/v1/projects",
                    method=method,
                    body={},
                    token=self.h.token,
                    origin=self.h.runtime.origin,
                )
                self.assertEqual(response.status, 405)
                self.assertEqual(response.headers.get("Allow"), "GET, HEAD, POST")

    def test_oversized_bodies_are_refused_before_parsing(self) -> None:
        oversized = b'{"path":"' + b"a" * (300 * 1024) + b'"}'
        response = http_request(
            self.h.runtime,
            "/api/v1/projects/probe",
            method="POST",
            raw_body=oversized,
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(response.status, 413)
        self.assertEqual(response.error_code, "request-too-large")

    def test_malformed_json_is_a_typed_rejection(self) -> None:
        response = http_request(
            self.h.runtime,
            "/api/v1/projects/probe",
            method="POST",
            raw_body=b"{not json",
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(response.error_code, "invalid-input")

    def test_head_requests_return_no_body(self) -> None:
        static = http_request(self.h.runtime, "/", method="HEAD")
        self.assertEqual(static.status, 200)
        self.assertEqual(static.body, b"")
        api = http_request(
            self.h.runtime, "/api/v1/projects", method="HEAD", token=self.h.token
        )
        self.assertEqual(api.status, 200)
        self.assertEqual(api.body, b"")

    def test_status_requires_authentication(self) -> None:
        response = http_request(self.h.runtime, "/api/v1/status")
        self.assertEqual(response.status, 401)
        authorized = http_request(
            self.h.runtime, "/api/v1/status", token=self.h.token
        )
        self.assertEqual(authorized.status, 200)
        self.assertEqual(authorized.json["bootId"], self.h.runtime.session.boot_id)


class RejectionLeakTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)

    def test_rejections_never_echo_the_attempted_path(self) -> None:
        secret_name = "top-secret-plans"
        missing = self.h.workspace / secret_name
        response = self.h.probe(missing)
        self.assertEqual(response.status, 400)
        self.assertEqual(response.error_code, "invalid-target")
        self.assertNotIn(secret_name, response.text)

        file_path = self.h.workspace / f"{secret_name}.txt"
        file_path.write_text("x", encoding="utf-8")
        file_response = self.h.probe(file_path)
        self.assertEqual(file_response.status, 400)
        self.assertNotIn(secret_name, file_response.text)

    def test_relative_and_remote_paths_cannot_be_registered(self) -> None:
        for path in ("relative/dir", "./here", r"\\server\share", "", "   "):
            with self.subTest(path=path):
                response = self.h.probe(path)
                self.assertEqual(response.status, 400, response.text)
                self.assertEqual(response.error_code, "invalid-target")

    def test_data_directory_can_never_be_a_project(self) -> None:
        response = self.h.probe(self.h.data_dir)
        self.assertEqual(response.status, 400)
        self.assertNotIn(str(self.h.data_dir), response.text)

    def test_confirmation_cannot_drift_from_the_probed_candidate(self) -> None:
        directory = self.h.make_directory("drift")
        probed = self.h.probe(directory)
        candidate = probed.json["candidate"]
        response = http_request(
            self.h.runtime,
            "/api/v1/projects",
            method="POST",
            body={
                "path": candidate["canonicalPath"],
                "candidateId": "cand_" + "0" * 32,
                "operation": {"operationId": "op_drift_0001", "payload": {}},
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(self.h.projects()["projects"], [])

    def test_registering_the_same_folder_twice_is_refused(self) -> None:
        directory = self.h.make_directory("duplicate")
        first = self.h.register(directory)
        self.assertEqual(first.status, 200, first.text)
        # The second attempt is refused at probe time already: one project
        # per real directory, before any registration mutation is offered.
        second = self.h.probe(directory)
        self.assertEqual(second.status, 400)
        self.assertEqual(second.error_code, "invalid-target")
        self.assertEqual(len(self.h.projects()["projects"]), 1)

    def test_case_variant_and_short_path_spellings_are_the_same_folder(self) -> None:
        directory = self.h.make_directory("case-variant")
        self.assertEqual(self.h.register(directory).status, 200)
        # A second spelling of the same directory (different case; on this
        # host the temporary root is also reachable as an 8.3 short name)
        # must not become a second project.
        for spelling in (str(directory).upper(), str(directory).lower()):
            with self.subTest(spelling=spelling):
                response = self.h.probe(spelling)
                self.assertEqual(response.status, 400, response.text)
                self.assertEqual(response.error_code, "invalid-target")
        self.assertEqual(len(self.h.projects()["projects"]), 1)

    def test_alias_of_a_registered_folder_is_refused(self) -> None:
        directory = self.h.make_directory("aliased")
        self.assertEqual(self.h.register(directory).status, 200)
        link = self.h.workspace / "aliased-link"
        if not make_directory_link(link, directory):
            self.skipTest("directory links are unavailable on this host")
        response = self.h.probe(link)
        self.assertEqual(response.status, 400)
        self.assertEqual(response.error_code, "invalid-target")


class SessionLifecycleTest(unittest.TestCase):
    def test_restart_invalidates_credentials_but_keeps_registrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            project = workspace / "alpha"
            project.mkdir()

            first = start_runtime(data_dir=data_dir)
            try:
                token = self._exchange(first)
                registered = http_request(
                    first,
                    "/api/v1/projects",
                    method="POST",
                    body={
                        "path": str(project),
                        "candidateId": self._candidate(first, token, project),
                        "operation": {
                            "operationId": "op_restart_0001",
                            "payload": {"action": "register-project"},
                        },
                    },
                    token=token,
                    origin=first.origin,
                )
                self.assertEqual(registered.status, 200, registered.text)
                old_bootstrap = first.bootstrap_url.split("#bootstrap=", 1)[1]
            finally:
                first.stop()
            self.assertFalse(data_dir.joinpath("session", "session.json").exists())

            second = start_runtime(data_dir=data_dir)
            try:
                stale = http_request(second, "/api/v1/projects", token=token)
                self.assertEqual(stale.status, 401)
                stale_bootstrap = http_request(
                    second,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": old_bootstrap},
                    origin=second.origin,
                )
                self.assertEqual(stale_bootstrap.status, 401)

                fresh = self._exchange(second)
                listing = http_request(second, "/api/v1/projects", token=fresh)
                self.assertEqual(listing.status, 200)
                self.assertEqual(len(listing.json["projects"]), 1)
                recorded = listing.json["projects"][0]["canonicalPath"]
                self.assertTrue(os.path.samefile(recorded, project))
                # The stored spelling is the resolved canonical path, so a
                # second spelling of the same directory cannot pose as a new
                # project (on this host the temp path is a short 8.3 form).
                self.assertEqual(recorded, str(project.resolve()))
            finally:
                second.stop()

    def test_expired_session_and_bootstrap_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1000.0}
            runtime = make_runtime(
                Path(tmp) / "data", ttl_seconds=60, now_fn=lambda: clock["now"]
            )
            try:
                token = self._exchange(runtime)
                self.assertEqual(
                    http_request(runtime, "/api/v1/projects", token=token).status, 200
                )
                clock["now"] += 61.0
                expired = http_request(runtime, "/api/v1/projects", token=token)
                self.assertEqual(expired.status, 401)
                secret = runtime.bootstrap_url.split("#bootstrap=", 1)[1]
                expired_bootstrap = http_request(
                    runtime,
                    "/api/v1/session",
                    method="POST",
                    body={"bootstrap": secret},
                    origin=runtime.origin,
                )
                self.assertEqual(expired_bootstrap.status, 401)
            finally:
                runtime.stop()

    def _candidate(self, runtime, token, project: Path) -> str:
        response = http_request(
            runtime,
            "/api/v1/projects/probe",
            method="POST",
            body={"path": str(project)},
            token=token,
            origin=runtime.origin,
        )
        assert response.status == 200, response.text
        return response.json["candidate"]["candidateId"]

    def _exchange(self, runtime) -> str:
        secret = runtime.bootstrap_url.split("#bootstrap=", 1)[1]
        response = http_request(
            runtime,
            "/api/v1/session",
            method="POST",
            body={"bootstrap": secret},
            origin=runtime.origin,
        )
        assert response.status == 200, response.text
        return response.json["token"]


class CredentialRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.record_path = self.h.runtime.data_dir.session_record_path

    def tearDown(self) -> None:
        self.h.stop()

    def test_record_is_private_to_the_current_os_user(self) -> None:
        self.assertTrue(self.record_path.exists())
        # The message is built lazily per platform: current_user_principal()
        # only resolves a name where an ACL is used (Windows), so calling it
        # on POSIX would fail on a host without USER set.
        detail = current_user_principal() if os.name == "nt" else "POSIX mode 0600"
        self.assertTrue(is_private(self.record_path), detail)

    def test_private_record_supports_non_ascii_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="权限-") as tmp:
            path = Path(tmp) / "会话" / "凭证.json"
            write_private_json(path, {"example": "no secret"})
            self.assertTrue(is_private(path))
            self.assertEqual(json.loads(path.read_text()), {"example": "no secret"})

    def test_record_is_the_os_private_credential_store(self) -> None:
        raw = self.record_path.read_text(encoding="utf-8")
        record = json.loads(raw)
        self.assertEqual(record["authority"], self.h.runtime.origin)
        self.assertEqual(record["bootId"], self.h.runtime.session.boot_id)
        self.assertTrue(record["bootstrapUrl"].startswith(self.h.runtime.origin))
        # R01 keeps the session credential in this record so the
        # maintainer's own slash entry point can reach the local service;
        # the record is private to the OS user and is never served.
        self.assertEqual(record["sessionToken"], self.h.token)
        served = http_request(
            self.h.runtime, "/session/session.json", token=self.h.token
        )
        self.assertNotEqual(served.status, 200)
        self.assertNotIn(self.h.token, served.text)
        # The credential must not leak through a query string either.
        leaked = http_request(
            self.h.runtime, "/api/v1/projects?token=" + self.h.token, token=self.h.token
        )
        self.assertEqual(leaked.status, 401)
        self.assertNotIn(self.h.token, leaked.text)

    def test_record_is_removed_when_the_service_stops(self) -> None:
        self.h.stop()
        self.assertFalse(self.record_path.exists())

    def test_no_secret_reaches_stdout_or_stderr_during_requests(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            http_request(self.h.runtime, "/api/v1/projects/probe", method="POST",
                         body={"path": "relative"}, token=self.h.token,
                         origin=self.h.runtime.origin)
            http_request(self.h.runtime, "/api/v1/projects")
        combined = out.getvalue() + err.getvalue()
        self.assertNotIn(self.h.token, combined)
        self.assertNotIn(self.h.bootstrap_secret(), combined)
        self.assertNotIn("Authorization", combined)


class CapabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.alpha = self.h.register(self.h.make_directory("alpha")).json["result"]
        self.beta = self.h.register(self.h.make_directory("beta")).json["result"]

    def _capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )

    def test_capability_reads_only_its_own_project(self) -> None:
        capability = self._capability(self.alpha["projectId"], ["read"])
        allowed = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.alpha['projectId']}",
            capability=capability,
        )
        self.assertEqual(allowed.status, 200, allowed.text)
        self.assertEqual(
            allowed.json["project"]["projectId"], self.alpha["projectId"]
        )
        other = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.beta['projectId']}",
            capability=capability,
        )
        self.assertEqual(other.status, 401)
        self.assertEqual(other.error_code, "unauthorized")

    def test_capability_must_present_no_origin(self) -> None:
        capability = self._capability(self.alpha["projectId"], ["read"])
        with_origin = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.alpha['projectId']}",
            capability=capability,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(with_origin.status, 403)
        self.assertEqual(with_origin.error_code, "origin-invalid")

    def test_capability_cannot_be_mixed_with_a_session_token(self) -> None:
        capability = self._capability(self.alpha["projectId"], ["read"])
        response = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.alpha['projectId']}",
            capability=capability,
            token=self.h.token,
        )
        self.assertEqual(response.status, 401)

    def test_capability_never_administers_projects(self) -> None:
        capability = self._capability(self.alpha["projectId"], ["read"])
        listing = http_request(
            self.h.runtime, "/api/v1/projects", capability=capability
        )
        self.assertEqual(listing.status, 401)
        rename = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.alpha['projectId']}/actions/rename",
            method="POST",
            body={
                "name": "Stolen",
                "operation": {"operationId": "op_cap_rename_1", "payload": {}},
            },
            capability=capability,
        )
        self.assertEqual(rename.status, 401)

    def test_capability_never_reaches_maintainer_mutations(self) -> None:
        # An Agent/slash capability holding full project write scope must
        # never reach maintainer-only mutations: publishing, reuse, upgrades,
        # canvas/orchestration authoring, or work/authoring actions. Its only
        # sanctioned write path is proposal submission (R01/R06/R11). Auth is
        # checked at the gate before any lookup, so dummy ids still prove it.
        write = self._capability(self.alpha["projectId"], ["read", "write"])
        pid = self.alpha["projectId"]
        op = {"operationId": "op_cap_probe", "payload": {}}

        def post(path: str, body: dict):
            return http_request(
                self.h.runtime,
                f"/api/v1/projects/{pid}/{path}",
                method="POST",
                body={**body, "operation": op},
                capability=write,
            )

        asset = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        for verb in (
            "publish", "publish-with-deps", "preview-enable", "refresh-draft",
            "derive", "copy", "reference", "import-closure", "upgrade",
            "rollback", "tokens-update", "tokens-publish", "propose-baseline",
            "component-update", "component-publish", "page-update",
            "page-publish", "distill-candidate", "publish-verified",
            "archive", "unarchive", "trash", "restore", "hard-delete",
        ):
            with self.subTest(asset_verb=verb):
                r = post(f"actions/assets/{asset}/{verb}", {})
                self.assertEqual(r.status, 401, f"{verb}: {r.text}")

        canvas = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        for verb in (
            "commands", "undo", "redo", "rename", "fork", "snapshots",
            "compare", "contexts", "confirm",
        ):
            with self.subTest(canvas_verb=verb):
                r = post(f"actions/canvases/{canvas}/{verb}", {})
                self.assertEqual(r.status, 401, f"{verb}: {r.text}")

        for action in (
            "instances", "components", "pages", "canvases", "requests",
            "imports", "confirmations", "backflow", "project-archive",
            "project-unarchive", "open", "rename", "rebind", "grants",
            "remove",
        ):
            with self.subTest(action=action):
                r = post(f"actions/{action}", {})
                self.assertEqual(r.status, 401, f"{action}: {r.text}")

        # The one sanctioned Agent write path (proposal submission) is gated
        # only on project write scope, not the browser session: proving the
        # gate does not deny it is covered by the proposal/work API tests
        # (an empty-change probe here would fail on the project grant, not
        # the maintainer/Agent partition).

    def test_capability_scopes_are_enforced(self) -> None:
        write_only = self._capability(self.alpha["projectId"], ["write"])
        denied = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.alpha['projectId']}",
            capability=write_only,
        )
        self.assertEqual(denied.status, 401)
        with self.assertRaises(WorkbenchError):
            self.h.runtime.session.issue_capability(
                project_id=self.alpha["projectId"], scopes=["nope"]
            )

    def test_unknown_and_random_capabilities_are_refused(self) -> None:
        for capability in ("c" * 43, "short", ""):
            with self.subTest(capability=capability):
                response = http_request(
                    self.h.runtime,
                    f"/api/v1/projects/{self.alpha['projectId']}",
                    capability=capability,
                )
                self.assertEqual(response.status, 401)


class ProjectJourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)

    def test_full_project_lifecycle_over_http(self) -> None:
        directory = self.h.make_directory("lifecycle")
        registered = self.h.register(directory, name="Lifecycle")
        self.assertEqual(registered.status, 200, registered.text)
        project = registered.json["result"]
        project_id = project["projectId"]
        self.assertEqual(project["grantScopes"], ["read"])

        opened = self.h.action(project_id, "open", expected_counter=0)
        self.assertEqual(opened.status, 200, opened.text)
        self.assertEqual(opened.json["result"]["currentProjectId"], project_id)

        renamed = self.h.action(
            project_id,
            "rename",
            payload={"name": "Renamed"},
            expected_counter=0,
            operation_id="op_rename_lifecycle_1",
        )
        self.assertEqual(renamed.status, 200, renamed.text)
        self.assertEqual(renamed.json["result"]["name"], "Renamed")
        self.assertEqual(renamed.json["counter"], 1)

        replayed = self.h.action(
            project_id,
            "rename",
            payload={"name": "Renamed"},
            expected_counter=0,
            operation_id="op_rename_lifecycle_1",
        )
        self.assertEqual(replayed.status, 200, replayed.text)
        self.assertTrue(replayed.json["replayed"])
        self.assertEqual(replayed.json["result"]["name"], "Renamed")

        stale = self.h.action(
            project_id, "rename", payload={"name": "Again"}, expected_counter=0
        )
        self.assertEqual(stale.status, 409)
        self.assertEqual(stale.error_code, "conflict")

        granted = self.h.action(
            project_id,
            "grants",
            payload={"scopes": ["read", "write"]},
            expected_counter=1,
        )
        self.assertEqual(granted.status, 200, granted.text)
        self.assertEqual(granted.json["result"]["grantScopes"], ["read", "write"])

        removed = self.h.action(project_id, "remove", expected_counter=2)
        self.assertEqual(removed.status, 200, removed.text)
        self.assertEqual(self.h.projects()["projects"], [])
        self.assertTrue(directory.exists())
        self.assertEqual(list(directory.iterdir()), [])

    def test_disconnected_project_reports_state_and_blocks_operations(self) -> None:
        directory = self.h.make_directory("vanishing")
        project = self.h.register(directory).json["result"]
        project_id = project["projectId"]
        directory.rmdir()

        target = self.h.project_target(project_id)
        self.assertEqual(target["connectionState"], "disconnected")

        blocked = self.h.action(project_id, "open", expected_counter=0)
        self.assertEqual(blocked.status, 409)
        self.assertEqual(blocked.error_code, "disconnected")

    def test_unknown_project_is_invalid_target(self) -> None:
        response = http_request(
            self.h.runtime, f"/api/v1/projects/{UNKNOWN_PROJECT}", token=self.h.token
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(response.error_code, "invalid-target")
        self.assertNotIn(UNKNOWN_PROJECT, response.json["error"]["message"])


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
