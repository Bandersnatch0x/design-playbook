"""Loopback HTTP surface for the Workbench API v1 (R01, R02).

One process-owned server, one IP-literal loopback listener, and exactly
one live session. Policy is enforced in a fixed order before any domain
code runs, so a rejected request has zero effect: request-size bound,
exact ``Host``, no credential in the query string, the static shell, then
authentication (bearer session or project capability, never both) and the
per-method ``Origin`` rule. Every response carries the restrictive header
policy; every failure is the fixed error envelope with no path, secret,
or traceback.
"""
from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
from urllib.parse import parse_qsl, urlsplit

from .assets import AssetService
from .canvas import CanvasService
from .orchestration import OrchestrationService
from .backup import BackupService
from .lifecycle import LifecycleService
from .owners import OwnerProjectionService
from .work import WorkRequestService
from .components import ComponentService
from .designsystem import DesignSystemService
from .errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    ORIGIN_INVALID,
    ROUTE_NOT_FOUND,
    REQUEST_TOO_LARGE,
    UNAUTHORIZED,
    WorkbenchError,
)
from .proposals import ProposalService
from .resolver import resolve
from .reuse import ReuseService
from .security import (
    DEFAULT_BIND_HOST,
    capability_header_value,
    canonical_authority,
    canonical_origin,
    ensure_loopback_bind_host,
    extract_bearer_token,
    host_header_is_valid,
    is_read_method,
    origin_header_is_valid,
    query_carries_auth_material,
    security_headers,
)
from .service import Operation, WorkbenchService, validate_operation
from .session import Principal, WorkbenchSession
from .store import SCHEMA_VERSION
from .ui import UIResources

SESSION_ROUTE = "/api/v1/session"
STATUS_ROUTE = "/api/v1/status"
RESOLVE_ROUTE = "/api/v1/resolve"
PROJECTS_ROUTE = "/api/v1/projects"
PROJECTS_PREFIX = "/api/v1/projects/"
BACKUP_ROUTE = "/api/v1/backup"
CAPABILITY_HEADER = "X-Workbench-Capability"
BOOTSTRAP_HEADER = "X-Workbench-Bootstrap"

READ_METHODS_HEADER = "GET, HEAD"
WRITE_METHODS_HEADER = "POST"
COLLECTION_METHODS_HEADER = "GET, HEAD, POST"

MAX_REQUEST_BODY_BYTES = 256 * 1024

_DUPLICATED = object()

#: Project actions the browser may perform; a slash capability may never
#: create, rename, re-grant, rebind, or remove a project.
_BROWSER_ONLY_ACTIONS = frozenset(
    {"open", "rename", "rebind", "grants", "remove"}
)

#: Proposal transitions that are a maintainer authorization decision. An
#: Agent capability may submit a proposal, never approve one.
_MAINTAINER_ONLY_PROPOSAL_ACTIONS = frozenset(
    {"apply", "recover", "revert", "reject"}
)


class _Rejection(Exception):
    """Internal control flow: nothing is sent until the handler decides."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class WorkbenchRequestHandler(http.server.BaseHTTPRequestHandler):
    """One request against the workbench: validate, authenticate, serve."""

    protocol_version = "HTTP/1.1"
    server_version = "DesignPlaybookWorkbench"
    sys_version = ""
    timeout = 30

    def version_string(self) -> str:
        return "DesignPlaybookWorkbench"

    def log_message(self, format: str, *args: object) -> None:
        """Never log: no URL, token, or path may reach any log."""

    def finish(self) -> None:
        """Graceful teardown: flush, half-close, drain, close."""
        super().finish()
        try:
            self.connection.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            self.connection.settimeout(0.2)
            while self.connection.recv(65536):
                pass
        except OSError:
            pass

    # -- dispatch -------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch()

    def do_TRACE(self) -> None:  # noqa: N802
        self._dispatch()

    def send_error(self, code, message=None, explain=None) -> None:  # type: ignore[override]
        """Bounded JSON for every stdlib-initiated rejection."""
        try:
            self.close_connection = True
            mapping = {
                400: (400, INVALID_INPUT),
                414: (413, REQUEST_TOO_LARGE),
                501: (405, "method-not-allowed"),
                505: (400, INVALID_INPUT),
            }
            status, error_code = mapping.get(code, (400, INVALID_INPUT))
            headers = None
            if status == 405:
                headers = {"Allow": READ_METHODS_HEADER}
            self._send_json(
                status,
                WorkbenchError(error_code).envelope(),
                close=True,
                extra_headers=headers,
            )
        except Exception:
            self.close_connection = True

    def _dispatch(self) -> None:
        self._responded = False
        try:
            self._process()
        except _Rejection as rejection:
            if not self._responded:
                self._send_error(rejection.code, detail=rejection.detail)
        except WorkbenchError as error:
            if not self._responded:
                self._send_json(error.status, error.envelope(), close=True)
        except Exception:
            if not self._responded:
                self._fail_closed()

    def _fail_closed(self) -> None:
        try:
            self._send_json(
                500, WorkbenchError("internal-error").envelope(), close=True
            )
        except Exception:
            self.close_connection = True

    # -- policy pipeline -------------------------------------------------

    def _process(self) -> None:
        server = self.server
        rejection = self._request_size_code()
        if rejection is not None:
            raise _Rejection(rejection)
        if not host_header_is_valid(
            self._single_header("Host"),
            bind_host=server.bind_host,
            port=server.server_port,
        ):
            raise _Rejection(ORIGIN_INVALID)
        split = urlsplit(self.path)
        if query_carries_auth_material(split.query):
            raise _Rejection(UNAUTHORIZED)
        if self._maybe_serve_ui(split.path, split.query):
            return

        capability_raw = self._single_header(CAPABILITY_HEADER)
        capability_presented = capability_raw is not None
        bearer = extract_bearer_token(self._single_header("Authorization"))
        read_only = is_read_method(self.command)
        if not origin_header_is_valid(
            self._single_header("Origin"),
            bind_host=server.bind_host,
            port=server.server_port,
            read_only=read_only,
            capability=capability_presented,
        ):
            raise _Rejection(ORIGIN_INVALID)

        if split.path == SESSION_ROUTE:
            # The one unauthenticated write: the one-time bootstrap exchange.
            self._serve_bootstrap(split.query)
            return

        session = server.session
        service = server.service
        proposals = server.proposals
        assets = server.assets
        reuse = server.reuse
        design_system = server.design_system
        components = server.components
        canvases = server.canvases
        orchestration = server.orchestration
        work = server.work
        owners = server.owners
        lifecycle = server.lifecycle
        backup = server.backup
        if (
            session is None
            or service is None
            or proposals is None
            or assets is None
            or reuse is None
            or design_system is None
            or components is None
            or canvases is None
            or orchestration is None
            or work is None
            or owners is None
            or lifecycle is None
            or backup is None
        ):
            raise _Rejection(UNAUTHORIZED)  # pragma: no cover - invariant
        if capability_presented and bearer is not None:
            # One credential per request: a browser session must not be
            # smuggled alongside a capability.
            raise _Rejection(UNAUTHORIZED)
        if capability_presented:
            principal = session.authorize_capability(
                capability_header_value(capability_raw)
            )
        else:
            principal = session.authorize_browser(bearer)

        path = split.path
        self._authorize_request_route(principal, path, split.query)
        if path == STATUS_ROUTE:
            self._require_method(read_only)
            self._serve_status(session)
            return
        if path == RESOLVE_ROUTE:
            self._require_method(read_only)
            self._serve_resolve(service, principal, split.query)
            return
        if path == PROJECTS_ROUTE:
            self._require_browser(principal)
            if read_only:
                if split.query:
                    raise _Rejection(INVALID_INPUT)
                self._serve_project_list(service)
                return
            if self.command != "POST":
                self._method_not_allowed(COLLECTION_METHODS_HEADER)
            self._serve_register(service)
            return
        if path == PROJECTS_ROUTE + "/probe":
            self._require_browser(principal)
            if self.command != "POST":
                self._method_not_allowed(WRITE_METHODS_HEADER)
            self._serve_probe(service)
            return
        if path == BACKUP_ROUTE:
            self._serve_backup(backup, principal)
            return
        if path.startswith(PROJECTS_PREFIX):
            self._serve_project_route(
                service,
                proposals,
                assets,
                reuse,
                design_system,
                components,
                canvases,
                orchestration,
                work,
                owners,
                lifecycle,
                principal,
                path,
                split.query,
            )
            return
        self._drain_body()
        raise _Rejection(ROUTE_NOT_FOUND)

    def _require_browser(self, principal: Principal) -> None:
        if not principal.is_browser:
            # A project-scoped capability never enumerates or administers
            # projects; only the maintainer's own session does.
            raise _Rejection(UNAUTHORIZED)

    def _require_method(self, read_only: bool) -> None:
        if not read_only:
            self._method_not_allowed(READ_METHODS_HEADER)

    def _method_not_allowed(self, allow: str) -> None:
        self._drain_body()
        self._send_json(
            405,
            WorkbenchError("method-not-allowed").envelope(),
            close=True,
            extra_headers={"Allow": allow},
        )
        raise _Rejection("method-not-allowed")

    def _single_header(self, name: str) -> object:
        values = self.headers.get_all(name)
        if not values:
            return None
        if len(values) > 1:
            return _DUPLICATED
        return values[0]

    def _request_size_code(self) -> str | None:
        if self.headers.get_all("Transfer-Encoding"):
            return REQUEST_TOO_LARGE
        values = self.headers.get_all("Content-Length")
        if not values:
            return None
        if len(values) > 1:
            return INVALID_INPUT
        try:
            length = int(values[0].strip())
        except ValueError:
            return INVALID_INPUT
        if length < 0:
            return INVALID_INPUT
        if length > MAX_REQUEST_BODY_BYTES:
            return REQUEST_TOO_LARGE
        return None

    def _drain_body(self) -> None:
        values = self.headers.get_all("Content-Length")
        if not values:
            return
        try:
            remaining = min(int(values[0]), MAX_REQUEST_BODY_BYTES)
        except ValueError:
            return
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                self.close_connection = True
                return
            remaining -= len(chunk)

    def _read_json_body(self) -> dict:
        """Read one bounded JSON object; malformed input is a typed rejection."""
        values = self.headers.get_all("Content-Length")
        if not values:
            raise _Rejection(INVALID_INPUT)
        try:
            remaining = int(values[0])
        except ValueError:
            raise _Rejection(INVALID_INPUT) from None
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                self.close_connection = True
                raise _Rejection(INVALID_INPUT)
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw:
            raise _Rejection(INVALID_INPUT)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _Rejection(INVALID_INPUT) from None
        if not isinstance(payload, dict):
            raise _Rejection(INVALID_INPUT)
        return payload

    # -- shared route helpers -------------------------------------------

    def _serve_bootstrap(self, query: str) -> None:
        if query:
            raise _Rejection(INVALID_INPUT)
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        payload = self._read_json_body()
        if set(payload) - {"bootstrap"}:
            raise _Rejection(INVALID_INPUT)
        receipt = self.server.session.exchange_bootstrap(payload.get("bootstrap"))
        self._send_json(200, {"schemaVersion": SCHEMA_VERSION, **receipt})

    def _serve_status(self, session: WorkbenchSession) -> None:
        self._drain_body()
        self._send_json(
            200,
            {
                "schemaVersion": SCHEMA_VERSION,
                "service": "design-playbook-workbench",
                **session.receipt(),
            },
            close=True,
        )

    def _serve_backup(self, backup: "BackupService", principal: Principal) -> None:
        """Backup, verify, and restore are maintainer-only settings actions."""
        self._require_browser(principal)
        if is_read_method(self.command):
            # GET verifies an existing archive named by ?path=.
            params = dict(parse_qsl(urlsplit(self.path).query, keep_blank_values=True))
            self._drain_body()
            if set(params) - {"path"}:
                raise _Rejection(INVALID_INPUT)
            self._send_json(
                200,
                {"schemaVersion": SCHEMA_VERSION, **backup.verify(params.get("path"))},
            )
            return
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        payload = self._read_json_body()
        action = payload.get("action")
        operation = self._operation(payload)
        if action == "create":
            self._send_mutation(
                backup.create(
                    destination=payload.get("destination"),
                    overwrite=payload.get("overwrite", False),
                    operation=operation,
                )
            )
            return
        if action == "restore":
            self._send_mutation(
                backup.restore(
                    archive_path=payload.get("path"),
                    target=payload.get("target"),
                    operation=operation,
                )
            )
            return
        raise _Rejection(ROUTE_NOT_FOUND)

    def _serve_resolve(
        self, service: WorkbenchService, principal: Principal, query: str
    ) -> None:
        """GET /api/v1/resolve: the one target both Web and slash resolve through."""
        self._drain_body()
        params = parse_qsl(query, keep_blank_values=True)
        allowed = {"project", "projectId", "request"}
        if any(name not in allowed for name, _ in params):
            raise _Rejection(INVALID_INPUT)
        seen: dict[str, str] = {}
        for name, value in params:
            if name in seen:
                raise _Rejection(INVALID_INPUT)
            seen[name] = value
        if ("project" in seen) == ("projectId" in seen):
            raise _Rejection(INVALID_TARGET)
        payload = resolve(
            service,
            project=seen.get("project"),
            project_id=seen.get("projectId"),
            request_id=seen.get("request"),
            task_lookup=self.server.task_lookup,
        )
        if not principal.is_browser:
            # A capability resolves only the project it was issued for;
            # path-based resolution must not become a scope bypass.
            if payload["project"]["projectId"] != principal.project_id:
                raise _Rejection(UNAUTHORIZED)
        self._send_json(200, {"schemaVersion": SCHEMA_VERSION, **payload})

    def _serve_project_list(self, service: WorkbenchService) -> None:
        self._drain_body()
        self._send_json(
            200, {"schemaVersion": SCHEMA_VERSION, **service.projects_overview()}
        )

    def _serve_probe(self, service: WorkbenchService) -> None:
        payload = self._read_json_body()
        exclude = payload.get("excludeProjectId")
        if exclude is not None and not isinstance(exclude, str):
            raise _Rejection(INVALID_INPUT)
        candidate = service.probe_folder(
            payload.get("path"), exclude_project_id=exclude
        )
        self._send_json(
            200, {"schemaVersion": SCHEMA_VERSION, "candidate": candidate.as_payload()}
        )

    def _serve_register(self, service: WorkbenchService) -> None:
        payload = self._read_json_body()
        operation = self._operation(payload)
        outcome = service.register_project(
            path=payload.get("path"),
            candidate_id=payload.get("candidateId"),
            name=payload.get("name"),
            operation=operation,
        )
        self._send_mutation(outcome)

    def _serve_project_route(
        self,
        service: WorkbenchService,
        proposals: ProposalService,
        assets: AssetService,
        reuse: ReuseService,
        design_system: DesignSystemService,
        components: ComponentService,
        canvases: CanvasService,
        orchestration: OrchestrationService,
        work: WorkRequestService,
        owners: OwnerProjectionService,
        lifecycle: LifecycleService,
        principal: Principal,
        path: str,
        query: str,
    ) -> None:
        segments = path[len(PROJECTS_PREFIX):].split("/")
        if len(segments) == 1 and segments[0]:
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            if query:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    "project": service.project_target(segments[0]),
                },
            )
            return
        if (
            len(segments) == 2
            and segments[0]
            and segments[1]
            in (
                "proposals",
                "assets",
                "instances",
                "canvases",
                "requests",
                "runs",
                "confirmations",
                "lifecycle",
                "deletion-impact",
            )
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            self._drain_body()
            if segments[1] == "runs":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **owners.list_runs(segments[0]),
                    },
                )
                return
            if segments[1] == "lifecycle":
                params = dict(parse_qsl(query, keep_blank_values=True))
                if set(params) - {"lifecycle"}:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **lifecycle.browse(
                            segments[0], lifecycle=params.get("lifecycle")
                        ),
                    },
                )
                return
            if segments[1] == "deletion-impact":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **lifecycle.project_deletion_impact(segments[0]),
                    },
                )
                return
            if segments[1] == "confirmations":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **owners.list_confirmations(segments[0]),
                    },
                )
                return
            if segments[1] == "requests":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **work.list_for_project(segments[0]),
                    },
                )
                return
            if segments[1] == "proposals":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **proposals.list_for_project(segments[0]),
                    },
                )
                return
            if segments[1] == "canvases":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **canvases.list_for_project(segments[0]),
                    },
                )
                return
            if segments[1] == "instances":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **reuse.list_instances(segments[0]),
                    },
                )
                return
            params = parse_qsl(query, keep_blank_values=True)
            allowed = {"query", "kind", "capability", "lifecycle"}
            if any(name not in allowed for name, _ in params):
                raise _Rejection(INVALID_INPUT)
            filters = dict(params)
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **assets.list_assets(
                        segments[0],
                        query=filters.get("query"),
                        kind=filters.get("kind"),
                        capability=filters.get("capability"),
                        lifecycle=filters.get("lifecycle"),
                    ),
                },
            )
            return
        if len(segments) == 3 and segments[0] and segments[1] == "actions":
            self._serve_action(
                service,
                proposals,
                assets,
                reuse,
                design_system,
                components,
                canvases,
                work,
                owners,
                lifecycle,
                principal,
                segments[0],
                segments[2],
            )
            return
        if (
            len(segments) == 3
            and segments[0]
            and segments[1] == "runs"
            and segments[2]
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            if query:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **owners.run(segments[0], segments[2]),
                },
            )
            return
        if (
            len(segments) == 4
            and segments[0]
            and segments[1] == "runs"
            and segments[2]
            and segments[3] == "freshness"
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            self._drain_body()
            params = dict(parse_qsl(query, keep_blank_values=True))
            if set(params) - {"objectType", "objectId", "sourceHash"}:
                raise _Rejection(INVALID_INPUT)
            payload = owners.freshness(
                segments[0],
                {
                    "runId": segments[2],
                    "objectType": params.get("objectType"),
                    "objectId": params.get("objectId"),
                    "sourceHash": params.get("sourceHash"),
                },
            )
            self._send_json(200, {"schemaVersion": SCHEMA_VERSION, **payload})
            return
        if (
            len(segments) == 3
            and segments[0]
            and segments[1] == "requests"
            and segments[2]
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            if principal.request_id is not None and principal.request_id != segments[2]:
                # A request-bound capability reads its own request only; it
                # never sees a sibling task in the same project (R11).
                raise _Rejection(UNAUTHORIZED)
            if query:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **work.detail(segments[0], segments[2], principal=principal),
                },
            )
            return
        if (
            len(segments) == 3
            and segments[0]
            and segments[1] == "proposals"
            and segments[2]
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            if query:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **proposals.detail(segments[0], segments[2]),
                },
            )
            return
        if len(segments) == 3 and segments[0] and segments[1] == "assets" and segments[2]:
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            if query:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **assets.asset_detail(segments[0], segments[2]),
                },
            )
            return
        if (
            len(segments) == 3
            and segments[0]
            and segments[1] == "canvases"
            and segments[2]
        ):
            self._serve_canvas_read(
                canvases,
                orchestration,
                principal,
                segments[0],
                segments[2],
                "detail",
                None,
                query,
            )
            return
        if (
            len(segments) == 4
            and segments[0]
            and segments[1] == "canvases"
            and segments[2]
            and segments[3] in ("snapshot", "snapshots", "contexts")
        ):
            self._serve_canvas_read(
                canvases,
                orchestration,
                principal,
                segments[0],
                segments[2],
                segments[3],
                None,
                query,
            )
            return
        if (
            len(segments) == 5
            and segments[0]
            and segments[1] == "canvases"
            and segments[2]
            and segments[3] in ("snapshots", "contexts")
            and segments[4]
        ):
            self._serve_canvas_read(
                canvases,
                orchestration,
                principal,
                segments[0],
                segments[2],
                segments[3],
                segments[4],
                query,
            )
            return
        if (
            len(segments) == 4
            and segments[0]
            and segments[1] == "assets"
            and segments[2]
            and segments[3]
            in ("preview", "history", "upgrade-plan", "reuse-plan", "references")
        ):
            self._require_method(is_read_method(self.command))
            self._authorize_project(principal, segments[0], "read")
            self._drain_body()
            project_id, asset_id, view = segments[0], segments[2], segments[3]
            if view == "preview":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **assets.preview_descriptor(
                            project_id,
                            asset_id,
                            preview_origin=self.server.preview_origin,
                        ),
                    },
                )
                return
            if view == "references":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **lifecycle.reference_report(project_id, asset_id),
                    },
                )
                return
            if view == "history":
                if query:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **reuse.asset_history(project_id, asset_id),
                    },
                )
                return
            params = dict(parse_qsl(query, keep_blank_values=True))
            if view == "upgrade-plan":
                if set(params) - {"toRevisionId"}:
                    raise _Rejection(INVALID_INPUT)
                self._send_json(
                    200,
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        **reuse.upgrade_plan(
                            project_id,
                            asset_id,
                            to_revision_id=params.get("toRevisionId"),
                        ),
                    },
                )
                return
            if set(params) - {"targetProjectId", "mode", "revisionId"}:
                raise _Rejection(INVALID_INPUT)
            target_project_id = params.get("targetProjectId")
            if not target_project_id:
                raise _Rejection(INVALID_INPUT)
            self._send_json(
                200,
                {
                    "schemaVersion": SCHEMA_VERSION,
                    **reuse.reuse_plan(
                        project_id,
                        source_asset_id=asset_id,
                        source_revision_id=params.get("revisionId"),
                        mode=params.get("mode") or "copy",
                        target_project_id=target_project_id,
                    ),
                },
            )
            return
        if (
            len(segments) == 5
            and segments[0]
            and segments[1] == "assets"
            and segments[2]
            and segments[3] == "tokens"
            and segments[4] in ("document", "validation", "preview", "diff", "affected")
        ):
            self._serve_token_view(
                design_system, principal, segments[0], segments[2], segments[4], query
            )
            return
        if (
            len(segments) == 5
            and segments[0]
            and segments[1] == "assets"
            and segments[2]
            and segments[3] == "document"
            and segments[4] in ("component", "page", "instance")
        ):
            self._serve_document_view(
                components, principal, segments[0], segments[2], segments[4], query
            )
            return
        if (
            len(segments) == 5
            and segments[0]
            and segments[1] == "actions"
            and segments[2] in ("proposals", "assets", "canvases", "requests")
            and segments[3]
            and segments[4]
        ):
            project_id, entity_id, verb = segments[0], segments[3], segments[4]
            if segments[2] == "requests":
                self._serve_request_verb(
                    work, principal, project_id, entity_id, verb
                )
                return
            if segments[2] == "canvases":
                self._serve_canvas_verb(
                    canvases,
                    orchestration,
                    principal,
                    project_id,
                    entity_id,
                    verb,
                )
                return
            if segments[2] == "proposals":
                self._serve_proposal_verb(
                    proposals, principal, project_id, entity_id, verb
                )
                return
            self._serve_asset_verb(
                service,
                assets,
                reuse,
                design_system,
                components,
                work,
                owners,
                lifecycle,
                principal,
                project_id,
                entity_id,
                verb,
            )
            return
        self._drain_body()
        raise _Rejection(ROUTE_NOT_FOUND)

    def _serve_token_view(
        self,
        design_system: DesignSystemService,
        principal: Principal,
        project_id: str,
        asset_id: str,
        view: str,
        query: str,
    ) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, project_id, "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if view == "document":
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = design_system.document(project_id, asset_id)
        elif view == "validation":
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = design_system.validate(project_id, asset_id)
        elif view == "preview":
            if set(params) - {"theme"}:
                raise _Rejection(INVALID_INPUT)
            payload = design_system.preview(
                project_id, asset_id, theme=params.get("theme")
            )
            payload["previewOrigin"] = self.server.preview_origin
            payload["previewUrl"] = self.server.preview_origin + payload.pop(
                "previewPath"
            )
        elif view == "diff":
            if set(params) - {"fromRevisionId", "toRevisionId"}:
                raise _Rejection(INVALID_INPUT)
            payload = design_system.diff(
                project_id,
                asset_id,
                from_revision=params.get("fromRevisionId"),
                to_revision=params.get("toRevisionId"),
            )
        else:
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = design_system.affected(project_id, asset_id)
        self._send_json(200, {"schemaVersion": SCHEMA_VERSION, **payload})

    def _attach_preview_urls(self, payload: dict) -> dict:
        """Give frozen snapshots a ready preview URL on the preview origin."""
        origin = self.server.preview_origin

        def fix(row: object) -> None:
            if isinstance(row, dict) and isinstance(row.get("previewPath"), str):
                row["previewUrl"] = origin + row.pop("previewPath")

        for key in ("snapshot", "left", "right"):
            fix(payload.get(key))
        for row in payload.get("snapshots") or []:
            fix(row)
        return payload

    def _serve_request_verb(
        self,
        work: WorkRequestService,
        principal: Principal,
        project_id: str,
        request_id: str,
        verb: str,
    ) -> None:
        maintainer_verbs = {"consent", "cancel", "confirm-cancelled", "retry", "reject"}
        agent_verbs = {"claim", "heartbeat", "result", "fail"}
        if verb not in maintainer_verbs | agent_verbs:
            self._drain_body()
            raise _Rejection(ROUTE_NOT_FOUND)
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        payload = self._read_json_body()
        operation = self._operation(payload)
        if verb in maintainer_verbs:
            # Sending scope, stopping, retrying and rejecting are the
            # maintainer's decisions; an Agent credential never holds them.
            self._require_browser(principal)
            self._authorize_project(principal, project_id, "write")
            if verb == "consent":
                self._send_mutation(
                    work.consent(
                        project_id,
                        request_id,
                        digest=payload.get("digest"),
                        ttl_seconds=payload.get("ttlSeconds"),
                        operation=operation,
                    )
                )
                return
            if verb == "cancel":
                self._send_mutation(
                    work.cancel(project_id, request_id, operation=operation)
                )
                return
            if verb == "confirm-cancelled":
                self._send_mutation(
                    work.confirm_cancelled(project_id, request_id, operation=operation)
                )
                return
            if verb == "retry":
                self._send_mutation(
                    work.retry(project_id, request_id, operation=operation)
                )
                return
            self._send_mutation(
                work.reject(project_id, request_id, operation=operation)
            )
            return
        # Agent traffic is authenticated by the request-bound capability.
        if verb == "claim":
            self._send_mutation(
                work.claim(
                    request_id,
                    principal=principal,
                    lease_seconds=payload.get("leaseSeconds"),
                    operation=operation,
                )
            )
            return
        if verb == "heartbeat":
            self._send_mutation(
                work.heartbeat(
                    request_id,
                    attempt_id=payload.get("attemptId"),
                    lease_id=payload.get("leaseId"),
                    sequence=payload.get("sequence"),
                    progress=payload.get("progress"),
                    principal=principal,
                    operation=operation,
                )
            )
            return
        if verb == "result":
            self._send_mutation(
                work.submit_result(
                    request_id,
                    attempt_id=payload.get("attemptId"),
                    lease_id=payload.get("leaseId"),
                    sequence=payload.get("sequence"),
                    result=payload.get("result"),
                    principal=principal,
                    operation=operation,
                )
            )
            return
        self._send_mutation(
            work.fail_attempt(
                request_id,
                attempt_id=payload.get("attemptId"),
                lease_id=payload.get("leaseId"),
                sequence=payload.get("sequence"),
                reason=payload.get("reason"),
                principal=principal,
                operation=operation,
            )
        )

    def _serve_canvas_read(
        self,
        canvases: CanvasService,
        orchestration: OrchestrationService,
        principal: Principal,
        project_id: str,
        canvas_id: str,
        suffix: str,
        entity_id: str | None,
        query: str,
    ) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, project_id, "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if suffix == "snapshots" and entity_id is None:
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = orchestration.list_snapshots(project_id, canvas_id)
        elif suffix == "snapshots":
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = orchestration.snapshot(project_id, canvas_id, entity_id)
        elif suffix == "contexts" and entity_id is None:
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = orchestration.list_contexts(project_id, canvas_id)
        elif suffix == "contexts":
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = orchestration.context(project_id, entity_id)
        elif suffix == "snapshot":
            if set(params) - {"boardId"}:
                raise _Rejection(INVALID_INPUT)
            payload = canvases.snapshot(
                project_id, canvas_id, board_id=params.get("boardId")
            )
            payload["previewOrigin"] = self.server.preview_origin
            payload["previewUrl"] = self.server.preview_origin + payload.pop(
                "previewPath"
            )
        else:
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = canvases.detail(project_id, canvas_id)
        self._send_json(
            200,
            {
                "schemaVersion": SCHEMA_VERSION,
                **self._attach_preview_urls(payload),
            },
        )

    def _serve_canvas_verb(
        self,
        canvases: CanvasService,
        orchestration: OrchestrationService,
        principal: Principal,
        project_id: str,
        canvas_id: str,
        verb: str,
    ) -> None:
        allowed = {
            "commands",
            "undo",
            "redo",
            "rename",
            "fork",
            "snapshots",
            "compare",
            "contexts",
            "confirm",
        }
        if verb not in allowed:
            self._drain_body()
            raise _Rejection(ROUTE_NOT_FOUND)
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        # The personal canvas and its orchestration are the maintainer's
        # workspace; an Agent never drives it, including the context
        # `confirm` that is the maintainer's send-scope decision (R09/R10).
        self._require_browser(principal)
        self._authorize_project(principal, project_id, "write")
        payload = self._read_json_body()
        operation = self._operation(payload)
        if verb == "commands":
            self._send_mutation(
                canvases.run_commands(
                    project_id,
                    canvas_id,
                    commands=payload.get("commands"),
                    operation=operation,
                )
            )
            return
        if verb == "undo":
            self._send_mutation(
                canvases.undo(project_id, canvas_id, operation=operation)
            )
            return
        if verb == "redo":
            self._send_mutation(
                canvases.redo(project_id, canvas_id, operation=operation)
            )
            return
        if verb == "rename":
            self._send_mutation(
                canvases.rename(
                    project_id, canvas_id, name=payload.get("name"), operation=operation
                )
            )
            return
        if verb == "snapshots":
            self._send_mutation(
                orchestration.create_snapshot(
                    project_id,
                    canvas_id,
                    board_id=payload.get("boardId"),
                    note=payload.get("note"),
                    operation=operation,
                )
            )
            return
        if verb == "compare":
            outcome = orchestration.compare(
                project_id,
                canvas_id,
                left=payload.get("left"),
                right=payload.get("right"),
                operation=operation,
            )
            outcome["result"] = self._attach_preview_urls(outcome["result"])
            self._send_mutation(outcome)
            return
        if verb == "contexts":
            self._send_mutation(
                orchestration.build_context(
                    project_id,
                    canvas_id,
                    selection_id=payload.get("selectionId"),
                    board_id=payload.get("boardId"),
                    node_ids=payload.get("nodeIds"),
                    revision_ids=payload.get("revisionIds"),
                    file_paths=payload.get("filePaths"),
                    operation=operation,
                )
            )
            return
        if verb == "confirm":
            selection_id = payload.get("selectionId")
            if not isinstance(selection_id, str) or not selection_id:
                raise _Rejection(INVALID_INPUT)
            self._send_mutation(
                orchestration.confirm_context(
                    project_id,
                    canvas_id,
                    selection_id,
                    digest=payload.get("digest"),
                    operation=operation,
                )
            )
            return
        self._send_mutation(
            canvases.fork(
                project_id,
                canvas_id,
                name=payload.get("name"),
                document=payload.get("document"),
                operation=operation,
            )
        )

    def _serve_document_view(
        self,
        components: ComponentService,
        principal: Principal,
        project_id: str,
        asset_id: str,
        view: str,
        query: str,
    ) -> None:
        """Read a workbench-owned component definition or page layout."""
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, project_id, "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if view in ("component", "page"):
            if params:
                raise _Rejection(INVALID_INPUT)
            payload = (
                components.component(project_id, asset_id)
                if view == "component"
                else components.page_layout(project_id, asset_id)
            )
        else:
            if set(params) - {"params"}:
                raise _Rejection(INVALID_INPUT)
            raw = params.get("params")
            instance_params: object = None
            if raw not in (None, ""):
                try:
                    instance_params = json.loads(raw)
                except json.JSONDecodeError:
                    raise _Rejection(INVALID_INPUT) from None
            payload = components.instance_preview(
                project_id, asset_id, params=instance_params
            )
            payload["previewOrigin"] = self.server.preview_origin
            payload["previewUrl"] = self.server.preview_origin + payload.pop(
                "previewUrl"
            )
        self._send_json(200, {"schemaVersion": SCHEMA_VERSION, **payload})

    def _serve_proposal_verb(
        self,
        proposals: ProposalService,
        principal: Principal,
        project_id: str,
        proposal_id: str,
        verb: str,
    ) -> None:
        if verb not in _MAINTAINER_ONLY_PROPOSAL_ACTIONS:
            self._drain_body()
            raise _Rejection(ROUTE_NOT_FOUND)
        # Approving, recovering, reverting, and rejecting a source write are
        # the maintainer's decisions: a capability is refused even though it
        # might hold the write scope.
        self._require_browser(principal)
        self._authorize_project(principal, project_id, "write")
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        payload = self._read_json_body()
        operation = self._operation(payload)
        if verb == "apply":
            self._send_mutation(
                proposals.apply(
                    project_id,
                    proposal_id,
                    digest=payload.get("digest"),
                    operation=operation,
                )
            )
            return
        if verb == "recover":
            self._send_mutation(
                proposals.recover(
                    project_id,
                    proposal_id,
                    mode=payload.get("mode"),
                    operation=operation,
                )
            )
            return
        if verb == "revert":
            self._send_mutation(
                proposals.revert(project_id, proposal_id, operation=operation)
            )
            return
        self._send_mutation(
            proposals.reject(project_id, proposal_id, operation=operation)
        )

    def _serve_asset_verb(
        self,
        service: WorkbenchService,
        assets: AssetService,
        reuse: ReuseService,
        design_system: DesignSystemService,
        components: ComponentService,
        work: WorkRequestService,
        owners: OwnerProjectionService,
        lifecycle: LifecycleService,
        principal: Principal,
        project_id: str,
        asset_id: str,
        verb: str,
    ) -> None:
        allowed = {
            "publish",
            "preview-enable",
            "refresh-draft",
            "publish-with-deps",
            "derive",
            "copy",
            "reference",
            "import-closure",
            "upgrade",
            "rollback",
            "tokens-update",
            "tokens-publish",
            "propose-baseline",
            "component-update",
            "component-publish",
            "page-update",
            "page-publish",
            "distill-candidate",
            "publish-verified",
            "archive",
            "unarchive",
            "trash",
            "restore",
            "hard-delete",
        }
        if verb not in allowed:
            self._drain_body()
            raise _Rejection(ROUTE_NOT_FOUND)
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        # Every asset verb here is a maintainer-only mutation (publish /
        # derive / copy / upgrade / rollback / tokens / component / page /
        # lifecycle). An Agent's only write path is proposal submission
        # (R11); it never reaches these routes even holding project write
        # scope. Project write scope alone must not separate maintainer
        # from Agent, so gate the whole verb set on the browser session.
        self._require_browser(principal)
        self._authorize_project(principal, project_id, "write")
        payload = self._read_json_body()
        operation = self._operation(payload)
        if verb == "publish":
            self._send_mutation(
                assets.publish_revision(project_id, asset_id, operation=operation)
            )
            return
        if verb == "preview-enable":
            self._send_mutation(
                assets.enable_dynamic_preview(
                    project_id, asset_id, operation=operation
                )
            )
            return
        if verb == "refresh-draft":
            self._send_mutation(
                assets.refresh_draft(project_id, asset_id, operation=operation)
            )
            return
        if verb == "tokens-update":
            self._send_mutation(
                design_system.update_tokens(
                    project_id,
                    asset_id,
                    document=payload.get("document"),
                    operation=operation,
                )
            )
            return
        if verb == "tokens-publish":
            self._send_mutation(
                design_system.publish(project_id, asset_id, operation=operation)
            )
            return
        if verb == "propose-baseline":
            self._send_mutation(
                design_system.propose_baseline(
                    project_id,
                    asset_id,
                    path=payload.get("path"),
                    operation=operation,
                )
            )
            return
        if verb in ("archive", "unarchive", "trash", "restore", "hard-delete"):
            if verb == "archive":
                self._send_mutation(
                    lifecycle.archive(project_id, asset_id, operation=operation)
                )
                return
            if verb == "unarchive":
                self._send_mutation(
                    lifecycle.unarchive(project_id, asset_id, operation=operation)
                )
                return
            if verb == "trash":
                self._send_mutation(
                    lifecycle.trash(project_id, asset_id, operation=operation)
                )
                return
            if verb == "restore":
                self._send_mutation(
                    lifecycle.restore(
                        project_id, asset_id, name=payload.get("name"),
                        operation=operation,
                    )
                )
                return
            self._send_mutation(
                lifecycle.hard_delete(
                    project_id, asset_id, confirm=payload.get("confirm"),
                    operation=operation,
                )
            )
            return
        if verb == "publish-verified":
            self._send_mutation(
                owners.publish_verified(
                    project_id,
                    asset_id,
                    run_id=payload.get("runId"),
                    object_id=payload.get("objectId"),
                    role=payload.get("role") or "owner-verified",
                    operation=operation,
                )
            )
            return
        if verb == "component-update":
            self._send_mutation(
                components.update_definition(
                    project_id,
                    asset_id,
                    definition=payload.get("definition"),
                    operation=operation,
                )
            )
            return
        if verb == "component-publish":
            self._send_mutation(
                components.publish(project_id, asset_id, operation=operation)
            )
            return
        if verb == "page-update":
            self._send_mutation(
                components.update_layout(
                    project_id,
                    asset_id,
                    layout=payload.get("layout"),
                    operation=operation,
                )
            )
            return
        if verb == "page-publish":
            self._send_mutation(
                components.publish_page(project_id, asset_id, operation=operation)
            )
            return
        if verb == "distill-candidate":
            source_page_id = payload.get("sourcePageAssetId")
            if not isinstance(source_page_id, str) or not source_page_id:
                raise _Rejection(INVALID_INPUT)
            self._send_mutation(
                components.distill_candidate(
                    project_id,
                    source_page_id,
                    node_ids=payload.get("nodeIds"),
                    name=payload.get("name"),
                    operation=operation,
                )
            )
            return
        if verb == "publish-with-deps":
            self._send_mutation(
                reuse.publish_with_dependencies(
                    project_id,
                    asset_id,
                    dependencies=payload.get("dependencies"),
                    operation=operation,
                )
            )
            return
        if verb in ("derive", "copy", "reference"):
            self._send_mutation(
                reuse.derive_or_copy(
                    project_id,
                    asset_id,
                    mode=verb,
                    name=payload.get("name"),
                    operation=operation,
                )
            )
            return
        if verb == "import-closure":
            source_asset_id = payload.get("sourceAssetId") or asset_id
            source_revision_id = payload.get("sourceRevisionId")
            target_project_id = payload.get("targetProjectId")
            mode = payload.get("mode")
            if not isinstance(target_project_id, str) or not target_project_id:
                raise _Rejection(INVALID_INPUT)
            # The source must be readable *and* the target writable: a
            # closure import touches two projects.
            self._authorize_project(principal, target_project_id, "write")
            self._send_mutation(
                reuse.import_closure(
                    project_id,
                    source_asset_id=source_asset_id,
                    source_revision_id=source_revision_id,
                    mode=mode or "copy",
                    target_project_id=target_project_id,
                    operation=operation,
                )
            )
            return
        if verb == "upgrade":
            self._send_mutation(
                reuse.upgrade_instances(
                    project_id,
                    asset_id,
                    instance_ids=payload.get("instanceIds"),
                    to_revision_id=payload.get("toRevisionId"),
                    operation=operation,
                )
            )
            return
        self._send_mutation(
            reuse.rollback_instances(
                project_id,
                asset_id,
                instance_ids=payload.get("instanceIds"),
                to_revision_id=payload.get("toRevisionId"),
                operation=operation,
            )
        )

    def _serve_action(
        self,
        service: WorkbenchService,
        proposals: ProposalService,
        assets: AssetService,
        reuse: ReuseService,
        design_system: DesignSystemService,
        components: ComponentService,
        canvases: CanvasService,
        work: WorkRequestService,
        owners: OwnerProjectionService,
        lifecycle: LifecycleService,
        principal: Principal,
        project_id: str,
        action: str,
    ) -> None:
        if action == "proposals":
            # The one Agent write path (R11): submit a proposal for the
            # maintainer to approve. Approval/apply stays maintainer-only.
            if principal.request_id is not None:
                # A request-bound capability reports through its task's
                # result path, which enforces the lease and honours cancel;
                # a direct proposal write would bypass that authority.
                raise _Rejection(UNAUTHORIZED)
            self._authorize_project(principal, project_id, "write")
        elif action in _BROWSER_ONLY_ACTIONS:
            # Only the maintainer's own session administers a project.
            self._require_browser(principal)
            self._authorize_project(principal, project_id, "write")
        elif action in (
            "instances",
            "components",
            "pages",
            "canvases",
            "requests",
            "imports",
            "confirmations",
            "backflow",
            "project-archive",
            "project-unarchive",
        ):
            # Authoring, import curation, work-request handoff, owner
            # confirmation/backflow and project archival are maintainer-only
            # mutations. An Agent capability with project write scope must
            # not reach them; only proposal submission is Agent-permitted.
            self._require_browser(principal)
            self._authorize_project(principal, project_id, "write")
        if self.command != "POST":
            self._method_not_allowed(WRITE_METHODS_HEADER)
        payload = self._read_json_body()
        operation = self._operation(payload)
        if action == "open":
            self._authorize_project(principal, project_id, "read")
            self._send_mutation(service.open_project(project_id, operation=operation))
            return
        if action == "rename":
            self._send_mutation(
                service.rename_project(
                    project_id, name=payload.get("name"), operation=operation
                )
            )
            return
        if action == "rebind":
            self._send_mutation(
                service.rebind_project(
                    project_id,
                    path=payload.get("path"),
                    candidate_id=payload.get("candidateId"),
                    operation=operation,
                )
            )
            return
        if action == "grants":
            self._send_mutation(
                service.set_grants(
                    project_id, scopes=payload.get("scopes"), operation=operation
                )
            )
            return
        if action == "remove":
            self._send_mutation(service.remove_project(project_id, operation=operation))
            return
        if action == "instances":
            self._send_mutation(
                reuse.create_instance(
                    project_id,
                    payload.get("assetId"),
                    revision_id=payload.get("revisionId"),
                    overrides=payload.get("overrides"),
                    operation=operation,
                )
            )
            return
        if action == "proposals":
            # An Agent holding a write capability may submit a proposal;
            # approval stays with the maintainer (handled above).
            self._send_mutation(
                proposals.create(
                    project_id,
                    changes=payload.get("changes"),
                    summary=payload.get("summary"),
                    dependency_changes=payload.get("dependencyChanges"),
                    operation=operation,
                )
            )
            return
        if action == "components":
            self._send_mutation(
                components.create_component(
                    project_id,
                    name=payload.get("name"),
                    definition=payload.get("definition"),
                    operation=operation,
                )
            )
            return
        if action in ("project-archive", "project-unarchive"):
            self._require_browser(principal)
            self._send_mutation(
                lifecycle.archive_project(
                    project_id,
                    archived=action == "project-archive",
                    operation=operation,
                )
            )
            return
        if action == "confirmations":
            self._require_browser(principal)
            self._send_mutation(
                owners.confirm(
                    project_id,
                    run_id=payload.get("runId"),
                    object_type=payload.get("objectType"),
                    object_id=payload.get("objectId"),
                    source_hash=payload.get("sourceHash"),
                    role=payload.get("role"),
                    note=payload.get("note"),
                    operation=operation,
                )
            )
            return
        if action == "backflow":
            self._require_browser(principal)
            self._send_mutation(
                owners.backflow_candidate(
                    project_id,
                    run_id=payload.get("runId"),
                    object_type=payload.get("objectType") or "criterion",
                    object_id=payload.get("objectId"),
                    name=payload.get("name"),
                    operation=operation,
                )
            )
            return
        if action == "requests":
            self._send_mutation(
                work.create(
                    project_id,
                    title=payload.get("title"),
                    goal=payload.get("goal"),
                    target_stack=payload.get("targetStack"),
                    plan=payload.get("plan"),
                    allowed_actions=payload.get("allowedActions"),
                    result_schema=payload.get("resultSchema"),
                    context_selection_id=payload.get("contextSelectionId"),
                    expires_in_seconds=payload.get("expiresInSeconds"),
                    operation=operation,
                )
            )
            return
        if action == "canvases":
            self._send_mutation(
                canvases.create(
                    project_id,
                    name=payload.get("name"),
                    document=payload.get("document"),
                    operation=operation,
                )
            )
            return
        if action == "pages":
            self._send_mutation(
                components.create_page(
                    project_id,
                    name=payload.get("name"),
                    layout=payload.get("layout"),
                    operation=operation,
                )
            )
            return
        if action == "imports":
            self._send_mutation(
                assets.import_selection(
                    project_id,
                    selections=payload.get("selections"),
                    operation=operation,
                )
            )
            return
        raise _Rejection(ROUTE_NOT_FOUND)

    def _operation(self, payload: dict) -> Operation:
        operation = validate_operation(payload.get("operation"))
        # Bind replay to the actual route and confirmed body, not a caller's
        # digest claim. The envelope (operationId plus the advisory
        # expectedCounter, which a retry may omit) is excluded: it varies
        # across an otherwise identical retry and would defeat idempotency.
        body = {key: value for key, value in payload.items() if key != "operation"}
        return Operation(
            operation_id=operation.operation_id,
            payload={"route": urlsplit(self.path).path, "body": body},
            expected_counter=operation.expected_counter,
        )

    def _authorize_request_route(self, principal: Principal, path: str, query: str) -> None:
        if principal.request_id is None:
            return
        project = f"{PROJECTS_PREFIX}{principal.project_id}"
        read_path = f"{project}/requests/{principal.request_id}"
        action_path = f"{project}/actions/requests/{principal.request_id}"
        if path == RESOLVE_ROUTE and is_read_method(self.command):
            if dict(parse_qsl(query)).get("request") == principal.request_id:
                return
        if path == read_path and is_read_method(self.command):
            return
        if self.command == "POST" and path in {
            f"{action_path}/{verb}" for verb in ("claim", "heartbeat", "result", "fail")
        }:
            return
        raise _Rejection(UNAUTHORIZED)

    def _authorize_project(
        self, principal: Principal, project_id: str, *scopes: str
    ) -> None:
        """A capability must hold every scope the operation will touch."""
        if principal.is_browser:
            return
        required = scopes or ("read",)
        for scope in required:
            if not principal.permits_project(project_id, scope):
                raise _Rejection(UNAUTHORIZED)

    def _send_mutation(self, outcome: dict) -> None:
        self._send_json(
            200,
            {
                "schemaVersion": SCHEMA_VERSION,
                "result": outcome["result"],
                "counter": outcome["counter"],
                "replayed": outcome["replayed"],
            },
        )

    # -- static shell ----------------------------------------------------

    def _maybe_serve_ui(self, path: str, query: str) -> bool:
        if self.headers.get_all("Authorization") or self.headers.get_all(
            CAPABILITY_HEADER
        ):
            return False
        resource = self.server.ui.lookup(path)
        if resource is None:
            return False
        if self.command not in ("GET", "HEAD"):
            self._method_not_allowed(READ_METHODS_HEADER)
        if query:
            raise _Rejection(INVALID_INPUT)
        self._send_static(resource)
        return True

    def _send_static(self, resource) -> None:
        headers = security_headers()
        headers["Content-Security-Policy"] = resource.content_security_policy
        self.send_response(200)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Type", resource.content_type)
        self.send_header("Content-Length", str(len(resource.body)))
        self.end_headers()
        self._responded = True
        if self.command != "HEAD":
            self.wfile.write(resource.body)

    # -- responses --------------------------------------------------------

    def _send_error(self, code: str, *, detail: str | None = None) -> None:
        error = WorkbenchError(code, detail=detail)
        self._send_json(error.status, error.envelope(), close=True)

    def _send_json(
        self, status: int, payload: object, *, close: bool = False, extra_headers=None
    ) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        self.send_response(status)
        for name, value in security_headers().items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        if close:
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        self._responded = True
        if self.command != "HEAD":
            self.wfile.write(body)


class WorkbenchHTTPServer(http.server.ThreadingHTTPServer):
    """One IP-literal loopback listener serving one workbench session."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        *,
        bind_host: str = DEFAULT_BIND_HOST,
        port: int = 0,
        ui_directory=None,
    ) -> None:
        host = ensure_loopback_bind_host(bind_host)
        if host == "::1":
            self.address_family = socket.AF_INET6
        self.session: WorkbenchSession | None = None
        self.service: WorkbenchService | None = None
        self.proposals: ProposalService | None = None
        self.assets: AssetService | None = None
        self.reuse: ReuseService | None = None
        self.design_system: DesignSystemService | None = None
        self.components: ComponentService | None = None
        self.canvases: CanvasService | None = None
        self.orchestration: OrchestrationService | None = None
        self.work: WorkRequestService | None = None
        self.owners: OwnerProjectionService | None = None
        self.lifecycle: LifecycleService | None = None
        self.backup: BackupService | None = None
        self.preview_origin = ""
        self.task_lookup = None
        super().__init__((host, port), WorkbenchRequestHandler)
        self.bind_host = host
        self.ui = UIResources(ui_directory)
        bound_host, bound_port = self.socket.getsockname()[:2]
        if bound_host != host:
            self.server_close()
            raise OSError("socket did not bind to the requested loopback literal")
        self.authority = canonical_authority(host, bound_port)
        self.origin = canonical_origin(host, bound_port)
        self._serve_thread: threading.Thread | None = None
        self._stopped = False

    def server_bind(self) -> None:
        # Bind without socket.getfqdn: no reverse DNS and no hostname.
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = host
        self.server_port = port

    @property
    def port(self) -> int:
        return self.socket.getsockname()[1]

    def attach(
        self,
        *,
        session: WorkbenchSession,
        service: WorkbenchService,
        proposals: ProposalService,
        assets: AssetService,
        reuse: ReuseService,
        design_system: DesignSystemService,
        components: ComponentService,
        canvases: CanvasService,
        orchestration: OrchestrationService,
        work: WorkRequestService,
        owners: OwnerProjectionService,
        lifecycle: LifecycleService,
        backup: BackupService,
        preview_origin: str,
    ) -> "WorkbenchHTTPServer":
        if session.authority != self.origin:
            raise ValueError("session authority must equal the bound origin")
        self.session = session
        self.service = service
        self.proposals = proposals
        self.assets = assets
        self.reuse = reuse
        self.design_system = design_system
        self.components = components
        self.canvases = canvases
        self.orchestration = orchestration
        self.work = work
        self.owners = owners
        self.lifecycle = lifecycle
        self.backup = backup
        self.preview_origin = preview_origin
        # Called once, before the first request: the served shell bytes stay
        # frozen for the whole session lifetime.
        self.ui.set_preview_origin(preview_origin)
        return self

    def start_serving(self, poll_interval: float = 0.05) -> "WorkbenchHTTPServer":
        if self._serve_thread is not None and self._serve_thread.is_alive():
            return self
        self._serve_thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"poll_interval": poll_interval},
            daemon=True,
            name="workbench-server",
        )
        self._serve_thread.start()
        return self

    def stop(self) -> None:
        """Stop serving, close the listener, and invalidate the session."""
        if self._stopped:
            return
        self._stopped = True
        thread = self._serve_thread
        if (
            thread is not None
            and thread is not threading.current_thread()
            and thread.is_alive()
        ):
            try:
                self.shutdown()
            except Exception:
                pass
        try:
            self.server_close()
        except Exception:
            pass
        finally:
            if self.session is not None:
                self.session.close()
