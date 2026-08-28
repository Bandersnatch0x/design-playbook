# craft rules

## State feedback

Loading tiers belong in `SKILL.md` loading tiers; this file covers only failure and degraded states:

- Failure: reason + recoverable action (retry / dismiss / view log)
- Insufficient permission: disabled + required permission description

## Craft

- Nested corner-radius and spacing are layered; avoid the same radius and shadow site-wide
- Shadow steps are few and stable; hierarchy via surface, not rainbow borders
- CJK+Latin mixed type: CJK line-height and punctuation take priority

## Interactive affordance (L4 interactive zones, grill v0.3 Q3.4)

Every L4-declared interactive zone (row, card, button group, clickable unit) must have intentional motion/hover affordance, with purpose stated in the craft review:

- Default hover/active has a transition (opacity / transform / background, ~120ms), purpose written in the craft report (e.g. example (zh): "行可点 → 提示可进入详情" meaning "row is clickable → hints it leads to detail"; example (zh): "行只读 → 不加 hover" meaning "row is read-only → no hover").
- Static throwaway prototypes must still express the affordance intent: either provide hover or explicitly declare example (zh): "此区只读，无 hover" meaning "this zone is read-only, no hover" — silent PASS where "zone has neither hover nor declaration" is not allowed.
- Ledger rows in data tables/lists are especially easy to miss: in dense scanning contexts hover is a scannability affordance, not decoration.

**Done when:** every L4 interactive zone has motion/hover purpose (provided or explicitly declared read-only); no zone silently missing hover.

## Charts

- Category colors are stable and nameable; risk colors delegate to `domain`
- Containers and axes are readable; do not sacrifice scannability for visual flair
