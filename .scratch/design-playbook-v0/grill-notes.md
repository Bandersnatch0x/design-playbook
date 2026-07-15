# Grill notes — design-playbook v0

Topic: 从 playbook 演示站转型为可安装 UI agent 插件；钉 v0 范围与成功标准。

## Open questions (answer in place)

### Q1 — First user
Who is v0 for?
- [ ] only me (local skills)
- [ ] small team (path/marketplace install)
- [x] public install

**Answer:** **C — public install.** Strangers must be able to install (marketplace/path docs), so v0 includes clearer distribution + license posture (not “local only” shortcuts).

### Q2 — Success criterion
What must one `/design-io` run produce every time?

**Answer:** **Default accepted.** Every public-install run of `/design-io` / `design-playbook` must:
1. Emit `spec.md` with substantive **L5/L6**
2. Produce **decision report** before code
3. End with **point-back** findings (`issue/source/fix/severity`)
4. **Recirculate** blocking to owning declaration (not whole-page restyle)
5. Install path in README works without tribal knowledge

### Q3 — Out of scope v0
Confirm cut list:
- style CSV / palette DB
- multi-platform CLI (`uipro`-like)
- Figma MCP
- demo-site redesign as delivery

**Answer:** **全砍+加码 (option 1).**

**Cut (not v0 product work):**
1. Style CSV / palette DB (compose with pro-max instead)
2. Multi-platform install CLI
3. Figma MCP as delivery dependency (README “optional later” one-liner OK)
4. Demo-site visual redesign as the release artifact

**Add (v0 blockers because public install):**
1. License / content boundary clear enough to ship
2. Copy-paste install path for strangers
3. Clean self-authored examples (not murky upstream copies) for dogfood/onboarding
4. README: how to stack with pro-max + frontend-design
5. craft-guard stays hard; verified by dogfood (not by building a style DB)

### Q4 — Content & license
What may ship inside the plugin vs demo-only?
- original skill text we wrote
- upstream manuscript / figures / ACD marks
- attachments derived from playbook examples

**Answer:** **Ship only our own skill / commands / workflow prose.**

Public plugin redistributable surface:
- `.claude/skills/**` we authored
- `.claude/commands/**` we authored
- `.claude-plugin/**` metadata we authored
- `docs/agents/product-workflow.md` + install docs we authored
- **self-written** clean examples only (rewrite; do not republish murky upstream-derived attachments as plugin content)

Not in public plugin claim / not redistributed as ours:
- upstream manuscript, figures, ACD marks, hero, demo-site chrome as product
- `public/attachments/*` until rewritten as original or marked demo-only / non-redistributable

Demo site may remain local learning copy with existing README rights notice; **not** the marketplace artifact.

### Q5 — SSOT
Single source of truth for declaration snippets:
- [x] `.claude/skills/*/references/*` only; attachments are demo copies
- [ ] `public/attachments/*` only; skills point out
- [ ] generate both from `manuscript/` or `content/declarations/`

**Answer:** **SSOT = `.claude/skills/*/references/*` (self-authored only).**

**Reference posture (user lock):** this repo **references** the upstream playbook as inspiration — it is **not** a port, overlay, or relocation of upstream materials.
- Strip or rewrite any skill/reference text that is playbook-specific lift (CloudAI product voice, upstream case copy, ACD-bound examples) into **generic Design I/O** language.
- Do **not** treat `public/attachments/*` or manuscript as sources to sync into the plugin.
- Demo attachments stay out of the public plugin pack (see Q4); optional later demo-only, never SSOT.

### Q6 — Repo shape v0
- [ ] monorepo keep demo + plugin (status quo)
- [x] split package + remove demo traces
- [ ] plugin-only path primary; demo secondary

**Answer:** **B — split.** Product at `packages/design-playbook/`. **Demo site removed** from monorepo (no `src/` reading app as deliverable). Root = docs + scratch + workflow only.

## Decisions locked

- **2026-07-15 Q1:** First user = **public install** (strangers). Implies install docs + license/content boundary are v0 blockers, not later polish.
- **2026-07-15 Q2:** Success = L5/L6 spec + decision report before code + point-back evaluator + recirculate blocking + copy-paste install docs.
- **2026-07-15 Q3:** Cut style-DB/CLI/Figma-dep/demo-redesign; **add** license boundary, install docs, clean examples, stack README, craft dogfood.
- **2026-07-15 Q4:** Public redistributable = our skills/commands/workflow + self-authored examples only; upstream manuscript/figures/ACD/demo chrome and unre-written attachments stay out of plugin ship claim.
- **2026-07-15 Q5:** SSOT = `.claude/skills/*/references/*` only; **reference ≠ port** — strip/rewrite playbook-lifted refs into generic Design I/O; no sync from attachments/manuscript into plugin.
- **2026-07-15 Q6:** Repo = `packages/design-playbook` product package; demo site traces removed (ADR-0005).

## Hygiene note (from Q5 scan)

Done during pivot: vendor lift removed from refs (ECS→generic, AccessKey→generic, dead “演示附件” link rewritten, examples labeled illustrative). Remaining audit for full generic pass is a v0 ticket.

## Grill complete

All Q1–Q6 locked. Phase → **2-dogfood**.
