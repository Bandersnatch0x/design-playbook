# ADR-0008: Preview feedback floor before confirm

## Status

Accepted (v0.3 grill, 2026-07-18). **Floor enforcement implemented 2026-07-18** — all Open enforcement sites landed; SEAM TEST PASSED. Pre-ADR confirm records (no `floor_pass`) now fail G5 by design.

## Context

Dogfood 0015 (`dogfood/2026-07-18-0015.md`, G1, high) showed `preview_prototype` returning non-actionable feedback ("安师大" — a valid Chinese string unrelated to the annotated element, plus an unrelated anchor) that still produced `confirmed=true` and advanced to Fill. The defect is **feedback unrelated to the annotated element**, not mojibake (the string is valid UTF-8).

Critically, the confirm record is **written by the preview MCP adapter** (`packages/design-playbook-preview/server.py`), not by the orchestrator: `do_POST` sets `confirmed=true` for any choice matching CONFIRM_LABELS and persists whatever `feedback` the form sent (default `''`). The client-side guard runs only for revise choices; confirm always succeeds. G5 (`validate_run.py` `check_preview`) then only verifies a `confirm-round-*.json` with `confirmed=true` exists — it does not inspect feedback. The pass fixture `g5-preview-confirmed` itself carries `"feedback": ""` and expects RUN OK. Result: a silent false-pass where a broken adapter handshake or empty/garbage feedback reads as "preview approved".

CONTEXT principle: "Evidence exists only to satisfy a declared criterion." A confirm record that greenlights non-actionable feedback is evidence of nothing.

## Decision

Two-layer feedback validation. Note the enforcement site: the floor executes **inside the adapter** (it owns the confirm write), not in the orchestrator.

1. **Adapter floor (machine, in `server.py` before `_write_confirm`).** Before writing `confirmed=true`, the adapter applies a **deterministic structural** floor to the feedback on a confirm choice:
   - trigger: feedback non-empty OR at least one anchor present; AND
   - if anchors are present, **every** anchor carries a non-empty `selector` AND a non-empty `comment` (the annotation text itself, not just a label).
   The "every anchor complete" constraint applies independently of whether feedback is non-empty - a non-empty feedback with an incomplete anchor still fails. This is deliberately structural, not semantic. It does NOT attempt to judge whether feedback "makes sense" or whether a selector resolves to a real DOM node (the selector is a JS-generated cssPath against the prototype HTML; the Python adapter has no DOM to validate against, so node-resolution is left to the evaluator's semantic layer). The floor only checks that feedback is self-consistent and substantive. On floor failure on a confirm choice: do NOT write `confirmed=true`; write a record with `confirmed=false` + `floor_failure` reason, and return it to the MCP caller so the orchestrator treats it as not-yet-confirmed.

   **Frontend defense-in-depth (in-page JS, same floor semantics).** The adapter floor catches empty/non-substantive confirms server-side, but the pill's primary "确认通过" button is `type="submit"` and previously submitted an empty form before the floor could guide the user. The frontend submit handler now mirrors the adapter floor: on a confirm (or revise) choice, if not substantive (no non-empty feedback AND no complete anchors), `preventDefault()`, open the drawer, focus the feedback field, and surface the hint - instead of round-tripping a doomed submit. This is **not** a 7th gate; it is the same ADR-0008 floor enforced client-side for UX, with the adapter floor remaining the authoritative backstop. Mirrored (not shared - JS vs Python) deliberately; `_self_check_floor` and `test_floor_frontend.py` (playwright) keep the two in lockstep.

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

1. ✅ `packages/design-playbook-preview/confirm.py` (sibling split from `server.py`, wired via `server.py` `do_POST`) — `_check_feedback_floor` + floor before `_write_confirm`; `floor_pass`/`floor_failure` in record + return payload; `_self_check_floor()` via `--self-check` (wired into seam test). Frontend mirror lives in `control.py` (`isSubstantive()`), kept in lockstep by `test_floor_frontend.py`.
2. ✅ `packages/design-playbook/skills/design-playbook/SKILL.md` — step 5 + "Done when": confirm requires `floor_pass: true`.
3. ✅ `packages/design-playbook/scripts/validate_run.py` — `check_preview` asserts `floor_pass`, rejects confirmed-without-floor.
4. ✅ G5 pass fixtures (`g5-preview-confirmed`, `g5-aborted-then-confirmed`, `g5-multi-round-last-confirmed`) carry substantive feedback + `floor_pass`; new fail fixture `g5-confirm-floor-fail` (empty feedback, no floor_pass) rejects with "failed feedback floor".
5. ✅ `ui-evaluator` rubric — preview-seam-health supporting finding, `source = preview* seam`.
6. ✅ Regression: dogfood 0015's pre-ADR confirm (no `floor_pass`) now fails G5 by design; new confirms with substantive feedback + `floor_pass=true` pass.
