# craft rules

## State feedback

Loading tiers belong in `SKILL.md` loading tiers. This file covers only failure and degraded states:

- Failure: reason + recoverable action (retry / dismiss / view log)
- Insufficient permission: disabled + required permission description

Copy quality is registry-owned: `COPY-01/02/03@1` (active voice, user-side naming, error tone) in [`../../design-playbook/references/rules.md`](../../design-playbook/references/rules.md), pointer only, rule bodies live in the registry.

## Craft

- Nested corner-radius and spacing are layered. Avoid the same radius and shadow site-wide
- Shadow steps are few and stable. Hierarchy via surface, not rainbow borders
- CJK+Latin mixed type: CJK line-height and punctuation take priority

## Interactive affordance (L4 interactive zones, grill v0.3 Q3.4)

Every L4-declared interactive zone (row, card, button group, clickable unit) must have intentional motion and hover affordance, with purpose stated in the craft review:

- Default hover and active states have a transition (opacity / transform / background, ~120ms), purpose written in the craft report (e.g. example (zh): "行可点时，提示可进入详情" meaning "row is clickable then hints it leads to detail". Example (zh): "行只读时，不加 hover" meaning "row is read-only then no hover").
- Static throwaway prototypes must still express the affordance intent. Either provide hover or explicitly declare example (zh): "此区只读，无 hover", meaning "this zone is read-only, no hover". A zone with neither hover nor declaration cannot silently PASS.
- Ledger rows in data tables and lists are especially easy to miss: in dense scanning contexts hover is a scannability affordance, not decoration.

**Done when:** every L4 interactive zone has motion and hover purpose (provided or explicitly declared read-only). No zone silently missing hover.

## Charts

- Category colors are stable and nameable. Risk colors delegate to `domain`
- Containers and axes are readable. Do not sacrifice scannability for visual flair
