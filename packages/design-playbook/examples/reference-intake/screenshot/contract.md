# Reference contract — screenshot fixture

## Source summary

- Ask (one line): Rebuild the ops alert list so empty/error states match this screenshot's information hierarchy, without copying brand chrome.
- Sources (ids matching `manifest.json`): src-1 (local screenshot)
- Captured at (ISO-8601; may match `manifest.json` top-level `captured_at`): 2026-07-22T10:00:00+08:00

## Evidence (observed)

- Dense console list: primary column is alert title; secondary meta is severity + time.
- Empty state is a centered panel with one primary action, not a blank table body only.
- Severity uses a compact status chip left of the title, not a colored full-row background.

## Inferred (labeled)

- Operators scan severity before title | confidence: medium | why: chip is left-aligned in the first 80px of each row
- Empty-state action creates a new alert rule | confidence: low | why: button label not fully legible in the crop

## Keep

- Severity-before-title scan order
- Empty state with a single primary recovery action

## Change

- Replace third-party product name and iconography with our product voice
- Map severity chip to our status role tokens, not the reference palette

## Do not copy

- Product logo, wordmark, and distinctive empty-state illustration
- Exact marketing microcopy on the primary button

## Functional constraints for ux-spec

- Goal / scene hints: operator can triage alerts and recover from empty/error
- States or edges implied: default list, empty, error reload
- Non-goals implied by Do not copy: do not reproduce vendor branding or illustration system
- always / ask / never hints: always show empty recovery action; ask before bulk-dismiss; never auto-delete alerts

## Visual cues for ui-picker

- Density: console-tight
- Scene class hints: list
- Region weight / hierarchy: main = table; action = top-right primary; status = per-row chip
- Explicit exclusions: no marketing hero, no full-row severity paint

## License / brand risks

- Screenshot appears to be a third-party product UI; treat as unlicensed reference only. Do not ship cropped brand assets into Fill or public demos.

## Unresolved questions

- Exact empty-state button label is illegible in the crop; confirm with product owner
