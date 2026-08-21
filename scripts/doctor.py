#!/usr/bin/env python3
"""Install / runtime health check for design-playbook.

Read-only: reports whether the redistributable plugin surface is present,
versions agree, bundled MCP adapters are reachable, and optional local
adapter floor self-check can run. Does not mutate the tree or create tags.

See docs/agents/release-checklist.md 'Validation surfaces' for the split
between validate.py (static structure gate), release.py (publish gate),
and this script (read-only diagnostic aggregator).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# scripts/ must resolve even when doctor.py is imported in-process
# (tests/test_doctor.py) rather than run as `python scripts/doctor.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _checks

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

# Gate 1 structural expectations. Skills count is doctor-local (validate.py
# does not enforce it); the command set is derived from the shared policy
# module scripts/_checks.py (ADR-0015 / OPP-01 mirror rule) so doctor and
# validate can never disagree on what a version line ships. Keep the
# checklist wording in docs/agents/release-checklist.md in sync when the
# plugin surface grows or shrinks.
GATE1_EXPECTED_SKILLS = 8
GATE1_EXPECTED_PLUGIN_NAME = "design-playbook"

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


def info(msg: str) -> None:
    """Advisory line: never recorded as a failure or warning, so it cannot
    influence the doctor verdict or exit code (issue 64)."""
    print(f"  info  {msg}")


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
        # Issue #71: audit-preferences module is part of the shipped
        # scripts surface (package.json files[] ships scripts/); doctor
        # must fail closed if it disappears from the layout.
        PKG / "scripts" / "audit_preferences.py",
        PKG / "codex" / "AGENTS.md",
    ]
    for path in check_paths:
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file():
            ok(rel)
        else:
            fail(f"missing {rel}")


# Mirrors release.py check_version's three-point plugin.json/marketplace
# comparison (release.py additionally checks README badges + release notes).
# Keep in sync when version sites change.
def check_gate1_smoke() -> None:
    plugin = read_json(PKG / ".claude-plugin" / "plugin.json")
    plugin_version = plugin.get("version", "") if isinstance(plugin, dict) else ""
    expected_cmds = _checks.expected_commands(plugin_version)
    if expected_cmds is None:
        expected_cmds = frozenset()
        fail(
            f"plugin.json version {plugin_version!r} has no declared command "
            f"inventory (ADR-0015); add it to scripts/_checks.py"
        )
    print(
        "== gate 1 structural smoke "
        f"({GATE1_EXPECTED_SKILLS} skills / "
        f"{len(expected_cmds)} commands / namespace) =="
    )
    # Semi-automated gate 1 (release-checklist): the static counts a human
    # would eyeball in /help. The dynamic `claude --plugin-dir` load + /help
    # listing stay human (host slash, not automatable - see memory).
    skills_dir = PKG / "skills"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()] if skills_dir.is_dir() else []
    if len(skill_dirs) == GATE1_EXPECTED_SKILLS:
        ok(f"{GATE1_EXPECTED_SKILLS} skills present")
    else:
        fail(f"expected {GATE1_EXPECTED_SKILLS} skills, got {len(skill_dirs)}")
    commands_dir = PKG / "commands"
    cmds = sorted(commands_dir.glob("*.md")) if commands_dir.is_dir() else []
    shipped_names = frozenset(p.stem for p in cmds)
    if shipped_names == expected_cmds:
        ok(f"{len(expected_cmds)} commands present")
    else:
        fail(
            f"expected commands {sorted(expected_cmds)}, "
            f"got {sorted(shipped_names)}"
        )
    if plugin is not None:
        if plugin.get("name") == GATE1_EXPECTED_PLUGIN_NAME:
            ok(f"plugin.json name = {GATE1_EXPECTED_PLUGIN_NAME}")
        else:
            fail(
                f"plugin.json name = {plugin.get('name')!r}, "
                f"expected {GATE1_EXPECTED_PLUGIN_NAME}"
            )


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


def check_release_group() -> None:
    print("== npm release group ==")
    main_manifest = read_json(PKG / "package.json")
    dsh_manifest = read_json(
        ROOT / "packages" / "dsh-design-playbook" / "package.json"
    )
    errors = _checks.release_group_errors(main_manifest, dsh_manifest)
    if errors:
        for message in errors:
            fail(message)
        return
    ok("design-playbook and dsh-design-playbook versions/dependency match")


# Mirrors validate.py bundled-MCP gate (.mcp.json present + both servers
# registered + ${CLAUDE_PLUGIN_ROOT}); validate.py additionally checks the
# bundled server.py runtime files exist. Keep in sync when adapter layout
# changes.
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


# Mirrors validate.py Codex manifest section (issue 07, ADR-0009). doctor is
# read-only, so this only reports drift rather than gating a release; the
# authoritative gate lives in validate.py / release.py. Keep in sync when
# the Codex dual-publish surface changes.
#
# Split into three single-responsibility helpers (H3) so each check is
# independently testable with a crafted payload, without standing up the
# full four-file fixture the orchestrator reads. ``check_codex_manifest``
# only loads the manifests and dispatches; behaviour is unchanged.
def _check_codex_plugin_version(
    claude_version: str, codex_plugin: dict | None
) -> None:
    """Surface Claude vs Codex ``plugin.json`` version drift (issue 07 / H5)."""
    if codex_plugin is None:
        return
    raw = codex_plugin.get("version", "")
    codex_version = raw if isinstance(raw, str) else ""
    if codex_version and codex_version == claude_version:
        ok(f".codex-plugin/plugin.json version matches Claude ({codex_version})")
    else:
        fail(
            f".codex-plugin/plugin.json version drift: "
            f"codex={codex_version!r}, claude={claude_version!r}"
        )


def _check_codex_mcp_targets(codex_mcp: dict | None) -> None:
    """Verify each Codex MCP server is registered and its ``args[0]`` resolves."""
    if codex_mcp is None:
        return
    servers = codex_mcp.get("mcpServers", {})
    servers = servers if isinstance(servers, dict) else {}
    for name in ("design-playbook-preview", "design-playbook-evidence"):
        entry = servers.get(name)
        if not isinstance(entry, dict):
            fail(f".codex-plugin/mcp.json missing server {name}")
            continue
        ok(f".codex-plugin/mcp.json registers {name}")
        raw_args = entry.get("args", [])
        args_list = raw_args if isinstance(raw_args, list) else []
        target_arg = args_list[0] if args_list and isinstance(args_list[0], str) else ""
        if not target_arg:
            fail(f".codex-plugin/mcp.json {name} missing args[0] path")
            continue
        target = PKG / target_arg
        if target.is_file():
            ok(f".codex-plugin/mcp.json {name} target exists: {target_arg}")
        else:
            fail(f".codex-plugin/mcp.json {name} target missing: {target_arg}")


def _check_agents_marketplace(agents_market: dict | None) -> None:
    """Verify ``.agents`` marketplace ``plugins[0].source.path`` resolves."""
    if agents_market is None:
        return
    plugins = agents_market.get("plugins", [])
    plugins = plugins if isinstance(plugins, list) else []
    if not plugins:
        fail(".agents marketplace lists no plugin")
    elif isinstance(plugins[0], dict):
        src = plugins[0].get("source", "")
        src_path = ""
        if isinstance(src, dict):
            raw_path = src.get("path", "")
            src_path = raw_path if isinstance(raw_path, str) else ""
        elif isinstance(src, str):
            src_path = src
        if not src_path:
            fail(".agents marketplace plugins[0].source.path missing")
        elif (ROOT / src_path).is_dir():
            ok(f".agents marketplace plugins[0].source.path exists: {src_path}")
        else:
            fail(
                ".agents marketplace plugins[0].source.path "
                f"missing on disk: {src_path}"
            )


def check_codex_manifest() -> None:
    print("== Codex manifest (ADR-0009 dual-publish) ==")
    claude_plugin = read_json(PKG / ".claude-plugin" / "plugin.json")
    codex_plugin = read_json(PKG / ".codex-plugin" / "plugin.json")
    codex_mcp = read_json(PKG / ".codex-plugin" / "mcp.json")
    agents_market = read_json(ROOT / ".agents" / "plugins" / "marketplace.json")

    claude_version = ""
    if claude_plugin is not None:
        raw = claude_plugin.get("version", "")
        claude_version = raw if isinstance(raw, str) else ""

    _check_codex_plugin_version(claude_version, codex_plugin)
    _check_codex_mcp_targets(codex_mcp)
    _check_agents_marketplace(agents_market)


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


# Issue 64: declarative reminder only. Host vision capability is
# self-declared by the host model; doctor must not probe or infer it
# (maintainer decision: automatic detection is technically unreliable).
# Wording mirrors CONTEXT.md "No-run disposition" and ADR-0032
# consequences: vision-capable hosts may inspect images directly;
# text-only hosts retain an explicit limitation. Keep in sync if the
# multimodal posture changes.
def check_host_vision() -> None:
    print("== host vision capability (self-declared) ==")
    info(
        "screenshot understanding depends on the host model's vision "
        "support; this capability is self-declared by the host model -- "
        "doctor does not auto-detect it"
    )
    info(
        "confirm the host supports vision input before using screenshots "
        "as a requirement source; text-only hosts should ask the user for "
        "a written description instead (reference-intake falls back to "
        "text explanations)"
    )


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
    check_gate1_smoke()
    check_versions()
    check_release_group()
    check_mcp()
    check_codex_manifest()
    check_host_vision()
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
