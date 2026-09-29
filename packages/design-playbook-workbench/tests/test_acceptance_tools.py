#!/usr/bin/env python3
"""Deterministic tests for the workbench acceptance tools in ``tools/``.

These cover only the pure helpers and the refusal paths. The live flows
(scale fixture build, clean install, real handoff) are operator-driven and
are not executed here; their evidence comes from an actual run, never from
this file.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = PACKAGE_DIR / "tools"


def _load(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS_DIR / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seed_scale = _load("dpb_seed_scale_under_test", "seed_scale.py")
install_smoke = _load("dpb_install_smoke_under_test", "install_smoke.py")
sample_targets = _load("dpb_sample_targets_under_test", "sample_targets.py")
perf_harness = _load("dpb_perf_harness_under_test", "perf_harness.py")


class SeedScaleHelpersTest(unittest.TestCase):
    def test_asset_names_are_stable_and_sortable(self) -> None:
        names = [seed_scale.asset_name(index) for index in range(12)]
        self.assertEqual(names[0], "asset-00000.md")
        self.assertEqual(names[11], "asset-00011.md")
        self.assertEqual(names, sorted(names))
        with self.assertRaises(ValueError):
            seed_scale.asset_name(-1)

    def test_asset_content_is_deterministic_and_revision_sensitive(self) -> None:
        self.assertEqual(
            seed_scale.asset_content(3, 1), seed_scale.asset_content(3, 1)
        )
        self.assertNotEqual(
            seed_scale.asset_content(3, 1), seed_scale.asset_content(3, 2)
        )
        self.assertNotEqual(
            seed_scale.asset_content(3, 1), seed_scale.asset_content(4, 1)
        )
        with self.assertRaises(ValueError):
            seed_scale.asset_content(0, 0)

    def test_chunked_respects_size_and_rejects_zero(self) -> None:
        self.assertEqual(
            list(seed_scale.chunked([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]]
        )
        with self.assertRaises(ValueError):
            list(seed_scale.chunked([1], 0))

    def test_asset_selections_keeps_one_name_per_asset(self) -> None:
        groups = seed_scale.asset_selections(5, batch=2)
        self.assertEqual([len(group) for group in groups], [2, 2, 1])
        flat = [name for group in groups for name in group]
        self.assertEqual(flat, [seed_scale.asset_name(i) for i in range(5)])

    def test_canvas_document_holds_the_requested_node_count(self) -> None:
        document = seed_scale.canvas_document("board", 200)
        nodes = document["boards"][0]["nodes"]
        self.assertEqual(len(nodes), 200)
        self.assertEqual(len({node["id"] for node in nodes}), 200)
        with self.assertRaises(ValueError):
            seed_scale.canvas_document("board", 0)

    def test_fixture_plan_counts_match_the_call_model(self) -> None:
        plan = seed_scale.fixture_plan(
            assets=5000, revisions_per_asset=4, canvas_instances=1
        )
        self.assertEqual(plan["assets"], 5000)
        self.assertEqual(plan["revisions"], 20000)
        # One import per asset; one publish per revision; one refresh-draft
        # for every revision after the first.
        self.assertEqual(plan["importCalls"], 5000)
        self.assertEqual(plan["publishCalls"], 20000)
        self.assertEqual(plan["refreshDraftCalls"], 15000)

    def test_fixture_plan_rejects_degenerate_input(self) -> None:
        for kwargs in (
            {"assets": 0, "revisions_per_asset": 1, "canvas_instances": 1},
            {"assets": 1, "revisions_per_asset": 0, "canvas_instances": 1},
            {"assets": 1, "revisions_per_asset": 1, "canvas_instances": 0},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                seed_scale.fixture_plan(**kwargs)

    def test_spec_scale_constants_match_r15(self) -> None:
        self.assertEqual(seed_scale.SPEC_ASSETS, 5_000)
        self.assertEqual(seed_scale.SPEC_REVISIONS, 20_000)
        self.assertEqual(seed_scale.SPEC_CANVAS_INSTANCES, 200)


class InstallSmokeHelpersTest(unittest.TestCase):
    def _launch(self) -> dict:
        return {
            "authority": "http://127.0.0.1:8123",
            "bootstrapUrl": "http://127.0.0.1:8123/#bootstrap=secret-value",
            "dataDir": "C:/tmp/data",
            "bootId": "boot-1",
        }

    def test_parse_launch_reads_the_printed_object(self) -> None:
        text = json.dumps(self._launch(), indent=2)
        self.assertEqual(install_smoke.parse_launch(text)["authority"],
                         "http://127.0.0.1:8123")

    def test_parse_launch_tolerates_leading_noise(self) -> None:
        text = "some warning line\n" + json.dumps(self._launch())
        self.assertEqual(install_smoke.parse_launch(text)["bootId"], "boot-1")

    def test_parse_launch_rejects_incomplete_output(self) -> None:
        for text in ("", "no json here", json.dumps({"authority": "x"})):
            with self.subTest(text=text), self.assertRaises(ValueError):
                install_smoke.parse_launch(text)

    def test_bootstrap_secret_requires_the_fragment(self) -> None:
        self.assertEqual(install_smoke.bootstrap_secret(self._launch()),
                         "secret-value")
        with self.assertRaises(ValueError):
            install_smoke.bootstrap_secret({"bootstrapUrl": "http://127.0.0.1:1/"})

    def test_venv_paths_follow_the_platform(self) -> None:
        venv = Path("v")
        expected_entry = (
            venv / "Scripts" / "design-playbook-workbench.exe"
            if install_smoke.os.name == "nt"
            else venv / "bin" / "design-playbook-workbench"
        )
        self.assertEqual(
            install_smoke.venv_executable(venv, "design-playbook-workbench"),
            expected_entry,
        )

    def test_forbidden_entries_spot_scratch_and_tests(self) -> None:
        clean = [
            "design_playbook_workbench/store.py",
            "design_playbook_workbench/web/app.html",
            "design_playbook_workbench-0.1.0.dist-info/METADATA",
        ]
        self.assertEqual(install_smoke.forbidden_entries(clean), [])
        self.assertEqual(install_smoke.unexpected_entries(clean), [])
        leaked = install_smoke.forbidden_entries(
            [".dbg_dup.py", "pkg/tests/test_store.py", "pkg/test_thing.py"]
        )
        self.assertEqual(len(leaked), 3)

    def test_unexpected_entries_is_a_whitelist(self) -> None:
        # Tools, benchmarks and tests live beside the package but must never
        # ship: the wheel is the app package plus dist-info and nothing else.
        for outsider in (
            "tools/seed_scale.py",
            ".benchmarks/proof/fixture-manifest.json",
            "tests/test_store.py",
        ):
            with self.subTest(outsider=outsider):
                self.assertEqual(
                    install_smoke.unexpected_entries([outsider]), [outsider]
                )

    def test_summarise_states_scope_and_non_scope(self) -> None:
        evidence = install_smoke.summarise(
            wheel="w.whl", python="3.12.0", probes={"sessionExchange": 200},
            forbidden=[], unexpected=[],
        )
        self.assertIn("A15 clean install", evidence["covers"][0])
        self.assertTrue(any("performance" in item for item in evidence["doesNotCover"]))
        self.assertTrue(any("ACL" in item for item in evidence["doesNotCover"]))


class SampleTargetsTest(unittest.TestCase):
    def test_write_tree_materialises_every_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "static-target"
            written = sample_targets.write_tree(root, sample_targets.STATIC_FILES)
            self.assertEqual(written, sorted(sample_targets.STATIC_FILES))
            for relative in written:
                self.assertTrue((root / relative).is_file(), relative)

    def test_react_and_static_targets_declare_their_entries(self) -> None:
        package = json.loads(sample_targets.REACT_FILES["package.json"])
        for script in ("build", "preview", "test"):
            self.assertIn(script, package["scripts"])
        self.assertIn("app.js", sample_targets.STATIC_FILES["index.html"])

    def test_relative_destination_is_refused(self) -> None:
        self.assertEqual(
            sample_targets.main(["--dest", "relative/targets"]), 2
        )

    def test_existing_files_are_not_overwritten_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp).resolve() / "targets"
            self.assertEqual(sample_targets.main(["--dest", str(dest)]), 0)
            self.assertEqual(sample_targets.main(["--dest", str(dest)]), 3)
            self.assertEqual(
                sample_targets.main(["--dest", str(dest), "--force"]), 0
            )


class PerfHarnessTest(unittest.TestCase):
    def test_percentile_uses_nearest_rank_and_none_for_no_samples(self) -> None:
        # No samples must be None, never 0: a missing measurement must not be
        # mistaken for a fast one.
        self.assertIsNone(perf_harness.percentile([], 0.95))
        self.assertEqual(perf_harness.percentile([42.0], 0.95), 42.0)
        values = [float(n) for n in range(1, 101)]
        self.assertEqual(perf_harness.percentile(values, 0.95), 95.0)
        self.assertEqual(perf_harness.percentile(values, 1.0), 100.0)
        with self.assertRaises(ValueError):
            perf_harness.percentile(values, 0.0)

    def test_verdict_below_scale_is_not_run_even_when_fast(self) -> None:
        result = perf_harness.verdict(
            [1.0] * 30, budget_ms=1000.0, required_samples=30, meets_scale=False
        )
        self.assertEqual(result["status"], "not-run")
        self.assertIn("below R15 scale", result["reason"])

    def test_verdict_needs_enough_samples_before_it_can_pass(self) -> None:
        result = perf_harness.verdict(
            [1.0] * 3, budget_ms=1000.0, required_samples=30, meets_scale=True
        )
        self.assertEqual(result["status"], "not-run")
        self.assertEqual(result["validSamples"], 3)

    def test_verdict_passes_and_fails_on_the_budget(self) -> None:
        fast = [10.0] * 30
        slow = [2000.0] * 30
        self.assertEqual(
            perf_harness.verdict(
                fast, budget_ms=1000.0, required_samples=30, meets_scale=True
            )["status"],
            "pass",
        )
        failed = perf_harness.verdict(
            slow, budget_ms=1000.0, required_samples=30, meets_scale=True
        )
        self.assertEqual(failed["status"], "fail")
        self.assertIn("exceeds", failed["reason"])

    def test_verdict_no_samples_is_not_run_not_pass(self) -> None:
        result = perf_harness.verdict(
            [], budget_ms=1000.0, required_samples=30, meets_scale=True, rejected=30
        )
        self.assertEqual(result["status"], "not-run")
        self.assertIsNone(result["p95Ms"])
        self.assertEqual(result["rejectedSamples"], 30)

    def test_overall_status_requires_every_metric_to_pass(self) -> None:
        self.assertEqual(
            perf_harness.overall_status(
                {"a": {"status": "pass"}, "b": {"status": "pass"}}
            ),
            "pass",
        )
        self.assertEqual(
            perf_harness.overall_status(
                {"a": {"status": "pass"}, "b": {"status": "fail"}}
            ),
            "fail",
        )
        self.assertEqual(
            perf_harness.overall_status(
                {"a": {"status": "pass"}, "b": {"status": "not-run"}}
            ),
            "not-run",
        )

    def test_summarise_binds_the_spec_budgets_and_scale(self) -> None:
        metrics = {
            "search": {"status": "pass"},
            "save200Node": {"status": "pass"},
            "selectionDrag": {"status": "pass"},
        }
        evidence = perf_harness.summarise(
            env={"platform": "x"},
            browser_version="chromium 1",
            scale={"assets": 5000, "canvasNodes": 200},
            metrics=metrics,
            method={"note": "x"},
        )
        self.assertEqual(evidence["overall"], "pass")
        self.assertTrue(evidence["scaleMeetsSpec"])
        self.assertEqual(evidence["spec"]["searchP95Ms"], 1000.0)
        self.assertEqual(evidence["spec"]["save200NodeP95Ms"], 2000.0)
        self.assertEqual(evidence["spec"]["selectionDragP95Ms"], 100.0)
        self.assertEqual(evidence["spec"]["requiredSamples"], 30)
        self.assertEqual(
            evidence["spec"]["requiredScale"],
            {"assets": 5000, "canvasNodes": 200},
        )

    def test_summarise_below_scale_cannot_pass(self) -> None:
        metrics = {
            "search": {"status": "pass"},
            "save200Node": {"status": "pass"},
            "selectionDrag": {"status": "pass"},
        }
        evidence = perf_harness.summarise(
            env={}, browser_version="chromium 1",
            scale={"assets": 150, "canvasNodes": 60},
            metrics=metrics, method={},
        )
        self.assertFalse(evidence["scaleMeetsSpec"])

    def test_spec_budgets_match_the_acceptance_numbers(self) -> None:
        self.assertEqual(perf_harness.BUDGET_SEARCH_MS, 1000.0)
        self.assertEqual(perf_harness.BUDGET_SAVE_MS, 2000.0)
        self.assertEqual(perf_harness.BUDGET_SELECTION_DRAG_MS, 100.0)
        self.assertEqual(perf_harness.REQUIRED_SAMPLES, 30)
        self.assertEqual(perf_harness.DRAG_SAMPLES, 100)

    def test_search_queries_match_names_not_contents(self) -> None:
        # Search matches asset names; a content-only term would yield zero
        # results and make every search sample invalid.
        for query in perf_harness.SEARCH_QUERIES:
            with self.subTest(query=query):
                self.assertTrue(seed_scale.asset_name(0).startswith("asset"))
                self.assertTrue(query.startswith("asset"))


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
