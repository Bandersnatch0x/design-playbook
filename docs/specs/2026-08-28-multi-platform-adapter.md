# Multi-platform adapter — implementation spec (2026-08-28)

- **Authority:** ADR-0042 (generator, npm shim → Python, three tiers). Research
  snapshots: `.scratch/platform-adapter/research.md` + `research2.md`
  (local working notes; the durable facts live here).
- **Canonical sources:** `packages/design-playbook/skills/`, `commands/`,
  `mcp/`, `.mcp.json`. Version source: `.claude-plugin/plugin.json`.

## 1. Platform capability matrix (initial rows)

| Agent | Tier | Rules target | Commands target | MCP (project-level) | Notes |
|---|---|---|---|---|---|
| Claude Code | 1 | native plugin (`skills/`) | `commands/*.md` | `.mcp.json` (`${CLAUDE_PLUGIN_ROOT}`) | existing, untouched |
| Codex | 1 | `.codex-plugin/` + `codex/AGENTS.md` | `$name` skills | `.codex-plugin/mcp.json` | becomes generated snapshot |
| Cursor | 2 | `.cursor/rules/<name>.mdc` (frontmatter: `description`, `alwaysApply: false`; orchestrator `alwaysApply: true`) | none — prompt docs | `.cursor/mcp.json` (stdio) | no slash commands |
| Gemini CLI | 2 | `GEMINI.md` section | `.gemini/commands/<name>.toml` (`{{args}}`) | `.gemini/settings.json` `mcpServers` | |
| OpenCode | 2 | `AGENTS.md` | prompt docs | `opencode.json` `mcp` | |
| Windsurf | 2 | `.windsurf/rules/<name>.md` | `/workflow` files | none project-level — emit guide + snippet for `~/.codeium/windsurf/mcp_config.json` | never write user global config |
| GitHub Copilot | 2 | `.github/copilot-instructions.md` + `.github/instructions/*.instructions.md` (`applyTo`) | none — prompt docs | `.mcp.json` (VS/solution) | |
| Qoder, Kiro (IDE/CLI), Amp, Auggie, CodeBuddy, Forge, IBM Bob, Jules, Kilo Code, Pi, Qwen Code, Roo Code (one agent, `roo-code`), SHAI, Tabnine, Mistral Vibe, Kimi Code, iFlow, Junie, Antigravity, Trae, generic | 3 | generated `AGENTS.md` | inline prompt list in AGENTS.md | inline MCP install guide | one renderer for all; matrix rows may promote agents later |

Matrix lives as data (`scripts/adapter_matrix.py` or YAML) — one row per
agent with per-surface flags; renderers key off flags, not agent names.

## 2. Generator contract

```
python scripts/generate_adapter.py <agent> [--out <dir>] [--dry-run] [--list]
npx design-playbook init <agent>          # npm bin shim, same behavior
```

- Reads canonical sources; never mutates them.
- `--dry-run` prints the file manifest + content hashes (drift gate input).
- Output defaults to the consumer project root (except Tier-1 snapshots,
  which render into the repo package during CI/release).
- Rendered artifacts whose format can carry an in-band comment (the
  markdown/`.mdc` targets) carry a generated-by header with the
  playbook version; JSON targets cannot carry comments and are
  excluded (lockstep via plugin.json, satisfying release.py badges
  rule indirectly — no new hand-edited version site).

## 3. Slices (tracer bullets, sequential)

- **S1 — core + Tier-1 parity:** matrix data + renderer framework +
  Codex renderer reproducing `.codex-plugin/` + `codex/AGENTS.md`
  byte-stable (or intentionally updated in the same PR); npm `bin` shim
  (`lib/cli.js`); `validate.py` drift gate (dry-run diff vs committed
  snapshots); unit tests (renderer goldens, matrix schema, shim smoke).
- **S2 — Tier-2 renderers:** Cursor, Gemini CLI, OpenCode, Windsurf,
  Copilot per the matrix; per-platform golden tests; MCP config
  emission honoring install-time absent→skip; Windsurf guide file.
- **S3 — Tier-3 + disclosure:** AGENTS.md generic renderer for the full
  matrix; README capability-matrix section (zh+en, honest degradation
  wording); package README `init` usage; doctor check for generator
  health; release-checklist note.

## 4. Constraints

- One rule must not fork: generated Tier-1 snapshots are CI-verified
  against the generator; hand edits fail validate.py.
- No network at generate time; no writes outside `--out`/project root;
  never touch user-global config files.
- zh+en parity for any user-facing docs; prose-contract tests must stay
  green; all existing gates (validate/seam/adapter floor) green.
