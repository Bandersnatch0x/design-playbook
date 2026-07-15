---
name: ux-spec
description: Write an outcome-first UI declaration. Use when turning a short product/UI ask into six-layer spec.md, or when goal, edge-state, acceptance, or evidence requirements are missing before build.
---

# ux-spec

Write a **six-layer `spec.md`**: the functional **declaration** for what must be true. Visual skin, tokens, and Badge-vs-Tag choices are out of scope.

## Steps

### 1. Pin L1

From the ask, fix the user-visible goal, target user, in-scope scenes, **non-goals**, and always/ask/never boundaries. Ask only when a missing answer materially changes one of them; otherwise record a conservative assumption.

**Done when:** a stranger could state the intended outcome, what the page is *not* for, and which actions require a user decision.

### 2. Expand L2–L4

- L2 regions and duties  
- L3 states and transitions  
- L4 control behavior per relevant state  

Use the headings in [`references/spec-template.md`](references/spec-template.md).

**Done when:** every primary user job has a state path; every region has an owner duty.

### 3. Force L5–L6

- L5: empty, loading, error, permission — each with what the user can do next  
- L6: checkable acceptance (Given/When/Then or equivalent), with the proof required for each item

Evidence is criterion-shaped: visible states require rendered inspection at named target viewports; behavior requires an interaction trace or automated check; implementation health uses the relevant tests, type/lint checks, or affected build when available. Planning-only work names the future proof instead of claiming it exists.

**Done when:** L5 is not a single word (“loading”); every L6 item can be ticked pass/fail without taste debate and says what evidence will prove it.

### 4. Emit

Output the full `spec.md` using the template structure. Stop. Do not scaffold UI or pick components here.

**Done when:** one complete markdown spec exists for the next pipeline step (`ui-picker` / fill).

## Scope fence

| In | Out → |
| --- | --- |
| Functional truth, flows, edges, acceptance | Color/type/motion → `design` / `craft-guard` |
| | Risk/secrets meaning → `domain` |
| | Component identity → `ui-picker` / `components` |
