# Reference contract — URL fixture

## Source summary

- Ask (one line): Settings page for notification channels; use the linked docs site IA as reference, not as a skin.
- Sources (ids matching `manifest.json`): src-1 (URL)
- Captured at (ISO-8601; may match `manifest.json` top-level `captured_at`): 2026-07-22T10:05:00+08:00

## Evidence (observed)

- Left nav groups settings into Account / Notifications / Integrations.
- Notifications page uses a definition-list of channels with a trailing toggle, not a multi-column form grid.
- Destructive actions stay outside the per-channel row.

## Inferred (labeled)

- Toggle is optimistic with toast rollback | confidence: low | why: network behavior not visible from static docs page
- Integrations is out of scope for this ask | confidence: high | why: user named notifications only

## Keep

- Grouped left nav with a single active section highlight
- Channel rows as label + short description + trailing control

## Change

- Replace docs-site content width with our app shell widths
- Use our settings template regions instead of docs sidebar chrome

## Do not copy

- Vendor site logo, docs search widget, and marketing CTA footer
- Exact section titles that are product-trademark phrases

## Functional constraints for ux-spec

- Goal / scene hints: user enables/disables notification channels and understands delivery target
- States or edges implied: loading channel list, save error, permission denied
- Non-goals implied by Do not copy: no docs search, no marketing footer, no integrations subtree in this run
- always / ask / never hints: always show channel delivery target; ask before disabling the last channel; never bury destructive actions in the row

## Visual cues for ui-picker

- Density: console-tight
- Scene class hints: settings
- Region weight / hierarchy: side = section nav; main = channel list; action = page-level save if required
- Explicit exclusions: docs-site header/footer patterns

## License / brand risks

- Public marketing/docs URL is third-party. Capture only structure notes; do not mirror proprietary illustration or trademarked slogans into Fill.

## Unresolved questions

- none
