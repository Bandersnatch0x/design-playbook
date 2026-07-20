#!/usr/bin/env python3
"""Install / runtime health check for design-playbook.

Read-only: reports whether the redistributable plugin surface is present,
versions agree, bundled MCP adapters are reachable, and optional local
adapter floor self-check can run. Does not mutate the tree or create tags.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    failures.append(msg)


def warn(msg: str) -> None:
    print(f"  WARN  {msg}")
    warnings.append(msg)


def read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return None
    if not isinstance(payload, dict):
        fail(f"{path.relative_to(ROOT)} must be a JSON object")
        return None
    return payload


def check_layout() -> None:
    print("== plugin layout ==")
    check_paths = [
        PKG / ".claude-plugin" / "plugin.json",
        PKG / ".mcp.json",
        PKG / "skills" / "design-playbook" / "SKILL.md",
        PKG / "commands" / "design-io.md",
        PKG / "mcp" / "preview" / "server.py",
        PKG / "mcp" / "evidence" / "server.py",
        PKG / "scripts" / "validate_run.py",
        PKG / "codex" / "AGENTS.md",
    ]
    for path in check_paths:
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file():
            ok(rel)
        else:
            fail(f"missing {rel}")


def check_versions() -> str:
    print("== versions ==")
    plugin = read_json(PKG / ".claude-plugin" / "plugin.json")
    market = read_json(ROOT / ".claude-plugin" / "marketplace.json")
    version = ""
    if plugin is not None:
        raw = plugin.get("version", "")
        version = raw if isinstance(raw, str) else ""
        if SEMVER.fullmatch(version):
            ok(f"plugin.json version {version}")
        else:
            fail(f"plugin.json version not semver: {version!r}")
    if market is not None:
        meta = market.get("metadata", {})
        plugins = market.get("plugins", [])
        meta_v = meta.get("version", "") if isinstance(meta, dict) else ""
        entry = plugins[0] if isinstance(plugins, list) and plugins else {}
        plug_v = entry.get("version", "") if isinstance(entry, dict) else ""
        if version and version == meta_v == plug_v:
            ok(f"marketplace versions match {version}")
        else:
            fail(
                f"version mismatch plugin={version!r} "
                f"market.meta={meta_v!r} market.plugin={plug_v!r}"
            )
    return version


def check_mcp() -> None:
    print("== bundled MCP ==")
    mcp_path = PKG / ".mcp.json"
    payload = read_json(mcp_path)
    if payload is None:
        return
    raw = mcp_path.read_text(encoding="utf-8")
    if "${CLAUDE_PLUGIN_ROOT}" in raw:
        ok(".mcp.json uses ${CLAUDE_PLUGIN_ROOT}")
    else:
        fail(".mcp.json missing ${CLAUDE_PLUGIN_ROOT}")
    servers = payload.get("mcpServers", {})
    if not isinstance(servers, dict):
        fail(".mcp.json mcpServers must be an object")
        return
    for name in ("design-playbook-preview", "design-playbook-evidence"):
        if name in servers:
            ok(f"registers {name}")
        else:
            fail(f"missing mcp server {name}")


def check_floor_self_check(*, skip: bool) -> None:
    print("== preview floor self-check ==")
    if skip:
        warn("skipped (--skip-self-check)")
        return
    server = PKG / "mcp" / "preview" / "server.py"
    if not server.is_file():
        fail("preview server missing; cannot self-check")
        return
    result = subprocess.run(
        [sys.executable, str(server), "--self-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and "FLOOR SELF-CHECK PASSED" in result.stdout:
        ok("FLOOR SELF-CHECK PASSED")
        return
    fail(f"floor self-check failed (exit {result.returncode})")
    if result.stdout.strip():
        print(result.stdout[-400:])
    if result.stderr.strip():
        print(result.stderr[-400:])


def check_launchers() -> None:
    print("== compatibility launchers ==")
    for rel in (
        "packages/design-playbook-preview/server.py",
        "packages/design-playbook-evidence/server.py",
    ):
        path = ROOT / rel
        if path.is_file():
            ok(rel)
        else:
            warn(f"missing optional launcher {rel}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="design-playbook doctor")
    parser.add_argument(
        "--skip-self-check",
        action="store_true",
        help="skip preview floor self-check (faster CI-friendly path)",
    )
    args = parser.parse_args(argv)

    check_layout()
    check_versions()
    check_mcp()
    check_launchers()
    check_floor_self_check(skip=args.skip_self_check)

    print()
    if failures:
        print(f"DOCTOR FAILED: {len(failures)} issue(s)")
        if warnings:
            print(f"({len(warnings)} warning(s))")
        return 1
    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    print(f"DOCTOR PASSED{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
