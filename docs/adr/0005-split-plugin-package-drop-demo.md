# ADR-0005: Plugin package split; demo site removed

## Status

Accepted (grill Q6 = B)

## Context

Public install requires a clear redistributable root. A reading demo site in the same tree blurred “what ships” and retained upstream-associated assets. User chose split layout and **removal of demo-site traces**.

## Decision

1. Product lives at **`packages/design-playbook/`** (skills, commands, plugin metadata, LICENSE, package README, optional self-authored examples).
2. **Remove** the former demo application surface from this monorepo (`src/`, demo `public/`, vite app config, pages workflow, demo scripts/assets as product).
3. Repo root retains engineering docs only: `CONTEXT.md`, `docs/`, `.scratch/`, root `CLAUDE.md` / `README.md` pointing at the package.
4. Install instructions target the **package path**, not “clone whole monorepo as the skill.”

## Consequences

- Marketplace `source` is `packages/design-playbook` (or that directory published alone later).
- No further demo visual work counts as product progress.
- Local Claude sessions should load skills from the package path; root is workflow/docs home.
