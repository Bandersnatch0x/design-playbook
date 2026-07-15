# 04 - Sixth dogfood gate: recirculate closure

**What to build:** Dogfood gains a sixth gate - blocking findings must show a `recirculate -> fix -> re-eval -> 0 blocking` trail (or explicit acceptance). Skill `Done when` criteria and the dogfood log template match.

**Blocked by:** 02 (resolved)

**Status:** implemented (pending commit)

- [x] `ui-evaluator` Done-when requires blocking findings to have a recirculate trail or explicit acceptance
- [x] `design-playbook` accept step Done-when references the closure (zero blocking or accepted)
- [x] Dogfood log template (under `.scratch/.../dogfood/`) has a sixth gate row: "Recirculate closure"
- [x] A re-run of a prior dogfood scene passes all six gates, with the closure trail logged

## Implementation notes

- `ui-evaluator` step 4 Done-when sharpened: every blocking finding needs a `recirculate -> fix -> re-eval -> 0 blocking` trail or explicit acceptance with recorded reason.
- `design-playbook` accept step Done-when mirrored the same closure requirement.
- `product-dogfood` command gate table expanded 4 -> 6 (added Generality + Recirculate closure); points at the new template.
- New `.scratch/design-playbook-v0/dogfood/_template.md` with six-gate table + recirculate closure trail section.
- Dogfood 003 re-runs the webhook scene and logs the closure trail for both blocking domain findings -> 0 blocking. Sixth gate passes.

## Review (standards + spec, inline; no git)

- **Spec:** matches 04-P0 decision (recirculate closure becomes a dogfood gate); Q2 success #4 now hard-verified.
- **Standards:** writing-great-skills - Done-when is checkable and exhaustive ("every blocking finding... or explicit acceptance"); no body sprawl.
- **Commit:** deferred to ticket 06.
