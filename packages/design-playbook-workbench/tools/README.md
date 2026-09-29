# Workbench acceptance tools

Operator tools for the acceptance items that need a real host. They are **not**
part of the shipped distribution: the wheel carries only
`design_playbook_workbench/` plus its metadata (verified by
[install_smoke.py](install_smoke.py)'s whitelist probe).

| Tool | Covers | Still needs |
| --- | --- | --- |
| [seed_scale.py](seed_scale.py) | Builds the R15-scale fixture (5,000 assets / 20,000 revisions / 200 canvas instances) as real files plus real service writes | — (input data only) |
| [perf_harness.py](perf_harness.py) | Measures the three R15 budgets in real Chromium against the real service: search p95 ≤ 1 s, 200-node save confirm p95 ≤ 2 s, 100 select/drag responses p95 ≤ 100 ms | A ≥ 4 core / 16 GiB / SSD baseline machine with the R15-scale fixture; below that scale it reports `not-run` |
| [install_smoke.py](install_smoke.py) | A15 clean install: built wheel, fresh venv, standalone run from a neutral cwd, real HTTP probes | Windows ACL / junction / file-occupation evidence on a real Windows host |
| [sample_targets.py](sample_targets.py) | The two A11 handoff targets (static HTML/CSS/JS and React/TypeScript) | A real Agent host to claim a request and return a proposal |

Deterministic helpers are covered by
`tests/test_acceptance_tools.py`; the live flows are operator-driven and their
evidence comes from an actual run, never from that test file.

## Honest scope

None of these tools marks an acceptance item `pass` on its own. `seed_scale.py`
builds input data and claims no timing. `perf_harness.py` measures in-page
against the real service but reports `not-run` below R15 scale or with too few
valid samples, and rejects samples that cannot be proven (a stale save label, a
drag that never moved). `install_smoke.py` reports exactly one A15 item and
lists what it does not cover. `sample_targets.py` writes source scaffolding and
proves no journey. A11, A12 and the rest of A15 stay `blocked`/`not-run` until
a real host produces the evidence.

## Typical acceptance run

```bash
python tools/seed_scale.py --workspace D:/bench/workbench-scale
python tools/perf_harness.py --data-dir D:/bench/workbench-scale/workbench-data \
    --evidence D:/bench/perf.json
python tools/install_smoke.py --evidence D:/bench/install-smoke.json
python tools/sample_targets.py --dest D:/bench/targets
```
