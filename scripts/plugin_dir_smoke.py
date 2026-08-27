#!/usr/bin/env python3
"""Isolated plugin-dir inventory handshake for design-playbook.

This is the dev half of install smoke: from a fresh isolated host config,
load the local package via the documented ``--plugin-dir`` path and prove
the live skills, commands, and bundled MCP tools match the source
inventory. No marketplace, no model, no public network.

The live surface is observed three ways, all fail-closed against the
canonical expectations from ``package_inventory.from_source``:

- ``claude --plugin-dir <pkg> plugin list --json`` — structured session
  plugin entry (id/version/scope/installPath). ``mcpServers`` is
  optional: host CLI 2.1.246+ stopped echoing it (plugin-cache rework,
  undocumented schema change, observed 2026-08-27). When the key is
  present its server set is asserted exactly; when absent the load-time
  registration claim is carried by the ``plugin details`` MCP line and
  the stdio probes below, and the smoke records a warning instead of
  failing on host schema drift.
- ``claude --plugin-dir <pkg> plugin details <name>`` — rendered
  component inventory. Its Skills line merges skills and commands into
  one multiset, so the handshake compares sorted(skills + commands).
- stdio MCP probes (initialize + tools/list) against the bundled
  servers, asserting the exact exposed tool names.

Exit codes: 0 pass, 1 fail, 2 skipped (host binary absent — explicit,
never silent green). Requires ``claude`` and ``python`` on PATH; CI runs
only the deterministic unit tests.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_smoke import (  # noqa: E402
    EXPECTED_MCP_TOOLS,
    PKG,
    PLUGIN_NAME,
    Recorder,
    SmokeFailure,
    _bounded,
    _console,
    _probe_mcp,
    _require,
    _run_command,
    _source_expectations,
    _timestamp_slug,
    _tool_version,
    _utc_now,
    cleanup_temporary_root,
)
from package_inventory import _plugin_entrypoint  # noqa: E402

INLINE_PLUGIN_ID = f"{PLUGIN_NAME}@inline"


@dataclass(frozen=True)
class PluginDirSmokeConfig:
    version: str
    plugin_dir: Path
    output_dir: Path
    timeout: int = 180
    keep_temp: bool = False
    claude_bin: str = "claude"


def _record_skip(recorder: Recorder, name: str, detail: str) -> None:
    recorder.checks.append({"name": name, "status": "skip", "detail": detail})
    _console(f"  skip  {name}: {detail}")


def _host_available(claude_bin: str) -> str | None:
    return shutil.which(claude_bin)


def _parse_plugin_list(
    stdout: str, plugin_dir: Path, expected: dict[str, Any]
) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"plugin list --json emitted invalid JSON: {exc}") from exc
    _require(isinstance(payload, list), "plugin list --json root must be an array")
    _require(
        len(payload) == 1, f"expected exactly one loaded plugin, got {len(payload)}"
    )
    entry = payload[0]
    _require(isinstance(entry, dict), "plugin list entry must be an object")
    _require(
        entry.get("id") == INLINE_PLUGIN_ID,
        f"loaded plugin id mismatch: {entry.get('id')!r}",
    )
    version = entry.get("version")
    _require(
        version == expected["version"],
        f"loaded version mismatch: {version!r} != {expected['version']!r}",
    )
    _require(
        entry.get("scope") == "session",
        f"loaded plugin scope must be session: {entry.get('scope')!r}",
    )
    _require(entry.get("enabled") is True, "loaded plugin is not enabled")
    raw_path = entry.get("installPath")
    _require(isinstance(raw_path, str) and bool(raw_path), "loaded installPath missing")
    install_path = Path(raw_path).resolve()
    _require(
        install_path == plugin_dir.resolve(),
        f"loaded installPath mismatch: {install_path}",
    )
    servers = entry.get("mcpServers")
    if servers is None:
        return {
            "id": INLINE_PLUGIN_ID,
            "version": version,
            "scope": "session",
            "enabled": True,
            "install_path": str(install_path),
            "mcp_servers": [],
            "mcp_entrypoints": {},
            "mcp_schema_note": (
                "host CLI omitted mcpServers from plugin list --json "
                "(schema drift since CLI 2.1.246); registration is proven "
                "by the plugin details MCP line and the stdio probes"
            ),
        }
    _require(isinstance(servers, dict), "loaded mcpServers missing")
    _require(
        sorted(servers) == expected["mcp_servers"],
        f"loaded mcpServers mismatch: {sorted(servers)}",
    )
    entrypoints = {
        name: _plugin_entrypoint(spec)
        for name, spec in sorted(servers.items())
        if isinstance(spec, dict)
    }
    _require(
        entrypoints == expected["mcp_entrypoints"],
        f"loaded mcp entrypoints mismatch: {entrypoints}",
    )
    return {
        "id": INLINE_PLUGIN_ID,
        "version": version,
        "scope": "session",
        "enabled": True,
        "install_path": str(install_path),
        "mcp_servers": sorted(servers),
        "mcp_entrypoints": entrypoints,
    }


def _detail_names(rest: str) -> list[str]:
    cleaned = rest.strip()
    trailing_note = cleaned.rfind(" (")
    if trailing_note != -1 and cleaned.endswith(")"):
        cleaned = cleaned[:trailing_note]
    return [name.strip() for name in cleaned.split(",") if name.strip()]


def _parse_plugin_details(stdout: str, expected: dict[str, Any]) -> dict[str, Any]:
    _require(
        "Component inventory" in stdout,
        "plugin details output lacks component inventory (plugin not loaded?)",
    )
    lines = stdout.splitlines()
    header = next((line for line in lines if line.strip()), "")
    parts = header.split()
    _require(
        len(parts) == 2 and parts[0] == PLUGIN_NAME,
        f"plugin details header mismatch: {header!r}",
    )
    version = parts[1]
    _require(
        version == expected["version"],
        f"plugin details version mismatch: {version!r} != {expected['version']!r}",
    )
    skills_names: list[str] | None = None
    mcp_names: list[str] | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Skills ("):
            skills_names = _names_with_count(stripped, "Skills")
        elif stripped.startswith("MCP servers ("):
            mcp_names = _names_with_count(stripped, "MCP servers")
    _require(skills_names is not None, "plugin details Skills line missing")
    _require(mcp_names is not None, "plugin details MCP servers line missing")
    expected_components = sorted(expected["skills"] + expected["commands"])
    _require(
        sorted(skills_names) == expected_components,
        f"live components mismatch: expected {expected_components}, "
        f"got {sorted(skills_names)}",
    )
    _require(
        sorted(mcp_names) == expected["mcp_servers"],
        f"live MCP servers mismatch: {sorted(mcp_names)}",
    )
    return {
        "version": version,
        "components": sorted(skills_names),
        "mcp_servers": sorted(mcp_names),
    }


def _names_with_count(line: str, label: str) -> list[str]:
    prefix = f"{label} ("
    _require(
        line.startswith(prefix),
        f"plugin details {label} line unreadable: {line!r}",
    )
    rest = line[len(prefix) :]
    count_text, _, names_text = rest.partition(")")
    _require(
        count_text.isdigit(),
        f"plugin details {label} count unreadable: {line!r}",
    )
    names = _detail_names(names_text)
    _require(
        len(names) == int(count_text),
        f"plugin details {label} count {count_text} != {len(names)} listed names",
    )
    return names


def run_smoke(
    config: PluginDirSmokeConfig, *, temp_root: Path | None = None
) -> dict[str, Any]:
    started = _utc_now()
    recorder = Recorder()
    expected = _source_expectations()
    _require(
        config.version == expected["version"],
        f"requested version {config.version} != local package {expected['version']}",
    )

    owned_temp = temp_root is None
    work_root = (
        Path(tempfile.mkdtemp(prefix="design-playbook-plugin-dir-smoke-"))
        if owned_temp
        else temp_root
    )
    work_root.mkdir(parents=True, exist_ok=True)
    config_dir = work_root / "claude"
    config_dir.mkdir(exist_ok=True)
    run_root = work_root / "run-root"
    run_root.mkdir(exist_ok=True)

    isolated_env = os.environ.copy()
    isolated_env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    isolated_env["DESIGN_PLAYBOOK_RUN_ROOT"] = str(run_root)

    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "fail",
        "started_at": started,
        "completed_at": None,
        "plugin_dir": str(config.plugin_dir),
        "expected": expected,
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "claude": None,
        },
        "checks": recorder.checks,
        "loaded": None,
        "details": None,
        "mcp": [],
        "temporary_root": {
            "path": str(work_root),
            "retained": True,
            "owned": owned_temp,
        },
        "warnings": [],
        "error": None,
        "skip_reason": None,
    }

    try:
        host_path = _host_available(config.claude_bin)
        if host_path is None:
            reason = f"host binary {config.claude_bin!r} not found on PATH"
            _record_skip(recorder, "host binary", reason)
            result["status"] = "skip"
            result["skip_reason"] = reason
        else:

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
            result["runtime"]["claude"] = claude_version

            def run_host(*args: str) -> str:
                completed = _run_command(
                    [config.claude_bin, "--plugin-dir", str(config.plugin_dir), *args],
                    env=isolated_env,
                    cwd=work_root,
                    timeout=config.timeout,
                )
                return completed.stdout

            loaded = recorder.stage(
                "plugin list load",
                lambda: _parse_plugin_list(
                    run_host("plugin", "list", "--json"),
                    config.plugin_dir,
                    expected,
                ),
                lambda value: (
                    f"{value['id']} v{value['version']} "
                    f"scope={value['scope']} mcp={len(value['mcp_servers'])}"
                ),
            )
            result["loaded"] = loaded
            if isinstance(loaded, dict) and loaded.get("mcp_schema_note"):
                result["warnings"].append(str(loaded["mcp_schema_note"]))

            details = recorder.stage(
                "plugin details",
                lambda: _parse_plugin_details(
                    run_host("plugin", "details", PLUGIN_NAME),
                    expected,
                ),
                lambda value: (
                    f"components={len(value['components'])} "
                    f"mcp={len(value['mcp_servers'])}"
                ),
            )
            result["details"] = details

            for server_name, expected_tool in EXPECTED_MCP_TOOLS.items():
                probe = recorder.stage(
                    f"MCP {server_name}",
                    lambda name=server_name, tool=expected_tool: _probe_mcp(
                        config.plugin_dir,
                        name,
                        tool,
                        env=isolated_env,
                        cwd=work_root,
                        timeout=config.timeout,
                    ),
                    lambda value: ", ".join(value["tools"]),
                )
                result["mcp"].append(probe)

            result["status"] = "pass"
    except Exception as exc:  # noqa: BLE001 - always write evidence
        result["error"] = _bounded(str(exc))
    finally:
        result["completed_at"] = _utc_now()
        result["checks"] = recorder.checks

    return result


def _render_markdown(result: dict[str, Any]) -> str:
    status = str(result.get("status", "fail")).upper()
    expected = result.get("expected") or {}
    loaded = result.get("loaded") or {}
    details = result.get("details") or {}
    temp = result.get("temporary_root") or {}
    lines = [
        f"# Plugin-dir smoke - v{expected.get('version', 'unknown')}",
        "",
        f"**Status:** **{status}**",
        f"**Plugin dir:** `{result.get('plugin_dir', '')}`",
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
    if loaded:
        lines.extend(
            [
                "",
                "## Loaded plugin",
                "",
                f"- ID: `{loaded.get('id', '')}`",
                f"- Version: `{loaded.get('version', '')}`",
                f"- Scope: `{loaded.get('scope', '')}`",
                f"- Enabled: `{loaded.get('enabled', False)}`",
                f"- Install path: `{loaded.get('install_path', '')}`",
            ]
        )
    if details:
        lines.extend(
            [
                "",
                "## Live components (skills + commands)",
                "",
                f"- Count: **{len(details.get('components', []))}**",
                f"- Names: {', '.join(details.get('components', []))}",
                f"- MCP servers: **{len(details.get('mcp_servers', []))}**",
            ]
        )
    if result.get("mcp"):
        lines.extend(["", "## MCP probes", ""])
        lines.extend(
            f"- {probe['server']}: {', '.join(probe['tools'])}"
            for probe in result["mcp"]
        )
    if result.get("skip_reason"):
        lines.extend(["", "## Skip reason", "", str(result["skip_reason"])])
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
    md_path.write_text(_render_markdown(result), encoding="utf-8")
    return json_path, md_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    local = _source_expectations()
    parser = argparse.ArgumentParser(
        description=(
            "Run an isolated --plugin-dir inventory handshake and write "
            "JSON/Markdown evidence."
        )
    )
    parser.add_argument("--version", default=local["version"])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="evidence directory (default: .scratch/plugin-dir-smoke/<timestamp>-v<version>)",
    )
    parser.add_argument(
        "--timeout", type=int, default=180, help="per-command timeout seconds"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="retain isolated config directory on success",
    )
    parser.add_argument("--claude-bin", default="claude")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = args.output_dir or (
        ROOT / ".scratch" / "plugin-dir-smoke" / f"{_timestamp_slug()}-v{args.version}"
    )
    config = PluginDirSmokeConfig(
        version=args.version,
        plugin_dir=PKG,
        output_dir=output_dir,
        timeout=args.timeout,
        keep_temp=args.keep_temp,
        claude_bin=args.claude_bin,
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
            "plugin_dir": str(config.plugin_dir),
            "expected": {"version": config.version},
            "runtime": {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
            "checks": [],
            "loaded": None,
            "details": None,
            "mcp": [],
            "temporary_root": {"path": "", "retained": False, "owned": False},
            "warnings": [],
            "error": _bounded(str(exc)),
            "skip_reason": None,
        }
    json_path, md_path = write_evidence(result, output_dir)
    if result["status"] in ("pass", "skip") and not config.keep_temp:
        cleanup_temporary_root(result)
        json_path, md_path = write_evidence(result, output_dir)
    _console(f"JSON: {json_path}")
    _console(f"Markdown: {md_path}")
    if result["status"] == "pass":
        _console("PLUGIN-DIR SMOKE PASSED")
        return 0
    if result["status"] == "skip":
        _console(f"PLUGIN-DIR SMOKE SKIPPED: {result.get('skip_reason', '')}")
        return 2
    _console(f"PLUGIN-DIR SMOKE FAILED: {result.get('error', '')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
