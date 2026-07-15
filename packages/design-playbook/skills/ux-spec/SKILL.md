---
name: ux-spec
description: Spec-driven UI planning. Use when turning a one-line product/UI ask into six-layer spec.md, or when empty/loading/error/permission acceptance is missing before build.
---

# ux-spec

Write a **six-layer `spec.md`**: the functional **declaration** for what must be true. Visual skin, tokens, and Badge-vs-Tag choices are out of scope.

## Steps

### 1. Pin L1

From the ask (and only necessary clarifying defaults if the user is silent), fix: one-line definition, user, in-scope scenes, **non-goals**, always/ask/never boundaries.

**Done when:** a stranger could tell what the page is *not* for.

### 2. Expand L2–L4

- L2 regions and duties  
- L3 states and transitions  
- L4 control behavior per relevant state  

Use the headings in [`references/spec-template.md`](references/spec-template.md).

**Done when:** every primary user job has a state path; every region has an owner duty.

### 3. Force L5–L6

- L5: empty, loading, error, permission — each with what the user can do next  
- L6: checkable acceptance (Given/When/Then or equivalent)

**Done when:** L5 is not a single word (“loading”); L6 items can be ticked pass/fail without taste debate.

### 4. Emit

Output the full `spec.md` using the template structure. Stop. Do not scaffold UI or pick components here.

**Done when:** one complete markdown spec exists for the next pipeline step (`ui-picker` / fill).

## Scope fence

| In | Out → |
| --- | --- |
| Functional truth, flows, edges, acceptance | Color/type/motion → `design` / `craft-guard` |
| | Risk/secrets meaning → `domain` |
| | Component identity → `ui-picker` / `components` |
