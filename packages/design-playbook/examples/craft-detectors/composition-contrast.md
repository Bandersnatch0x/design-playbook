# Composition detector contrast cases

Authored worked cases for CRAFT-01 through CRAFT-05. Each case combines a rendered observation with independent source evidence. `Expected` is advisory detector status, not evaluator severity or verdict.

| Case | ID | Expected | Rendered evidence | Source evidence | Exception check | Owner hint | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| competing-actions-hit | CRAFT-01 | hit | Header exposes Create, Import, and Export with equal filled emphasis | All three actions use primary Button variant | Spec names Create as main task; no equal-choice exception | craft | Keep Create primary and group Import/Export as secondary actions |
| equal-choice-clear | CRAFT-01 | clear | Two plan options receive equal weight in a deliberate comparison | Shared selectable-card primitive applies same selected affordance | Spec requires neutral side-by-side choice before Continue | craft | - |
| queue-card-wall-hit | CRAFT-02 | hit | Twelve equal cards make status and owner hard to compare | Queue records map directly to Card wrappers | Records are operational rows, not independent browse objects | template | Replace card wall with table/list and stable comparison columns |
| card-collection-clear | CRAFT-02 | clear | Gallery cards represent independent templates with image, owner, and open action | TemplateCard owns preview and item-level interaction | Browsable independent objects fit card semantics | template | - |
| nested-panels-hit | CRAFT-03 | hit | Page section floats as a shadowed card containing three more bordered cards | Card wraps section and nested Cards provide spacing only | No modal, tool, or repeated-item semantics justify frames | template | Flatten section, group with spacing/dividers, retain frame only for tool |
| drawer-tool-clear | CRAFT-03 | clear | Unframed page contains one bounded detail drawer | Drawer primitive owns focus and dismiss behavior; no nested Card | Detail drawer is a genuine framed tool | components | - |
| blue-everywhere-hit | CRAFT-04 | hit | Canvas, surfaces, actions, charts, and state badges use blue variants | Single blue ramp fills surface, action, success, and selected roles | No verified monochrome baseline or semantic role separation | design | Restore neutral surfaces and assign distinct semantic state roles |
| semantic-color-clear | CRAFT-04 | clear | Neutral surfaces dominate; cyan marks selection, amber warning, red failure | Tokens map each semantic role independently | Brand accent remains selective and states stay distinguishable | design | - |
| pill-everything-hit | CRAFT-05 | hit | Tabs, buttons, fields, filters, and section labels all use pill silhouettes | Global radius-full token applies across unrelated controls | No baseline or semantic grouping justifies uniform pill geometry | components | Restore control-specific shapes and reserve pills for compact tags |
| status-pill-clear | CRAFT-05 | clear | Compact pills appear only for status and removable filter chips | Badge and Chip primitives use pill shape; buttons use restrained radius | Shape communicates status/grouping and is not page-wide | components | - |
