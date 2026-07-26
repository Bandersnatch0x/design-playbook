# Landing and product detector contrast cases

Authored worked cases for CRAFT-06 through CRAFT-08. Each result is advisory and leaves declaration mapping, severity, and verdict to `ui-evaluator`.

| Case | ID | Expected | Rendered evidence | Source evidence | Exception check | Owner hint | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dashboard-display-type-hit | CRAFT-06 | hit | Compact metrics panel uses 72px heading that crowds values below | Panel heading references display-hero token | Surface is an operational panel, not a literal hero | design | Use panel title role and preserve hierarchy through grouping and weight |
| product-hero-clear | CRAFT-06 | clear | Product name leads first viewport while next section remains visible | H1 uses display token within bounded responsive hero | Literal product hero warrants display scale and text fits target viewports | design | - |
| verbose-toolbar-hit | CRAFT-07 | hit | Toolbar repeats Undo, Redo, Save, Zoom in, and Zoom out as wide text pills | Generic Button renders familiar tool actions despite icon library availability | Actions are familiar and low-risk; accessible icon labels are possible | components | Use icon buttons with accessible names and tooltips; keep text for ambiguous commands |
| destructive-text-clear | CRAFT-07 | clear | Delete workspace remains an explicit text action with consequence copy | Destructive Button opens confirmation Dialog | High-risk action benefits from explicit language | components | - |
| looping-decoration-hit | CRAFT-08 | hit | CTA badge bounces continuously without state change | Infinite keyframes animate translateY and ignore reduced-motion | No game or immersive intent is declared | craft | Remove loop and use short transform/opacity feedback only for a named state change |
| state-transition-clear | CRAFT-08 | clear | Saved indicator fades in after persistence and stays stable | 160ms opacity transition follows saved state and reduced-motion disables it | Motion explains persistence completion | craft | - |
