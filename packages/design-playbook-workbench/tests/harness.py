"""Shared test harness for the workbench: real service, real temp dirs.

Nothing here mocks the service: every test drives a real loopback
listener over a real SQLite database in a temporary directory, exactly as
the launcher builds it. Only the Agent/model protocol (a later ticket)
would ever be a test double.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from design_playbook_workbench.http_server import (  # noqa: E402
    BOOTSTRAP_HEADER,
    CAPABILITY_HEADER,
)
from design_playbook_workbench.launcher import (  # noqa: E402
    WorkbenchRuntime,
    start_runtime,
)

# Chromium refuses to navigate to these ports with ERR_UNSAFE_PORT.
CHROMIUM_RESTRICTED_PORTS = frozenset(
    {
        1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69,
        77, 79, 87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119,
        123, 135, 137, 139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515,
        526, 530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990,
        993, 995, 1719, 1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000, 6565,
        6665, 6666, 6667, 6668, 6669, 6697, 10080,
    }
)


#: One opener with proxies disabled: the workbench is loopback-only, and an
#: ambient proxy would answer for a forged Host instead of the real server.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    @property
    def error_code(self) -> str | None:
        payload = self.json
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return payload["error"].get("code")
        return None


def make_directory_link(link: Path, target: Path) -> bool:
    """Create a directory symlink or Windows junction; False when unavailable.

    On Windows the junction is the interesting case: it is what an attacker
    or a careless setup uses to alias a folder, and ``Path.resolve`` must
    collapse it before any decision is made.
    """
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and link.exists()
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        return False
    return True


def _new_operation_id(prefix: str) -> str:
    return f"op_{prefix}_{uuid.uuid4().hex[:12]}"


def http_request(
    runtime: WorkbenchRuntime,
    path: str,
    *,
    method: str = "GET",
    body: Any = None,
    token: str | None = None,
    capability: str | None = None,
    host: str | None = None,
    origin: str | None = None,
    raw_body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
    origin_url: bool = True,
) -> Response:
    """One raw HTTP request, so tests can forge Host/Origin/headers."""
    base = runtime.origin if origin_url else ""
    url = base + path
    data = raw_body
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if data is not None and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if capability is not None:
        headers[CAPABILITY_HEADER] = capability
    if host is not None:
        headers["Host"] = host
    if origin is not None:
        headers["Origin"] = origin
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=15) as response:
            return Response(
                response.status, dict(response.headers), response.read()
            )
    except urllib.error.HTTPError as error:
        return Response(error.code, dict(error.headers), error.read())


class WorkbenchHarness:
    """A running workbench plus maintainer-side helpers for the journey."""

    def __init__(
        self,
        *,
        ttl_seconds: int | None = None,
        data_dir: Path | None = None,
        consume_bootstrap: bool = True,
    ):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = data_dir or (self.base / "workbench-data")
        self.workspace = self.base / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {}
        if ttl_seconds is not None:
            kwargs["ttl_seconds"] = ttl_seconds
        self.runtime = self._start(**kwargs)
        # A browser journey needs the one-time secret to still be unused, so
        # it can start from the real launch URL instead of a spent session;
        # maintainer-side calls then use the live session token directly.
        self.token = (
            self.exchange_bootstrap()
            if consume_bootstrap
            else self.runtime.session.token
        )

    def _start(self, **kwargs: Any) -> WorkbenchRuntime:
        for _ in range(20):
            runtime = start_runtime(
                data_dir=self.data_dir, bind_host="127.0.0.1", port=0, **kwargs
            )
            if runtime.server.port not in CHROMIUM_RESTRICTED_PORTS:
                return runtime
            runtime.stop()
        raise OSError("no navigable ephemeral port available")

    def exchange_bootstrap(self, presented: str | None = None) -> str:
        payload = {"bootstrap": presented or self.bootstrap_secret()}
        response = http_request(
            self.runtime,
            "/api/v1/session",
            method="POST",
            body=payload,
            origin=self.runtime.origin,
        )
        assert response.status == 200, response.text
        return response.json["token"]

    @property
    def origin(self) -> str:
        """The management origin for this running service."""
        return self.runtime.origin

    @property
    def preview_origin(self) -> str:
        """The isolated preview origin for this running service."""
        return self.runtime.preview_origin

    def bootstrap_secret(self) -> str:
        url = self.runtime.bootstrap_url
        return url.split("#bootstrap=", 1)[1]

    def make_directory(self, name: str = "project") -> Path:
        """A real, empty project directory under the harness workspace."""
        path = self.workspace / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def probe(self, path: Path | str, *, exclude_project_id: str | None = None) -> Response:
        body: dict[str, Any] = {"path": str(path)}
        if exclude_project_id:
            body["excludeProjectId"] = exclude_project_id
        return http_request(
            self.runtime,
            "/api/v1/projects/probe",
            method="POST",
            body=body,
            token=self.token,
            origin=self.runtime.origin,
        )

    def register(self, path: Path | str, *, name: str | None = None, operation_id: str | None = None):
        probed = self.probe(path)
        assert probed.status == 200, probed.text
        candidate = probed.json["candidate"]
        body: dict[str, Any] = {
            "path": candidate["canonicalPath"],
            "candidateId": candidate["candidateId"],
            "operation": {
                "operationId": operation_id or _new_operation_id("register"),
                "payload": {
                    "action": "register-project",
                    "path": candidate["canonicalPath"],
                    "candidateId": candidate["candidateId"],
                },
            },
        }
        if name is not None:
            body["name"] = name
        return http_request(
            self.runtime,
            "/api/v1/projects",
            method="POST",
            body=body,
            token=self.token,
            origin=self.runtime.origin,
        )

    def action(
        self,
        project_id: str,
        action: str,
        *,
        payload: dict | None = None,
        expected_counter: int | None = None,
        operation_id: str | None = None,
        capability: str | None = None,
    ) -> Response:
        operation: dict[str, Any] = {
            "operationId": operation_id or _new_operation_id(action),
            "payload": {"action": action, "projectId": project_id, **(payload or {})},
        }
        if expected_counter is not None:
            operation["expectedCounter"] = expected_counter
        body = {"operation": operation, **(payload or {})}
        use_capability = capability is not None
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/actions/{action}",
            method="POST",
            body=body,
            token=None if use_capability else self.token,
            capability=capability,
            origin=None if use_capability else self.runtime.origin,
        )

    def projects(self) -> dict:
        response = http_request(
            self.runtime, "/api/v1/projects", token=self.token
        )
        assert response.status == 200, response.text
        return response.json

    # -- proposals (WB-09) ---------------------------------------------

    def grant(
        self, project_id: str, scopes: list[str], *, expected_counter: int
    ) -> Response:
        return self.action(
            project_id,
            "grants",
            payload={"scopes": scopes},
            expected_counter=expected_counter,
        )

    def create_proposal(
        self,
        project_id: str,
        changes: list[dict],
        *,
        summary: str = "",
        operation_id: str | None = None,
        capability: str | None = None,
    ) -> Response:
        operation = {
            "operationId": operation_id or _new_operation_id("proposal"),
            "payload": {
                "action": "proposals",
                "projectId": project_id,
                "changes": changes,
            },
        }
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/actions/proposals",
            method="POST",
            body={"operation": operation, "changes": changes, "summary": summary},
            token=None if capability else self.token,
            capability=capability,
            origin=None if capability else self.runtime.origin,
        )

    def proposal_action(
        self,
        project_id: str,
        proposal_id: str,
        verb: str,
        *,
        digest: str | None = None,
        mode: str | None = None,
        operation_id: str | None = None,
        capability: str | None = None,
        token: str | None = None,
    ) -> Response:
        body: dict[str, Any] = {
            "operation": {
                "operationId": operation_id or _new_operation_id(verb),
                "payload": {"action": verb, "proposalId": proposal_id},
            }
        }
        if digest is not None:
            body["digest"] = digest
        if mode is not None:
            body["mode"] = mode
        use_capability = capability is not None
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/actions/proposals/{proposal_id}/{verb}",
            method="POST",
            body=body,
            token=(
                None
                if use_capability
                else (token if token is not None else self.token)
            ),
            capability=capability,
            origin=None if use_capability else self.runtime.origin,
        )

    def proposals(self, project_id: str, *, capability: str | None = None) -> Response:
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/proposals",
            token=None if capability else self.token,
            capability=capability,
        )

    # -- assets and previews (WB-03) -----------------------------------

    def import_assets(
        self,
        project_id: str,
        selections: list,
        *,
        operation_id: str | None = None,
        capability: str | None = None,
    ) -> Response:
        operation = {
            "operationId": operation_id or _new_operation_id("import"),
            "payload": {"action": "imports", "projectId": project_id},
        }
        use_capability = capability is not None
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/actions/imports",
            method="POST",
            body={"operation": operation, "selections": selections},
            token=None if use_capability else self.token,
            capability=capability,
            origin=None if use_capability else self.runtime.origin,
        )

    def assets(
        self, project_id: str, *, query: str = "", capability: str | None = None
    ) -> Response:
        suffix = "?" + query if query else ""
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/assets{suffix}",
            token=None if capability else self.token,
            capability=capability,
        )

    def asset_detail(
        self, project_id: str, asset_id: str, *, capability: str | None = None
    ) -> Response:
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/assets/{asset_id}",
            token=None if capability else self.token,
            capability=capability,
        )

    def asset_action(
        self,
        project_id: str,
        asset_id: str,
        verb: str,
        *,
        payload: dict | None = None,
        capability: str | None = None,
        operation_id: str | None = None,
    ) -> Response:
        operation = {
            "operationId": operation_id or _new_operation_id(verb),
            "payload": {"action": verb, "assetId": asset_id, **(payload or {})},
        }
        use_capability = capability is not None
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/actions/assets/{asset_id}/{verb}",
            method="POST",
            body={"operation": operation, **(payload or {})},
            token=None if use_capability else self.token,
            capability=capability,
            origin=None if use_capability else self.runtime.origin,
        )

    def asset_action_import_closure(
        self,
        source_project_id: str,
        asset_id: str,
        *,
        target_project_id: str,
        mode: str = "copy",
        source_revision_id: str | None = None,
        capability: str | None = None,
        operation_id: str | None = None,
    ) -> Response:
        payload = {
            "targetProjectId": target_project_id,
            "mode": mode,
            "sourceAssetId": asset_id,
        }
        if source_revision_id:
            payload["sourceRevisionId"] = source_revision_id
        return self.asset_action(
            source_project_id,
            asset_id,
            "import-closure",
            payload=payload,
            capability=capability,
            operation_id=operation_id,
        )

    def asset_preview(
        self, project_id: str, asset_id: str, *, capability: str | None = None
    ) -> Response:
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/assets/{asset_id}/preview",
            token=None if capability else self.token,
            capability=capability,
        )

    def proposal_detail(
        self, project_id: str, proposal_id: str, *, capability: str | None = None
    ) -> Response:
        return http_request(
            self.runtime,
            f"/api/v1/projects/{project_id}/proposals/{proposal_id}",
            token=None if capability else self.token,
            capability=capability,
        )

    def project_target(self, project_id: str) -> dict:
        response = http_request(
            self.runtime, f"/api/v1/projects/{project_id}", token=self.token
        )
        assert response.status == 200, response.text
        return response.json["project"]

    def bootstrap_request(self, secret: str, *, origin: str | None = None) -> Response:
        return http_request(
            self.runtime,
            "/api/v1/session",
            method="POST",
            body={"bootstrap": secret},
            origin=origin if origin is not None else self.runtime.origin,
        )

    def stop(self) -> None:
        try:
            self.runtime.stop()
        finally:
            self._tmp.cleanup()

    def __enter__(self) -> "WorkbenchHarness":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def make_runtime(
    tmp_root: Path,
    *,
    ttl_seconds: int | None = None,
    port: int = 0,
    now_fn=None,
) -> WorkbenchRuntime:
    """Start a runtime in an explicit data directory (for restart tests)."""
    kwargs: dict[str, Any] = {}
    if ttl_seconds is not None:
        kwargs["ttl_seconds"] = ttl_seconds
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    return start_runtime(
        data_dir=tmp_root, bind_host="127.0.0.1", port=port, **kwargs
    )


__all__ = [
    "BOOTSTRAP_HEADER",
    "CAPABILITY_HEADER",
    "CHROMIUM_RESTRICTED_PORTS",
    "Response",
    "WorkbenchHarness",
    "http_request",
    "make_directory_link",
    "make_runtime",
]
