# ADR-0007: native-craft - authored absorption of native-feel

## Status

Accepted (wayfinder ticket 03, user-directed)

## Context

User requested absorbing [yetone/native-feel-skill](https://github.com/yetone/native-feel-skill) (MIT) into the plugin as a sixth skill, combined with the project's existing web-skill design principles and the Design I/O method framing, rewritten and renamed. ADR-0004 forbids porting third-party material; ADR-0003 restricts the redistributable surface to authored content.

## Decision

1. Add a sixth skill `native-craft` - the native-feel desktop declaration leaf (render-surface seam + native conventions), twin of `craft-guard` for native/desktop targets.
2. **Authored, not ported.** The SKILL.md and `references/native-feel.md` are written in our voice following writing-great-skills (leading word `native-feel`, Done when, progressive disclosure). We condense the decision gate and native-conventions audit; we do **not** copy the original's 8 reference files (WebView survival, IPC contract, memory truths, Raycast evidence).
3. **Depth points outward.** Full depth remains in the original `native-feel-skill`, which users install separately. Our `references/native-feel.md` names those files and links the repo. Single source of truth for deep content stays with the original.
4. **Attribution.** README Acknowledgements + NOTICE credit yetone/native-feel-skill (MIT), reproduce the MIT copyright line, and note the Design I/O framing is inspired by (not copied from) alibaba-cloud-design/vibe-designing-playbook.
5. This is a **narrow, licensed, attributed exception** to ADR-0004's "no port" stance - it is absorption-by-reauthoring, not redistribution of third-party text. ADR-0004's prohibition on porting the upstream playbook corpus is unchanged.

## Consequences

- Skill count is now six; orchestrator `design-playbook` invokes `native-craft` at the shell step for native-desktop targets, and the recirculate/contracts tables list it.
- `craft-guard` rules apply above the render seam; native conventions below it. `native-craft` wins below the seam where the two would conflict.
- Maintenance: our condensed reference must track the original's substantive changes; a periodic sync note is an implement-time task, not part of this decision.
- If the original changes license or is removed, we retain our authored leaf (attribution stays); only the outward depth pointer breaks.
