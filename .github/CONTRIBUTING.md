# Contributing

Thanks for your interest in design-playbook — a UI Design I/O plugin for coding agents.

## Orientation

Root documents each serve one audience:

| File | Audience |
| --- | --- |
| `README.md` / `README-zh.md` | Users installing the plugin |
| `PRODUCT.md` · `CONTEXT.md` | Product/domain context (vocabulary, decisions) |
| `AGENTS.md` (imported by `CLAUDE.md`) | Coding agents working in this repo |
| `docs/adr/` | Architecture decision records |

## Working on the repo

- Read `AGENTS.md` first — it defines the distributable surface, SSOT, and generated-snapshot rules.
- Issues and labels: `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`.
- Quick gates before a commit: `python scripts/validate.py` · `python scripts/check_doc_links.py` · `python scripts/doctor.py --skip-self-check`. The full matrix (pytest + Chromium e2e) runs in `.github/workflows/ci.yml`.
- Releases follow `docs/agents/release-checklist.md`; `main` is the stable channel.

## Boundaries

The public distributable surface is only first-party content inside `packages/`. Do not copy text, examples, or names from third-party skills or repositories into product content — absorb ideas in original wording only.
