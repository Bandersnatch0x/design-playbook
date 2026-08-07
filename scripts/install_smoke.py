#!/usr/bin/env python3
"""Isolated public-install smoke for design-playbook.

This is a release/operator tool, not part of the npm/plugin package. It uses a
fresh ``CLAUDE_CONFIG_DIR``, installs from the public HTTPS marketplace, checks
the installed inventory, probes both bundled MCP servers over stdio, installs
the npm artifact in a clean consumer directory, and writes bounded JSON and
Markdown evidence.

The live smoke requires network access plus ``claude``, ``git``, ``npm``, and
``python`` on PATH. CI runs unit tests for the deterministic helpers and mocked
orchestration; it does not run the live network flow.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
PLUGIN_NAME = "design-playbook"
MARKETPLACE_NAME = "design-playbook"
PLUGIN_ID = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
NPM_PACKAGE = "design-playbook"
DEFAULT_SOURCE = "https://github.com/Bandersnatch0x/design-playbook.git"
EXPECTED_MCP_TOOLS = {
    "design-playbook-preview": "preview_prototype",
    "design-playbook-evidence": "execute_capture_plan",
}
JSONRPC_REQUESTS = (
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18"},
    },
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
)
T = TypeVar("T")


class SmokeFailure(RuntimeError):
    """Expected smoke failure with a concise evidence-safe message."""


def _console(message: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding)
    print(safe_message)


@dataclass(frozen=True)
class SmokeConfig:
    version: str
    source: str
    output_dir: Path
    timeout: int = 180
    keep_temp: bool = False
    claude_bin: str = "claude"
    npm_bin: str = "npm"
    git_bin: str = "git"


class Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, str]] = []

    def pass_(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "pass", "detail": detail})
        _console(f"  ok    {name}: {detail}")

    def fail(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "fail", "detail": detail})
        _console(f"  FAIL  {name}: {detail}")

    def stage(
        self,
        name: str,
        action: Callable[[], T],
        detail: Callable[[T], str] | str,
    ) -> T:
        try:
            value = action()
            rendered = detail(value) if callable(detail) else detail
        except Exception as exc:  # noqa: BLE001 - evidence boundary
            message = _bounded(str(exc))
            self.fail(name, message)
            if isinstance(exc, SmokeFailure):
                raise
            raise SmokeFailure(message) from exc
        self.pass_(name, _bounded(rendered))
        return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _bounded(text: str, limit: int = 1000) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[-limit:]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeFailure(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"JSON root must be an object: {path}")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _run_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 180,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeFailure(f"command failed to start/finish: {cmd[0]}: {exc}") from exc
    if completed.returncode != 0:
        tail = _bounded(f"{completed.stdout}\n{completed.stderr}")
        raise SmokeFailure(
            f"command exit {completed.returncode}: {' '.join(cmd)}: {tail}"
        )
    return completed


def _tool_version(command: str, timeout: int) -> str:
    completed = _run_command([command, "--version"], timeout=timeout)
    return _bounded(completed.stdout or completed.stderr, 300)


def _source_expectations() -> dict[str, Any]:
    plugin = _read_json(PKG / ".claude-plugin" / "plugin.json")
    package = _read_json(PKG / "package.json")
    mcp = _read_json(PKG / ".mcp.json")
    version = plugin.get("version")
    _require(isinstance(version, str) and bool(version), "local plugin version missing")
    _require(package.get("version") == version, "local plugin/npm version drift")

    skills = sorted(
        path.name
        for path in (PKG / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )
    commands = sorted(path.stem for path in (PKG / "commands").glob("*.md"))
    servers = mcp.get("mcpServers")
    _require(isinstance(servers, dict), "local .mcp.json mcpServers missing")
    mcp_names = sorted(servers)
    _require(
        set(mcp_names) == set(EXPECTED_MCP_TOOLS),
        f"local MCP inventory drift: {mcp_names}",
    )
    return {
        "version": version,
        "skills": skills,
        "commands": commands,
        "mcp_servers": mcp_names,
    }


def _inspect_plugin_inventory(plugin_root: Path) -> dict[str, Any]:
    package = _read_json(plugin_root / "package.json")
    mcp = _read_json(plugin_root / ".mcp.json")
    servers = mcp.get("mcpServers")
    _require(isinstance(servers, dict), f"installed mcpServers missing: {plugin_root}")
    return {
        "version": package.get("version"),
        "skills": sorted(
            path.name
            for path in (plugin_root / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ),
        "commands": sorted(
            path.stem for path in (plugin_root / "commands").glob("*.md")
        ),
        "mcp_servers": sorted(servers),
    }


def _inspect_npm_inventory(package_root: Path) -> dict[str, Any]:
    package = _read_json(package_root / "package.json")
    runtime_paths = {
        name: package_root / "mcp" / short / "server.py"
        for name, short in (
            ("design-playbook-preview", "preview"),
            ("design-playbook-evidence", "evidence"),
        )
    }
    return {
        "version": package.get("version"),
        "skills": sorted(
            path.name
            for path in (package_root / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ),
        "commands": sorted(
            path.stem for path in (package_root / "commands").glob("*.md")
        ),
        "mcp_servers": sorted(
            name for name, path in runtime_paths.items() if path.is_file()
        ),
    }


def _assert_inventory(
    actual: dict[str, Any], expected: dict[str, Any], label: str
) -> dict[str, Any]:
    for key in ("version", "skills", "commands", "mcp_servers"):
        _require(
            actual.get(key) == expected.get(key),
            f"{label} {key} mismatch: expected {expected.get(key)!r}, "
            f"got {actual.get(key)!r}",
        )
    return actual


def _installed_metadata(config_dir: Path, expected_version: str) -> dict[str, Any]:
    installed = _read_json(config_dir / "plugins" / "installed_plugins.json")
    settings = _read_json(config_dir / "settings.json")
    plugins = installed.get("plugins")
    _require(isinstance(plugins, dict), "installed_plugins.json plugins missing")
    entries = plugins.get(PLUGIN_ID)
    _require(isinstance(entries, list) and len(entries) == 1, f"expected one {PLUGIN_ID} entry")
    entry = entries[0]
    _require(isinstance(entry, dict), f"invalid installed entry for {PLUGIN_ID}")
    _require(entry.get("version") == expected_version, "installed metadata version mismatch")
    _require(entry.get("scope") == "user", "installed plugin scope is not user")

    enabled = settings.get("enabledPlugins")
    _require(isinstance(enabled, dict), "settings enabledPlugins missing")
    _require(enabled.get(PLUGIN_ID) is True, f"{PLUGIN_ID} is not enabled")

    raw_path = entry.get("installPath")
    _require(isinstance(raw_path, str) and bool(raw_path), "installPath missing")
    install_path = Path(raw_path).resolve()
    config_root = config_dir.resolve()
    _require(
        install_path.is_relative_to(config_root),
        f"installPath escapes isolated CLAUDE_CONFIG_DIR: {install_path}",
    )
    _require(install_path.is_dir(), f"installPath missing: {install_path}")
    return {
        "version": expected_version,
        "enabled": True,
        "scope": "user",
        "install_path": str(install_path),
        "git_commit_sha": entry.get("gitCommitSha"),
    }


def _marketplace_metadata(config_dir: Path, expected_source: str) -> dict[str, str]:
    known = _read_json(config_dir / "plugins" / "known_marketplaces.json")
    entry = known.get(MARKETPLACE_NAME)
    _require(isinstance(entry, dict), f"marketplace {MARKETPLACE_NAME} missing")
    source = entry.get("source")
    _require(isinstance(source, dict), "marketplace source metadata missing")
    _require(source.get("url") == expected_source, "marketplace source URL mismatch")
    location = entry.get("installLocation")
    _require(isinstance(location, str) and bool(location), "marketplace installLocation missing")
    path = Path(location).resolve()
    _require(path.is_dir(), f"marketplace checkout missing: {path}")
    return {"source": expected_source, "path": str(path)}


def _expand_plugin_root(value: str, plugin_root: Path) -> str:
    return value.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))


def _probe_mcp(
    plugin_root: Path,
    server_name: str,
    expected_tool: str,
    *,
    env: dict[str, str],
    cwd: Path,
    timeout: int,
) -> dict[str, Any]:
    manifest = _read_json(plugin_root / ".mcp.json")
    servers = manifest.get("mcpServers")
    _require(isinstance(servers, dict), "installed .mcp.json mcpServers missing")
    server = servers.get(server_name)
    _require(isinstance(server, dict), f"installed MCP server missing: {server_name}")
    command = server.get("command")
    args = server.get("args", [])
    _require(isinstance(command, str) and bool(command), f"{server_name} command missing")
    _require(isinstance(args, list) and all(isinstance(x, str) for x in args), f"{server_name} args invalid")
    expanded = [_expand_plugin_root(value, plugin_root) for value in args]
    wire = "".join(json.dumps(request, ensure_ascii=False) + "\n" for request in JSONRPC_REQUESTS)
    completed = _run_command(
        [command, *expanded],
        env=env,
        cwd=cwd,
        timeout=min(timeout, 60),
        input_text=wire,
    )
    responses: dict[int, dict[str, Any]] = {}
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"{server_name} emitted non-JSON stdout: {line[:200]}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("id"), int):
            responses[payload["id"]] = payload
    _require(set(responses) == {1, 2}, f"{server_name} response ids: {sorted(responses)}")
    initialize = responses[1].get("result")
    _require(isinstance(initialize, dict), f"{server_name} initialize result missing")
    info = initialize.get("serverInfo")
    _require(isinstance(info, dict) and info.get("name") == server_name, f"{server_name} serverInfo mismatch")
    listed = responses[2].get("result")
    _require(isinstance(listed, dict), f"{server_name} tools/list result missing")
    tools = listed.get("tools")
    _require(isinstance(tools, list), f"{server_name} tools list invalid")
    names = sorted(
        item.get("name") for item in tools
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )
    _require(names == [expected_tool], f"{server_name} tools mismatch: {names}")
    return {"server": server_name, "tools": names}


def _inventory_detail(value: dict[str, Any]) -> str:
    return (
        f"version={value['version']} skills={len(value['skills'])} "
        f"commands={len(value['commands'])} mcp={len(value['mcp_servers'])}"
    )


def run_smoke(config: SmokeConfig, *, temp_root: Path | None = None) -> dict[str, Any]:
    started = _utc_now()
    recorder = Recorder()
    expected = _source_expectations()
    _require(
        config.version == expected["version"],
        f"requested version {config.version} != local package {expected['version']}",
    )

    owned_temp = temp_root is None
    work_root = Path(tempfile.mkdtemp(prefix="design-playbook-install-smoke-")) if owned_temp else temp_root
    work_root.mkdir(parents=True, exist_ok=True)
    config_dir = work_root / "claude"
    config_dir.mkdir()
    npm_consumer = work_root / "npm-consumer"
    npm_consumer.mkdir()
    run_root = work_root / "run-root"
    run_root.mkdir()

    isolated_env = os.environ.copy()
    isolated_env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    isolated_env["DESIGN_PLAYBOOK_RUN_ROOT"] = str(run_root)

    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "fail",
        "started_at": started,
        "completed_at": None,
        "source": config.source,
        "expected": expected,
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "checks": recorder.checks,
        "installed": None,
        "npm": None,
        "temporary_root": {
            "path": str(work_root),
            "retained": True,
            "owned": owned_temp,
        },
        "warnings": [],
        "error": None,
    }

    try:
        def assert_empty_config() -> list[Path]:
            items = list(config_dir.iterdir())
            _require(not items, f"unexpected files: {items}")
            return items

        recorder.stage(
            "isolated config",
            assert_empty_config,
            "empty CLAUDE_CONFIG_DIR",
        )

        claude_version = recorder.stage(
            "Claude CLI",
            lambda: _tool_version(config.claude_bin, config.timeout),
            lambda value: value,
        )
        npm_version = recorder.stage(
            "npm CLI",
            lambda: _tool_version(config.npm_bin, config.timeout),
            lambda value: value,
        )
        result["runtime"].update({"claude": claude_version, "npm": npm_version})

        recorder.stage(
            "marketplace add",
            lambda: _run_command(
                [config.claude_bin, "plugin", "marketplace", "add", config.source],
                env=isolated_env,
                timeout=config.timeout,
            ),
            f"{MARKETPLACE_NAME} from explicit source",
        )
        market = recorder.stage(
            "marketplace metadata",
            lambda: _marketplace_metadata(config_dir, config.source),
            lambda value: value["source"],
        )
        head = recorder.stage(
            "marketplace HEAD",
            lambda: _run_command(
                [config.git_bin, "-C", market["path"], "rev-parse", "HEAD"],
                timeout=config.timeout,
            ),
            lambda completed: completed.stdout.strip(),
        ).stdout.strip()
        result["marketplace_head"] = head

        recorder.stage(
            "plugin install",
            lambda: _run_command(
                [
                    config.claude_bin,
                    "plugin",
                    "install",
                    PLUGIN_ID,
                    "--scope",
                    "user",
                ],
                env=isolated_env,
                timeout=config.timeout,
            ),
            f"{PLUGIN_ID} at user scope",
        )
        installed = recorder.stage(
            "installed metadata",
            lambda: _installed_metadata(config_dir, config.version),
            lambda value: f"version={value['version']} enabled={value['enabled']}",
        )
        plugin_root = Path(installed["install_path"])
        inventory = recorder.stage(
            "installed inventory",
            lambda: _assert_inventory(
                _inspect_plugin_inventory(plugin_root), expected, "installed plugin"
            ),
            _inventory_detail,
        )
        installed["inventory"] = inventory
        installed["mcp"] = []
        result["installed"] = installed

        recorder.stage(
            "strict plugin validation",
            lambda: _run_command(
                [config.claude_bin, "plugin", "validate", "--strict", str(plugin_root)],
                env=isolated_env,
                timeout=config.timeout,
            ),
            "claude plugin validate --strict passed",
        )

        for server_name, expected_tool in EXPECTED_MCP_TOOLS.items():
            probe = recorder.stage(
                f"MCP {server_name}",
                lambda name=server_name, tool=expected_tool: _probe_mcp(
                    plugin_root,
                    name,
                    tool,
                    env=isolated_env,
                    cwd=work_root,
                    timeout=config.timeout,
                ),
                lambda value: ", ".join(value["tools"]),
            )
            installed["mcp"].append(probe)

        recorder.stage(
            "npm consumer init",
            lambda: _run_command(
                [config.npm_bin, "init", "-y"],
                cwd=npm_consumer,
                timeout=config.timeout,
            ),
            "clean consumer package created",
        )
        recorder.stage(
            "npm install",
            lambda: _run_command(
                [
                    config.npm_bin,
                    "install",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    f"{NPM_PACKAGE}@{config.version}",
                ],
                cwd=npm_consumer,
                timeout=config.timeout,
            ),
            f"{NPM_PACKAGE}@{config.version}",
        )
        npm_root = npm_consumer / "node_modules" / NPM_PACKAGE
        npm_inventory = recorder.stage(
            "npm inventory",
            lambda: _assert_inventory(
                _inspect_npm_inventory(npm_root), expected, "npm package"
            ),
            _inventory_detail,
        )
        registry = recorder.stage(
            "npm registry metadata",
            lambda: _npm_registry(config.npm_bin, config.version, config.timeout),
            lambda value: f"version={value['version']} shasum={value.get('shasum', '')}",
        )
        result["npm"] = {"inventory": npm_inventory, **registry}
        result["status"] = "pass"
    except Exception as exc:  # noqa: BLE001 - always write evidence
        result["error"] = _bounded(str(exc))
    finally:
        result["completed_at"] = _utc_now()
        result["checks"] = recorder.checks

    return result


def _clear_readonly_and_retry(
    function: Callable[[str], Any], path: str, _exc_info: Any
) -> None:
    """Let shutil remove read-only Git pack files on Windows."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def cleanup_temporary_root(result: dict[str, Any]) -> None:
    """Best-effort cleanup after initial evidence exists on disk."""
    temp = result.get("temporary_root")
    if not isinstance(temp, dict) or not temp.get("owned") or not temp.get("retained"):
        return
    path = Path(str(temp.get("path", "")))
    try:
        shutil.rmtree(path, onerror=_clear_readonly_and_retry)
    except OSError as exc:
        warnings = result.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(f"temporary cleanup failed; retained {path}: {_bounded(str(exc))}")
        return
    temp["retained"] = False


def _npm_registry(npm_bin: str, version: str, timeout: int) -> dict[str, Any]:
    completed = _run_command(
        [
            npm_bin,
            "view",
            f"{NPM_PACKAGE}@{version}",
            "version",
            "dist.shasum",
            "dist.tarball",
            "--json",
        ],
        timeout=timeout,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure("npm view returned invalid JSON") from exc
    _require(isinstance(payload, dict), "npm view response must be an object")
    _require(payload.get("version") == version, "npm registry version mismatch")
    shasum = payload.get("dist.shasum")
    tarball = payload.get("dist.tarball")
    _require(isinstance(shasum, str) and bool(shasum), "npm registry shasum missing")
    _require(isinstance(tarball, str) and bool(tarball), "npm registry tarball missing")
    return {"version": version, "shasum": shasum, "tarball": tarball}


def render_markdown(result: dict[str, Any]) -> str:
    status = str(result.get("status", "fail")).upper()
    expected = result.get("expected") or {}
    installed = result.get("installed") or {}
    npm = result.get("npm") or {}
    temp = result.get("temporary_root") or {}
    lines = [
        f"# Install smoke - v{expected.get('version', 'unknown')}",
        "",
        f"**Status:** **{status}**",
        f"**Source:** `{result.get('source', '')}`",
        f"**Started:** {result.get('started_at', '')}",
        f"**Completed:** {result.get('completed_at', '')}",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in result.get("checks", []):
        detail = str(check.get("detail", "")).replace("|", "\\|")
        lines.append(
            f"| {check.get('name', '')} | {str(check.get('status', '')).upper()} | {detail} |"
        )
    lines.extend(["", "## Inventory", ""])
    inventory = installed.get("inventory") or {}
    if inventory:
        lines.extend(
            [
                f"- Installed version: `{installed.get('version', '')}`",
                f"- Enabled: `{installed.get('enabled', False)}`",
                f"- Skills: **{len(inventory.get('skills', []))}**",
                f"- Commands: **{len(inventory.get('commands', []))}**",
                f"- MCP servers: **{len(inventory.get('mcp_servers', []))}**",
                f"- Marketplace HEAD: `{result.get('marketplace_head', '')}`",
            ]
        )
    npm_inventory = npm.get("inventory") or {}
    if npm_inventory:
        lines.extend(
            [
                "",
                "## npm",
                "",
                f"- Version: `{npm.get('version', '')}`",
                f"- Shasum: `{npm.get('shasum', '')}`",
                f"- Skills / commands / MCP: "
                f"{len(npm_inventory.get('skills', []))} / "
                f"{len(npm_inventory.get('commands', []))} / "
                f"{len(npm_inventory.get('mcp_servers', []))}",
            ]
        )
    if result.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    if result.get("error"):
        lines.extend(["", "## Failure", "", str(result["error"])])
    lines.extend(
        [
            "",
            "## Temporary directory",
            "",
            f"- Retained: `{temp.get('retained', False)}`",
            f"- Path: `{temp.get('path', '')}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "result.json"
    md_path = output_dir / "result.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    local = _source_expectations()
    parser = argparse.ArgumentParser(
        description="Run an isolated public install smoke and write JSON/Markdown evidence."
    )
    parser.add_argument("--version", default=local["version"])
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="evidence directory (default: .scratch/install-smoke/<timestamp>-v<version>)",
    )
    parser.add_argument("--timeout", type=int, default=180, help="per-command timeout seconds")
    parser.add_argument("--keep-temp", action="store_true", help="retain isolated install directory on success")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--npm-bin", default="npm")
    parser.add_argument("--git-bin", default="git")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = args.output_dir or (
        ROOT / ".scratch" / "install-smoke" / f"{_timestamp_slug()}-v{args.version}"
    )
    config = SmokeConfig(
        version=args.version,
        source=args.source,
        output_dir=output_dir,
        timeout=args.timeout,
        keep_temp=args.keep_temp,
        claude_bin=args.claude_bin,
        npm_bin=args.npm_bin,
        git_bin=args.git_bin,
    )
    try:
        result = run_smoke(config)
    except Exception as exc:  # noqa: BLE001 - CLI must still emit evidence
        now = _utc_now()
        result = {
            "schema_version": 1,
            "status": "fail",
            "started_at": now,
            "completed_at": now,
            "source": config.source,
            "expected": {"version": config.version},
            "runtime": {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
            "checks": [],
            "installed": None,
            "npm": None,
            "temporary_root": {"path": "", "retained": False, "owned": False},
            "warnings": [],
            "error": _bounded(str(exc)),
        }
    json_path, md_path = write_evidence(result, output_dir)
    if result["status"] == "pass" and not config.keep_temp:
        cleanup_temporary_root(result)
        json_path, md_path = write_evidence(result, output_dir)
    _console(f"JSON: {json_path}")
    _console(f"Markdown: {md_path}")
    if result["status"] == "pass":
        _console("INSTALL SMOKE PASSED")
        return 0
    _console(f"INSTALL SMOKE FAILED: {result.get('error', '')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
