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
Tier-1 paths are relative to PKG; Tier-2/3 paths are relative to --out / cwd.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PKG_DIR = _SCRIPTS_DIR.parent
_TEMPLATES_DIR = _SCRIPTS_DIR / "adapter_templates"

sys.path.insert(0, str(_SCRIPTS_DIR))
from adapter_matrix import MATRIX, get_agent  # noqa: E402


# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------


def _tmpl(name: str) -> str:
    """Load a template file from adapter_templates/."""
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Canonical-source readers
# ---------------------------------------------------------------------------


def _read_claude_plugin() -> dict:
    """Read .claude-plugin/plugin.json — version source of record."""
    path = _PKG_DIR / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _get_version() -> str:
    return _read_claude_plugin()["version"]


def _parse_fm(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML-lite frontmatter (single-line values only). Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([\w-]+):\s*(.+)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta, parts[2].lstrip("\n")


def _read_skills() -> list[dict]:
    """Return sorted skill dicts from skills/*/SKILL.md."""
    skills = []
    for d in sorted((_PKG_DIR / "skills").iterdir()):
        f = d / "SKILL.md"
        if not (d.is_dir() and f.is_file()):
            continue
        meta, body = _parse_fm(f.read_text(encoding="utf-8"))
        skills.append({
            "dirname": d.name,
            "name": meta.get("name", d.name),
            "description": meta.get("description", ""),
            "body": body,
        })
    return skills


def _read_commands() -> list[dict]:
    """Return sorted command dicts from commands/*.md."""
    cmds = []
    for f in sorted((_PKG_DIR / "commands").glob("*.md")):
        meta, body = _parse_fm(f.read_text(encoding="utf-8"))
        # Commands have no `name:` key; use the filename stem.
        cmds.append({
            "name": f.stem,
            "description": meta.get("description", ""),
            "body": body,
        })
    return cmds


# ---------------------------------------------------------------------------
# MCP server path helpers
# ---------------------------------------------------------------------------


def _mcp_servers_abs() -> dict[str, dict]:
    """Absolute-path MCP server specs (for Tier-2 consumer configs)."""
    preview = (_PKG_DIR / "mcp" / "preview" / "server.py").as_posix()
    evidence = (_PKG_DIR / "mcp" / "evidence" / "server.py").as_posix()
    return {
        "design-playbook-preview": {
            "command": "python",
            "args": [preview],
            "timeout": 3600000,
        },
        "design-playbook-evidence": {
            "command": "python",
            "args": [evidence],
            "env": {"DESIGN_PLAYBOOK_RUN_ROOT": ""},
            "timeout": 3600000,
        },
    }


# ---------------------------------------------------------------------------
# Merge-safe JSON helper
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. Unknown keys in base are preserved."""
    result = dict(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def merge_json_str(existing_text: str | None, our_data: dict) -> str:
    """Merge our_data into existing JSON text. Returns new serialised JSON string.

    Never removes keys present in existing_text that are absent from our_data.
    Stable ordering: existing keys first, then new keys from our_data.

    Raises ValueError if existing_text is present but malformed or not a JSON object.
    Callers that read from disk should catch this and surface it to the user — silent
    rebuild from empty would silently destroy the user's existing configuration.
    """
    base: dict = {}
    if existing_text:
        try:
            parsed = json.loads(existing_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"existing JSON is malformed and cannot be safely merged: {exc}. "
                "Fix or remove the file before running the generator."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"existing JSON root must be an object, got {type(parsed).__name__}. "
                "Fix or remove the file before running the generator."
            )
        base = parsed
    return json.dumps(_deep_merge(base, our_data), indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Markdown marker-block helper (for files that may pre-exist in user projects)
# ---------------------------------------------------------------------------

_BLOCK_BEGIN = "<!-- design-playbook:begin -->"
_BLOCK_END = "<!-- design-playbook:end -->"


def apply_marker_block(existing_text: str | None, version: str, block_content: str) -> str:
    """Return file content with our block inserted, replaced, or appended.

    Rules (idempotent):
    - existing_text is None (new file): return just the marker block.
    - Marker pair already present: replace only the block in-place; user content
      outside the markers is preserved exactly.
    - File exists but no markers: append our block after a blank line.

    The block_content must NOT include the marker tags themselves; they are
    added here.  The generated-by comment is the first line inside the block.
    """
    block = (
        f"{_BLOCK_BEGIN}\n"
        f"<!-- generated-by design-playbook v{version} -->\n"
        f"{block_content.rstrip()}\n"
        f"{_BLOCK_END}"
    )
    if existing_text is None:
        return block + "\n"

    if _BLOCK_BEGIN in existing_text and _BLOCK_END in existing_text:
        begin_idx = existing_text.index(_BLOCK_BEGIN)
        end_idx = existing_text.index(_BLOCK_END, begin_idx) + len(_BLOCK_END)
        return existing_text[:begin_idx] + block + existing_text[end_idx:]

    # File exists but has no markers — append
    return existing_text.rstrip("\n") + "\n\n" + block + "\n"


# ---------------------------------------------------------------------------
# SHA-256 helper
# ---------------------------------------------------------------------------


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Codex renderer (Tier 1)
# ---------------------------------------------------------------------------

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


def _render_codex_plugin_json(version: str) -> str:
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
    body = _tmpl("codex-agents.md")
    return f"<!-- generated-by design-playbook v{version} -->\n{body}"


def _codex_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    return [
        (".codex-plugin/plugin.json", _render_codex_plugin_json(version)),
        (".codex-plugin/mcp.json", _render_codex_mcp_json()),
        ("codex/AGENTS.md", _render_codex_agents_md(version)),
    ]


# ---------------------------------------------------------------------------
# Cursor renderer (Tier 2)
# ---------------------------------------------------------------------------

_GENERATED_BY_MDC = "<!-- generated-by design-playbook v{version} -->\n"


def _cursor_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    skills = _read_skills()
    commands = _read_commands()
    header = _GENERATED_BY_MDC.format(version=version)

    # One .mdc rule file per skill
    for skill in skills:
        always_apply = "true" if skill["dirname"] == "design-playbook" else "false"
        content = (
            f"{header}"
            f"---\n"
            f"description: {skill['description']}\n"
            f"alwaysApply: {always_apply}\n"
            f"---\n"
            f"{skill['body']}"
        )
        files.append((f".cursor/rules/{skill['dirname']}.mdc", content))

    # Commands reference file (no native slash commands in Cursor)
    cmd_lines = [
        f"{header}---\n"
        "description: design-playbook commands — use these as prompt templates\n"
        "alwaysApply: false\n"
        "---\n"
        "# design-playbook Commands\n\n"
        "Cursor has no native slash-command equivalent. Use these as prompt templates "
        "by pasting the relevant section into the chat.\n\n"
    ]
    for cmd in commands:
        cmd_lines.append(f"## /{cmd['name']}\n\n{cmd['description']}\n\n")
        cmd_lines.append(f"{cmd['body']}\n")
    files.append((".cursor/rules/design-playbook-commands.mdc", "".join(cmd_lines)))

    # MCP note (explanation; JSON can't carry comments)
    files.append((".cursor/rules/design-playbook-mcp.mdc", _tmpl("cursor-mcp-note.mdc")))

    # Actual .cursor/mcp.json — merge-safe with any existing config
    mcp_servers = _mcp_servers_abs()
    cursor_servers = {}
    for name, srv in mcp_servers.items():
        entry: dict = {"type": "stdio", "command": srv["command"], "args": srv["args"]}
        if "env" in srv and any(v for v in srv["env"].values()):
            entry["env"] = srv["env"]
        cursor_servers[name] = entry
    existing_mcp_path = out_dir / ".cursor" / "mcp.json"
    existing_text = existing_mcp_path.read_text(encoding="utf-8") if existing_mcp_path.is_file() else None
    files.append((".cursor/mcp.json", merge_json_str(existing_text, {"mcpServers": cursor_servers})))

    return files


# ---------------------------------------------------------------------------
# Gemini CLI renderer (Tier 2)
# ---------------------------------------------------------------------------


def _gemini_cli_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    skills = _read_skills()
    commands = _read_commands()

    # GEMINI.md — marker-block (may pre-exist in consumer project)
    orchestrator = next((s for s in skills if s["dirname"] == "design-playbook"), None)
    sub_skills = [s for s in skills if s["dirname"] != "design-playbook"]
    gemini_block_parts = ["# design-playbook\n\n"]
    if orchestrator:
        gemini_block_parts.append(orchestrator["body"])
        gemini_block_parts.append("\n")
    gemini_block_parts.append("## Sub-skills\n\n")
    for sk in sub_skills:
        gemini_block_parts.append(f"- **{sk['name']}**: {sk['description']}\n")
    gemini_md_path = out_dir / "GEMINI.md"
    existing_gemini = gemini_md_path.read_text(encoding="utf-8") if gemini_md_path.is_file() else None
    files.append(("GEMINI.md", apply_marker_block(existing_gemini, version, "".join(gemini_block_parts))))

    # .gemini/commands/<name>.toml per command (our namespaced dir — whole-file)
    for cmd in commands:
        prompt_body = cmd["body"].replace("$ARGUMENTS", "{{args}}")
        content = (
            f"# generated-by design-playbook v{version}\n"
            f'description = "{cmd["description"]}"\n\n'
            f"prompt = '''\n{prompt_body}\n'''\n"
        )
        files.append((f".gemini/commands/{cmd['name']}.toml", content))

    # .gemini/settings.json — merge-safe mcpServers
    mcp_servers = _mcp_servers_abs()
    gemini_servers: dict = {}
    for name, srv in mcp_servers.items():
        entry: dict = {"command": srv["command"], "args": srv["args"]}
        if "env" in srv:
            entry["env"] = srv["env"]
        gemini_servers[name] = entry
    existing_path = out_dir / ".gemini" / "settings.json"
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else None
    files.append((".gemini/settings.json", merge_json_str(existing_text, {"mcpServers": gemini_servers})))

    return files


# ---------------------------------------------------------------------------
# OpenCode renderer (Tier 2)
# ---------------------------------------------------------------------------


def _opencode_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    skills = _read_skills()
    commands = _read_commands()

    # AGENTS.md — marker-block (may pre-exist in consumer project)
    orchestrator = next((s for s in skills if s["dirname"] == "design-playbook"), None)
    sub_skills = [s for s in skills if s["dirname"] != "design-playbook"]
    block_parts = ["# design-playbook\n\n"]
    if orchestrator:
        block_parts.append(orchestrator["body"])
        block_parts.append("\n")
    block_parts.append("## Sub-skills\n\n")
    for sk in sub_skills:
        block_parts.append(f"- **{sk['name']}**: {sk['description']}\n")
    block_parts.append("\n## Commands\n\n")
    block_parts.append(
        "Use `/init` to regenerate or `/share` to share context. "
        "The following design-playbook commands are available as prompt templates:\n\n"
    )
    for cmd in commands:
        block_parts.append(f"### /{cmd['name']}\n\n{cmd['description']}\n\n{cmd['body']}\n")
    agents_md_path = out_dir / "AGENTS.md"
    existing_agents = agents_md_path.read_text(encoding="utf-8") if agents_md_path.is_file() else None
    files.append(("AGENTS.md", apply_marker_block(existing_agents, version, "".join(block_parts))))

    # opencode.json — merge-safe mcp key
    mcp_servers = _mcp_servers_abs()
    opencode_mcp: dict = {}
    for name, srv in mcp_servers.items():
        entry: dict = {"command": srv["command"], "args": srv["args"]}
        if "env" in srv:
            entry["env"] = srv["env"]
        opencode_mcp[name] = entry
    existing_path = out_dir / "opencode.json"
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else None
    files.append(("opencode.json", merge_json_str(existing_text, {"mcp": opencode_mcp})))

    return files


# ---------------------------------------------------------------------------
# Windsurf renderer (Tier 2)
# ---------------------------------------------------------------------------


def _windsurf_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    skills = _read_skills()
    commands = _read_commands()
    header = f"<!-- generated-by design-playbook v{version} -->\n"

    # One .md rule file per skill
    for skill in skills:
        content = (
            f"{header}"
            f"# {skill['name']}\n\n"
            f"{skill['body']}"
        )
        files.append((f".windsurf/rules/{skill['dirname']}.md", content))

    # Workflow files for each command (invoked as /design-playbook-<cmd>)
    for cmd in commands:
        content = (
            f"{header}"
            f"# design-playbook: {cmd['name']}\n\n"
            f"{cmd['description']}\n\n"
            f"{cmd['body']}"
        )
        files.append((f".windsurf/workflows/design-playbook-{cmd['name']}.md", content))

    # MCP setup guide (NEVER write the global config file itself — ADR-0042 §4)
    files.append(("design-playbook-mcp-setup.md", _tmpl("windsurf-mcp-guide.md")))

    return files


# ---------------------------------------------------------------------------
# GitHub Copilot renderer (Tier 2)
# ---------------------------------------------------------------------------


def _github_copilot_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    skills = _read_skills()
    header = f"<!-- generated-by design-playbook v{version} -->\n"

    # .github/copilot-instructions.md — marker-block (may pre-exist)
    orchestrator = next((s for s in skills if s["dirname"] == "design-playbook"), None)
    sub_skills = [s for s in skills if s["dirname"] != "design-playbook"]
    instr_block_parts = ["# design-playbook\n\n"]
    if orchestrator:
        instr_block_parts.append(orchestrator["body"])
        instr_block_parts.append("\n")
    instr_block_parts.append("## Sub-skills\n\n")
    for sk in sub_skills:
        instr_block_parts.append(f"- **{sk['name']}**: {sk['description']}\n")
    copilot_instr_path = out_dir / ".github" / "copilot-instructions.md"
    existing_instr = copilot_instr_path.read_text(encoding="utf-8") if copilot_instr_path.is_file() else None
    files.append((".github/copilot-instructions.md",
                  apply_marker_block(existing_instr, version, "".join(instr_block_parts))))

    # .github/instructions/<skill>.instructions.md per skill (our namespaced dir — whole-file)
    for skill in skills:
        content = (
            f"{header}"
            f"---\n"
            f"applyTo: \"**\"\n"
            f"---\n"
            f"# {skill['name']}\n\n"
            f"{skill['body']}"
        )
        files.append((f".github/instructions/{skill['dirname']}.instructions.md", content))

    # .mcp.json — solution-level MCP config (VS / Copilot format), merge-safe
    mcp_servers = _mcp_servers_abs()
    vs_servers: dict = {}
    for name, srv in mcp_servers.items():
        entry: dict = {"type": "stdio", "command": srv["command"], "args": srv["args"]}
        if "env" in srv:
            entry["env"] = srv["env"]
        vs_servers[name] = entry
    existing_path = out_dir / ".mcp.json"
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else None
    files.append((".mcp.json", merge_json_str(existing_text, {"servers": vs_servers})))

    return files


# ---------------------------------------------------------------------------
# Renderer dispatch
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tier-3 generic renderer (AGENTS.md floor for all 22 tier-3 agents)
# ---------------------------------------------------------------------------


def _tier3_files(version: str, out_dir: Path) -> list[tuple[str, str]]:
    """One AGENTS.md with orchestrator contract, sub-skills, commands, and MCP guide."""
    skills = _read_skills()
    commands = _read_commands()
    mcp_servers = _mcp_servers_abs()

    orchestrator = next((s for s in skills if s["dirname"] == "design-playbook"), None)
    sub_skills = [s for s in skills if s["dirname"] != "design-playbook"]

    preview_path = mcp_servers["design-playbook-preview"]["args"][0]
    evidence_path = mcp_servers["design-playbook-evidence"]["args"][0]

    block_parts: list[str] = ["# design-playbook\n\n"]

    # Orchestrator contract
    if orchestrator:
        block_parts.append(orchestrator["body"])
        block_parts.append("\n")

    # Sub-skill index
    block_parts.append("## Sub-skills\n\n")
    for sk in sub_skills:
        block_parts.append(f"- **{sk['name']}**: {sk['description']}\n")

    # Commands as copy-paste prompt equivalents
    block_parts.append("\n## Commands\n\n")
    block_parts.append(
        "The following design-playbook commands are available as copy-paste "
        "prompt templates. Invoke them directly in your agent chat.\n\n"
    )
    for cmd in commands:
        block_parts.append(f"### /{cmd['name']}\n\n{cmd['description']}\n\n{cmd['body']}\n")

    # Inline MCP install guide
    block_parts.append(
        "## MCP install guide\n\n"
        "Two optional MCP servers enable preview (G5) and evidence (G6) gates.\n"
        "Install the package as a **persistent dependency** (not ephemeral `npx`)\n"
        "so the absolute paths below remain valid across sessions.\n\n"
        "```bash\n"
        "npm install --save-dev design-playbook   # or: pip install playwright\n"
        "```\n\n"
        "Add to your agent's MCP config (key names are `mcpServers` or `mcp`\n"
        "depending on your platform — see platform docs):\n\n"
        "```json\n"
        "{\n"
        '  "design-playbook-preview": {\n'
        '    "command": "python",\n'
        f'    "args": ["{preview_path}"]\n'
        "  },\n"
        '  "design-playbook-evidence": {\n'
        '    "command": "python",\n'
        f'    "args": ["{evidence_path}"],\n'
        '    "env": { "DESIGN_PLAYBOOK_RUN_ROOT": "<your-project-root>" }\n'
        "  }\n"
        "}\n"
        "```\n\n"
        "Both servers implement the absent→skip contract: if a tool probe finds "
        "them absent, the orchestrator skips the corresponding gate — no crash.\n"
        "`design-playbook-evidence` requires "
        "`pip install playwright && playwright install chromium`.\n"
    )

    agents_md_path = out_dir / "AGENTS.md"
    existing = agents_md_path.read_text(encoding="utf-8") if agents_md_path.is_file() else None
    return [("AGENTS.md", apply_marker_block(existing, version, "".join(block_parts)))]


# ---------------------------------------------------------------------------
# Renderer dispatch
# ---------------------------------------------------------------------------

_TIER3_RENDERER_AGENTS = (
    "qoder", "kiro-ide", "kiro-cli", "amp", "auggie", "codebuddy", "forge",
    "ibm-bob", "jules", "kilo-code", "pi", "qwen-code", "roo-code", "shai",
    "tabnine", "mistral-vibe", "kimi-code", "iflow", "junie", "antigravity",
    "trae", "generic",
)

_RENDERERS: dict[str, object] = {
    "codex": _codex_files,
    "cursor": _cursor_files,
    "gemini-cli": _gemini_cli_files,
    "opencode": _opencode_files,
    "windsurf": _windsurf_files,
    "github-copilot": _github_copilot_files,
    **{agent: _tier3_files for agent in _TIER3_RENDERER_AGENTS},
}


def render(agent: str, out_dir: Path | None = None, *, dry_run: bool = False) -> dict:
    """Render adapter artifacts for *agent*. Returns the manifest dict.

    When *dry_run* is True, no files are written.
    Tier-1 agents default out_dir to PKG; Tier-2/3 default to cwd.
    """
    row = get_agent(agent)
    if row is None:
        raise ValueError(f"unknown agent: {agent!r}")

    version = _get_version()

    renderer = _RENDERERS.get(agent)
    if renderer is None:
        raise NotImplementedError(
            f"no renderer for {agent!r} (tier {row.tier})"
        )

    if out_dir is None:
        out_dir = _PKG_DIR if row.tier == 1 else Path.cwd()

    files = renderer(version, out_dir)  # type: ignore[call-arg]

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
        help="Output directory (default: PKG for Tier-1, cwd for Tier-2/3)",
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
