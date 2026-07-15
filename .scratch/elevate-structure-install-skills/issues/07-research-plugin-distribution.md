# 07 — Claude Code plugin distribution facts

**Type:** research  
**Status:** resolved  
**Blocked by:** None — can start immediately

## Question

What are the **current (primary-docs) facts** for distributing a Claude Code plugin to strangers?

Need:

- Local: `--plugin-dir`, skills-directory plugins, local marketplace layout (`marketplace.json` + `source`)
- Remote: git marketplace add syntax; private vs public
- Community catalog submission path (if any) and pinning model
- Namespacing rules for skills/commands after install
- Anything that invalidates our package layout (skills/commands at plugin root)

Resolve with citations to official docs; no product decision in this ticket (feeds 02 and 06).

## Answer

**Gist:** Strangers install via marketplace (`/plugin marketplace add` then `/plugin install name@marketplace`). Local paths are `--plugin-dir`, `@skills-dir` under `~/.claude/skills/` or project skills, or a local marketplace with `.claude-plugin/marketplace.json` + relative `./plugins/...` sources. Community catalog = submit form → review → SHA pin in `claude-community`; official catalog is Anthropic-curated only. Plugin skills are always `/plugin-name:skill`. Valid layout: components at plugin root (not inside `.claude-plugin/`); multi-skill uses `skills/<name>/SKILL.md`; single root `SKILL.md` OK with frontmatter `name`.

Full notes: `.scratch/elevate-structure-install-skills/research/07-plugin-distribution.md`

No install-path-of-record decision here (ticket 02).
