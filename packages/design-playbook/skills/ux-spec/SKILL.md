---
name: ux-spec
description: Declaration-first UI spec (six-layer spec.md) shaped through an S0-S6 interactive session. Use when turning a short product and UI ask into six-layer spec.md, or when goal, edge-state, acceptance, or evidence requirements are missing before build.
---

# ux-spec

Write a **six-layer `spec.md`**: the functional **declaration** for what must be true. Visual skin, tokens, and Badge-vs-Tag choices are out of scope.

Shaping runs as a session state machine (S0-S6) with append-only artifacts under `.scratch/<run>/shaping/`:

- `shaping-log.jsonl`, append-only event log (process authority; mirrors the decision-log philosophy)
- `queue.json`, derived state (pending questions / staged assumptions / open confirmations), always rebuildable from the log

Events (closed enum): `asked / answered / assumption_staged / confirm_presented / item_confirmed / item_rejected / item_revised / projected / suspended / resumed / superseded_by / archived`.

**Terminology:** In Chinese responses, use「成形（会话）」for "shaping (session)", see `CONTEXT.md` glossary.

## Steps

### 0. Bind project contract, S0 intake assembly

When the host project has a persistent contract v1 (`contract.json` + optional `decisions.jsonl`), **bind-first** via `scripts/contract_v1.py` before writing L1–L6. Resurface every `assumed` / `open` field and any source-hash drift; `open` blocks dependent work; `assumed` needs explicit per-run acknowledgement. Reject unknown `schemaVersion` values. Do not invent layered inheritance or partial overrides (ADR-0019). Accepting a run spec may promote fields only as `assumed`/`open`, never as `decided` without named user confirmation in the decision log (ADR-0017).

S0 assembles the session inputs: persistent contract + decision log (bind semantics pre-check), project design baseline state, existing spec, and reference contracts. Record the request **verbatim** as the first shaping-log event. Any state may `suspended`/`resumed`. On resume, rebuild `queue.json` from the log and re-ask only `asked`-without-`answered` items, already-`item_confirmed` values are never re-asked (revise only via `supersedes`). Resume is not queue replay alone: first re-run `bind_first` and diff the contract SHA against the first-bind snapshot. When the contract drifted while suspended, diff the affected fields. Items grounded on a changed field lose their standing. Void affected unconfirmed items and reopen them in the queue. A confirmed item on a drifted field loses its confirmed status; revise via `supersedes`. Confirmations on unaffected fields are preserved (the append-only decision log loses nothing).

**Done when:** either no project contract exists, or bind-first recorded contract and decision-log SHAs and every unresolved or stale field was surfaced before authoring. The session log exists with the request recorded verbatim.

**Event append tool:** Use `python scripts/shaping_log.py append <log-path> --type <event> [--key value ...]` to append events to `shaping-log.jsonl`. Valid event types: `asked`, `answered`, `assumption_staged`, `confirm_presented`, `item_confirmed`, `item_rejected`, `item_revised`, `projected`, `suspended`, `resumed`, `superseded_by`, `archived`. Do not write temporary helper scripts, the official CLI handles all append operations.

**Derived state:** `queue.json` is always rebuilt from the log by `shaping_log.py`'s `derive_queue` (`resumed` events produce no queue items), append an event, then re-derive. Never hand-edit the queue. `contract_v1.py` is a **module-level API** (no CLI): bind, promote, and decide are composed from skill-side Python, not invoked as a script.

**Output note:** When no project contract exists, S0 is a silent no-op (result records in shaping-log only). Do not narrate internal implementation details ("contract_v1", "模块级 API", "bind-first 空操作") to the user.

### 1. Shape requirements, S1-S6 session state machine

**S1 GRADE.** Grade gaps on four consequence tiers:
- T1 consequential: goal, target user, success criteria, and non-goals.
- T2 structural: materially different IA or primary-path alternatives.
- T3 visual-identity: register and route to the design-decision track. Shaping never adjudicates.
- T4 local: inside confirmed declarations, agent-autonomous, never asked.

Produce the question queue (T1 first; ≤3 questions per batch. Every question names the downstream field(s)/L6 it changes) and the assumption plan. Questions with no downstream impact are not asked, they become T4 assumptions. Check whether every required field already carries a contract value and grading surfaces no new gap (common on repeat runs). If so, skip S2 and go directly to S3.

**S2 CLARIFY**, present batches (≤3), user answers. Log `asked`/`answered` with each question's impact note. A refused T1 answer downgrades to an **explicit-risk assumption** into CP-C (never a silent `assumed`). After 2 consecutive batches without new T1 information, remaining T2/T3 items must convert to the assumption plan (fatigue cap; session soft cap 9 questions).

**S3 DRAFT**, draft L1-L6 from confirmed values + registered assumptions. A materially different IA or primary-path alternative surfaced while drafting becomes a T2 question back to S2. Allow at most one such jump per drafting round. T4 local choices land directly in the draft. Draft the L2-L5 structured fields (per-page duty table, path table, per-page five-state matrix, see the template).

**S4 CONFIRM.** Present confirmation batches:
- **CP-A** intent: ≤4 items covering goal, target user, success criteria wording, and non-goals.
- **CP-B** structural: ≤2 items, ≤3 options each. The chosen value writes an `l2.*` field.
- **CP-C** assumptions: ≤5 items, each with reason + risk + fallback. Per-item confirm / reject / revise, log `confirm_presented` / `item_confirmed` / `item_rejected` / `item_revised`. Rejected items re-enter the S2 queue alone. Confirmed items are immutable (revision only via `supersedes`).

**S5 PROJECT.** Use this strict function order:
1. `promote_fields` registers `assumed` fields only.
2. `append_decision` runs per user-confirmed item.
3. `apply_decisions` runs.
4. Write `spec.md`.
5. `bind_first` produces `contract-bind.json` + the assumed-ack list.
6. Run the G7 drift check.

Log one `projected` event carrying the mapping rows (decision id ↔ contract field ↔ spec section). This record is what G9 checks. A G7 drift failure blocks the projection. Return to S1 and re-grade with the new contract. Already-confirmed items persist in the decision log; only the re-graded gaps re-enter the queue.

**S6 EXIT.** All five conditions must hold before the session may close:
- The bound subset has zero `open` fields.
- Every `assumed` field has this run's explicit ack.
- L1 five fields + L6 criteria are all valued and traceable (decided or acknowledged-assumed).
- decisions.jsonl and contract have no unrecorded drift (G7).
- spec.md has all six layers (G1). Then log `archived`. There is no silent-downgrade exit: either S6 passes or the session suspends with the open queue and reasons saved. Machine check: `python scripts/g9_shaping.py <shaping_dir>`, the argument is the **shaping directory** (`.scratch/<run>/shaping/`), not the run root.

From the ask, fix the user-visible goal, target user, in-scope scenes, **non-goals**, and `always/ask/never` boundaries. Ask only when a missing answer materially changes one of them. Otherwise record a conservative assumption (CP-C visible). When `.scratch/<run>/reference/contract.md` exists (ADR-0011), **read it before writing L1–L6**. Fold its functional constraints, non-goals implied by Do not copy, and `always/ask/never` hints into L1 (and later L5/L6 edges). Cite the path. Do not re-derive the screenshot from memory. The reference contract is input only, it does not replace any L1–L6 heading.

**Done when:** all five L1 fields are explicit, goal, target user, in-scope scenes, non-goals, and `always/ask/never` boundaries, with each assumption labeled as such. None left blank or implied. If a reference contract exists, its functional constraints are reflected (or an explicit rejected-with-reason note is recorded). And the S6 exit conditions hold with the session archived.

### 2. Expand L2–L4

- L2 regions and duties, plus the **Page duties** table (one owner duty per page)
- L3 states and transitions, plus the **Paths** table (ordered path rows `P1…Pn`)
- L4 control behavior per relevant state

Use the headings in [`references/spec-template.md`](references/spec-template.md).

**Done when:** every primary user job has a state path. Every region has an owner duty. Every page in the L5 matrix has a duty row.

### 3. Force L5–L6

- L5: empty, loading, error, and permission states, each with what the user can do next. Include the per-page **five-state matrix**: initial, loading, success, failure, and empty, enumerable per page.
- L6: checkable acceptance. Every top-level item explicitly contains `Given`, then `When`, then `Then`, with the proof required for that item and a `(path: P<n>)` reference into the L3 path table

**L6 granularity (ADR-0016):** one top-level L6 item = one independently blocking **user-visible risk or outcome**. Three to seven items is a soft authoring budget, write more only with an explicit rationale that each extra item is independently blocking. There is **no** numeric validator gate. Accessibility and multi-stack proof attach to an existing criterion when they test the same risk. Create a standalone accessibility L6 item only when the failure is independently blocking. Do **not** auto-generate accessibility or multi-stack L6 seeds. Validators count **every top-level list item** in the L6 section as a criterion and check `Given`, then `When`, then `Then` order on it, non-criterion content (e.g. a Design done definition) must be a plain paragraph, never a list item.

Evidence is criterion-shaped: visible states require rendered inspection at named target viewports. Behavior requires an interaction trace or automated check. Implementation health uses the relevant tests, type and lint checks, or affected build when available. Planning-only work names the future proof instead of claiming it exists. Where the proof is a runtime state, name the **capture seed**, the state to capture (e.g. "error-state screenshot") and the capture type. This is the seed the `observe*` step derives a capture plan from (`Given`/`When` then state+actions, `Then` then required). Do not write selectors, URLs, or actions here, those are derived later. Capture contract v1 requires `schemaVersion: 1` and an explicit viewport at observe time (ADR-0018).

The host model may have no vision (text-only input): render artifacts are bound by **path reference** (manifest + ledger), never by viewing them. Machine assertions for review use the **text face**: HTML and CSS source, `a11y tree` text, and interaction-trace action records. An interaction trace is a Playwright trace **ZIP**. Unzip before reading; the artifact is not JSON. A no-vision run follows this mode end to end. It is not a protocol downgrade, so do not write L6 proof that requires the composing model to look at a screenshot.

**Done when:** L5 is not a single word (“loading”). Ensure every L6 item is a top-level list item using `Given, then When, then Then` in that order. It must be tickable pass or fail without taste debate and says what evidence will prove it. For runtime-state proof, name the capture seed. Every L6 item references a reachable path row; L6 items stay user-risk units rather than one row per evidence type.

### 4. Emit

Output the full `spec.md` using the template structure. Stop. Do not scaffold UI or pick components here. Refresh `shaping/queue.json` from the log before stopping.

**Done when:** one markdown spec exists containing every L1–L6 heading from the template. Steps 1–3 Done-when criteria still hold in the emitted file. The spec is ready for the next pipeline step (`ui-picker` or fill). Machine check right after writing spec.md: `python scripts/g1_spec.py .scratch/<run>/spec.md`, do not wait for the end-of-run `validate_run.py` sweep.

## Scope fence

| In | Out of scope |
| --- | --- | --- |
| Functional truth, flows, edges, acceptance | Color, type, and motion belongs to `design` / `craft-guard` |
| | Risk and secrets meaning belongs to `domain` |
| | Component identity belongs to `ui-picker` / `components` |
