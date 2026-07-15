# 03 - Description trigger-branch trim (P2)

**What to build:** A light writing-great-skills pass on the six skill descriptions - each keeps leading word + one trigger branch + reach clause; synonym branches dropped. Bodies untouched.

**Blocked by:** None - can start immediately

**Status:** implemented (pending commit)

- [x] Each of the six `SKILL.md` descriptions front-loads its leading word
- [x] No description carries two synonym triggers for the same branch
- [x] Each description keeps a reach clause (what it invokes / when another skill reaches it)
- [x] Skill bodies unchanged (no sprawl)
- [x] `native-craft` description still triggers on native-desktop asks

## Implementation notes

- `native-craft`: dropped six synonym trigger phrases ("Electron alternative", "Tauri vs native", "feels like a web page", "native windowing", "system tray / launcher", "cross-platform desktop") - all one branch. Kept reach clause "Invoked before ui-picker for native-desktop targets, not web pages."
- `craft-guard`: collapsed "polishing / adding motion / fixing loading" facets into one polish branch; kept the distinct AI-slop branch.
- `ui-evaluator`: collapsed "design review / acceptance / recirculatable critique" synonyms into one branch.
- `ui-picker`: condensed the page-type list into one parenthetical (examples, not branches).
- `design-playbook` (3 distinct branches: build / fix / recirculate + reach) and `ux-spec` (2 distinct: author / gap) already met the bar - left as-is.
- Only `description:` lines edited; bodies byte-identical (line counts unchanged).

## Review (standards + spec, inline; no git)

- **Spec:** matches 04-P2 decision (description trim, bodies untouched).
- **Standards:** writing-great-skills - front-loaded leading words, one-trigger-per-branch (synonyms collapsed), reach clauses retained, no sprawl. Lower context load, sharper triggering.
- **Commit:** deferred to ticket 06.
