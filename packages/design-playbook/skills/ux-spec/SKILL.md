---
name: ux-spec
description: Declaration-first UI spec (six-layer spec.md). Use when turning a short product/UI ask into six-layer spec.md, or when goal, edge-state, acceptance, or evidence requirements are missing before build.
---

# ux-spec

Write a **six-layer `spec.md`**: the functional **declaration** for what must be true. Visual skin, tokens, and Badge-vs-Tag choices are out of scope.

## Steps

### 0. Bind project contract (when present)

When the host project has a persistent contract v1 (`contract.json` + optional `decisions.jsonl`), **bind-first** via `scripts/contract_v1.py` before writing L1–L6. Resurface every `assumed` / `open` field and any source-hash drift; `open` blocks dependent work; `assumed` needs explicit per-run acknowledgement. Reject unknown `schemaVersion` values. Do not invent layered inheritance or partial overrides (ADR-0019). Accepting a run spec may promote fields only as `assumed`/`open` — never as `decided` without named user confirmation in the decision log (ADR-0017).

**Done when:** either no project contract exists, or bind-first recorded contract/decision-log SHAs and every unresolved or stale field was surfaced before authoring.

### 1. Pin L1

From the ask, fix the user-visible goal, target user, in-scope scenes, **non-goals**, and always/ask/never boundaries. Ask only when a missing answer materially changes one of them; otherwise record a conservative assumption.

When `.scratch/<run>/reference/contract.md` exists (ADR-0011), **read it before writing L1–L6**. Fold its functional constraints, non-goals implied by Do not copy, and always/ask/never hints into L1 (and later L5/L6 edges). Cite the path; do not re-derive the screenshot from memory. The reference contract is input only — it does not replace any L1–L6 heading.

**Done when:** all five L1 fields are explicit — goal, target user, in-scope scenes, non-goals, and always/ask/never boundaries — with each assumption labeled as such; none left blank or implied; and if a reference contract exists, its functional constraints are reflected (or an explicit rejected-with-reason note is recorded).

### 2. Expand L2–L4

- L2 regions and duties  
- L3 states and transitions  
- L4 control behavior per relevant state  

Use the headings in [`references/spec-template.md`](references/spec-template.md).

**Done when:** every primary user job has a state path; every region has an owner duty.

### 3. Force L5–L6

- L5: empty, loading, error, permission — each with what the user can do next  
- L6: checkable acceptance; every top-level item explicitly contains `Given`, then `When`, then `Then`, with the proof required for that item

**L6 granularity (ADR-0016):** one top-level L6 item = one independently blocking **user-visible risk or outcome**. Three to seven items is a soft authoring budget — write more only with an explicit rationale that each extra item is independently blocking. There is **no** numeric validator gate. Accessibility and multi-stack proof attach to an existing criterion when they test the same risk; create a standalone accessibility L6 item only when the failure is independently blocking. Do **not** auto-generate accessibility or multi-stack L6 seeds.

Evidence is criterion-shaped: visible states require rendered inspection at named target viewports; behavior requires an interaction trace or automated check; implementation health uses the relevant tests, type/lint checks, or affected build when available. Planning-only work names the future proof instead of claiming it exists. Where the proof is a runtime state, name the **capture seed** — the state to capture (e.g. "error-state screenshot") and the capture type. This is the seed the `observe*` step derives a capture plan from (`Given`/`When` → state+actions, `Then` → required); do not write selectors, URLs, or actions here — those are derived later. Capture contract v1 requires `schemaVersion: 1` and an explicit viewport at observe time (ADR-0018).

**Done when:** L5 is not a single word (“loading”); every L6 item is a top-level list item that uses `Given -> When -> Then` in that order, can be ticked pass/fail without taste debate, and says what evidence will prove it (naming the capture seed where the proof is a runtime state); L6 items stay user-risk units rather than one row per evidence type.

### 4. Emit

Output the full `spec.md` using the template structure. Stop. Do not scaffold UI or pick components here.

**Done when:** one markdown spec exists containing every L1–L6 heading from the template, with steps 1–3 Done-when criteria still holding in the emitted file, ready for the next pipeline step (`ui-picker` / fill).

## Scope fence

| In | Out → |
| --- | --- |
| Functional truth, flows, edges, acceptance | Color/type/motion → `design` / `craft-guard` |
| | Risk/secrets meaning → `domain` |
| | Component identity → `ui-picker` / `components` |
