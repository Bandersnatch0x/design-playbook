# components (component semantics)

## Four registration layers

| Layer | What to declare |
| --- | --- |
| Source | shadcn / in-house / custom for product |
| Semantic role | state / category / action / container / navigation / feedback |
| Variants and states | size, variant, loading, disabled… |
| Composition boundary | allowed/prohibited nesting and substitution |

## Easily confused

| Pair | Difference |
| --- | --- |
| Badge / Tag | state·count vs category·selectable·removable |
| Modal / Dialog / Drawer | interruption level, information density, dismiss method |
| Tabs / Tabs-Switch | same-space view vs mode/scope switch |
| Dropdown / Menu / Command | scoped selection / action set / search-driven operation |

## Illustrative mapping (agent-ops list row)

Generic example — adapt per product; not a fixed template.

| Datum | Role | Component |
| --- | --- | --- |
| running / failed | run status | Badge |
| high-risk | risk | RiskBadge (+ domain) |
| instance type / environment | category | Tag |
| view log | inline action | Link/Button |
| retry | recovery action | Button |
