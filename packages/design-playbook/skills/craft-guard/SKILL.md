---
name: craft-guard
description: UI craft and feedback quality. Use when polishing product UI (motion, loading/error feedback) or when a page reads as AI slop.
---

# craft-guard

**Craft** declaration for cross-product quality: hierarchy, wait feedback, purposeful motion, CJK-safe type. Does not own business risk (`domain`) or token inventory (`design`).

## Apply (checklist)

Treat as exhaustive for the surface under edit.

### Hierarchy and type

- One clear primary; secondary recedes via density/space, not rainbow chrome.  
- CJK UI uses the project Chinese stack (`var(--font-cn)` or equivalent).  
- Brand solid + brand-gradient **≤ 3** emphasis hits per viewport; neutrals carry the rest.

**Done when:** a cold reader can name the primary action/region in one glance.

### Loading tiers

```text
<300ms      no indicator
300ms–2s    skeleton (layout stable)
>2s         loader + what is happening
>10s        timeout + retry (or cancel)
```

**Done when:** every async path in scope maps to a tier with a next action on failure/timeout.

### Motion

- UI motion ≤ 300ms; animate `transform` / `opacity` only.  
- Each animation names the state change it explains.  
- Honor `prefers-reduced-motion`. Keyboard-triggered actions stay free of decorative motion.

**Done when:** no motion lacks a stated purpose.

### AI slop → target look

| Push toward | Instead of default sludge |
| --- | --- |
| Accent on key noun + primary CTA | Purple–blue gradient wallpaper |
| Glass only on rare floating layers | Blur on every card |
| Project CJK stack | Inter/Roboto as Chinese body |
| Weighted modules | Equal white card grid |
| State-explaining motion | Bounce/elastic decoration |

More edge craft: [`references/craft.md`](references/craft.md).

## Completion

**Done when:** hierarchy, every in-scope wait/fail path, and every animation pass the checks above; residual issues are listed for `ui-evaluator` with source `craft`.
