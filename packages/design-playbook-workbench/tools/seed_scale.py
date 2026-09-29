#!/usr/bin/env python3
"""Scale fixture builder for the design-playbook workbench (A15 support).

This is an operator/acceptance tool, not part of the shipped package.

It builds **real** scale data — real source files on disk, imported and
published through the running service over real HTTP — so that an A15
performance run measures the application at the R15 acceptance scale
(per project: 5,000 assets, 20,000 revisions, 200 canvas instances).

It deliberately does **not** time anything or produce performance verdicts.
R15 requires timings from a real browser + service run and states that
synthetic timing may not stand in for that ("不用模拟计时代替浏览器/服务实测").
This tool only produces the input data and a machine-readable fixture
manifest; any p95 result must come from a separate browser-driven harness.

Usage (plan only, no writes)::

    python tools/seed_scale.py --plan

Small local proof (fast, not the acceptance scale)::

    python tools/seed_scale.py --assets 12 --revisions-per-asset 2 \
        --canvas-instances 2 --nodes-per-canvas 5

Acceptance scale (run on the >= 4 core / 16 GiB / SSD baseline machine)::

    python tools/seed_scale.py --workspace D:/bench/workbench-scale

With no ``--workspace`` the fixture is built under a per-user temp directory,
never inside the repository checkout. The target folder must be an absolute
path: the service refuses relative project targets by design (R02).

The tool is deterministic: identical arguments produce byte-identical asset
content, so two runs are comparable.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
HARNESS_PATH = PACKAGE_DIR / "tests" / "harness.py"

#: R15 acceptance scale per project (spec R15).
SPEC_ASSETS = 5_000
SPEC_REVISIONS = 20_000
SPEC_CANVAS_INSTANCES = 200

#: Progress cadence for the long fixture build.
PROGRESS_EVERY = 250


def load_harness():
    """Load the in-repo test harness so the tool drives the real service.

    Reusing the harness keeps the tool on the same real HTTP surface the
    suites use instead of re-deriving request shapes (one code path, no
    second authority). It is loaded by path because ``tests`` is not an
    importable package.
    """
    spec = importlib.util.spec_from_file_location(
        "dpb_workbench_harness_under_test", HARNESS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- deterministic fixture helpers (unit-tested, no I/O) -----------------


def asset_name(index: int) -> str:
    """A stable, sortable asset file name for ``index`` (0-based)."""
    if index < 0:
        raise ValueError("index must be non-negative")
    return f"asset-{index:05d}.md"


def asset_content(index: int, revision: int) -> str:
    """Deterministic asset content; ``revision`` changes the body."""
    if index < 0 or revision < 1:
        raise ValueError("index must be >= 0 and revision >= 1")
    digest = hashlib.sha256(f"{index}:{revision}".encode("utf-8")).hexdigest()
    return (
        f"# Asset {index:05d}\n\n"
        f"revision: {revision}\n"
        f"fingerprint: {digest}\n"
        f"body: deterministic fixture line for scale testing\n"
    )


def chunked(items: Sequence[Any], size: int) -> Iterator[list[Any]]:
    """Yield ``items`` in consecutive lists of at most ``size``."""
    if size < 1:
        raise ValueError("size must be positive")
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def asset_selections(count: int, *, batch: int) -> list[list[str]]:
    """Selections to submit, in order, to create ``count`` assets.

    One import call produces exactly one asset (all files in its selections
    merge into a single asset), so each asset needs its own call. ``batch``
    exists only to group names deterministically for progress reporting.
    """
    if count < 1 or batch < 1:
        raise ValueError("count and batch must be positive")
    names = [asset_name(index) for index in range(count)]
    return [list(group) for group in chunked(names, batch)]


def canvas_document(name: str, node_count: int) -> dict[str, Any]:
    """A canvas document holding exactly ``node_count`` nodes (instances).

    ``canvas.MAX_INSTANCES`` caps a canvas at 200, so the R15 canvas scale is
    one full board rather than many small ones.
    """
    if node_count < 1:
        raise ValueError("node_count must be positive")
    nodes = [
        {
            "id": f"n{i + 1}",
            "type": "text",
            "props": {"text": f"node {i + 1}"},
            "layout": {
                "x": 40.0 + (i % 10) * 110.0,
                "y": 40.0 + (i // 10) * 70.0,
                "width": 100.0,
                "height": 40.0,
                "z": i,
            },
        }
        for i in range(node_count)
    ]
    return {
        "name": name,
        "boards": [
            {
                "id": "b1",
                "name": name,
                "width": 1600,
                "height": 1200,
                "nodes": nodes,
                "flowEdges": [],
            }
        ],
    }


def fixture_plan(
    *, assets: int, revisions_per_asset: int, canvas_instances: int
) -> dict[str, int]:
    """Counts this run will produce, so ``--plan`` can be checked up front."""
    if assets < 1 or revisions_per_asset < 1 or canvas_instances < 1:
        raise ValueError("assets, revisions and canvas instances must be >= 1")
    revisions = assets * revisions_per_asset
    return {
        "assets": assets,
        "revisionsPerAsset": revisions_per_asset,
        "revisions": revisions,
        "canvasInstances": canvas_instances,
        # One import call per asset (one asset per call), one publish per
        # revision, plus one refresh-draft for every revision after the first
        # (the initial import is already the draft).
        "importCalls": assets,
        "publishCalls": revisions,
        "refreshDraftCalls": assets * (revisions_per_asset - 1),
    }


def _write_project_files(project_dir: Path, assets: int) -> list[str]:
    """Materialise ``assets`` real source files; return relative names."""
    names: list[str] = []
    for index in range(assets):
        name = asset_name(index)
        (project_dir / name).write_text(asset_content(index, 1), encoding="utf-8")
        names.append(name)
    return names


def _build_project(harness: Any, project_dir: Path, plan: dict[str, int]) -> dict:
    """Register the project and import one asset per fixture file."""
    project = harness.register(project_dir, name="scale-fixture")
    assert project.status == 200, project.text
    project_id = project.json["result"]["projectId"]
    granted = harness.grant(project_id, ["read", "write"], expected_counter=0)
    assert granted.status == 200, granted.text

    imported: list[dict] = []
    for index in range(plan["assets"]):
        name = asset_name(index)
        response = harness.import_assets(project_id, [name])
        assert response.status == 200, f"{name}: {response.text}"
        imported.append(response.json["result"]["asset"])
        if (index + 1) % PROGRESS_EVERY == 0:
            print(f"  imported {index + 1}/{plan['assets']} assets", flush=True)
    if len(imported) != plan["assets"]:
        raise AssertionError(
            f"imported {len(imported)} assets, expected {plan['assets']}"
        )
    return {"projectId": project_id, "assets": imported}


def _publish_revisions(harness: Any, project_dir: Path, built: dict, plan: dict) -> int:
    """Drive every asset through ``revisionsPerAsset`` published revisions."""
    project_id = built["projectId"]
    by_name = {row["name"]: row for row in built["assets"]}
    published = 0
    for index in range(plan["assets"]):
        name = asset_name(index)
        asset_id = by_name[name]["assetId"]
        first = harness.asset_action(project_id, asset_id, "publish")
        assert first.status == 200, f"{name} publish 1: {first.text}"
        published += 1
        for revision in range(2, plan["revisionsPerAsset"] + 1):
            (project_dir / name).write_text(
                asset_content(index, revision), encoding="utf-8"
            )
            refreshed = harness.asset_action(project_id, asset_id, "refresh-draft")
            assert refreshed.status == 200, f"{name} refresh: {refreshed.text}"
            again = harness.asset_action(project_id, asset_id, "publish")
            assert again.status == 200, f"{name} publish {revision}: {again.text}"
            published += 1
        if (index + 1) % PROGRESS_EVERY == 0:
            print(
                f"  published {published} revisions across {index + 1} assets",
                flush=True,
            )
    return published


def _build_canvases(harness: Any, plan: dict) -> list[dict]:
    """Create the acceptance-scale canvases (one board of instances each)."""
    project_id = plan["projectId"]
    created: list[dict] = []
    for index in range(plan["canvasInstances"]):
        name = f"scale-canvas-{index + 1:03d}"
        document = canvas_document(name, min(200, plan["nodesPerCanvas"]))
        response = harness.action(
            project_id, "canvases", payload={"name": name, "document": document}
        )
        assert response.status == 200, response.text
        created.append(response.json["result"])
    return created


def seed(
    *,
    assets: int,
    revisions_per_asset: int,
    canvas_instances: int,
    nodes_per_canvas: int,
    workspace: Path,
) -> dict:
    """Build the whole fixture and return its manifest (no timing)."""
    plan = fixture_plan(
        assets=assets,
        revisions_per_asset=revisions_per_asset,
        canvas_instances=canvas_instances,
    )
    plan = {**plan, "nodesPerCanvas": nodes_per_canvas}

    workspace.mkdir(parents=True, exist_ok=True)
    project_dir = workspace / "scale-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    data_dir = workspace / "workbench-data"

    harness_module = load_harness()
    started = time.monotonic()
    harness = harness_module.WorkbenchHarness(data_dir=data_dir)
    try:
        fixtures_written = _write_project_files(project_dir, assets)
        built = _build_project(harness, project_dir, plan)
        published = _publish_revisions(harness, project_dir, built, plan)
        canvases = _build_canvases(harness, {**plan, "projectId": built["projectId"]})
        elapsed = time.monotonic() - started
        return {
            "kind": "workbench-scale-fixture",
            "specScale": {
                "assets": SPEC_ASSETS,
                "revisions": SPEC_REVISIONS,
                "canvasInstances": SPEC_CANVAS_INSTANCES,
                "source": "spec R15",
            },
            "requested": plan,
            "produced": {
                "assets": len(built["assets"]),
                "revisions": published,
                "canvasInstances": len(canvases),
                "filesOnDisk": len(fixtures_written),
            },
            "paths": {
                "projectDir": str(project_dir),
                "dataDir": str(data_dir),
            },
            "buildSeconds": round(elapsed, 3),
            "note": (
                "Fixture only. This tool builds input data and claims no "
                "performance result; R15 p95 must be measured by a real "
                "browser + service run, not by synthetic timing."
            ),
        }
    finally:
        harness.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_scale.py",
        description=(
            "Build the R15-scale workbench fixture (real files + real service)."
        ),
    )
    parser.add_argument("--assets", type=int, default=SPEC_ASSETS)
    parser.add_argument(
        "--revisions-per-asset",
        type=int,
        default=SPEC_REVISIONS // SPEC_ASSETS,
        help="Revisions published per asset (default 4 => 20,000 total).",
    )
    parser.add_argument("--canvas-instances", type=int, default=1)
    parser.add_argument("--nodes-per-canvas", type=int, default=SPEC_CANVAS_INSTANCES)
    parser.add_argument(
        "--workspace",
        default=None,
        help=(
            "Absolute folder to build in (default: a per-user temp benchmark "
            "folder, never the repository checkout)."
        ),
    )
    parser.add_argument(
        "--evidence",
        default=None,
        help="Manifest path (default: <workspace>/fixture-manifest.json).",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the planned counts and exit without writing anything.",
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove an existing workspace first."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.nodes_per_canvas > 200:
        print("nodes-per-canvas exceeds canvas MAX_INSTANCES (200)", file=sys.stderr)
        return 2
    plan = fixture_plan(
        assets=args.assets,
        revisions_per_asset=args.revisions_per_asset,
        canvas_instances=args.canvas_instances,
    )
    if args.plan:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    workspace = (
        Path(args.workspace).expanduser().resolve()
        if args.workspace
        else Path(tempfile.gettempdir()) / "design-playbook-workbench-benchmarks"
    )
    if args.clean and workspace.exists():
        shutil.rmtree(workspace)

    manifest = seed(
        assets=args.assets,
        revisions_per_asset=args.revisions_per_asset,
        canvas_instances=args.canvas_instances,
        nodes_per_canvas=args.nodes_per_canvas,
        workspace=workspace,
    )
    evidence = Path(args.evidence) if args.evidence else workspace / "fixture-manifest.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nmanifest: {evidence}")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry
    raise SystemExit(main())
