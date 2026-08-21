"""Normalized package inventory facts for install/release smoke adapters.

This root-only module owns inventory shape. Source tree, installed plugin, and
npm unpacked package remain adapters because their MCP declarations differ.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InventoryError(ValueError):
    """Package inventory is missing or malformed."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read inventory JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InventoryError(f"inventory JSON must be object: {path}")
    return value


def _common(root: Path, version: Any) -> dict[str, Any]:
    skills_dir = root / "skills"
    commands_dir = root / "commands"
    scripts_dir = root / "scripts"
    return {
        "version": version,
        "skills": sorted(
            path.name for path in skills_dir.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ) if skills_dir.is_dir() else [],
        "commands": sorted(path.stem for path in commands_dir.glob("*.md"))
        if commands_dir.is_dir() else [],
        # Issue #71: the shipped scripts are a public surface (package.json
        # files[] ships scripts/); the precise inventory fails closed on a
        # dropped module (e.g. audit_preferences, ADR-0033).
        "scripts": sorted(
            path.stem for path in scripts_dir.glob("*.py")
            if path.stem != "__init__"
        ) if scripts_dir.is_dir() else [],
    }


def from_plugin(root: Path) -> dict[str, Any]:
    """Inspect plugin package and its declared MCP launch specs."""
    package = _read_json(root / "package.json")
    mcp = _read_json(root / ".mcp.json")
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        raise InventoryError(f"installed mcpServers missing: {root}")
    result = _common(root, package.get("version"))
    result["mcp_servers"] = sorted(servers)
    result["mcp_entrypoints"] = {
        name: _plugin_entrypoint(value)
        for name, value in sorted(servers.items())
        if isinstance(value, dict)
    }
    return result


def from_npm(root: Path, runtime_names: dict[str, str]) -> dict[str, Any]:
    """Inspect npm package using its bundled runtime adapter paths."""
    package = _read_json(root / "package.json")
    runtime_paths = {
        name: root / "mcp" / short / "server.py"
        for name, short in runtime_names.items()
    }
    result = _common(root, package.get("version"))
    result["mcp_servers"] = sorted(
        name for name, path in runtime_paths.items() if path.is_file()
    )
    result["mcp_entrypoints"] = {
        name: path.relative_to(root).as_posix()
        for name, path in sorted(runtime_paths.items()) if path.is_file()
    }
    return result


def from_source(
    root: Path,
    *,
    expected_mcp_tools: dict[str, str],
) -> dict[str, Any]:
    """Build canonical expectations from package-owned source files."""
    plugin = _read_json(root / ".claude-plugin" / "plugin.json")
    package = _read_json(root / "package.json")
    version = plugin.get("version")
    if not isinstance(version, str) or not version:
        raise InventoryError("local plugin version missing")
    if package.get("version") != version:
        raise InventoryError("local plugin/npm version drift")
    mcp = _read_json(root / ".mcp.json")
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        raise InventoryError("local .mcp.json mcpServers missing")
    names = sorted(servers)
    if set(names) != set(expected_mcp_tools):
        raise InventoryError(f"local MCP inventory drift: {names}")
    result = _common(root, version)
    result["mcp_servers"] = names
    result["mcp_entrypoints"] = {
        name: _plugin_entrypoint(value)
        for name, value in sorted(servers.items())
        if isinstance(value, dict)
    }
    return result


def _plugin_entrypoint(spec: dict[str, Any]) -> str:
    args = spec.get("args")
    if not isinstance(args, list):
        return ""
    target = next((value for value in args if isinstance(value, str) and value.endswith("server.py")), "")
    return target.replace("${CLAUDE_PLUGIN_ROOT}/", "").replace("\\", "/")


def compare(actual: dict[str, Any], expected: dict[str, Any], label: str) -> dict[str, Any]:
    """Fail closed on every normalized public inventory field."""
    for key in ("version", "skills", "commands", "scripts", "mcp_servers", "mcp_entrypoints"):
        if actual.get(key) != expected.get(key):
            raise InventoryError(
                f"{label} {key} mismatch: expected {expected.get(key)!r}, "
                f"got {actual.get(key)!r}"
            )
    return actual
