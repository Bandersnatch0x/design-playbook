# 05 - Monorepo root role

**Type:** grilling  
**Status:** resolved  
**Blocked by:** 01 (resolved)

## Question

After elevate, what is the **role of the monorepo root**?

Decide ownership of:

- `CONTEXT.md` / `docs/adr` / `.scratch` (engineering)
- Root `README` / `CLAUDE.md` vs package README (who is "front door" for GitHub strangers?)
- `.claude/commands/product-*` (maintainer-only) - stay root-only forever?

If topology (01) is package-only public repo, this ticket may resolve as "N/A - root dissolves."

## Answer

**Decision: default accepted. Root = "GitHub front door + engineering shell", NOT the plugin runtime surface.**

Ownership:

- **Root = front door**: `README.md` - stranger landing: install trio + link to package README. Does not sprawl skill detail at root.
- **Root = engineering shell**: `CLAUDE.md` (agent engineering instructions), `CONTEXT.md` (glossary), `docs/`, `.scratch/`, `.claude/commands/product-*`. Read by maintainers + this repo's agents.
- **Root = release catalog**: `.claude-plugin/marketplace.json` (per 01) - read by Claude Code installer.
- **Package = plugin runtime surface**: `packages/design-playbook/**` - read by installed users.

Three rules:

1. **Front door = root README**, but only "install this plugin" + pointer to package README; no skill detail at root.
2. **`product-*` stays root forever** - they reference `.scratch/`, `CONTEXT.md`, `docs/` (all root-shell assets); never enter the package (confirms the code-review fix as permanent).
3. **`CLAUDE.md` is single-layer at root** - it owns engineering flow (phase/map/workflow pointers). Package has no separate CLAUDE.md; package README suffices. No double front door.

Boundary: root `docs/` and `.scratch/` are engineering artifacts, NOT in the plugin install surface - the marketplace catalog `source` points only at the package, so the two are physically isolated. A stranger `marketplace add` pulls only the package, never the root shell.
