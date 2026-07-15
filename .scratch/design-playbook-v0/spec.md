# Spec — design-playbook v0 (public-installable Design I/O plugin)

Collapses grill decisions (ADR 0001–0005) + dogfood 001 into a buildable plan.

## Goal

A stranger can install `packages/design-playbook`, run `/design-io`, and get a predictable Design I/O pass (L5/L6 spec → decision report → point-back accept → recirculate), with a clear license boundary and generic (non-ported) references.

## Success criteria (from Q2)

1. `spec.md` with substantive L5/L6 every run
2. decision report before code
3. point-back evaluator findings
4. blocking recirculates to owning declaration
5. copy-paste install works for a stranger

## Constraints / decisions

- Redistributable = authored package content only (ADR-0003)
- SSOT = package skills refs; reference ≠ port (ADR-0004)
- Split package; demo removed (ADR-0005)
- Out: style DB, multi-platform CLI, Figma dependency, demo redesign (ADR-0002)

## Deliverables

- D1 Install docs verified (package path + marketplace) — README copy-paste correct
- D2 Package LICENSE + NOTICE boundary (no upstream claim)
- D3 References generic-pass audit complete (no vendor/playbook lift)
- D4 `design-playbook` step-3 completion criterion branched (codebase vs planning) — dogfood 001
- D5 README “stack with pro-max / frontend-design” section
- D6 Second dogfood after D3–D4, gates green, logged

## Acceptance (v0 ship)

- Install from package path succeeds in a clean Claude session
- `rg` over package skills finds no vendor product names / dead demo links
- One full dogfood post-fix: all five gates pass
- All issues resolved or wontfix
