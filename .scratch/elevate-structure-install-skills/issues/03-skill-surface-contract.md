# 03 - Skill surface contract

**Type:** grilling  
**Status:** resolved  
**Blocked by:** None - can start immediately

## Question

What is the **skill surface contract** for elevate (not implementation)?

## Answer

**Decision: six skills (five + native-craft), all model-invoked; three commands; examples as human-only onboarding packs.**

1. **Skill set = six.** Keep `design-playbook` (flagship orchestrator), `ux-spec`, `ui-picker`, `craft-guard`, `ui-evaluator`. **Add `native-craft`** - the native-feel desktop declaration leaf (render-surface seam + native conventions), twin of `craft-guard` for native/desktop targets. No merges (preserves per-step triggering + anti-premature-completion); no further splits (Design I/O steps already matched).
2. **All model-invoked.** Five originals stay model-invoked; `native-craft` is model-invoked too (triggered by desktop/native-feel asks, reachable by the orchestrator). No user-only skills this increment - context load is acceptable at six. Candidate to demote to user-only if load reports: `craft-guard`/`ui-evaluator` - parked in Not-yet-specified.
3. **Commands stay three.** `design-io` (full pipeline), `ux-spec` (spec only), `ui-review` (accept only). No `native-craft`/`ui-picker`/`craft-guard` commands - they are skill-triggered, not explicit pipeline entries.
4. **examples/ = human onboarding packs only.** SSOT remains `skills/*/references/*` (ADR-0004). `examples/` is never auto-loaded by skills; users `@`-reference manually. No duplicate maintenance between examples and references.

**native-craft authoring (B1, per user):** authored in our voice, not a verbatim port. Condensed decision gate + native-conventions audit in `references/native-feel.md`; full depth (WebView survival, IPC, memory, Raycast evidence) stays in the original [yetone/native-feel-skill](https://github.com/yetone/native-feel-skill) (MIT). Attribution in README Acknowledgements + NOTICE. Method framing inspired by [vibe-designing-playbook](https://alibaba-cloud-design.github.io/vibe-designing-playbook/) (not copied). See ADR-0007.

**Surface contract (README one-pager):** six namespaced skills + three commands, stack-with-ecosystem table, acknowledgements. Unblocks **04** (workflow process upgrades).
