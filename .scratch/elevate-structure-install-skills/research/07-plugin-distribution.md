# 07 — Claude Code plugin distribution (primary docs)

**Date:** 2026-07-15  
**Ticket:** `issues/07-research-plugin-distribution.md`  
**Scope:** Facts only from official Claude Code docs. No install-path-of-record decision (ticket 02).

## Sources

- [Create plugins](https://code.claude.com/docs/en/plugins)
- [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- [Discover and install prebuilt plugins](https://code.claude.com/docs/en/discover-plugins)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- Index: [docs llms.txt](https://code.claude.com/docs/llms.txt)

---

## 1. What a plugin is (vs standalone)

- Standalone config lives under `.claude/` and uses short skill names like `/hello`. ([plugins](https://code.claude.com/docs/en/plugins))
- Plugins are self-contained directories with skills/agents/hooks/etc., optionally with `.claude-plugin/plugin.json`. Skill names are namespaced: `/plugin-name:hello`. ([plugins](https://code.claude.com/docs/en/plugins))
- Use plugins when sharing with team/community, reusing across projects, versioning, or marketplace distribution. ([plugins](https://code.claude.com/docs/en/plugins))

---

## 2. Local distribution / load paths

### 2.1 `--plugin-dir` (dev / session load)

- Load a plugin without marketplace install:  
  `claude --plugin-dir ./my-plugin`  
  ([plugins](https://code.claude.com/docs/en/plugins))
- Multiple plugins: repeat the flag. ([plugins](https://code.claude.com/docs/en/plugins))
- Accepts a `.zip` of the plugin directory (Claude Code **v2.1.128+**). ([plugins](https://code.claude.com/docs/en/plugins))
- Session-only remote zip: `--plugin-url https://example.com/my-plugin.zip` (or multiple URLs). Fetch failure → load error for that plugin; session continues. ([plugins](https://code.claude.com/docs/en/plugins))
- If `--plugin-dir` name collides with an installed marketplace plugin, the local copy wins for that session, except managed force-enable/force-disable cannot be overridden. ([plugins](https://code.claude.com/docs/en/plugins))
- After edits, `/reload-plugins` reloads plugins/skills/agents/hooks/MCP/LSP without full restart. ([plugins](https://code.claude.com/docs/en/plugins), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))

### 2.2 Skills-directory plugins (no marketplace)

- Any folder under a skills directory that contains `.claude-plugin/plugin.json` loads as `<name>@skills-dir` on the next session — no marketplace, no install step. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins), [plugins](https://code.claude.com/docs/en/plugins))
- Scaffold: `claude plugin init my-tool` → creates `~/.claude/skills/my-tool/` with manifest + starter skill; loads as `my-tool@skills-dir`. ([plugins](https://code.claude.com/docs/en/plugins), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#plugin-init))
- Skills-directory tree distinctions:  
  - `<skills-dir>/foo/SKILL.md` (no manifest) → plain skill `foo`  
  - `<skills-dir>/foo/.claude-plugin/plugin.json` → plugin `foo@skills-dir`  
  - `<plugin>/skills/bar/SKILL.md` → skill `bar` inside a plugin  
  ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))
- Load scopes:  
  - `~/.claude/skills/` → personal, every project  
  - `<cwd>/.claude/skills/` → project; only after workspace trust dialog  
  ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))
- Project-scope `@skills-dir` plugins load only from the `.claude/skills/` of the **start cwd** — they do **not** walk up to repo root the way plain skills do. Launch from repo root or `/reload-plugins` after cd. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))
- Unlike marketplace install, skills-dir plugins are discovered **in place** (not copied into plugin cache). ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))
- Disable: `claude plugin disable my-tool@skills-dir` (or delete folder). No uninstall step. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))
- Admins can block `skills-dir` via `strictKnownMarketplaces` / `blockedMarketplaces` with `{"source": "skills-dir"}`. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#plugin-init))

### 2.3 Local marketplace layout (`marketplace.json` + `source`)

- A marketplace is a catalog (`marketplace.json`) that lists plugins and where to fetch them. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))
- Local walkthrough structure:  
  - `my-marketplace/.claude-plugin/marketplace.json`  
  - `my-marketplace/plugins/<plugin>/.claude-plugin/plugin.json`  
  - `my-marketplace/plugins/<plugin>/skills/...`  
  ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))
- Minimal marketplace catalog example:  
  ```json
  {
    "name": "my-plugins",
    "owner": { "name": "Your Name" },
    "plugins": [
      {
        "name": "quality-review-plugin",
        "source": "./plugins/quality-review-plugin",
        "description": "..."
      }
    ]
  }
  ```  
  ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))
- Add + install locally:  
  `/plugin marketplace add ./my-marketplace`  
  `/plugin install quality-review-plugin@my-plugins`  
  ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Relative plugin `source` must start with `./`; resolves from **marketplace root** (directory containing `.claude-plugin/`), not from inside `.claude-plugin/`. Do not use `../` outside marketplace root. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#relative-paths))
- Optional `metadata.pluginRoot` (e.g. `"./plugins"`) prepends a base to relative sources. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#optional-fields))
- After fetch, plugins are copied into versioned cache under `~/.claude/plugins/cache`. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))
- URL-based marketplace add (direct `marketplace.json` URL) does **not** resolve relative plugin paths — only the catalog file is downloaded. Use git/GitHub/npm sources for plugins, or git/local marketplace sources. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))

---

## 3. Remote marketplace distribution

### 3.1 Add marketplace syntax

User-facing (`/plugin`) and CLI (`claude plugin marketplace add`) accept:

| Source | Syntax examples |
| :----- | :-------------- |
| GitHub shorthand | `owner/repo`; pin branch/tag with `owner/repo@ref` (CLI) |
| Git URL (HTTPS/SSH) | `https://gitlab.com/company/plugins.git`; pin with `#ref` |
| Local path | `./my-marketplace` or path to `marketplace.json` |
| Remote catalog URL | `https://example.com/marketplace.json` |

([discover-plugins](https://code.claude.com/docs/en/discover-plugins#add-marketplaces), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#plugin-marketplace-add))

- Full git URLs should include scheme (`https://`); bare host/path without scheme is invalid `owner/repo` as of **v2.1.196**. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))
- Include `.git` suffix on non-GitHub git URLs so Claude Code clones the repo rather than treating the URL as a hosted `marketplace.json`. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Hosting recommendation: GitHub repo with `.claude-plugin/marketplace.json`; users add with `/plugin marketplace add owner/repo`. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#host-on-github-recommended))

### 3.2 Plugin `source` types inside `marketplace.json`

| Source | Shape | Notes |
| :----- | :---- | :---- |
| Relative path | `"./plugins/my-plugin"` | Same repo as marketplace |
| `github` | `{ "source": "github", "repo": "owner/repo", "ref"?, "sha"? }` | |
| `url` | `{ "source": "url", "url": "https://...git", "ref"?, "sha"? }` | Any git host |
| `git-subdir` | `{ "source": "git-subdir", "url", "path", "ref"?, "sha"? }` | Sparse clone monorepo subdir |
| `npm` | `{ "source": "npm", "package", "version"?, "registry"? }` | Public or private registry |

([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))

- **Marketplace source** (where catalog lives) ≠ **plugin source** (where each plugin is fetched). Pin independently. Marketplace add supports `ref` but not `sha`; plugin sources support both `ref` and `sha`. When both set, **`sha` is the effective pin**. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))

### 3.3 Private vs public

- Public: any of the above; no special auth. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces))
- Private repos: manual install/update uses existing git credential helpers / SSH agent. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#private-repositories))
- Background auto-update disables credential helpers on `git pull` (HTTPS private may fail; SSH with agent OK). Fallbacks/settings documented (`CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE`, URL rewrite with token, `gh auth setup-git`). ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#private-repositories))
- To keep a plugin internal to a team: host marketplace in a private repository. ([plugins](https://code.claude.com/docs/en/plugins#share-your-plugins))

### 3.4 Team / org distribution (not stranger-facing, but related)

- Project `.claude/settings.json` can declare `extraKnownMarketplaces` and `enabledPlugins` so collaborators are prompted after folder trust. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins#configure-team-marketplaces), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#require-marketplaces-for-your-team))
- Managed settings can restrict which marketplaces users may add. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#managed-marketplace-restrictions), [discover-plugins](https://code.claude.com/docs/en/discover-plugins#security))

---

## 4. Community / official catalogs & pinning model

### 4.1 Official marketplace

- Name: `claude-plugins-official`. Auto-available after first interactive Claude Code start. ([plugins](https://code.claude.com/docs/en/plugins), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Install: `/plugin install <name>@claude-plugins-official`. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- If missing: `/plugin marketplace update claude-plugins-official` or `/plugin marketplace add anthropics/claude-plugins-official`. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Curated by Anthropic at discretion. **No application process**; submission forms do **not** add plugins here. ([plugins](https://code.claude.com/docs/en/plugins#submit-your-plugin-to-the-community-marketplace), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Catalog also browsable at [claude.com/plugins](https://claude.com/plugins). ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))

### 4.2 Community marketplace

- Repo: [`anthropics/claude-plugins-community`](https://github.com/anthropics/claude-plugins-community). Marketplace name used for install: **`claude-community`**. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins#community-marketplace))
- Add: `/plugin marketplace add anthropics/claude-plugins-community`  
  Install: `/plugin install <plugin-name>@claude-community`  
  ([discover-plugins](https://code.claude.com/docs/en/discover-plugins#community-marketplace))
- **Submission path** (third-party → community, after review):  
  - claude.ai form: [claude.ai/admin-settings/directory/submissions/plugins/new](https://claude.ai/admin-settings/directory/submissions/plugins/new) — requires Team/Enterprise + directory management access  
  - Console form: [platform.claude.com/plugins/submit](https://platform.claude.com/plugins/submit) — for individual authors  
  ([plugins](https://code.claude.com/docs/en/plugins#submit-your-plugin-to-the-community-marketplace))
- Run `claude plugin validate` before submit; review pipeline runs the same check + automated safety screening. ([plugins](https://code.claude.com/docs/en/plugins#submit-your-plugin-to-the-community-marketplace))
- **Pinning model (community catalog):** approved plugins are **pinned to a specific commit SHA** in the community catalog; CI bumps the pin as authors push new commits. Public catalog syncs nightly from review pipeline — delay possible between approval and appearance in `marketplace.json`. Checkability: search name in community `marketplace.json`. ([plugins](https://code.claude.com/docs/en/plugins#submit-your-plugin-to-the-community-marketplace), [discover-plugins](https://code.claude.com/docs/en/discover-plugins#community-marketplace))

### 4.3 Independent distribution to strangers

- Create/host your own marketplace (git recommended) and tell users:  
  1. `/plugin marketplace add <your-source>`  
  2. `/plugin install <plugin>@<marketplace-name>`  
  ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Demo marketplace example: `/plugin marketplace add anthropics/claude-code` then install from that catalog. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))

### 4.4 Version / update pinning (author control)

Version resolution order (first set wins):

1. `version` in plugin’s `plugin.json`  
2. `version` in marketplace entry  
3. git commit SHA of plugin source (git-based sources)  
4. `unknown` (npm / non-git local)

([plugins-reference](https://code.claude.com/docs/en/plugins-reference#version-management), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))

- Explicit `version` **pins** updates: users only get updates when that string changes. Omit `version` → every commit is a new version. ([plugins](https://code.claude.com/docs/en/plugins), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#version-management))
- Avoid setting `version` in both `plugin.json` and marketplace entry; `plugin.json` always wins without warning. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))
- Plugin-source `sha` pins exact commit; `ref` is branch/tag. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources))
- Release channels: separate marketplaces pointing at different refs/SHAs of the same plugin repo. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))

---

## 5. Namespacing after install

- Plugin skills are **always** namespaced: `/plugin-name:skill-name` (namespace = plugin `name` field). ([plugins](https://code.claude.com/docs/en/plugins), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Skill folder name under `skills/` becomes the skill name; e.g. `skills/hello/` in plugin `my-first-plugin` → `/my-first-plugin:hello`. ([plugins](https://code.claude.com/docs/en/plugins))
- Install identifier form: `plugin-name@marketplace-name` (e.g. `commit-commands@claude-code-plugins`, `github@claude-plugins-official`). ([discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Marketplace entry `name` is what `enabledPlugins` keys and `/plugin install` use; may differ from `plugin.json` `name`. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#required-fields), [discover-plugins](https://code.claude.com/docs/en/discover-plugins))
- Agents appear scoped as `plugin-name:agent-name` in UI. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#required-fields))
- Standalone vs plugin after migrate: original `/skill-name` and plugin `/plugin-name:skill-name` **both remain** (plugin does not replace short name). Project/user `.claude/agents/` **override** same-named plugin agents. ([plugins](https://code.claude.com/docs/en/plugins#what-changes-when-migrating))
- `displayName` is UI-only; **not** used for namespacing or lookup. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#optional-plugin-fields), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#metadata-fields))
- Skills-directory plugins use marketplace-like id `name@skills-dir`. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills-directory-plugins))

---

## 6. Package layout rules (what invalidates / what is valid)

### 6.1 Plugin root layout

- Plugin root = directory containing `.claude-plugin/plugin.json` (or the plugin directory for default discovery). **Never** `~/.claude/` as plugin root. ([plugins](https://code.claude.com/docs/en/plugins#plugin-structure-overview))
- **Only** `plugin.json` belongs inside `.claude-plugin/`.  
  **Invalid:** putting `commands/`, `agents/`, `skills/`, or `hooks/` inside `.claude-plugin/`. Those must sit at **plugin root**. ([plugins](https://code.claude.com/docs/en/plugins#plugin-structure-overview), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#standard-plugin-layout))

Default component locations at plugin root:

| Component | Default path |
| :-------- | :----------- |
| Manifest | `.claude-plugin/plugin.json` (optional if defaults suffice) |
| Skills | `skills/<name>/SKILL.md` |
| Commands | `commands/*.md` (flat; docs say prefer `skills/` for new plugins) |
| Agents | `agents/` |
| Hooks | `hooks/hooks.json` |
| MCP | `.mcp.json` |
| LSP | `.lsp.json` |
| Monitors | `monitors/monitors.json` |
| Bin / settings | `bin/`, `settings.json` |

([plugins](https://code.claude.com/docs/en/plugins), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#file-locations-reference))

### 6.2 Skills at plugin root (valid special case)

- A plugin that ships **exactly one** skill may place `SKILL.md` **directly at plugin root** instead of `skills/`. Loaded as a single skill; frontmatter `name` sets invocation name. Prefer `skills/` if more than one skill may appear. ([plugins](https://code.claude.com/docs/en/plugins#plugin-structure-overview), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills))
- Auto single-skill root layout (no `skills/` dir, no `skills` manifest field) requires Claude Code **v2.1.142+**. Without frontmatter `name`, invocation falls back to install directory basename — for marketplace installs that can be a **version string that changes every update**. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills))
- Docs recommend setting frontmatter `name` for stable invocation. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills))

### 6.3 Commands vs skills

- `commands/` = flat Markdown skill files; `skills/` = directories with `SKILL.md`. Prefer `skills/` for new plugins. ([plugins](https://code.claude.com/docs/en/plugins), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#skills))

### 6.4 Manifest path fields

- Custom paths must be relative to plugin root and start with `./`. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#path-behavior-rules))
- `commands` / `agents` / etc. **replace** default dirs when set; `skills` **adds** to default `skills/` scan (except marketplace-root shared-skills advanced case). ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#path-behavior-rules), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries))
- Manifest optional; without it, components auto-discovered from defaults; name from directory. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema))
- `CLAUDE.md` at plugin root is **not** loaded as project context. ([plugins-reference](https://code.claude.com/docs/en/plugins-reference#standard-plugin-layout))
- Paths outside plugin directory break after install (plugins copied to cache). Use `${CLAUDE_PLUGIN_ROOT}` in hooks/MCP. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries), [discover-plugins](https://code.claude.com/docs/en/discover-plugins#troubleshooting))

### 6.5 Marketplace reserved names

- Third-party marketplaces cannot use reserved names including: `claude-plugins-official`, `claude-plugins-community`, `claude-community`, `claude-code-plugins`, etc. ([plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces#required-fields))

---

## 7. Install scopes (stranger UX)

When installing a marketplace plugin, user chooses:

- **User** (default): self, all projects  
- **Project**: all collaborators; writes `.claude/settings.json`  
- **Local**: self, this repo only  

CLI: `claude plugin install <name>@<marketplace> [--scope user|project|local]`  
([discover-plugins](https://code.claude.com/docs/en/discover-plugins#install-plugins), [plugins-reference](https://code.claude.com/docs/en/plugins-reference#plugin-install))

Security note: only install plugins/marketplaces from trusted sources; Anthropic does not control third-party plugin contents. ([discover-plugins](https://code.claude.com/docs/en/discover-plugins#security))

---

## 8. Implications for our layout

Facts only — not an install-path decision (see ticket 02):

- **Valid multi-skill plugin layout** for distribution: plugin root with `.claude-plugin/plugin.json` + `skills/<skill-name>/SKILL.md` (not nested under `.claude-plugin/`).
- **Single-skill root `SKILL.md`** is officially supported but needs frontmatter `name` for stable `/plugin:skill` after marketplace install (install dir basename is unstable under versioned cache).
- **`commands/` at plugin root** is valid but docs steer new plugins to `skills/`.
- **Stranger install path** supported by docs is marketplace-mediated: host `marketplace.json` (own git repo or community catalog), users `marketplace add` then `plugin install name@marketplace`.
- **Local-only stranger-less paths** (`--plugin-dir`, `~/.claude/skills/` plugin, local marketplace) are for dev/team, not primary public discovery.
- **Community catalog** exists with formal submit forms + SHA pin + nightly sync; official catalog is invite/curated-only.
- **Namespacing is mandatory** for plugin skills (`/plugin-name:skill`); short names only for standalone `.claude/` skills.
- **Version field** in `plugin.json` freezes updates until bumped; omit for commit-SHA continuous updates — relevant for release gate (ticket 06), not decided here.
- Private git marketplaces work for internal; public strangers need a public git host or community submission.
