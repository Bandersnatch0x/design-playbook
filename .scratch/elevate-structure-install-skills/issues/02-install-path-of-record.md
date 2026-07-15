# 02 — Install path of record

**Type:** grilling  
**Status:** resolved  
**Blocked by:** 01 (resolved)

## Question

What is the **single install path of record** we document first for strangers (and what are secondary)?

Candidates:

- `claude --plugin-dir <path>`
- `/plugin marketplace add <local-or-git>` + `/plugin install design-playbook@design-playbook`
- Future: community / official marketplace listing

Also decide:

- Required **smoke gate** before calling a release “shipped” (manual checklist vs scripted).
- How we teach **namespaced** invokes (`/design-playbook:design-io`) so bare `/design-io` is not the primary story.

## Answer

**Decision: default accepted.**

**Path of record (first-class, stranger public install):**

```text
/plugin marketplace add <owner>/<repo>
/plugin install design-playbook@design-playbook
```

**Secondary (documented, not lead):**

- Dev/self-test: `claude --plugin-dir <abs>/packages/design-playbook`
- Upgrade: `/plugin marketplace update` then `/reload-plugins`
- Community catalog (`@claude-community`): deferred - out of this increment, stays in Not-yet-specified.

**Smoke gate (manual checklist; stays manual until a git remote exists):**

1. `claude --plugin-dir <abs>/packages/design-playbook` -> `/reload-plugins` no errors.
2. `/design-playbook:design-io <real ask>` passes all five dogfood gates.
3. `claude plugin validate` if available; else skip + note.
4. Package `rg -i "cloudai|阿里云|ACD|ECS|演示附件|manuscript"` clean.
5. README install trio copy-paste works, no monorepo-internal paths.

**Namespacing teaching:**

- README tables use namespaced `/design-playbook:design-io` · `:ux-spec` · `:ui-review`.
- Explicit note: bare `/design-io` is a `--plugin-dir` dev-time alias only; **not** valid after marketplace install.
- Skill bodies' slash references updated to namespaced form.

Unblocks: **06** (release + distribution gate, which owns `git init`/remote/versioning).
