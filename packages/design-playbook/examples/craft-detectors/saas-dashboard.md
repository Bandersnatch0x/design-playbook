# SaaS dashboard craft audit

Worked fixture for the seven-column registry audit format. Rendered and source descriptions are independent authored observations, not validator-generated expectations.

## Input

- Rendered surface: desktop operations dashboard at 1440 x 900.
- Source surface: React page using shared Button, Table, Card, Badge, and motion tokens.
- Baseline: none.
- Registry: `skills/design-playbook/references/rules.md`, full catalog enabled (no contract subset declared).

## Craft audit

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | - | hit | Header has three equally filled primary actions | Three Button instances use `variant="primary"` | No equal-choice flow in spec | Keep Create run primary; move Import and Export to secondary/menu actions |
| CRAFT-02@1 | applicable | - | hit | Twelve equal cards hide queue comparison | Queue records map directly to Card wrappers | Records are comparable operational rows, not independent browse objects | Use a table/list with stable columns and one framed detail tool |
| CRAFT-03@1 | applicable | - | clear | Page bands are unframed; detail drawer alone is framed | Card is not nested and Drawer owns detail | Drawer is a genuine framed tool | - |
| CRAFT-04@1 | applicable | - | clear | Neutral surfaces carry most area; amber and red have named state roles | Semantic tokens map warning and failure independently | No monochrome exception needed | - |
| CRAFT-05@1 | not-applicable | Surface declares one restrained standard control radius in design tokens; no pill or shape-geometry variation face is in scope | - | - | - | No geometry face to check | - |
| CRAFT-06@1 | applicable | - | clear | Panel headings fit dense dashboard hierarchy | Display type token is absent inside panels | No hero context claimed | - |
| CRAFT-07@1 | applicable | - | clear | Refresh and close use named icon buttons; destructive action keeps text | IconButton has accessible labels and destructive Button remains explicit | High-risk action needs text | - |
| CRAFT-08@1 | blocked | Motion source was not included in review input; static capture cannot prove transition purpose or reduced-motion behavior | - | Static capture shows a CTA badge mid-animation | Motion source absent from review input | No exception can be checked without source | Provide motion source and interaction trace before complete craft Pass |

## Expected contract observations

- All eight registry craft IDs appear exactly once with pinned versions.
- The ledger demonstrates `applicable` rows with `hit` and `clear`, one `not-applicable` row carrying an observable reason, and one `blocked` row naming its missing proof.
- Hit rows carry rendered evidence, source evidence, exception check, and positive fix.
- No row assigns declaration source, severity, or verdict.
