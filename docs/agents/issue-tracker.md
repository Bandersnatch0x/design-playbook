# Issue tracker: GitHub for bugs, local files for the rest

GitHub Issues carry **bug tickets only** — defects in shipped behavior that anyone could report. Every other planning artifact (specs, research notes, non-bug work tickets, wayfinder maps) lives as local files under `.agents/` (gitignored, never pushed). Use the `gh` CLI for all GitHub operations.

## Routing

| Artifact | Home | Reference in commits |
| --- | --- | --- |
| Bug ticket | GitHub issue (`gh issue create`) | `(#NNN)` |
| Spec | `.agents/specs/YYYY-MM-DD-<slug>.md` | path |
| Research note | `.agents/research/YYYY-MM-DD-<slug>.md` | path |
| Work ticket (non-bug) | `.agents/tickets/T-NNN-<slug>.md` | `(T-NNN)` |
| Wayfinder map | `.agents/tickets/M-NNN-<slug>.md` | `(M-NNN)` |

- **When a skill says "publish to the issue tracker"**: route by the table above — only bugs become GitHub issues.
- **When a skill says "fetch the relevant ticket"**: `gh issue view <number> --comments` for `#NNN`; read the file for `T-NNN` / `M-NNN`.

## GitHub conventions (bug tickets)

- **Create**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read**: `gh issue view <number> --comments`, also fetching labels.
- **List**: `gh issue list --state open --json number,title,body,labels,comments` with appropriate `--label` and `--state` filters.
- **Comment / label / close**: `gh issue comment`, `gh issue edit --add-label` / `--remove-label`, `gh issue close --comment`.
- Triage labels apply to GitHub bug tickets; see `triage-labels.md`.

Infer the repository from `git remote -v`; `gh` does this automatically inside the clone.

## Local tickets

One file per ticket, front matter first:

```yaml
---
id: T-014            # or M-NNN for a wayfinder map
status: open         # open | in-progress | done | wontfix
owner:               # empty = unclaimed
blocked-by: []       # e.g. [T-012, T-013]
part-of:             # map id, when the ticket belongs to a wayfinder map
spec:                # optional path to the driving spec
---
```

- **Numbering**: next integer after the highest existing `T-NNN` / `M-NNN` in `.agents/tickets/`.
- Triage roles map onto `status` + `owner`: an open, unclaimed, unblocked ticket is ready to pick up.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one `M-NNN` file holding Notes, Decisions-so-far, and Fog; children are ordinary `T-NNN` tickets carrying `part-of: M-NNN`.

- **Blocking**: `blocked-by` front matter on the child.
- **Frontier**: choose the first open child in map order that has no open blocker and no owner.
- **Claim**: set `owner` in the child's front matter; this is the session's first write.
- **Resolve**: append the answer to the child, set `status: done`, then append a gist to the map's Decisions-so-far.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set this to `yes` only if external PRs should enter the triage queue.

GitHub shares one number space across issues and PRs. Resolve an ambiguous `#<number>` with `gh pr view <number>` and fall back to `gh issue view <number>`.

## Legacy

Issues ≤ #114 predate this policy and include specs and non-bug tickets: finish them where they are and close them — do not migrate.
