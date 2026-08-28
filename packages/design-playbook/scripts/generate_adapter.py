#!/usr/bin/env python3
"""Multi-platform adapter generator (ADR-0042).

Usage:
  python packages/design-playbook/scripts/generate_adapter.py <agent> [--out <dir>]
  python packages/design-playbook/scripts/generate_adapter.py <agent> --dry-run
  python packages/design-playbook/scripts/generate_adapter.py --list

Tier-1 agents (codex) regenerate committed snapshots inside the package.
Tier-2/3 agents write into --out (defaults to cwd of the caller).

Dry-run prints a JSON manifest to stdout:
  {"agent": "...", "version": "...", "files": [{"path": "...", "sha256": "..."}]}
All paths in the manifest are relative to the package root (PKG).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PKG_DIR = _SCRIPTS_DIR.parent

sys.path.insert(0, str(_SCRIPTS_DIR))
from adapter_matrix import MATRIX, get_agent  # noqa: E402


# ---------------------------------------------------------------------------
# Canonical-source readers
# ---------------------------------------------------------------------------


def _read_claude_plugin() -> dict:
    """Read .claude-plugin/plugin.json — version source of record."""
    path = _PKG_DIR / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _get_version() -> str:
    return _read_claude_plugin()["version"]


# ---------------------------------------------------------------------------
# Codex renderer
# ---------------------------------------------------------------------------

# Codex-specific additions not derivable from .claude-plugin/plugin.json.
# These are stable and change only with deliberate product decisions.
_CODEX_PLUGIN_EXTRA = {
    "author_url": "https://github.com/Bandersnatch0x",
    "homepage": "https://github.com/Bandersnatch0x/design-playbook",
    "repository": "https://github.com/Bandersnatch0x/design-playbook",
    "skills": "./skills/",
    "mcpServers": "./.codex-plugin/mcp.json",
    "interface": {
        "displayName": "design-playbook",
        "shortDescription": "Design I/O declarations + contracts for product UI",
        "developerName": "Bandersnatch0x",
        "category": "Design",
        "brandColor": "#2DD4BF",
        "websiteURL": "https://github.com/Bandersnatch0x/design-playbook",
    },
}

# Codex AGENTS.md body (below the generated-by comment).
# This is the canonical Codex bridge document for the design-playbook agent.
# Edit here to update the committed codex/AGENTS.md — the generator owns the
# canonical form. The drift gate in validate.py catches any committed divergence.
_CODEX_AGENTS_MD_BODY = """\
# design-playbook for Codex

## Install (path of record)

Marketplace catalog lives at the **repo root** (same GitHub repo as Claude Code).

```bash
# published
codex plugin marketplace add Bandersnatch0x/design-playbook
codex plugin add design-playbook@design-playbook

# local monorepo (dev)
codex plugin marketplace add <abs-path-to-repo-root>
codex plugin add design-playbook@design-playbook
```

Verify:

```bash
codex plugin list -m design-playbook --available --json
# expect: design-playbook@design-playbook, enabled=true after add
```

Codex-native manifest: `packages/design-playbook/.codex-plugin/plugin.json`  
Codex MCP (relative paths, no `CLAUDE_PLUGIN_ROOT`): `.codex-plugin/mcp.json`  
Skills: `packages/design-playbook/skills/*`

## Fallback: skills-only install

If you only want skills under `~/.codex/skills` (no plugin marketplace):

```bash
# from repo root — copies/symlinks skill trees into ~/.codex/skills
python packages/design-playbook/codex/install_skills.py --force
# or @-reference a single skill:
#   @packages/design-playbook/skills/design-playbook/SKILL.md
```

Register MCP directly (fallback when `codex plugin add` is unavailable):

`codex plugin add` depends on a healthy codex marketplace subsystem. If `codex doctor`
or `codex plugin marketplace list` fails (e.g. a stale marketplace source path), register
the servers directly in `~/.codex/config.toml` (or your `CODEX_HOME`):

```toml
# ~/.codex/config.toml  (or $CODEX_HOME/config.toml)
[mcp_servers.design-playbook-preview]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/preview/server.py"]

[mcp_servers.design-playbook-evidence]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/evidence/server.py"]
# evidence also needs: pip install playwright && playwright install chromium
```

Verify: `codex mcp list` should list both. `preview*` needs a system Edge/Chrome (the
adapter spawns it via `--app=`); `observe*` needs Playwright + Chromium.

> **`preview*` silently skips when `preview_prototype` is absent.** If preview does not
> appear, the orchestrator probed `tools/list`, found no `preview_prototype`, and skipped
> G5 - this is designed skip behaviour, not a crash. Confirm the tool is registered
> (`codex mcp list`) before treating it as a preview failure. Codex end-to-end preview
> smoke is not yet validated (v0.4.4 deferred the codex E2E smoke; only evidence/G6 was
> server-level smoked).

## Load order

1. `skills/design-playbook/SKILL.md`
2. Standard order: `design-baseline?` → `ux-spec` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Conditional entry `design-baseline?` (ADR-0012) runs before `reference-intake?` when the router returns `requires_baseline`. Existing-product Fill requires a valid existing baseline, an accepted generated baseline, or an explicit user waiver.

Conditional entry `reference-intake?` (screenshot/URL/design/product analogy, ADR-0011) runs **before** `ux-spec?` when the router returns `requires_reference_contract` — fixed orchestrator order, not reorderable. Run `native-craft` only for an explicit native-desktop/native-feel target. Web and mobile Web skip `native-craft`; if the platform is unclear, ask before choosing the order. The orchestrator owns the decision gate, render-surface seam handoff, and fail-closed behavior.

Mirror the orchestrator's skip narration (SKILL.md Steps preamble): when a step is skipped, output one line — step name + reason + how to enable, with the gate label when one applies, e.g. `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.

Audit preferences (ADR-0033) apply identically on Codex. Follow `skills/design-playbook/SKILL.md` § *Audit preferences* as sole authority; this bridge adds no host-specific preference rules.

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
"""


def _render_codex_plugin_json(version: str) -> str:
    """Render .codex-plugin/plugin.json from canonical sources."""
    src = _read_claude_plugin()
    data = {
        "name": src["name"],
        "version": version,
        "description": src["description"],
        "author": {
            "name": src["author"]["name"],
            "url": _CODEX_PLUGIN_EXTRA["author_url"],
        },
        "homepage": _CODEX_PLUGIN_EXTRA["homepage"],
        "repository": _CODEX_PLUGIN_EXTRA["repository"],
        "license": src["license"],
        "keywords": src["keywords"],
        "skills": _CODEX_PLUGIN_EXTRA["skills"],
        "mcpServers": _CODEX_PLUGIN_EXTRA["mcpServers"],
        "interface": _CODEX_PLUGIN_EXTRA["interface"],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render_codex_mcp_json() -> str:
    """Render .codex-plugin/mcp.json (stable; paths relative to install cwd)."""
    data = {
        "mcpServers": {
            "design-playbook-preview": {
                "command": "python",
                "args": ["./mcp/preview/server.py"],
                "cwd": ".",
                "timeout": 3600000,
            },
            "design-playbook-evidence": {
                "command": "python",
                "args": ["./mcp/evidence/server.py"],
                "cwd": ".",
                "env_vars": ["DESIGN_PLAYBOOK_RUN_ROOT"],
                "timeout": 3600000,
            },
        }
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _render_codex_agents_md(version: str) -> str:
    """Render codex/AGENTS.md with a generated-by header."""
    return f"<!-- generated-by design-playbook v{version} -->\n{_CODEX_AGENTS_MD_BODY}"


# ---------------------------------------------------------------------------
# Renderer dispatch
# ---------------------------------------------------------------------------


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _codex_files(version: str) -> list[tuple[str, str]]:
    """Return [(pkg-relative-path, content)] for all Codex artifacts."""
    return [
        (".codex-plugin/plugin.json", _render_codex_plugin_json(version)),
        (".codex-plugin/mcp.json", _render_codex_mcp_json()),
        ("codex/AGENTS.md", _render_codex_agents_md(version)),
    ]


_RENDERERS: dict[str, object] = {
    "codex": _codex_files,
}


def render(agent: str, out_dir: Path | None = None, *, dry_run: bool = False) -> dict:
    """Render adapter artifacts for *agent*.

    Returns the manifest dict.  When *dry_run* is True, no files are written.
    When *out_dir* is None and agent is Tier 1, output goes into PKG.
    """
    row = get_agent(agent)
    if row is None:
        raise ValueError(f"unknown agent: {agent!r}")

    version = _get_version()

    renderer = _RENDERERS.get(agent)
    if renderer is None:
        raise NotImplementedError(
            f"no renderer for {agent!r} (tier {row.tier}); "
            "S2/S3 renderers are not yet implemented"
        )

    files = renderer(version)  # type: ignore[call-arg]

    if out_dir is None:
        out_dir = _PKG_DIR

    manifest = {
        "agent": agent,
        "version": version,
        "files": [
            {"path": rel, "sha256": _sha256(content)}
            for rel, content in files
        ],
    }

    if not dry_run:
        for rel, content in files:
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _list_agents() -> None:
    for row in MATRIX:
        renderer_note = "(renderer ready)" if row.agent in _RENDERERS else ""
        print(f"  {row.agent:<20} tier={row.tier}  {renderer_note}".rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_adapter",
        description="Render per-platform adapter artifacts from canonical sources.",
    )
    parser.add_argument(
        "agent",
        nargs="?",
        help="Agent identifier (see --list for options)",
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        help="Output directory (default: package root for Tier-1, cwd otherwise)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON manifest with content hashes; do not write files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print all agents in the capability matrix and exit",
    )
    args = parser.parse_args(argv)

    if args.list:
        _list_agents()
        return 0

    if not args.agent:
        parser.error("agent argument is required (or use --list)")

    out_dir = Path(args.out).resolve() if args.out else None

    try:
        manifest = render(args.agent, out_dir=out_dir, dry_run=args.dry_run)
    except (ValueError, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        for entry in manifest["files"]:
            print(f"  wrote  {entry['path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
