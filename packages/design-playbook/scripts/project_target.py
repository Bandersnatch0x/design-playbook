#!/usr/bin/env python3
"""Resolve the target project for a slash invocation (R02).

Slash commands are prompt text, so the *resolution* has to be a real,
checkable step rather than a sentence an agent may interpret loosely.
This script is that step:

- the install scope is decided from adapter metadata or an explicit
  configuration file -- never from the current working directory;
- a project-level install binds the project that carries the marker;
- a user-level install refuses to guess: an explicit absolute directory
  (or an explicit registered project id) is required, and the home
  directory, the plugin install directory, the current working
  directory, and any previous target are never used as a fallback;
- the answer comes from the local workbench service, which is the
  authority for bindings. Without a request, an explicit absolute
  directory also resolves while the service is stopped, so the
  pre-workbench slash workflow keeps working; nothing is registered and no
  competing, offline asset directory is ever created. With a request, or a
  registered project id, the service must be running -- otherwise the
  result is ``unavailable`` and the command stops.

Usage::

    python project_target.py --project "<absolute-directory>" [--request <id>]
    python project_target.py --project-id "<uuid>"
    python project_target.py --describe-scope

Exit codes: 0 resolved, 3 target refused (invalid/disconnected/unknown),
4 service unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCOPE_PROJECT = "project-level"
SCOPE_USER = "user-level"
SCOPE_UNKNOWN = "unknown"

EXIT_OK = 0
EXIT_REFUSED = 3
EXIT_UNAVAILABLE = 4

#: Marker files that identify a project-level install without asking the
#: current working directory anything: the adapter metadata lives inside
#: the project the plugin was installed into.
PROJECT_MARKERS: tuple[str, ...] = (
    ".claude/settings.json",
    ".claude-plugin/plugin.json",
    ".design-playbook/project.json",
)

DEFAULT_DATA_DIR_ENV = "DESIGN_PLAYBOOK_WORKBENCH_DATA_DIR"
RECORD_RELATIVE = ("session", "session.json")

SERVICE_TIMEOUT_SECONDS = 10


class TargetRefused(Exception):
    """The caller must stop: no project may be read or written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ServiceUnavailable(Exception):
    """The local workbench service is not running (or has no live record)."""


def _workbench_data_dir(environ: dict | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = env.get(DEFAULT_DATA_DIR_ENV)
    if override:
        return Path(override)
    if os.name == "nt":
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        if base:
            return Path(base) / "design-playbook-workbench"
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "design-playbook-workbench"
    return Path.home() / ".local" / "share" / "design-playbook-workbench"


def read_session_record(data_dir: Path | str | None = None) -> dict:
    """The OS-protected credential record, or ``ServiceUnavailable``."""
    root = Path(data_dir) if data_dir is not None else _workbench_data_dir()
    path = root.joinpath(*RECORD_RELATIVE)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise ServiceUnavailable(
            "the workbench service is not running (no session record)"
        ) from None
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        raise ServiceUnavailable("the session record is not readable") from None
    if not isinstance(record, dict) or not record.get("authority"):
        raise ServiceUnavailable("the session record is incomplete")
    return record


def detect_install_scope(
    *,
    plugin_root: Path | str | None,
    cwd: Path | str | None,
    environ: dict | None = None,
    explicit_scope: str | None = None,
) -> tuple[str, str | None]:
    """Decide the install scope from metadata, never from ``cwd`` alone.

    Returns ``(scope, project_root)``. A project-level install is detected
    by an adapter marker inside the project directory itself, and the
    reported project root is the directory that carries the marker.
    """
    env = os.environ if environ is None else environ
    configured = explicit_scope or env.get("DESIGN_PLAYBOOK_INSTALL_SCOPE")
    if configured in (SCOPE_PROJECT, SCOPE_USER):
        root = env.get("DESIGN_PLAYBOOK_PROJECT_ROOT")
        if configured == SCOPE_PROJECT:
            if not root:
                raise TargetRefused(
                    "invalid-target",
                    "a project-level install must declare DESIGN_PLAYBOOK_PROJECT_ROOT",
                )
            return SCOPE_PROJECT, str(Path(root).expanduser().resolve())
        return SCOPE_USER, None
    if configured is not None:
        raise TargetRefused(
            "invalid-input",
            "DESIGN_PLAYBOOK_INSTALL_SCOPE must be 'project-level' or 'user-level'",
        )

    candidates: list[Path] = []
    if plugin_root is not None:
        candidates.append(Path(plugin_root).expanduser().resolve().parent)
    if cwd is not None:
        candidates.append(Path(cwd).expanduser().resolve())
    seen: set[str] = set()
    for candidate in candidates:
        for marker in PROJECT_MARKERS:
            marker_path = candidate / marker
            if not marker_path.is_file():
                continue
            text = marker_path.read_text(encoding="utf-8", errors="replace")
            if "design-playbook" not in text:
                continue
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            return SCOPE_PROJECT, key
    return SCOPE_USER, None


def parse_request_arguments(text: str) -> dict:
    """Parse the ``project="..." request="..."`` text convention.

    Only those two names are recognised, values may contain spaces and
    CJK characters, and the result is never assembled into a shell
    string: the caller passes the value as an argument.
    """
    result: dict[str, str] = {}
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        match = None
        for name in ("project", "request"):
            if text.startswith(name, index):
                after = index + len(name)
                if after < length and text[after] == "=":
                    match = (name, after + 1)
                    break
        if match is None:
            index += 1
            continue
        name, value_start = match
        if value_start < length and text[value_start] in "\"'":
            quote = text[value_start]
            end = text.find(quote, value_start + 1)
            if end == -1:
                raise TargetRefused("invalid-input", f"unterminated {name} value")
            result[name] = text[value_start + 1 : end]
            index = end + 1
            continue
        end = value_start
        while end < length and not text[end].isspace():
            end += 1
        result[name] = text[value_start:end]
        index = end
    return result


def _http_get(record: dict, path: str, query: str) -> dict:
    url = record["authority"] + path + ("?" + query if query else "")
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", "Bearer " + str(record.get("sessionToken", "")))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=SERVICE_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = None
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except Exception:
            payload = None
        code = (
            payload.get("error", {}).get("code")
            if isinstance(payload, dict)
            else None
        )
        raise TargetRefused(code or "invalid-target", "the service refused the target")
    except (urllib.error.URLError, OSError, ValueError):
        raise ServiceUnavailable(
            "the workbench service is not reachable on its bound address"
        ) from None


def _resolve_offline(project: str) -> dict:
    """Resolve one explicit absolute directory without the service.

    Only reachable when no request is named and the service is not running:
    an existing workflow keeps its explicit directory. Nothing is registered
    and no asset directory is created -- the directory alone is the answer.
    """
    if not isinstance(project, str) or not project.strip():
        raise TargetRefused(
            "invalid-target", "an explicit project directory is required"
        )
    path = Path(project).expanduser()
    if not path.is_absolute():
        raise TargetRefused("invalid-target", "an absolute directory is required")
    if not path.is_dir():
        raise TargetRefused("invalid-target", "the target directory is not reachable")
    canonical = path.resolve()
    return {
        "resolved": True,
        "mode": "offline",
        "authority": None,
        "project": {
            "projectId": None,
            "name": canonical.name,
            "canonicalPath": str(canonical),
        },
        "requestId": None,
        "taskState": None,
    }


def resolve_target(
    *,
    project: str | None = None,
    project_id: str | None = None,
    request_id: str | None = None,
    data_dir: Path | str | None = None,
) -> dict:
    """Ask the local service to resolve one explicit target.

    A request, or a registered project id, is always the service's answer:
    without the service it is ``unavailable``. A bare explicit directory
    with no request still resolves while the service is stopped, so the
    pre-workbench slash workflow keeps working.
    """
    if bool(project) == bool(project_id):
        raise TargetRefused(
            "invalid-target",
            "an explicit project directory or project id is required",
        )
    if project_id:
        query = "projectId=" + urllib.parse.quote(project_id, safe="")
    else:
        query = "project=" + urllib.parse.quote(str(project), safe="")
    if request_id:
        query += "&request=" + urllib.parse.quote(request_id, safe="")
    try:
        record = read_session_record(data_dir)
        payload = _http_get(record, "/api/v1/resolve", query)
    except ServiceUnavailable:
        if project_id or request_id:
            raise
        return _resolve_offline(str(project))
    payload["authority"] = record["authority"]
    payload["bootId"] = record.get("bootId")
    return payload


def describe_scope(
    *, plugin_root: Path | str | None = None, cwd: Path | str | None = None
) -> dict:
    scope, project_root = detect_install_scope(
        plugin_root=plugin_root, cwd=cwd
    )
    return {
        "installScope": scope,
        "projectRoot": project_root,
        "explicitTargetRequired": scope == SCOPE_USER,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project_target",
        description=(
            "Resolve the project target for a design-playbook slash command. "
            "Never falls back to the home directory, the plugin install "
            "directory, the current working directory, or a previous target."
        ),
    )
    parser.add_argument("--project", help="Absolute project directory.")
    parser.add_argument("--project-id", dest="project_id", help="Registered project id.")
    parser.add_argument("--request", help="Work request id bound to the project.")
    parser.add_argument(
        "--arguments",
        help=(
            "Raw slash argument text; project= and request= values are read "
            "from it when the matching flags are absent."
        ),
    )
    parser.add_argument(
        "--data-dir", help="Workbench data directory (default: per-user location)."
    )
    parser.add_argument(
        "--describe-scope",
        action="store_true",
        help="Report the detected install scope and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    stream = sys.stdout
    try:
        if arguments.describe_scope:
            payload = describe_scope(
                plugin_root=os.environ.get("CLAUDE_PLUGIN_ROOT"),
                cwd=os.getcwd(),
            )
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return EXIT_OK
        project = arguments.project
        request_id = arguments.request
        if arguments.arguments:
            parsed = parse_request_arguments(arguments.arguments)
            if not project:
                project = parsed.get("project")
            if not request_id:
                request_id = parsed.get("request")
        payload = resolve_target(
            project=project,
            project_id=arguments.project_id,
            request_id=request_id,
            data_dir=arguments.data_dir,
        )
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return EXIT_OK
    except TargetRefused as refusal:
        stream.write(
            json.dumps(
                {"resolved": False, "code": refusal.code, "message": refusal.message},
                ensure_ascii=False,
            )
            + "\n"
        )
        return EXIT_REFUSED
    except ServiceUnavailable as unavailable:
        stream.write(
            json.dumps(
                {
                    "resolved": False,
                    "code": "unavailable",
                    "message": str(unavailable),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        return EXIT_UNAVAILABLE


if __name__ == "__main__":  # pragma: no cover - script entry
    # One pipe-encoding seam (T-105): UTF-8 on piped stdout/stderr
    # regardless of the host code page. See scripts/stdio_encoding.py.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
