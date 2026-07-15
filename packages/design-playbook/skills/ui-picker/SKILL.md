---
name: ui-picker
description: UI shell and component semantics. Use when scaffolding a product page (list, dashboard, settings, detail, agent-admin), or when the wrong template/Badge-Tag pairing is about to be coded.
---

# ui-picker

Before code: map the job to a **template** (shell) and **component semantics**. Appearance follows meaning.

## Steps

### 1. Density + scene

Choose density (console-tight vs marketing-loose) and scene class (list / detail / settings / dashboard / editor / agent-admin / …).

**Done when:** one scene label and one density choice are explicit.

### 2. Template

Read [`references/template.md`](references/template.md). Assign main / side / action / status regions.

**Done when:** each region maps to a duty from `spec` L2 (or a stated gap in the spec).

### 3. Components

Read [`references/components.md`](references/components.md). For each field/action, pick by **role** (status vs category vs confirm vs detail).

Load only if needed:

- business risk / desensitize → [`references/domain.md`](references/domain.md)
- token roles while deciding surfaces → [`references/design.md`](references/design.md)

**Done when:** every primary datum/action has a named component role; easy-mix pairs (Badge/Tag, Dialog/Drawer, Dropdown/Menu/Command) are resolved in writing.

### 4. Decision report

Write, then wait for confirmation if the user is in the loop:

```text
scene:
density:
template:
regions: …
components: …
risks: …
```

**Done when:** the report exists and coding has not started without it.

### Branch — structure still open

If template is underdetermined, offer 2–3 IA variants (same `spec`, different main-region weight), one-line tradeoff each, pick one, then complete step 4.

## Defaults that hold

- Prefer production templates over sample/playground shells.  
- Brand color as token/role, not a hex literal.  
- Badge → status/count/attachment; Tag → type/category/removable facet.  
- Dialog → interrupt confirm; Drawer → dense detail.
