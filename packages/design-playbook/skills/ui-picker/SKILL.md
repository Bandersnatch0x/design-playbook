---
name: ui-picker
description: UI shell and component semantics. Use when scaffolding a product page (list, dashboard, settings, detail, agent-admin), or when the wrong template/Badge-Tag pairing is about to be coded.
---

# ui-picker

Before code: map the job to a **template** (shell) and **component semantics**. Appearance follows meaning.

## Steps

### 1. Density + scene

Choose density (console-tight vs marketing-loose) and scene class (list / detail / settings / dashboard / editor / agent-admin / …).

When a verified `.scratch/<run>/design-baseline/state.json` binds a baseline (`status: ready` from `design_baseline.verify`), read that binding path first (`baseline.path`, usually `DESIGN.md` or `.stitch/DESIGN.md`). It is the project-specific authority for atmosphere, visual roles, density, layout, motion, and component conventions. Preserve it unless the requested change explicitly revises the baseline.

When `.scratch/<run>/reference/contract.md` exists (ADR-0011), read its **Visual cues for ui-picker**, Keep/Change, and Do not copy / exclusions. Use them as input for density, scene, region weight, and risks — never as hex tokens or as a license to copy brand chrome.

**Done when:** one scene label and one density choice are explicit; a bound baseline is cited by path + SHA-256; if a reference contract exists, the decision report's risks or exclusions surface its Do not copy / brand risks (path citation is enough).

### 2. Template

Read [`references/template.md`](references/template.md). Assign main / side / action / status regions.

**Done when:** each region maps to a duty from `spec` L2 (or a stated gap in the spec).

### 3. Components

Read [`references/components.md`](references/components.md). For each field/action, pick by **role** (status vs category vs confirm vs detail).

Load only if needed:

- business risk / desensitize → [`references/domain.md`](references/domain.md)
- token roles while deciding surfaces → verified `<binding.path>` first, then generic fallback [`references/design.md`](references/design.md)

**Done when:** every primary datum/action has a named component role; easy-mix pairs (Badge/Tag, Dialog/Drawer, Dropdown/Menu/Command) are resolved in writing.

### 4. Decision report

Write, then wait for confirmation if the user is in the loop:

```text
design-baseline: <binding.path> sha256:<digest> | waived:<reason>
scene:
density:
template:
regions: …
components: …
baseline-changes: none | <explicitly approved change>
risks: …
```

**Done when:** the report exists, records the bound baseline or explicit waiver, and coding has not started without it.

### Branch — structure still open

If template is underdetermined, offer 2–3 IA variants (same `spec`, different main-region weight), one-line tradeoff each, pick one, then complete step 4.

## Defaults that hold

- Brand color as token/role, not a hex literal.  
- Easy-mix pair semantics and shell 禁用 rules live in `references/components.md` and `references/template.md` — resolve against those tables, not from memory.
