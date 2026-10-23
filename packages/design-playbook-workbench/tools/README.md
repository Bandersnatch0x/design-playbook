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

`perf_harness.py` records the browser it actually drove. Set
`DESIGN_PLAYBOOK_WORKBENCH_BROWSER_CHANNEL` (`msedge`, `chrome`, …) to use a
branded channel; unset means the bundled Chromium. The evidence records the
channel as `env.browserChannel` and the version as the top-level `browser`
field. The drag verdict
always requires the full 100 valid samples, and `--drag-samples` below that
floor is refused, so a shortened smoke run cannot be mistaken for evidence.
Exit codes carry the outcome: 0 every metric passed, 1 a metric failed, 2 the
arguments were refused, 3 the run was `not-run`, 4 a precondition failed
(the fixture was not seeded, or the UI was not in the expected state), so a
broken fixture is never recorded as a performance regression.

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
proves no journey. A11 and A12 were closed on 2026-10-22/23 by real host
journeys on both targets (static HTML and React/TS), so they no longer wait on
this tooling; the rest of A15 (clean target machine, Ubuntu CI, human keyboard
acceptance, runtime owner integration) stays `not-run` until that environment
produces the evidence.

## Typical acceptance run

```bash
python tools/seed_scale.py --workspace D:/bench/workbench-scale
python tools/perf_harness.py --data-dir D:/bench/workbench-scale/workbench-data \
    --evidence D:/bench/perf.json
python tools/install_smoke.py --evidence D:/bench/install-smoke.json
python tools/sample_targets.py --dest D:/bench/targets
```
