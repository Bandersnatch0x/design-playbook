# design.md (visual-system execution constraints)

## Intent (defaults)

- CJK-first; console density priority; brand color restrained; neutral colors carry hierarchy.

## Role examples

- `--brand`  primary CTA
- `--brand-surface`  selected row / soft badge
- `--foreground-link`  body text link
- `--warning-high`  high risk
- `--chart-1..12`  multi-series chart

## Three execution rules

1. All visual values via `var(--*)`
2. hover/active/disabled/selected derived from base tokens
3. Token not found: log `gaps.log` + valid fallback, or refuse to generate that detail

Do not write bare hex, arbitrary px/ms/cubic-bezier literals that bypass the system.
