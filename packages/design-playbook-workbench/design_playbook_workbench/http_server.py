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
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, urlsplit

from .assets import AssetService
from .canvas import CanvasService
from .orchestration import OrchestrationService
from .backup import BackupService
from .lifecycle import LifecycleService
from .listener import LoopbackHTTPServer, finish_gracefully
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
    READ_METHODS,
    capability_header_value,
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
    {"open", "rename", "rebind", "grants", "remove", "delete-data"}
)

#: Proposal transitions that are a maintainer authorization decision. An
#: Agent capability may submit a proposal, never approve one.
_MAINTAINER_ONLY_PROPOSAL_ACTIONS = frozenset(
    {"apply", "recover", "revert", "reject"}
)

#: Project actions that author or administer. An Agent capability with
#: project write scope must not reach them; only proposal submission is
#: Agent-permitted.
_MAINTAINER_ONLY_ACTIONS = frozenset(
    {
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
        "notes-propose",
    }
)


@dataclass(frozen=True)
class _FixedRoute:
    """One exact path and the methods it accepts.

    ``allow`` is the header this path has always sent when the method is
    refused. ``browser`` runs the maintainer-session check before the method
    check, which is the order these routes have always had.
    """

    path: str
    methods: frozenset[str]
    allow: str
    handler: str
    browser: bool = False


_FIXED_ROUTES = (
    _FixedRoute(STATUS_ROUTE, READ_METHODS, READ_METHODS_HEADER, "status"),
    _FixedRoute(RESOLVE_ROUTE, READ_METHODS, READ_METHODS_HEADER, "resolve"),
    _FixedRoute(
        PROJECTS_ROUTE,
        READ_METHODS,
        COLLECTION_METHODS_HEADER,
        "project-list",
        browser=True,
    ),
    _FixedRoute(
        PROJECTS_ROUTE,
        frozenset({"POST"}),
        COLLECTION_METHODS_HEADER,
        "register",
        browser=True,
    ),
    _FixedRoute(
        PROJECTS_ROUTE + "/probe",
        frozenset({"POST"}),
        WRITE_METHODS_HEADER,
        "probe",
        browser=True,
    ),
    _FixedRoute(
        BACKUP_ROUTE,
        READ_METHODS | {"POST"},
        WRITE_METHODS_HEADER,
        "backup",
        browser=True,
    ),
)


#: A quoted id anywhere in a project path: matched, never captured.
_ANY = object()
#: The one segment the previous router let through empty (``.../actions/``).
_ANY_OR_EMPTY = object()

_TOKEN_VIEWS = frozenset({"document", "validation", "preview", "diff", "affected"})
_DOCUMENT_VIEWS = frozenset({"component", "page", "instance"})


def _matches(parts: tuple[object, ...], segments: list[str]) -> bool:
    if len(parts) != len(segments):
        return False
    for part, segment in zip(parts, segments):
        if part is _ANY_OR_EMPTY:
            continue
        if not segment:
            return False
        if isinstance(part, str):
            if segment != part:
                return False
        elif isinstance(part, frozenset) and segment not in part:
            return False
    return True


_PROJECT_ROUTES = (
    ((_ANY,), "_route_project_detail"),
    ((_ANY, "proposals"), "_route_proposals_list"),
    ((_ANY, "assets"), "_route_assets_list"),
    ((_ANY, "instances"), "_route_instances_list"),
    ((_ANY, "canvases"), "_route_canvases_list"),
    ((_ANY, "requests"), "_route_requests_list"),
    ((_ANY, "runs"), "_route_runs_list"),
    ((_ANY, "confirmations"), "_route_confirmations_list"),
    ((_ANY, "lifecycle"), "_route_lifecycle_list"),
    ((_ANY, "archive-overview"), "_route_archive_overview"),
    ((_ANY, "deletion-impact"), "_route_deletion_impact"),
    ((_ANY, "actions", _ANY_OR_EMPTY), "_route_action"),
    ((_ANY, "runs", _ANY), "_route_run"),
    ((_ANY, "runs", _ANY, "freshness"), "_route_run_freshness"),
    ((_ANY, "requests", _ANY), "_route_request_detail"),
    ((_ANY, "proposals", _ANY), "_route_proposal_detail"),
    ((_ANY, "assets", _ANY), "_route_asset_detail"),
    ((_ANY, "canvases", _ANY), "_route_canvas_detail"),
    ((_ANY, "canvases", _ANY, "snapshot"), "_route_canvas_snapshot"),
    ((_ANY, "canvases", _ANY, "snapshots"), "_route_snapshots"),
    ((_ANY, "canvases", _ANY, "contexts"), "_route_contexts"),
    ((_ANY, "canvases", _ANY, "snapshots", _ANY), "_route_snapshot"),
    ((_ANY, "canvases", _ANY, "contexts", _ANY), "_route_context"),
    ((_ANY, "assets", _ANY, "preview"), "_route_asset_preview"),
    ((_ANY, "assets", _ANY, "history"), "_route_asset_history"),
    ((_ANY, "assets", _ANY, "upgrade-plan"), "_route_asset_upgrade_plan"),
    ((_ANY, "assets", _ANY, "reuse-plan"), "_route_asset_reuse_plan"),
    ((_ANY, "assets", _ANY, "references"), "_route_asset_references"),
    ((_ANY, "assets", _ANY, "tokens", _TOKEN_VIEWS), "_route_token_view"),
    ((_ANY, "assets", _ANY, "document", _DOCUMENT_VIEWS), "_route_document_view"),
    ((_ANY, "actions", "proposals", _ANY, _ANY), "_route_proposal_verb"),
    ((_ANY, "actions", "assets", _ANY, _ANY), "_route_asset_verb"),
    ((_ANY, "actions", "canvases", _ANY, _ANY), "_route_canvas_verb"),
    ((_ANY, "actions", "requests", _ANY, _ANY), "_route_request_verb"),
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
        finish_gracefully(self.connection)

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
        matched = [route for route in _FIXED_ROUTES if route.path == path]
        if matched:
            # Authentication class first: a capability may not learn whether
            # its method would have been accepted.
            if matched[0].browser:
                self._require_browser(principal)
            route = next(
                (item for item in matched if self.command in item.methods), None
            )
            if route is None:
                self._method_not_allowed(matched[0].allow)
            handlers = {
                "status": lambda: self._serve_status(session),
                "resolve": lambda: self._serve_resolve(
                    service, principal, split.query
                ),
                "project-list": lambda: self._serve_project_list(
                    service, split.query
                ),
                "register": lambda: self._serve_register(service),
                "probe": lambda: self._serve_probe(service),
                "backup": lambda: self._serve_backup(backup),
            }
            handlers[route.handler]()
            return
        if path.startswith(PROJECTS_PREFIX):
            self._serve_project_route(principal, path, split.query)
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
        self._respond(receipt)

    def _serve_status(self, session: WorkbenchSession) -> None:
        self._drain_body()
        payload = {"service": "design-playbook-workbench", **session.receipt()}
        # R14: the startup check reports missing referenced content here. It
        # is a fact for the maintainer, not a reason to refuse to serve.
        if self.server.blob_integrity is not None:
            payload["blobIntegrity"] = self.server.blob_integrity
        self._respond(payload, close=True)

    def _serve_backup(self, backup: "BackupService") -> None:
        """Backup, verify, and restore are maintainer-only settings actions."""
        if is_read_method(self.command):
            # GET verifies an existing archive named by ?path=.
            params = dict(parse_qsl(urlsplit(self.path).query, keep_blank_values=True))
            self._drain_body()
            if set(params) - {"path"}:
                raise _Rejection(INVALID_INPUT)
            self._respond(backup.verify(params.get("path")))
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
        self._respond(payload)

    def _serve_project_list(self, service: WorkbenchService, query: str) -> None:
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond(service.projects_overview())

    def _serve_probe(self, service: WorkbenchService) -> None:
        payload = self._read_json_body()
        exclude = payload.get("excludeProjectId")
        if exclude is not None and not isinstance(exclude, str):
            raise _Rejection(INVALID_INPUT)
        candidate = service.probe_folder(
            payload.get("path"), exclude_project_id=exclude
        )
        self._respond({"candidate": candidate.as_payload()})

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
        self, principal: Principal, path: str, query: str
    ) -> None:
        segments = path[len(PROJECTS_PREFIX):].split("/")
        for parts, handler in _PROJECT_ROUTES:
            if _matches(parts, segments):
                getattr(self, handler)(segments, query, principal)
                return
        self._drain_body()
        raise _Rejection(ROUTE_NOT_FOUND)

    def _serve_collection(
        self,
        principal: Principal,
        project_id: str,
        query: str,
        loader: Callable[[], dict],
    ) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, project_id, "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(loader())

    def _route_project_detail(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond({"project": self.server.service.project_target(segments[0])})

    def _route_proposals_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.proposals.list_for_project(segments[0]),
        )

    def _route_instances_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.reuse.list_instances(segments[0]),
        )

    def _route_canvases_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.canvases.list_for_project(segments[0]),
        )

    def _route_requests_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.work.list_for_project(segments[0]),
        )

    def _route_runs_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.owners.list_runs(segments[0]),
        )

    def _route_confirmations_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_collection(
            principal,
            segments[0],
            query,
            lambda: self.server.owners.list_confirmations(segments[0]),
        )

    def _route_assets_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        params = parse_qsl(query, keep_blank_values=True)
        allowed = {"query", "kind", "capability", "lifecycle"}
        if any(name not in allowed for name, _ in params):
            raise _Rejection(INVALID_INPUT)
        filters = dict(params)
        self._respond(
            self.server.assets.list_assets(
                segments[0],
                query=filters.get("query"),
                kind=filters.get("kind"),
                capability=filters.get("capability"),
                lifecycle=filters.get("lifecycle"),
            )
        )

    def _route_lifecycle_list(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if set(params) - {"lifecycle"}:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.lifecycle.browse(
                segments[0], lifecycle=params.get("lifecycle")
            )
        )

    def _route_archive_overview(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.lifecycle.archive_overview(
                segments[0],
                canvases=self.server.canvases,
                proposals=self.server.proposals,
                owners=self.server.owners,
            )
        )

    def _route_deletion_impact(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(self.server.lifecycle.project_deletion_impact(segments[0]))

    def _route_action(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_action(
            self.server.service,
            self.server.proposals,
            self.server.assets,
            self.server.reuse,
            self.server.design_system,
            self.server.components,
            self.server.canvases,
            self.server.work,
            self.server.owners,
            self.server.lifecycle,
            principal,
            segments[0],
            segments[2],
        )

    def _route_run(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond(self.server.owners.run(segments[0], segments[2]))

    def _route_run_freshness(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if set(params) - {"objectType", "objectId", "sourceHash"}:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.owners.freshness(
                segments[0],
                {
                    "runId": segments[2],
                    "objectType": params.get("objectType"),
                    "objectId": params.get("objectId"),
                    "sourceHash": params.get("sourceHash"),
                },
            )
        )

    def _route_request_detail(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        if principal.request_id is not None and principal.request_id != segments[2]:
            # A request-bound capability reads its own request only; it
            # never sees a sibling task in the same project (R11).
            raise _Rejection(UNAUTHORIZED)
        params = dict(parse_qsl(query, keep_blank_values=True))
        if params:
            # The counter is concurrency metadata, not the context payload
            # (T-127); the Agent client reads it before every work write.
            if params != {"fields": "counter"}:
                raise _Rejection(INVALID_INPUT)
            self._drain_body()
            self._respond(
                self.server.work.counter(segments[0], segments[2], principal=principal)
            )
            return
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond(
            self.server.work.detail(segments[0], segments[2], principal=principal)
        )

    def _route_proposal_detail(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond(self.server.proposals.detail(segments[0], segments[2]))

    def _route_asset_detail(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        if query:
            raise _Rejection(INVALID_INPUT)
        self._drain_body()
        self._respond(self.server.assets.asset_detail(segments[0], segments[2]))

    def _route_canvas_detail(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "detail",
            None,
            query,
        )

    def _route_canvas_snapshot(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "snapshot",
            None,
            query,
        )

    def _route_snapshots(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "snapshots",
            None,
            query,
        )

    def _route_contexts(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "contexts",
            None,
            query,
        )

    def _route_snapshot(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "snapshots",
            segments[4],
            query,
        )

    def _route_context(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_read(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[2],
            "contexts",
            segments[4],
            query,
        )

    def _route_asset_preview(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.assets.preview_descriptor(
                segments[0],
                segments[2],
                preview_origin=self.server.preview_origin,
            )
        )

    def _route_asset_references(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.lifecycle.reference_report(segments[0], segments[2])
        )

    def _route_asset_history(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        if query:
            raise _Rejection(INVALID_INPUT)
        self._respond(self.server.reuse.asset_history(segments[0], segments[2]))

    def _route_asset_upgrade_plan(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if set(params) - {"toRevisionId"}:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.reuse.upgrade_plan(
                segments[0],
                segments[2],
                to_revision_id=params.get("toRevisionId"),
            )
        )

    def _route_asset_reuse_plan(self, segments: list[str], query: str, principal: Principal) -> None:
        self._require_method(is_read_method(self.command))
        self._authorize_project(principal, segments[0], "read")
        self._drain_body()
        params = dict(parse_qsl(query, keep_blank_values=True))
        if set(params) - {"targetProjectId", "mode", "revisionId"}:
            raise _Rejection(INVALID_INPUT)
        target_project_id = params.get("targetProjectId")
        if not target_project_id:
            raise _Rejection(INVALID_INPUT)
        self._respond(
            self.server.reuse.reuse_plan(
                segments[0],
                source_asset_id=segments[2],
                source_revision_id=params.get("revisionId"),
                mode=params.get("mode") or "copy",
                target_project_id=target_project_id,
            )
        )

    def _route_token_view(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_token_view(
            self.server.design_system,
            principal,
            segments[0],
            segments[2],
            segments[4],
            query,
        )

    def _route_document_view(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_document_view(
            self.server.components,
            principal,
            segments[0],
            segments[2],
            segments[4],
            query,
        )

    def _route_proposal_verb(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_proposal_verb(
            self.server.proposals,
            principal,
            segments[0],
            segments[3],
            segments[4],
        )

    def _route_asset_verb(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_asset_verb(
            self.server.service,
            self.server.assets,
            self.server.reuse,
            self.server.design_system,
            self.server.components,
            self.server.work,
            self.server.owners,
            self.server.lifecycle,
            principal,
            segments[0],
            segments[3],
            segments[4],
        )

    def _route_canvas_verb(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_canvas_verb(
            self.server.canvases,
            self.server.orchestration,
            principal,
            segments[0],
            segments[3],
            segments[4],
        )

    def _route_request_verb(self, segments: list[str], query: str, principal: Principal) -> None:
        self._serve_request_verb(
            self.server.work,
            principal,
            segments[0],
            segments[3],
            segments[4],
        )

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
        self._respond(payload)

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
        # Agent traffic is authenticated by the request-bound capability.
        handlers = {
            "consent": lambda: work.consent(
                project_id,
                request_id,
                digest=payload.get("digest"),
                ttl_seconds=payload.get("ttlSeconds"),
                operation=operation,
            ),
            "cancel": lambda: work.cancel(
                project_id, request_id, operation=operation
            ),
            "confirm-cancelled": lambda: work.confirm_cancelled(
                project_id, request_id, operation=operation
            ),
            "retry": lambda: work.retry(
                project_id, request_id, operation=operation
            ),
            "reject": lambda: work.reject(
                project_id, request_id, operation=operation
            ),
            "claim": lambda: work.claim(
                request_id,
                principal=principal,
                lease_seconds=payload.get("leaseSeconds"),
                operation=operation,
            ),
            "heartbeat": lambda: work.heartbeat(
                request_id,
                attempt_id=payload.get("attemptId"),
                lease_id=payload.get("leaseId"),
                sequence=payload.get("sequence"),
                progress=payload.get("progress"),
                principal=principal,
                operation=operation,
            ),
            "result": lambda: work.submit_result(
                request_id,
                attempt_id=payload.get("attemptId"),
                lease_id=payload.get("leaseId"),
                sequence=payload.get("sequence"),
                result=payload.get("result"),
                principal=principal,
                operation=operation,
            ),
            "fail": lambda: work.fail_attempt(
                request_id,
                attempt_id=payload.get("attemptId"),
                lease_id=payload.get("leaseId"),
                sequence=payload.get("sequence"),
                reason=payload.get("reason"),
                principal=principal,
                operation=operation,
            ),
        }
        self._send_mutation(handlers[verb]())

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
        self._respond(self._attach_preview_urls(payload))

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
        handlers = {
            "commands": lambda: canvases.run_commands(
                project_id,
                canvas_id,
                commands=payload.get("commands"),
                operation=operation,
            ),
            "undo": lambda: canvases.undo(
                project_id, canvas_id, operation=operation
            ),
            "redo": lambda: canvases.redo(
                project_id, canvas_id, operation=operation
            ),
            "rename": lambda: canvases.rename(
                project_id,
                canvas_id,
                name=payload.get("name"),
                operation=operation,
            ),
            "fork": lambda: canvases.fork(
                project_id,
                canvas_id,
                name=payload.get("name"),
                document=payload.get("document"),
                operation=operation,
            ),
            "snapshots": lambda: orchestration.create_snapshot(
                project_id,
                canvas_id,
                board_id=payload.get("boardId"),
                note=payload.get("note"),
                operation=operation,
            ),
            "compare": lambda: self._with_preview_urls(
                orchestration.compare(
                    project_id,
                    canvas_id,
                    left=payload.get("left"),
                    right=payload.get("right"),
                    operation=operation,
                )
            ),
            "contexts": lambda: orchestration.build_context(
                project_id,
                canvas_id,
                selection_id=payload.get("selectionId"),
                board_id=payload.get("boardId"),
                node_ids=payload.get("nodeIds"),
                revision_ids=payload.get("revisionIds"),
                file_paths=payload.get("filePaths"),
                operation=operation,
            ),
            "confirm": lambda: self._canvas_confirm(
                orchestration, project_id, canvas_id, payload, operation
            ),
        }
        self._send_mutation(handlers[verb]())

    def _with_preview_urls(self, outcome: dict) -> dict:
        outcome["result"] = self._attach_preview_urls(outcome["result"])
        return outcome

    def _canvas_confirm(
        self,
        orchestration: OrchestrationService,
        project_id: str,
        canvas_id: str,
        payload: dict,
        operation: Operation,
    ) -> dict:
        selection_id = payload.get("selectionId")
        if not isinstance(selection_id, str) or not selection_id:
            raise _Rejection(INVALID_INPUT)
        return orchestration.confirm_context(
            project_id,
            canvas_id,
            selection_id,
            digest=payload.get("digest"),
            operation=operation,
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
        self._respond(payload)

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
        handlers = {
            "apply": lambda: proposals.apply(
                project_id,
                proposal_id,
                digest=payload.get("digest"),
                operation=operation,
            ),
            "recover": lambda: proposals.recover(
                project_id,
                proposal_id,
                mode=payload.get("mode"),
                operation=operation,
            ),
            "revert": lambda: proposals.revert(
                project_id, proposal_id, operation=operation
            ),
            "reject": lambda: proposals.reject(
                project_id, proposal_id, operation=operation
            ),
        }
        self._send_mutation(handlers[verb]())

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
        handlers = {
            "publish": lambda: assets.publish(
                project_id, asset_id, operation=operation
            ),
            "preview-enable": lambda: assets.enable_dynamic_preview(
                project_id, asset_id, operation=operation
            ),
            "refresh-draft": lambda: assets.refresh_draft(
                project_id, asset_id, operation=operation
            ),
            "tokens-update": lambda: design_system.update_tokens(
                project_id,
                asset_id,
                document=payload.get("document"),
                operation=operation,
            ),
            "tokens-publish": lambda: design_system.publish(
                project_id, asset_id, operation=operation
            ),
            "propose-baseline": lambda: design_system.propose_baseline(
                project_id,
                asset_id,
                path=payload.get("path"),
                operation=operation,
            ),
            "archive": lambda: lifecycle.archive(
                project_id, asset_id, operation=operation
            ),
            "unarchive": lambda: lifecycle.unarchive(
                project_id, asset_id, operation=operation
            ),
            "trash": lambda: lifecycle.trash(
                project_id, asset_id, operation=operation
            ),
            "restore": lambda: lifecycle.restore(
                project_id,
                asset_id,
                name=payload.get("name"),
                operation=operation,
            ),
            "hard-delete": lambda: lifecycle.hard_delete(
                project_id,
                asset_id,
                confirm=payload.get("confirm"),
                operation=operation,
            ),
            "publish-verified": lambda: owners.publish_verified(
                project_id,
                asset_id,
                run_id=payload.get("runId"),
                object_id=payload.get("objectId"),
                role=payload.get("role") or "owner-verified",
                operation=operation,
            ),
            "component-update": lambda: components.update_definition(
                project_id,
                asset_id,
                definition=payload.get("definition"),
                operation=operation,
            ),
            "component-publish": lambda: components.publish(
                project_id, asset_id, operation=operation
            ),
            "page-update": lambda: components.update_layout(
                project_id,
                asset_id,
                layout=payload.get("layout"),
                operation=operation,
            ),
            "page-publish": lambda: components.publish_page(
                project_id, asset_id, operation=operation
            ),
            "distill-candidate": lambda: self._asset_distill_candidate(
                components, project_id, payload, operation
            ),
            "publish-with-deps": lambda: assets.publish(
                project_id,
                asset_id,
                operation=operation,
                kind="asset-publish-deps",
                dependencies=payload.get("dependencies"),
            ),
            "derive": lambda: reuse.derive_or_copy(
                project_id,
                asset_id,
                mode="derive",
                name=payload.get("name"),
                operation=operation,
            ),
            "copy": lambda: reuse.derive_or_copy(
                project_id,
                asset_id,
                mode="copy",
                name=payload.get("name"),
                operation=operation,
            ),
            "reference": lambda: reuse.derive_or_copy(
                project_id,
                asset_id,
                mode="reference",
                name=payload.get("name"),
                operation=operation,
            ),
            "import-closure": lambda: self._asset_import_closure(
                reuse, principal, project_id, asset_id, payload, operation
            ),
            "upgrade": lambda: reuse.upgrade_instances(
                project_id,
                asset_id,
                instance_ids=payload.get("instanceIds"),
                to_revision_id=payload.get("toRevisionId"),
                operation=operation,
            ),
            "rollback": lambda: reuse.rollback_instances(
                project_id,
                asset_id,
                instance_ids=payload.get("instanceIds"),
                to_revision_id=payload.get("toRevisionId"),
                operation=operation,
            ),
        }
        self._send_mutation(handlers[verb]())

    def _asset_distill_candidate(
        self,
        components: ComponentService,
        project_id: str,
        payload: dict,
        operation: Operation,
    ) -> dict:
        source_page_id = payload.get("sourcePageAssetId")
        if not isinstance(source_page_id, str) or not source_page_id:
            raise _Rejection(INVALID_INPUT)
        return components.distill_candidate(
            project_id,
            source_page_id,
            node_ids=payload.get("nodeIds"),
            name=payload.get("name"),
            operation=operation,
        )

    def _asset_import_closure(
        self,
        reuse: ReuseService,
        principal: Principal,
        project_id: str,
        asset_id: str,
        payload: dict,
        operation: Operation,
    ) -> dict:
        target_project_id = payload.get("targetProjectId")
        if not isinstance(target_project_id, str) or not target_project_id:
            raise _Rejection(INVALID_INPUT)
        # The source must be readable *and* the target writable: a closure
        # import touches two projects.
        self._authorize_project(principal, target_project_id, "write")
        return reuse.import_closure(
            project_id,
            source_asset_id=payload.get("sourceAssetId") or asset_id,
            source_revision_id=payload.get("sourceRevisionId"),
            mode=payload.get("mode") or "copy",
            target_project_id=target_project_id,
            operation=operation,
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
        elif action in _MAINTAINER_ONLY_ACTIONS:
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
        handlers = {
            "open": lambda: self._action_open(
                service, principal, project_id, operation
            ),
            "rename": lambda: service.rename_project(
                project_id, name=payload.get("name"), operation=operation
            ),
            "rebind": lambda: service.rebind_project(
                project_id,
                path=payload.get("path"),
                candidate_id=payload.get("candidateId"),
                operation=operation,
            ),
            "grants": lambda: service.set_grants(
                project_id, scopes=payload.get("scopes"), operation=operation
            ),
            "remove": lambda: service.remove_project(
                project_id, operation=operation
            ),
            "delete-data": lambda: service.delete_project_data(
                project_id, operation=operation
            ),
            "instances": lambda: reuse.create_instance(
                project_id,
                payload.get("assetId"),
                revision_id=payload.get("revisionId"),
                overrides=payload.get("overrides"),
                operation=operation,
            ),
            "components": lambda: components.create_component(
                project_id,
                name=payload.get("name"),
                definition=payload.get("definition"),
                operation=operation,
            ),
            "pages": lambda: components.create_page(
                project_id,
                name=payload.get("name"),
                layout=payload.get("layout"),
                operation=operation,
            ),
            "canvases": lambda: canvases.create(
                project_id,
                name=payload.get("name"),
                document=payload.get("document"),
                operation=operation,
            ),
            "requests": lambda: work.create(
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
            ),
            "imports": lambda: assets.import_selection(
                project_id,
                selections=payload.get("selections"),
                operation=operation,
            ),
            "confirmations": lambda: owners.confirm(
                project_id,
                run_id=payload.get("runId"),
                object_type=payload.get("objectType"),
                object_id=payload.get("objectId"),
                source_hash=payload.get("sourceHash"),
                role=payload.get("role"),
                note=payload.get("note"),
                operation=operation,
            ),
            "backflow": lambda: owners.backflow_candidate(
                project_id,
                run_id=payload.get("runId"),
                object_type=payload.get("objectType") or "criterion",
                object_id=payload.get("objectId"),
                name=payload.get("name"),
                operation=operation,
            ),
            "project-archive": lambda: lifecycle.archive_project(
                project_id, archived=True, operation=operation
            ),
            "project-unarchive": lambda: lifecycle.archive_project(
                project_id, archived=False, operation=operation
            ),
            "notes-propose": lambda: {
                "result": design_system.propose_notes(
                    project_id,
                    path=payload.get("path"),
                    text=payload.get("text"),
                    operation=operation,
                ),
                "counter": None,
                "replayed": False,
            },
            "proposals": lambda: proposals.create(
                project_id,
                changes=payload.get("changes"),
                summary=payload.get("summary"),
                dependency_changes=payload.get("dependencyChanges"),
                operation=operation,
            ),
        }
        handler = handlers.get(action)
        if handler is None:
            raise _Rejection(ROUTE_NOT_FOUND)
        self._send_mutation(handler())

    def _action_open(
        self,
        service: WorkbenchService,
        principal: Principal,
        project_id: str,
        operation: Operation,
    ) -> dict:
        self._authorize_project(principal, project_id, "read")
        return service.open_project(project_id, operation=operation)

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
        self._respond(
            {
                "result": outcome["result"],
                "counter": outcome["counter"],
                "replayed": outcome["replayed"],
            }
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

    def _respond(self, payload: dict, *, close: bool = False) -> None:
        """The one success response: envelope, status, CSP, close."""
        self._send_json(
            200, {"schemaVersion": SCHEMA_VERSION, **payload}, close=close
        )

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


class WorkbenchHTTPServer(LoopbackHTTPServer):
    """One IP-literal loopback listener serving one workbench session."""

    serve_thread_name = "workbench-server"

    def __init__(
        self,
        *,
        bind_host: str = DEFAULT_BIND_HOST,
        port: int = 0,
        ui_directory=None,
    ) -> None:
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
        self.blob_integrity: dict | None = None
        self.task_lookup = None
        super().__init__(WorkbenchRequestHandler, bind_host=bind_host, port=port)
        self.ui = UIResources(ui_directory)

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

    def _close_owned(self) -> None:
        if self.session is not None:
            self.session.close()
