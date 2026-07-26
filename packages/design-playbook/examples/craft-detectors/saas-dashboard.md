# SaaS dashboard detector contrast

Worked fixture for detector protocol validation. Rendered and source descriptions are independent authored observations, not validator-generated expectations.

## Input

- Rendered surface: desktop operations dashboard at 1440 x 900.
- Source surface: React page using shared Button, Table, Card, Badge, and motion tokens.
- Baseline: none.

## Detector ledger

| ID | Status | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- |
| CRAFT-01 | hit | Header has three equally filled primary actions | Three Button instances use `variant="primary"` | No equal-choice flow in spec | Keep Create run primary; move Import and Export to secondary/menu actions |
| CRAFT-02 | hit | Twelve equal cards hide queue comparison | Queue records map directly to Card wrappers | Records are comparable operational rows, not independent browse objects | Use a table/list with stable columns and one framed detail tool |
| CRAFT-03 | clear | Page bands are unframed; detail drawer alone is framed | Card is not nested and Drawer owns detail | Drawer is a genuine framed tool | - |
| CRAFT-04 | clear | Neutral surfaces carry most area; amber and red have named state roles | Semantic tokens map warning and failure independently | No monochrome exception needed | - |
| CRAFT-05 | clear | Pills appear only for status badges | Badge uses pill radius; buttons and inputs use control-specific shape | Status grouping warrants compact pill | - |
| CRAFT-06 | clear | Panel headings fit dense dashboard hierarchy | Display type token is absent inside panels | No hero context claimed | - |
| CRAFT-07 | clear | Refresh and close use named icon buttons; destructive action keeps text | IconButton has accessible labels and destructive Button remains explicit | High-risk action needs text | - |
| CRAFT-08 | blocked | Static capture cannot prove transition purpose or reduced-motion behavior | Motion source was not included in review input | No exception can be checked without source | Provide motion source and interaction trace before complete craft Pass |

## Expected contract observations

- All eight stable IDs appear exactly once.
- Ledger contains `hit`, `clear`, and `blocked`.
- Hit rows carry rendered evidence, source evidence, exception check, and positive fix.
- No row assigns declaration source, severity, or verdict.
