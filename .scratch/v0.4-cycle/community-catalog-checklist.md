# Community catalog submission checklist (`@claude-community`)

**Status:** **READY FOR HUMAN SUBMIT — authenticated account required** (refreshed 2026-08-04).

Package and public channels are ready. Agent-side checks are complete; final form authentication and POST remain human-only.

Submission pin: `aed0e87540278529b5c89160b52c21ff1e938c7b` (tag **v0.10.0**).
Decision source: v0.4-cycle issue 03 Theme 3b; v0.9-cycle Q4 retained community distribution as the external-signal path after `run-review` shipped.

## Gate

- [x] **Gate 5 public install smoke** on `v0.10.0`, clean isolated `CLAUDE_CONFIG_DIR`, no `--plugin-dir`
  1. documented explicit HTTPS marketplace add → PASS
  2. `design-playbook@design-playbook` user install → `0.10.0`, enabled
  3. on-disk inventory → 8 skills, 4 commands, 2 MCP servers
  4. `claude plugin validate --strict` → PASS
  5. Preview + Evidence MCP `initialize` / `tools/list` → PASS
  6. clean npm consumer install → `design-playbook@0.10.0`, matching 8 / 4 / 2 inventory
- [x] Smoke evidence: `.scratch/design-playbook-v0/evidence/gate5-install-smoke-v0.10.0-2026-08-04/result.md`
- [x] Release gate passed before tag; release commit and tag are identical at `aed0e87`
- [x] GitHub Release: https://github.com/Bandersnatch0x/design-playbook/releases/tag/v0.10.0
- [x] npm `latest=0.10.0`; shasum `b4b9b3b84bb22a0057d2a1d24499642deed3af69`
- [x] Final main CI passed: https://github.com/Bandersnatch0x/design-playbook/actions/runs/30881127987

## Pre-submit checks

- [x] Five version sites + README badges match `0.10.0`
- [x] `claude plugin validate --strict packages/design-playbook` passed (2026-08-04)
- [x] `scripts/doctor.py --skip-self-check` passed with 8 skills / 4 commands / 2 MCP servers (2026-08-04)
- [x] Showcase demonstrates spec → decision report → preview HITL → point-back; observe evidence remains covered by dogfood and MCP gates
- [x] Community catalog scan (2026-08-04): `anthropics/claude-plugins-community` has 2298 entries; no `design-playbook` / `Bandersnatch0x`
- [x] Official catalog scan (2026-08-04): `anthropics/claude-plugins-official` has 278 entries; no `design-playbook` / `Bandersnatch0x`

## Submission route

Current Claude plugin docs still define `claude-community` as the public marketplace where reviewed third-party submissions land:

1. Individual author Console form: https://platform.claude.com/plugins/submit
2. Team/Enterprise directory form: https://claude.ai/admin-settings/directory/submissions/plugins/new
3. Canonical docs pointer: https://clau.de/plugin-directory-submission
4. Run strict validation before submission; review runs validation plus automated safety screening.
5. Approved plugins are pinned to a commit SHA in `anthropics/claude-plugins-community`; catalog CI may advance the pin when repository commits are pushed.
6. After approval, install with `/plugin install design-playbook@claude-community`.

### Current access evidence

| Check | Result |
| --- | --- |
| Console form anonymous GET (2026-08-04) | HTTP 200; prior `app-unavailable-in-region` redirect not reproduced anonymously |
| Team/Enterprise form anonymous GET | HTTP 403; authenticated organization context required |
| Canonical short link | HTTP 200 → Claude plugin submission docs |
| Authenticated form state | not tested; prior system-browser identity was on hold (`account_banned`, recorded 2026-07-21) |
| Direct PR to community mirror | unsupported; use submission form |

**Human gate:** open one submission form with an eligible authenticated account, verify region/account access, submit the fields below, then record confirmation or ticket ID. Agent must not bypass regional availability or account restrictions.

## Paste-ready fields

| Field | Value |
| --- | --- |
| Plugin name | `design-playbook` |
| Version | `0.10.0` |
| Author | `Bandersnatch0x` |
| License | `MIT` |
| Homepage | `https://github.com/Bandersnatch0x/design-playbook` |
| GitHub / source URL | `https://github.com/Bandersnatch0x/design-playbook.git` |
| Plugin subpath | `packages/design-playbook` |
| Commit pin | `aed0e87540278529b5c89160b52c21ff1e938c7b` |
| Tag pin | `v0.10.0` |
| Inventory | 8 model skills · 4 commands · 2 bundled MCP servers |
| Category / keywords | design · ui · ux · design-io · spec · craft · evaluator · console · cjk |
| Short description | Design I/O plugin for coding agents: declarations + contracts that make product UI generation constrained, reviewable, and recirculatable. |
| Longer description | Design I/O pipeline for coding agents: optional project baseline and reference intake, outcome-first UX spec, pre-code UI decision report, optional HITL preview, Fill + craft checks, criterion-addressable runtime evidence, point-back evaluation, bounded recirculation, and cross-run review. Compose with ui-ux-pro-max and Anthropic frontend-design for aesthetics; design-playbook owns pipeline and acceptance. |

## Expected catalog entry

```json
{
  "name": "design-playbook",
  "description": "Design I/O plugin for coding agents: declarations + contracts that make product UI generation constrained, reviewable, and recirculatable.",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/Bandersnatch0x/design-playbook.git",
    "path": "packages/design-playbook",
    "ref": "v0.10.0",
    "sha": "aed0e87540278529b5c89160b52c21ff1e938c7b"
  },
  "homepage": "https://github.com/Bandersnatch0x/design-playbook"
}
```

Do not submit repository root as plugin root. Root holds marketplace catalog; plugin manifest lives under `packages/design-playbook/`.

## After submission

1. Record confirmation / ticket ID here.
2. Change status to `SUBMITTED · awaiting review`.
3. When entry appears in community `marketplace.json`, change status to `LIVE` and record pinned SHA.
4. Run `claude plugin install design-playbook@claude-community` in an isolated config.

## Out of scope

- Automating authenticated form POST.
- Circumventing Anthropic regional or account restrictions.
- Treating `claude-plugins-official` as third-party submission target; official docs route reviewed third-party plugins to `claude-community`.
