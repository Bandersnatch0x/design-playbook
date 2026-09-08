# craft-guard audit — case-reader Fill

Registry: `skills/design-playbook/references/rules.md`. Applicable rows evaluated on the Fill (`showcase/case-reader/index.html`) with rendered evidence under `run/evidence/` and source `showcase/case-reader/index.html` + `_gen_docs.js`.

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | Fill has a single primary region (article) led by one h2; nav is secondary | clear | evidence/L6.1-a11y-tree.json (article landmark single) | index.html:16 main grid, one article | none | - |
| CRAFT-02@1 | applicable | surface contains a list (nav material directory) | clear | evidence/L6.1-a11y-tree.json (navigation list, not card wall) | index.html:22 nav grid of anchors | none | - |
| CRAFT-03@1 | not-applicable | single flat article container; no nested/floating layer stack (observable: one article, one aside, no dialogs/drawers/popovers) | - | evidence/L6.1-a11y-tree.json | index.html:47-49 | none | - |
| CRAFT-04@1 | applicable | palette is two greens + neutrals from confirmed feedback | clear | evidence/L6.4-desktop-1440.png | index.html:7 --page/--surface/--accent tokens | none | - |
| CRAFT-05@1 | not-applicable | no pill/chip components on the audited surface (observable: anchors and one input only) | - | evidence/L6.1-a11y-tree.json | index.html:22-25 | none | - |
| CRAFT-06@1 | applicable | 18px body confirmed by user; 16px source text; 13-15px labels distinct scale | clear | evidence/L6.4-desktop-1440.png | index.html:7 font tokens, plan.md 18px decision | none | - |
| CRAFT-07@1 | not-applicable | no icon usage; all controls are native labeled input/links (observable) | - | evidence/L6.1-a11y-tree.json (searchbox labeled, links named) | index.html:45 | none | - |
| CRAFT-08@1 | not-applicable | no animation declared or present (observable: no transition/animation in CSS) | - | - | index.html:7-39 (no animation properties) | none | - |
| A11Y-01@1 | applicable | Fill has interactive elements (search, links) | clear | evidence/L6.1-a11y-tree.json (names/roles present); keyboard path verified in sweep | index.html:45 label/for, nav aria-label | none | - |
| A11Y-02@1 | applicable | keyboard-focusable links/input | clear | evidence/L6.4-keyboard.json; focus moved to h2 on selection | index.html:9 focus-visible outline 3px | none | - |
| RESP-01@1 | applicable | spec L6.4 declares 1440/768/390 | clear | evidence/L6.4-desktop-1440.png, L6.4-tablet-768.png, L6.4-mobile-390.png; no-overflow assertions | index.html:39 media query | none | - |
| I18N-01@1 | not-applicable | single-language (zh-CN) document interface, no i18n field declared in contract (observable) | - | - | contract.json (no i18n field) | none | - |
| PERF-01@1 | not-applicable | no async operation declared; spec L5 loading = synchronous embedded data (observable) | - | - | index.html (no fetch) | none | - |
| SEC-01@1 | not-applicable | no sensitive data or dangerous operation in scope; read-only page (observable) | - | - | spec.md L1 non-goals | none | - |
| COPY-01@1 | applicable | surface has labeled controls (查找材料, 返回首篇) | clear | evidence/L6.1-a11y-tree.json (searchbox labeled) | index.html:45, 49 | none | - |
| COPY-02@1 | applicable | surface names objects users act on (材料, 案例) | clear | evidence/L6.1-a11y-tree.json | index.html header/footer copy | none | - |
| COPY-03@1 | applicable | error state rendered (invalid fragment) | clear | evidence/L6.3-unknown-fragment-v2.png (error message + recovery link) | index.html:49 error copy | none | - |
| CRAFT-09@1 | applicable | styling source available | clear | evidence/L6.4-desktop-1440.png (single consistent stylesheet renders one visual system) | index.html:7-39 (single stylesheet, no repeated overrides) | none | - |
| CRAFT-10@1 | applicable | structural devices used (eyebrow, numbering 01/02, boundary panel) | clear | evidence/L6.4-desktop-1440.png | index.html:11, 45-49 | none | - |
| DECIDE-01@1 | applicable | decision report carries DD-0001 tier: compare | clear | evidence/L6.4-desktop-1440.png (chosen option A rendered: native directory links + single article) | run/decision-report.md:38-42 (compare tier recorded with rationale) | none | - |

Applicable count: 12 (CRAFT-01/02/04/06/09/10, A11Y-01/02, RESP-01, COPY-01/02/03, DECIDE-01). No blocked rows; no hits.
