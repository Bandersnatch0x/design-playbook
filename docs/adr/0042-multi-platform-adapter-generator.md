# ADR-0042: Multi-platform adapter generator (three-tier fidelity)

Accepted (grilling + two research rounds, 2026-08-28). Extends ADR-0009
(Codex dual-publish) from one hand-maintained sibling manifest to a
generator that renders every platform surface from the canonical
sources.

## Context

The playbook ships natively for Claude Code and, via ADR-0009, Codex.
The user wants installs for the full modern agent matrix (28 agents:
Cursor, OpenCode, GitHub Copilot, Gemini CLI, Windsurf, Qoder, Kiro,
Amp, Trae, Antigravity, ...). Two research rounds
(`.scratch/platform-adapter/research{,2}.md`, snapshots summarized in
`docs/specs/2026-08-28-multi-platform-adapter.md`) surveyed
auto-embedded, spec-kit (upstream), ruler, rulesync, vibe-rules,
BMAD-METHOD, ai-rulez, and the Linux Foundation AGENTS.md standard.
Findings: npx is the dominant entry form (4/6 active tools); the two
strongest fidelity strategies are rulesync's per-agent capability flag
matrix and spec-kit's binary skills-vs-prompts tier gate; 22+ agents
natively read AGENTS.md, making it the generic floor. A strict
full-fidelity gate would ship only the two platforms that already
exist, so breadth requires explicit, honest degradation.

## Decision

1. **Generator, not N hand-built directories.**
   `scripts/generate_adapter.py` renders per-platform artifacts from
   the canonical `skills/`, `commands/`, and `mcp/` sources. One rule
   must not fork: hand-editing generated output is prohibited.
2. **Entry form: npm bin shim delegating to Python.**
   `package.json` gains `"bin"`; a small JS shim checks for Python and
   delegates. `npx design-playbook init <platform>` is the primary
   invocation; direct `python scripts/generate_adapter.py` remains
   equivalent.
3. **Three-tier fidelity model** (capability matrix is data, one row
   per agent, tracked in the repo):
   - **Tier 1 — full fidelity:** Claude Code, Codex — skills, commands,
     MCP registration, hooks where supported.
   - **Tier 2 — skills + MCP:** Cursor, Gemini CLI, OpenCode, Windsurf,
     GitHub Copilot — skills rendered into the platform's rules format,
     project-level MCP config where the platform supports it; commands
     degrade to documented prompt equivalents.
   - **Tier 3 — rules floor:** all matrix agents — a generated
     AGENTS.md carrying the orchestrator contract plus an MCP
     installation guide. AGENTS.md is the fallback for any agent
     without a dedicated renderer.
4. **Install-time absent→skip.** The runtime G5/G6 probe-and-skip
   contract extends to install time: the generator emits MCP config
   only where a project-level file exists (Windsurf's global-only MCP
   is documented, never written into user global config).
5. **`.codex-plugin/` becomes a generated, committed snapshot.**
   `validate.py` gains a drift gate: regenerate in dry-run and diff
   against committed Tier-1 snapshots; any mismatch fails the gate.
6. **Honest surface disclosure.** The capability matrix (tier, per-
   surface support) is published in the README; degraded surfaces are
   named, never silently dropped.

## Consequences

- New tracked spec: `docs/specs/2026-08-28-multi-platform-adapter.md`
  (platform matrix + artifact map + slice plan) is the implementation
  authority.
- `release.py` version-lockstep extends to generated manifests via the
  generator templates, not new hand-edited version sites.
- Adding an agent = adding a matrix row (+ renderer only if it rises
  above Tier 3); removing ADR-0009's hand-maintained status for
  `.codex-plugin/` supersedes that portion of ADR-0009 while keeping
  its dual-publish intent.
- The npm package must keep working when consumers lack Python: the
  shim fails with a clear message; the plugin surfaces for Claude Code
  remain usable without ever running the generator.
