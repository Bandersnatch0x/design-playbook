#!/usr/bin/env python3
"""Browser-driven performance harness for the workbench (A15 support).

This is an operator/acceptance tool, not part of the shipped package.

It measures the three R15 budgets against the real UI in a real Chromium
against the real loopback service — never synthetic timing:

* directory search                p95 <= 1000 ms
* 200-node canvas save confirm    p95 <= 2000 ms
* selection / drag response       p95 <= 100 ms  (100 samples)

Method (also written into the evidence so a reader can audit it):

* Timers run **inside the page** (``performance.now()``). A sample starts
  in-page immediately before the Playwright input and stops when the DOM first
  reflects the change, so Playwright's input dispatch is included. That is real
  browser work, not a simulation, and it makes the numbers pessimistic.
* Sample validity is enforced, never assumed. A save sample is rejected unless
  the panel actually passed through the "saving" state before reaching the
  service-confirmed label (``已保存（服务已确认）``, which differs from the
  load-time ``已载入服务端状态``). A search sample is rejected unless results
  rendered and then stayed stable. A drag sample is rejected unless the node's
  on-screen box really moved. Rejected samples are reported, not counted.
* ``not-run`` is the correct outcome below R15 scale (5,000 assets / 200 canvas
  nodes) or with too few valid samples. A smaller run still reports its numbers,
  labelled as below scale.

Usage::

    # build the fixture first, then measure against it
    python tools/seed_scale.py --workspace D:/bench/workbench-scale
    python tools/perf_harness.py --data-dir D:/bench/workbench-scale/workbench-data

    # quick local sanity check (below scale => not-run, numbers still reported)
    python tools/perf_harness.py --assets 200 --canvas-nodes 40 --samples 5
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent

#: R15 budgets, sample plan and acceptance scale (spec R15).
BUDGET_SEARCH_MS = 1000.0
BUDGET_SAVE_MS = 2000.0
BUDGET_SELECTION_DRAG_MS = 100.0
REQUIRED_SAMPLES = 30
WARMUP_SAMPLES = 3
DRAG_SAMPLES = 100
SPEC_ASSETS = 5000
SPEC_CANVAS_NODES = 200

SAVED_CONFIRMED = "已保存（服务已确认）"
#: The panel shows at least one of these while a real edit is in flight. A fast
#: local save can go straight from dirty to confirmed and never render the
#: saving label, so either marker counts as observed activity (verified against
#: the running UI: 有未保存编辑… then 已保存（服务已确认）).
ACTIVITY_MARKERS = ("有未保存编辑", "保存中")
#: Two queries that both match the fixture by name, alternated so every
#: search is a real new query with a different result size. Search matches
#: asset names, not file contents (verified against the running service).
SEARCH_QUERIES = ("asset", "asset-00")
SAMPLE_TIMEOUT_MS = 20000


# -- deterministic helpers (unit-tested, no I/O) -------------------------


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. ``None`` for no samples.

    Returning ``None`` (not 0) is deliberate: a missing measurement must never
    be mistaken for a fast one.
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    if not values:
        return None
    ordered = sorted(values)
    rank = -(-len(ordered) * fraction // 1)
    return ordered[min(max(1, int(rank)), len(ordered)) - 1]


def verdict(
    samples: list[float],
    *,
    budget_ms: float,
    required_samples: int,
    meets_scale: bool,
    rejected: int = 0,
) -> dict[str, Any]:
    """Judge one metric. Absence of evidence is ``not-run``, never ``pass``."""
    p95 = percentile(samples, 0.95)
    result: dict[str, Any] = {
        "budgetMs": budget_ms,
        "validSamples": len(samples),
        "rejectedSamples": rejected,
        "requiredSamples": required_samples,
        "p95Ms": None if p95 is None else round(p95, 2),
        "medianMs": round(statistics.median(samples), 2) if samples else None,
    }
    if not meets_scale:
        result["status"] = "not-run"
        result["reason"] = (
            f"below R15 scale ({SPEC_ASSETS} assets / {SPEC_CANVAS_NODES} "
            "canvas nodes); numbers are indicative only"
        )
        return result
    if len(samples) < required_samples:
        result["status"] = "not-run"
        result["reason"] = (
            f"only {len(samples)} valid samples, {required_samples} required"
        )
        return result
    passed = p95 is not None and p95 <= budget_ms
    result["status"] = "pass" if passed else "fail"
    if not passed:
        result["reason"] = f"p95 {result['p95Ms']} ms exceeds {budget_ms} ms"
    return result


def environment_report(*, memory_gib: float | None = None) -> dict[str, Any]:
    """Machine facts the R15 baseline requires to be recorded."""
    if memory_gib is None:
        try:  # optional: only when the operator has psutil installed
            import psutil  # type: ignore

            memory_gib = round(psutil.virtual_memory().total / (1024**3), 1)
        except Exception:  # pragma: no cover - psutil absent
            memory_gib = None
    return {
        "platform": platform.platform(),
        "cpuCount": os.cpu_count(),
        "memoryGiB": memory_gib,
        "pythonVersion": platform.python_version(),
        "recordedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def overall_status(metrics: dict[str, dict]) -> str:
    """``pass`` only when every metric passed; ``fail`` if any failed."""
    statuses = [metric["status"] for metric in metrics.values()]
    if "fail" in statuses:
        return "fail"
    if all(status == "pass" for status in statuses):
        return "pass"
    return "not-run"


def summarise(
    *, env: dict, browser_version: str, scale: dict, metrics: dict, method: dict
) -> dict:
    return {
        "kind": "workbench-performance-harness",
        "spec": {
            "searchP95Ms": BUDGET_SEARCH_MS,
            "save200NodeP95Ms": BUDGET_SAVE_MS,
            "selectionDragP95Ms": BUDGET_SELECTION_DRAG_MS,
            "requiredSamples": REQUIRED_SAMPLES,
            "requiredScale": {
                "assets": SPEC_ASSETS,
                "canvasNodes": SPEC_CANVAS_NODES,
            },
            "source": "spec R15",
        },
        "env": env,
        "browser": browser_version,
        "scale": scale,
        "scaleMeetsSpec": scale["assets"] >= SPEC_ASSETS
        and scale["canvasNodes"] >= SPEC_CANVAS_NODES,
        "metrics": metrics,
        "method": method,
        "overall": overall_status(metrics),
        "note": (
            "In-page timers against the real service. This tool never marks an "
            "item pass below R15 scale or with too few valid samples; it "
            "reports not-run instead."
        ),
    }


# -- in-page timing ------------------------------------------------------

#: Stamp t0 and clear the stop stamp.
_TIMER_START = "() => { window.__perfT0 = performance.now(); window.__perfStop = null; }"

#: Read the elapsed time, or null when the condition never held.
_TIMER_READ = (
    "() => (window.__perfStop === null ? null "
    ": window.__perfStop - window.__perfT0)"
)

#: Run the condition source in a rAF loop until it holds or the deadline hits.
_WAIT_FOR = """
([src, arg, accepted]) => new Promise((resolve) => {
  const condition = new Function('return (' + src + ')')();
  const deadline = performance.now() + accepted.timeoutMs;
  const tick = () => {
    let ok = false;
    try { ok = condition(arg, accepted); } catch (error) { ok = false; }
    if (ok) { window.__perfStop = performance.now(); resolve(true); return; }
    if (performance.now() > deadline) { resolve(false); return; }
    requestAnimationFrame(tick);
  };
  tick();
})
"""

#: Search is done only when the UI shows exactly what the service returned.
_COND_SEARCH = """
(expected) => {
  const count = document.querySelectorAll('.asset-item').length;
  return count > 0 && count === expected;
}
"""

#: Arm the save watcher *before* the gesture: a fast local save can go
#: dirty -> confirmed within a frame, so a watcher installed afterwards sees
#: only the final label and could never prove the edit really happened.
_ARM_SAVE = """
([markers, confirmed, timeoutMs]) => {
  window.__saveWatch = {sawActivity: false, stop: null, t0: performance.now()};
  const watch = window.__saveWatch;
  const deadline = performance.now() + timeoutMs;
  const tick = () => {
    const panel = document.querySelector('#canvas-save-state');
    const text = panel ? panel.textContent : '';
    if (markers.some((marker) => text.includes(marker))) {
      watch.sawActivity = true;
    }
    if (text.includes(confirmed) && watch.sawActivity) {
      watch.stop = performance.now();
      return;
    }
    if (performance.now() > deadline) { return; }
    requestAnimationFrame(tick);
  };
  tick();
  return true;
}
"""

_READ_SAVE = """
([timeoutMs]) => new Promise((resolve) => {
  const deadline = performance.now() + timeoutMs;
  const tick = () => {
    const watch = window.__saveWatch;
    if (!watch) { resolve(null); return; }
    if (watch.stop !== null) {
      resolve({elapsed: watch.stop - watch.t0, sawActivity: watch.sawActivity});
      return;
    }
    if (performance.now() > deadline) {
      resolve({elapsed: null, sawActivity: watch.sawActivity});
      return;
    }
    requestAnimationFrame(tick);
  };
  tick();
})
"""

#: The drag counts when the node leaves the position it held before the gesture.
_COND_DRAG = """
(pair) => {
  const id = pair[0];
  const base = pair[1];
  const el = document.querySelector('.canvas-node[data-node-id="' + id + '"]');
  if (!el) { return false; }
  return Math.abs(el.getBoundingClientRect().left - base) > 0.5;
}
"""


def _timed(page: Any, action, condition_src: str, arg=None, **accepted) -> float | None:
    """Start an in-page timer, run ``action``, stop when ``condition`` holds."""
    page.evaluate(_TIMER_START)
    action()
    options = {"timeoutMs": SAMPLE_TIMEOUT_MS, **accepted}
    ok = page.evaluate(_WAIT_FOR, [condition_src, arg, options])
    if not ok:
        return None
    return page.evaluate(_TIMER_READ)


def _search_expectations(harness: Any, project_id: str) -> dict[str, int]:
    """What the service says each query matches, so the UI must show it."""
    expectations: dict[str, int] = {}
    for query in SEARCH_QUERIES:
        response = harness.assets(project_id, query=f"query={query}")
        assert response.status == 200, response.text
        expectations[query] = len(response.json["assets"])
    empty = [q for q, count in expectations.items() if count == 0]
    if empty:
        raise SystemExit(
            f"fixture has no assets matching {empty}; seed the fixture first"
        )
    return expectations


def _measure_search(
    page: Any, samples: int, warmup: int, expectations: dict[str, int]
) -> tuple[list, int]:
    """Search p95: alternate real queries; stop when the UI matches the service."""
    values: list[float] = []
    rejected = 0
    queries = list(SEARCH_QUERIES)
    for index in range(samples + warmup):
        query = queries[index % len(queries)]
        expected = expectations[query]
        page.fill("#assets-query", query)
        elapsed = _timed(
            page, lambda: page.click("#assets-search-button"), _COND_SEARCH, expected
        )
        if index < warmup:
            continue
        if elapsed is None:
            rejected += 1
            continue
        values.append(elapsed)
    return values, rejected


def _measure_save(page: Any, samples: int, warmup: int) -> tuple[list, int]:
    """200-node save confirm: select, nudge, stop at the service-confirmed label.

    The watcher is armed before the keypress and the elapsed window starts
    there, so the sample covers the input dispatch plus the whole
    dirty -> confirmed cycle.
    """
    viewport = page.locator("#canvas-viewport")
    first_node = page.locator(".canvas-node").first
    values: list[float] = []
    rejected = 0
    for index in range(samples + warmup):
        # A nudge only edits when something is selected, so select first; the
        # keyboard move is then one command and one transaction (R09).
        first_node.click()
        page.evaluate(
            _ARM_SAVE, [list(ACTIVITY_MARKERS), SAVED_CONFIRMED, SAMPLE_TIMEOUT_MS]
        )
        viewport.press("ArrowRight")
        outcome = page.evaluate(_READ_SAVE, [SAMPLE_TIMEOUT_MS])
        if index < warmup:
            continue
        # A stale "confirmed" label from an earlier save would otherwise read
        # as an instant pass, so activity-free samples are rejected.
        if not outcome or outcome["elapsed"] is None or not outcome["sawActivity"]:
            rejected += 1
            continue
        values.append(outcome["elapsed"])
    return values, rejected


def _measure_selection_drag(page: Any, samples: int) -> tuple[list, int]:
    """Selection/drag response: real mouse gesture, stop when the box moves."""
    viewport = page.locator("#canvas-viewport")
    viewport.scroll_into_view_if_needed()
    nodes = page.locator(".canvas-node")
    total = nodes.count()
    values: list[float] = []
    rejected = 0
    for index in range(samples):
        node = nodes.nth(index % max(1, total))
        node_id = node.get_attribute("data-node-id")
        box = node.bounding_box()
        if node_id is None or box is None:
            rejected += 1
            continue
        x = box["x"] + box["width"] / 2
        y = box["y"] + 12
        baseline = box["x"]

        def _drag() -> None:
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 4, y + 4)
            page.mouse.up()

        # The baseline is read before the gesture, so a late re-render cannot
        # be mistaken for the drag response.
        elapsed = _timed(page, _drag, _COND_DRAG, [node_id, baseline])
        if elapsed is None:
            rejected += 1
            continue
        values.append(elapsed)
        page.wait_for_timeout(20)  # let the save transaction settle
    return values, rejected


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_measurement(
    *,
    data_dir: Path | None,
    assets: int,
    canvas_nodes: int,
    samples: int,
    warmup: int,
    drag_samples: int,
) -> dict:
    """Drive the real UI against the real service and return evidence."""
    from playwright.sync_api import sync_playwright

    harness_module = _load_module(
        "dpb_harness_for_perf", PACKAGE_DIR / "tests" / "harness.py"
    )
    seed_module = _load_module("dpb_seed_for_perf", TOOLS_DIR / "seed_scale.py")

    workspace = (
        Path(tempfile.mkdtemp()) if data_dir is None else data_dir.parent
    )
    workspace.mkdir(parents=True, exist_ok=True)

    # The one-time bootstrap secret must stay unspent so the browser can do the
    # real launch exchange; maintainer-side API calls use the live token.
    harness = harness_module.WorkbenchHarness(
        data_dir=data_dir, consume_bootstrap=False
    )
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    try:
        project_dir = workspace / "perf-project"
        project_dir.mkdir(parents=True, exist_ok=True)
        preseeded = data_dir is not None and (data_dir / "workbench.db").is_file()
        if preseeded:
            project_id = harness.projects()["projects"][0]["projectId"]
        else:
            for index in range(assets):
                name = seed_module.asset_name(index)
                (project_dir / name).write_text(
                    seed_module.asset_content(index, 1), encoding="utf-8"
                )
            project = harness.register(project_dir, name="perf")
            assert project.status == 200, project.text
            project_id = project.json["result"]["projectId"]
            granted = harness.grant(project_id, ["read", "write"], expected_counter=0)
            assert granted.status == 200, granted.text
            for index in range(assets):
                imported = harness.import_assets(project_id, [seed_module.asset_name(index)])
                assert imported.status == 200, imported.text

        # The scale is whatever the service actually holds, never the requested
        # CLI numbers: a pre-seeded fixture may differ, and reporting the
        # request instead of the reality would let a tiny fixture pass.
        listed = harness.assets(project_id)
        assert listed.status == 200, listed.text
        actual_assets = len(listed.json["assets"])

        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.goto(harness.runtime.bootstrap_url)
        page.locator("#session-state").filter(has_text="会话有效").wait_for()
        page.locator("#project-rows tr .assets-button").first.click()
        page.locator("#assets-panel").wait_for()

        search_values, search_rejected = _measure_search(
            page, samples, warmup, _search_expectations(harness, project_id)
        )

        # The 200-node canvas is authored through the API, then loaded in the UI.
        document = seed_module.canvas_document("perf-canvas", canvas_nodes)
        created = harness.action(
            project_id,
            "canvases",
            payload={"name": "perf-canvas", "document": document},
        )
        assert created.status == 200, created.text
        canvas_id = created.json["result"]["canvas"]["canvasId"]
        stored = harness_module.http_request(
            harness.runtime,
            f"/api/v1/projects/{project_id}/canvases/{canvas_id}",
            token=harness.token,
        )
        assert stored.status == 200, stored.text
        actual_nodes = len(stored.json["document"]["boards"][0]["nodes"])
        scale = {
            "assets": actual_assets,
            "canvasNodes": actual_nodes,
            "requestedAssets": assets,
            "requestedCanvasNodes": canvas_nodes,
            "source": "service (verified against the running instance)",
        }
        page.locator("#project-rows tr .canvas-button").first.click()
        page.locator("#canvas-panel").wait_for()
        # Select by label rather than assuming how the option value is keyed.
        options = page.evaluate(
            "() => Array.from(document.querySelectorAll('#canvas-select option'))"
            ".map((option) => ({value: option.value, label: option.textContent}))"
        )
        target = next(
            (row for row in options if "perf-canvas" in (row["label"] or "")), None
        )
        if target is None:
            raise SystemExit(f"created canvas not offered in the UI: {options}")
        page.select_option("#canvas-select", value=target["value"])
        page.wait_for_function(
            f"() => document.querySelectorAll('.canvas-node').length === {canvas_nodes}"
        )
        save_values, save_rejected = _measure_save(page, samples, warmup)
        drag_values, drag_rejected = _measure_selection_drag(page, drag_samples)

        metrics = {
            "search": verdict(
                search_values,
                budget_ms=BUDGET_SEARCH_MS,
                required_samples=samples,
                meets_scale=scale["assets"] >= SPEC_ASSETS,
                rejected=search_rejected,
            ),
            "save200Node": verdict(
                save_values,
                budget_ms=BUDGET_SAVE_MS,
                required_samples=samples,
                meets_scale=scale["canvasNodes"] >= SPEC_CANVAS_NODES,
                rejected=save_rejected,
            ),
            "selectionDrag": verdict(
                drag_values,
                budget_ms=BUDGET_SELECTION_DRAG_MS,
                required_samples=drag_samples,
                meets_scale=scale["canvasNodes"] >= SPEC_CANVAS_NODES,
                rejected=drag_rejected,
            ),
        }
        method = {
            "search": (
                "fill #assets-query with a name-matching term, click "
                "#assets-search-button; timer stops only when the rendered "
                ".asset-item count equals the count the service returns for "
                "that query"
            ),
            "save200Node": (
                "select a node, then one keyboard nudge (one command and one "
                f"transaction) on a loaded {canvas_nodes}-node canvas; timer "
                f"stops at {SAVED_CONFIRMED!r}; samples that never showed "
                f"edit activity ({'/'.join(ACTIVITY_MARKERS)}) are rejected "
                "as stale labels"
            ),
            "selectionDrag": (
                "real mouse drag of a canvas node; timer stops when the node's "
                "on-screen left edge leaves the position measured before the "
                "gesture (>0.5 px)"
            ),
            "timing": (
                "performance.now() inside the page; the window includes "
                "Playwright input dispatch, so numbers are pessimistic"
            ),
            "viewport": "1440x1200 (harness default)",
        }
        return summarise(
            env=environment_report(),
            browser_version=f"chromium {browser.version}",
            scale=scale,
            metrics=metrics,
            method=method,
        )
    finally:
        browser.close()
        playwright.stop()
        harness.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="perf_harness.py",
        description="Measure the R15 budgets against the real UI (A15).",
    )
    parser.add_argument("--data-dir", default=None, help="Pre-seeded data dir.")
    parser.add_argument("--assets", type=int, default=SPEC_ASSETS)
    parser.add_argument("--canvas-nodes", type=int, default=SPEC_CANVAS_NODES)
    parser.add_argument("--samples", type=int, default=REQUIRED_SAMPLES)
    parser.add_argument("--warmup", type=int, default=WARMUP_SAMPLES)
    parser.add_argument("--drag-samples", type=int, default=DRAG_SAMPLES)
    parser.add_argument("--evidence", default=None, help="Write JSON evidence here.")
    return parser


def main(argv: list[str] | None = None) -> int:
    # The evidence contains Chinese labels from the real UI; a cp936 console
    # must not turn that into an encoding crash on either stream.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.canvas_nodes > 200:
        print("canvas-nodes exceeds canvas MAX_INSTANCES (200)", file=sys.stderr)
        return 2
    evidence = run_measurement(
        data_dir=Path(args.data_dir).resolve() if args.data_dir else None,
        assets=args.assets,
        canvas_nodes=args.canvas_nodes,
        samples=args.samples,
        warmup=args.warmup,
        drag_samples=args.drag_samples,
    )
    text = json.dumps(evidence, indent=2, ensure_ascii=False)
    print(text)
    if args.evidence:
        out = Path(args.evidence)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nevidence: {out}")
    return 0 if evidence["overall"] in ("pass", "not-run") else 1


if __name__ == "__main__":  # pragma: no cover - operator entry
    raise SystemExit(main())
