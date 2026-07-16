# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.

## Active product effort

- v0 (mostly done): `.scratch/design-playbook-v0/` (see `docs/agents/product-workflow.md`).
- **Wayfinder elevate:** `.scratch/elevate-structure-install-skills/` — map `map.md`; structure / install / skill-workflow decisions.
- **Wayfinder pipeline-plan-preview:** `.scratch/pipeline-plan-preview/` — map `map.md`; plan 前移 + ui-picker ⇄ preview 循环 + 机器 gate 决策。已 **Clear**（2026-07-16）；implement handoff #1–#5 已落地（skill/G5/adapter/CONTEXT/dogfood；见 map.md）。
- **Wayfinder criterion-addressable-evidence:** `.scratch/criterion-addressable-evidence/` — map `map.md`; post-Fill 运行取证契约（capture plan / manifest / provider / G6）。已 **Clear**（2026-07-16），转 implement（G6 代码 + step 8 文案 + 词汇；见 map.md「Map status」）。
