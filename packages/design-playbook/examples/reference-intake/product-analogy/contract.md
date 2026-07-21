# Reference contract — product-analogy fixture

## Source summary

- Ask (one line): Agent ops dashboard that feels as scannable as Linear's issue list, but for our agent runs.
- Sources (ids matching `manifest.json`): src-1 (product analogy)
- Captured at (ISO-8601; may match `manifest.json` top-level `captured_at`): 2026-07-22T10:10:00+08:00

## Evidence (observed)

- User provided no screenshot; only the product name "Linear" as a taste anchor.
- Requested qualities in chat: scannable rows, keyboard-friendly, low decoration.

## Inferred (labeled)

- Prefer tight row height and muted meta columns | confidence: medium | why: common Linear-list reading of "scannable"
- Avoid kanban as default | confidence: medium | why: user said list, not board

## Keep

- Scannable list semantics: identity column + sparse meta + quiet density

## Change

- Domain objects are agent runs, not issues; columns and empty states follow our L2 duties
- Keyboard map must match our app, not Linear shortcuts

## Do not copy

- Linear wordmark, issue ID format, and any trademarked product chrome
- Distinctive empty-state illustration or onboarding checklist copy

## Functional constraints for ux-spec

- Goal / scene hints: operator scans agent runs and opens one run detail
- States or edges implied: empty fleet, filtered-empty, run failure badge
- Non-goals implied by Do not copy: not a Linear clone; no issue-tracker information architecture
- always / ask / never hints: always show run state chip; ask before bulk cancel; never use Linear keyboard map as default

## Visual cues for ui-picker

- Density: console-tight
- Scene class hints: list / agent-admin
- Region weight / hierarchy: main = run table; side optional filters; status = run state chip
- Explicit exclusions: marketing hero, board/kanban default

## License / brand risks

- Product analogy only. Do not download or embed Linear brand assets. If a later screenshot is added, re-run reference-intake and tighten Do not copy.

## Unresolved questions

- Which columns are mandatory for v0 agent-run list?
