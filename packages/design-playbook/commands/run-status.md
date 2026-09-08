---
description: Report Design I/O run phase, blocker, and next resume action
---

# run-status

Inspect a stopped Design I/O run without reconstructing state from scratch files by hand.

## Usage

```text
python <plugin>/scripts/run_status.py [.scratch/<run>] [--json] [--list] [--scratch <dir>]
```

- Omit the run path to pick the newest directory under `--scratch` (default `.scratch/`).
- `--json` emits machine-readable stages + `next` action, plus the continuation block: selected run, current phase, blocker, run integrity, and the Console capability receipt (`implementation` / `validation` / `availability` / `publicClaim`).
- `--list` only lists discovered runs.

For an eligible run the continuation names an explicit `open-console` command for the local, experimental, trial-gated Run Console — no authorized external trial or public release is claimed until the separately authorized read-only trial gate passes (ADR-0043). `run-status` never starts a server, daemon, or background process itself; an ineligible run reports the blocking reason and a safe fallback instead.

## Done when

The command names completed stage markers, any active blocker (preview floor, baseline gate, recirculate verdict), and the single next valid resume action. It reuses `validate_run` judgments for G5 confirm validity rather than inventing a second state machine. Stale, partial, hash-mismatched, malformed, or inconsistent runs stay visible as those states and are never replaced by an older successful snapshot.
