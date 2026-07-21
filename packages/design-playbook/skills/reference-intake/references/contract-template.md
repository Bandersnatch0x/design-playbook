# Reference contract template

Emit as `.scratch/<run>/reference/contract.md`. Headings are required.

## Source summary

- Ask (one line):
- Sources (ids matching `manifest.json`):
- Captured at (ISO-8601; may match `manifest.json` top-level `captured_at`):

## Evidence (observed)

- ...

## Inferred (labeled)

- ... | confidence: high|medium|low | why:

## Keep

- ...

## Change

- ...

## Do not copy

- ...

## Functional constraints for ux-spec

- Goal / scene hints:
- States or edges implied:
- Non-goals implied by Do not copy:
- always / ask / never hints:

## Visual cues for ui-picker

- Density:
- Scene class hints:
- Region weight / hierarchy:
- Explicit exclusions:

## License / brand risks

- ...

## Unresolved questions

- ... (or `none`)

---

## manifest.json shape

Write beside this contract as `.scratch/<run>/reference/manifest.json`:

```json
{
  "schema": "design-playbook.reference.manifest/v1",
  "run_id": "<run>",
  "captured_at": "2026-07-22T00:00:00+08:00",
  "tool": "reference-intake",
  "sources": [
    {
      "id": "src-1",
      "kind": "screenshot",
      "locator": "assets/hero.png",
      "sha256": "<hex or null>",
      "note": "optional"
    }
  ]
}
```

Rules:

- `kind` is one of: `screenshot`, `url`, `design_file`, `product_analogy`, `other`
- file locators are run-root-relative under `reference/` when copied into `assets/`
- URL locators are absolute strings; `sha256` is null for pure URLs and product analogies
- do not put host Fill paths into `sources`
