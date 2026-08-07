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
- `--json` emits machine-readable stages + `next` action.
- `--list` only lists discovered runs.

## Done when

The command names completed stage markers, any active blocker (preview floor, baseline gate, recirculate verdict), and the single next valid resume action. It reuses `validate_run` judgments for G5 confirm validity rather than inventing a second state machine.
