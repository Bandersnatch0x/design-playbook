# ADR-0008: Preview feedback floor before confirm

## Status

Accepted (v0.3 grill, 2026-07-18). **Floor enforcement implemented 2026-07-18** — all Open enforcement sites landed; SEAM TEST PASSED. Pre-ADR confirm records (no `floor_pass`) now fail G5 by design.

## Context

Dogfood 0015 (`dogfood/2026-07-18-0015.md`, G1, high) showed `preview_prototype` returning non-actionable feedback ("安师大" — a valid Chinese string unrelated to the annotated element, plus an unrelated anchor) that still produced `confirmed=true` and advanced to Fill. The defect is **feedback unrelated to the annotated element**, not mojibake (the string is valid UTF-8).

Critically, the confirm record is **written by the preview MCP adapter** (`packages/design-playbook/mcp/preview/server.py`), not by the orchestrator: `do_POST` sets `confirmed=true` for any choice matching CONFIRM_LABELS and persists whatever `feedback` the form sent (default `''`). The client-side guard runs only for revise choices; confirm always succeeds. G5 (`validate_run.py` `check_preview`) then only verifies a `confirm-round-*.json` with `confirmed=true` exists — it does not inspect feedback. The pass fixture `g5-preview-confirmed` itself carries `"feedback": ""` and expects RUN OK. Result: a silent false-pass where a broken adapter handshake or empty/garbage feedback reads as "preview approved".

CONTEXT principle: "Evidence exists only to satisfy a declared criterion." A confirm record that greenlights non-actionable feedback is evidence of nothing.

## Decision

Two-layer feedback validation. Note the enforcement site: authoritative floor rule lives in **Preview integrity** and executes inside the transaction before it writes a confirm; it does not move decision authority out of the transaction (ADR-0013).

1. **Adapter floor (machine, `mcp/preview/integrity.py`, called by `transaction.py`).** Before writing `confirmed=true`, the transaction applies the authoritative deterministic structural floor to the feedback on a confirm choice:
   - trigger: feedback non-empty OR at least one anchor present; AND
   - if anchors are present, **every** anchor carries a non-empty `selector` AND a non-empty `comment` (the annotation text itself, not just a label).
   The "every anchor complete" constraint applies independently of whether feedback is non-empty - a non-empty feedback with an incomplete anchor still fails. This is deliberately structural, not semantic. It does NOT attempt to judge whether feedback "makes sense" or whether a selector resolves to a real DOM node (the selector is a JS-generated cssPath against the prototype HTML; the Python adapter has no DOM to validate against, so node-resolution is left to the evaluator's semantic layer). The floor only checks that feedback is self-consistent and substantive. On floor failure on a confirm choice: do NOT write `confirmed=true`; write a record with `confirmed=false` + `floor_failure` reason, and return it to the MCP caller so the orchestrator treats it as not-yet-confirmed.

   **Frontend defense-in-depth (in-page JS, advisory only).** The Python Preview integrity rule catches empty/non-substantive confirms authoritatively, but the pill's primary "确认通过" button is `type="submit"` and previously submitted an empty form before the floor could guide the user. The frontend submit handler performs an advisory pre-check: on a confirm (or revise) choice, if not substantive (no non-empty feedback AND no complete anchors), `preventDefault()`, open the drawer, focus the feedback field, and surface the hint - instead of round-tripping a doomed submit. This is **not** a 7th gate and cannot produce an authoritative confirmation; `transaction.py` always applies the Python rule. `test_floor_frontend.py` covers UX behavior, while Preview integrity tests cover authority.

2. **Evaluator semantic judgment (G6, `ui-evaluator`).** `ui-evaluator` reads `preview/log.md` + confirm json as a supporting finding: did feedback actually drive a revision, or was it non-actionable that slipped past the floor? Finding `source` is attributed to `preview* seam` (the adapter-loop contract), not UI source, when the defect is in the adapter loop. This catches what the structural floor cannot — e.g. "安师大" passes the floor (non-empty, may resolve) but is semantically unrelated; only the evaluator reading log.md catches it.

Floor = cheap deterministic structural check in the adapter; semantic judgment = expensive check in the evaluator. G5 (machine) gates on the floor having passed; semantics live in G6 (acceptance).

## Consequences

- `server.py` `_write_confirm` / `do_POST` gains the floor before persisting `confirmed=true`; signature/callers updated as needed.
- `SKILL.md` step 5 + "Done when" updated: `confirmed=true` from the tool is **not authoritative** until the floor passed (or a `floor_pass` flag exists); the orchestrator treats a confirm record without floor-pass as a revise.
- `ui-evaluator` adds preview-seam-health to its supporting findings checklist.
- G5 gate (`validate_run.py` `check_preview`) asserts the floor ran (e.g. confirm record carries `floor_pass: true`), not just file existence. The existing `g5-preview-confirmed` fixture must be updated to carry substantive feedback + `floor_pass`, else it must fail.
- Garbage/empty/non-actionable adapter feedback no longer silently advances to Fill.
- No new gate (G7) is introduced (issue 04 bans it); the floor is enforced inside the existing G5 path and the adapter write.
- Out of scope: full semantic validation of feedback in the adapter; manifest schema structural fields (still DEFER post-v1, only `observed` field format tightened by Q3.2).

## Migration / backward compatibility

Pre-ADR confirm records (written before 2026-07-18) carry **no `floor_pass` field**. Under the new G5, `data.get("floor_pass") is not True` treats them as floor-failed → they fail G5 with `failed feedback floor: no floor_pass=true`.

This is **intentional and by design**, not a regression:
- v0.2.0 shipped only days prior; the install base of in-flight runs is negligible.
- A confirm record that cannot prove its feedback passed the floor is, under the new contract, not authoritative evidence — exactly the silent false-pass ADR-0008 closes.
- Dogfood throwaway runs (e.g. 0015) are not migrated; their pre-ADR confirms correctly fail G5 on re-validation.

No schema-version field is added (manifest/confirm schema structural fields remain DEFER post-v1, per Q3.2 non-goals). If a pre-ADR run must be re-validated, re-run its preview step to produce a floor-passed confirm rather than patching the old record.

## Enforcement sites (landed 2026-07-18, SEAM TEST PASSED)

1. ✅ `packages/design-playbook/mcp/preview/integrity.py` owns `evaluate_feedback_floor`; `transaction.py` applies it before persisting `confirmed=true`, records `floor_pass`/`floor_failure`, and exposes `_self_check_floor()` via `server.py --self-check`. Frontend advisory behavior lives in `control.js` and is covered independently by `test_floor_frontend.py`.
2. ✅ `packages/design-playbook/skills/design-playbook/SKILL.md` — step 5 + "Done when": confirm requires `floor_pass: true`.
3. ✅ `packages/design-playbook/scripts/validate_run.py` — `check_preview` asserts `floor_pass`, rejects confirmed-without-floor.
4. ✅ G5 pass fixtures (`g5-preview-confirmed`, `g5-aborted-then-confirmed`, `g5-multi-round-last-confirmed`) carry substantive feedback + `floor_pass`; new fail fixture `g5-confirm-floor-fail` (empty feedback, no floor_pass) rejects with "failed feedback floor".
5. ✅ `ui-evaluator` rubric — preview-seam-health supporting finding, `source = preview* seam`.
6. ✅ Regression: dogfood 0015's pre-ADR confirm (no `floor_pass`) now fails G5 by design; new confirms with substantive feedback + `floor_pass=true` pass.

## Amendment (2026-10-08): effective visual edits may confirm without notes

The maintainer explicitly requested edit-only submission and clickable submission
buttons. This supersedes the original trigger for rounds carrying visual edits:
non-empty feedback, at least one complete anchor, **or a validated visual-edit
batch with an effective change** satisfies the structural floor. An effective
change has a different final value from its original value for the same `kind`,
`locator`, and `property`; no-op edits and chains undone to their baseline do
not qualify. `viewport` is deliberately **not** part of that key: the editor has
one shared DOM, so a change made while one viewport is selected and its reversal
under another act on the same element. Keying by viewport would count that round
trip as two effective changes and let a zero-net-change round confirm, which is
the hole an independent review found and this wording closes. Viewport stays on
each edit as provenance.

Every supplied anchor still needs a non-empty selector and comment, regardless
of edits or overall feedback. An empty round remains blocked, with an actionable
on-click hint rather than a disabled submission control. The editor's readiness
mirror follows the same rule: a stale batch does not read as ready, and an edit
whose receipt has not arrived yet counts as pending so the first edit is
submittable.

What "validated" does and does not mean (recorded after an independent review
tried to break the rule):

- It means the batch has a canonical shape, is bound to the current source and
  route, and its canonical hash matches. It does **not** mean the transaction can
  prove that a DOM edit actually happened: the batch is trusted input from the
  parent control shell, exactly as free-text feedback is. A user who can rewrite
  the hidden batch field can therefore stage a fabricated edit; that was already
  true of feedback, and the floor has never been a semantic or anti-forgery
  control. Requiring a `batchHash` raises the effort but cannot close this,
  because the client is not a trust boundary.
- A malformed, stale, or hash-mismatched batch cannot **itself** satisfy the
  floor. It does not poison a round that also supplies non-empty feedback or a
  complete anchor: such a round still confirms, and the batch error is recorded
  in `visual_edits_error` and surfaced on the response page. Tightening that is
  a separate decision, not part of this amendment.
- The "every supplied anchor is complete" rule is enforced over the anchors the
  adapter parser retains. `review_session._parse_anchors` used to drop an anchor
  whose selector was empty instead of failing the round, which let a hand-crafted
  POST bypass the check. Fixed on 2026-10-08 under an ADR-0045 scope extension:
  the parser now raises and `do_POST` refuses the round before the one-time token
  is spent, so a malformed submission cannot burn a reviewer's session. An anchor
  with a selector and an empty comment is still retained, because that is a
  supplied but incomplete anchor and the floor is what reports it.

Preview confirmation remains separate from source-write authorization. Valid
edit-only confirms carry the same `floor_pass` and source-bound agent handoff;
`writesSource` remains false, and G5 token/first-decision authority is unchanged.
The frontend drains outstanding edits before evaluating its advisory mirror.
The header is the only decision surface, and it stays reachable when the rail is
collapsed, so no second submission control exists anywhere in the shell. The rail
reports readiness and names the action instead of offering one. Annotation
drafts retain automatic persistence without a second decision-like draft button.

## Amendment: skip disposition (2026-08-22)

The control UI gains an explicit **skip** choice (drawer quiet button, locale
label `t("skip")`; `SKIP_LABELS` in `i18n.py` is the single label source). A
skip is an **explicit non-confirm disposition**, deliberately outside
`CONFIRM_LABELS`:

- `user_confirmed` stays `false`; no `confirm-round-*.json` is written (the
  entry is audited in `log.md` like a revise, with `- selected: <skip label>`).
- The floor is **not evaluated** against a skip (`floor_pass=true`,
  `floor_failure=""`): an exempt pass is not a floor verdict on feedback.
  Because `user_confirmed` stays `false` and no confirm record is written,
  a skip never satisfies G5 — matching "preview confirmation stays
  unskippable" (CONTEXT.md): you cannot skip **to** a confirmation.
- The decision entry and transaction result carry `skipped: true` so
  orchestrators can narrate the round as user-declined rather than revise.
- Frontend advisory (`control.js isSkipChoice`) mirrors `SKIP_LABELS`
  (defense-in-depth, never authoritative); `"pass"` remains a confirm label
  and is excluded from the skip set on both sides.

A skipped round ends unconfirmed; the orchestrator may start a new round or
move on per its own stop policy.
