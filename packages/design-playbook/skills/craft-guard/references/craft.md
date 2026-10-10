# craft rules

## State feedback

Loading tiers belong in `SKILL.md` loading tiers. This file covers only failure and degraded states:

- Failure: reason + recoverable action (retry / dismiss / view log)
- Insufficient permission: disabled + required permission description

Copy quality is registry-owned: `COPY-01/02@1` and `COPY-03@2` (active voice, user-side naming, error tone) in [`../../design-playbook/references/rules.md`](../../design-playbook/references/rules.md), pointer only, rule bodies live in the registry.

## Craft

- Nested corner-radius and spacing are layered. Avoid the same radius and shadow site-wide
- Shadow steps are few and stable. Hierarchy via surface, not rainbow borders
- CJK+Latin mixed type: CJK line-height and punctuation take priority

## Interactive affordance (L4 interactive zones, grill v0.3 Q3.4)

Every L4-declared interactive zone (row, card, button group, clickable unit) states its affordance intent in the craft review: either a hover and pressed response, or an explicit read-only declaration (example (zh): "此区只读，无 hover", meaning "this zone is read-only, no hover"). Hover responses apply only where a fine pointer is present; touch-primary viewports express affordance through shape, labeling, or a pressed state instead. Hover and pressed transitions use the motion token for high-frequency interaction and stay within `high-frequency-motion-max` in `CRAFT-08@2`; dense lists may use an instant state change with no transition. Native desktop targets follow the `native-craft` row conventions instead.

- State the purpose in the craft report (example (zh): "行可点时，提示可进入详情", meaning "row is clickable then hints it leads to detail").
- Ledger rows in data tables and lists are especially easy to miss: in dense scanning contexts hover is a scannability affordance, not decoration.

**Done when:** every L4 interactive zone has a stated affordance intent (response provided or read-only declared), matched to the declared input modality, with no raw duration literal.

## Charts

- Category colors are stable and nameable. Risk colors delegate to `domain`
- Containers and axes are readable. Do not sacrifice scannability for visual flair
