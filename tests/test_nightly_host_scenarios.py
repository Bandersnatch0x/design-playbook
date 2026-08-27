#!/usr/bin/env python3
"""Executable contract tests for the nightly host-scenario workflow (#51).

Mirrors tests/test_release_workflow.py: load the workflow YAML with the
GitHub Actions loader (YAML 1.1 otherwise turns ``on`` into a boolean) and
assert the scheduled/dispatch contract - the plugin-dir inventory
handshake plus both host slices run with their exit codes captured, skips
(exit 2) are summarized without failing while real failures do fail,
evidence is uploaded under always(), and no live release-gate surface
(install smoke, dogfood, marketplace, HITL) leaks in. PR CI keeps running
only the deterministic unit suites.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "nightly-host-scenarios.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

HANDSHAKE_STEP = "Inventory handshake (plugin-dir smoke)"
UX_SPEC_STEP = "Host slice: ux-spec-slice"
UI_PICKER_STEP = "Host slice: ui-picker-slice"
UPLOAD_STEP = "Upload evidence"
VERDICT_STEP = "Verdict (skip is visible; only failures are red)"


class NightlyHostScenariosWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.ci_workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        class GithubActionsLoader(yaml.SafeLoader):
            pass

        GithubActionsLoader.yaml_implicit_resolvers = {
            key: list(resolvers)
            for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }
        for key in ("o", "O"):
            GithubActionsLoader.yaml_implicit_resolvers[key] = [
                resolver
                for resolver in GithubActionsLoader.yaml_implicit_resolvers[key]
                if resolver[0] != "tag:yaml.org,2002:bool"
            ]
        # YAML 1.1 treats on as boolean; GitHub treats it as the trigger key.
        cls.document = yaml.load(cls.workflow, Loader=GithubActionsLoader)
        cls.job = cls.document["jobs"]["host-scenarios"]
        cls.steps = {step["name"]: step for step in cls.job["steps"]}

    def _step_surface(self) -> str:
        """Names, uses, run bodies, and with-values of every step.

        Negative assertions target this machine surface instead of the raw
        file text: the header comment is allowed to explain that dogfood,
        marketplace installs, and HITL surfaces stay out of the nightly.
        """
        parts: list[str] = []
        for step in self.job["steps"]:
            parts.append(str(step.get("name", "")))
            parts.append(str(step.get("uses", "")))
            parts.append(str(step.get("run", "")))
            parts.extend(str(value) for value in (step.get("with") or {}).values())
        return "\n".join(parts)

    def test_triggers_are_schedule_and_dispatch_only(self) -> None:
        triggers = self.document["on"]
        self.assertIn("schedule", triggers)
        self.assertNotIn("push", triggers)
        self.assertNotIn("pull_request", triggers)
        schedules = triggers["schedule"]
        self.assertTrue(schedules)
        for entry in schedules:
            with self.subTest(entry=entry):
                self.assertRegex(str(entry["cron"]), r"^[\d*/,-]+ [\d*/,-]+ \* \* \*$")
        self.assertIn("workflow_dispatch", triggers)
        dispatch_inputs = (triggers["workflow_dispatch"] or {}).get("inputs") or {}
        for name, spec in dispatch_inputs.items():
            with self.subTest(dispatch_input=name):
                self.assertFalse(spec.get("required", False))

    def test_run_steps_execute_handshake_and_both_host_slices(self) -> None:
        self.assertIn(
            "python3 scripts/plugin_dir_smoke.py",
            self.steps[HANDSHAKE_STEP]["run"],
        )
        self.assertIn(
            "python3 scripts/host_scenario.py run ux-spec-slice",
            self.steps[UX_SPEC_STEP]["run"],
        )
        self.assertIn(
            "python3 scripts/host_scenario.py run ui-picker-slice",
            self.steps[UI_PICKER_STEP]["run"],
        )

    def test_step_order_runs_all_slices_before_upload_and_verdict(self) -> None:
        self.assertEqual(
            list(self.steps),
            [
                "Checkout",
                "Setup Python",
                "Setup Node",
                "Install Claude Code CLI (npm)",
                HANDSHAKE_STEP,
                UX_SPEC_STEP,
                UI_PICKER_STEP,
                UPLOAD_STEP,
                VERDICT_STEP,
            ],
        )

    def test_run_steps_capture_rc_into_env(self) -> None:
        for step_name, var in (
            (HANDSHAKE_STEP, "HANDSHAKE_RC"),
            (UX_SPEC_STEP, "UX_SPEC_RC"),
            (UI_PICKER_STEP, "UI_PICKER_RC"),
        ):
            with self.subTest(step=step_name):
                run = self.steps[step_name]["run"]
                self.assertIn("set +e", run)
                self.assertIn("rc=$?", run)
                self.assertIn(f"{var}=$rc", run)
                self.assertIn('"$GITHUB_ENV"', run)

    def test_evidence_upload_always_runs_and_covers_both_dirs(self) -> None:
        upload = self.steps[UPLOAD_STEP]
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["uses"], "actions/upload-artifact@v4")
        self.assertEqual(upload["with"]["if-no-files-found"], "ignore")
        path = upload["with"]["path"]
        self.assertIn(".scratch/plugin-dir-smoke/", path)
        self.assertIn(".scratch/host-scenario/", path)

    def test_verdict_step_summarizes_and_only_fails_on_real_failures(self) -> None:
        verdict = self.steps[VERDICT_STEP]
        self.assertEqual(verdict["if"], "always()")
        run = verdict["run"]
        self.assertIn('"$GITHUB_STEP_SUMMARY"', run)
        for var in ("HANDSHAKE_RC", "UX_SPEC_RC", "UI_PICKER_RC"):
            with self.subTest(var=var):
                self.assertIn(f"${{{var}:-}}", run)
        # Skip-not-silent-green: the exit-2 arm renders a SKIP row and never
        # touches the failure flag.
        self.assertIn('[[ "$rc" == "2" ]]', run)
        skip_arm = run.split('[[ "$rc" == "2" ]]', 1)[1].split("else", 1)[0]
        self.assertIn("SKIP", skip_arm)
        self.assertNotIn("verdict_rc=1", skip_arm)
        # Only real failures are red: rc 1/other, or an unset rc recorded
        # after a hard crash before the step could write its env var.
        self.assertIn('[[ "$rc" == "0" ]]', run)
        self.assertIn("verdict_rc=1", run)
        self.assertIn('exit "$verdict_rc"', run)

    def test_step_surface_has_no_live_release_or_hitl_surfaces(self) -> None:
        surface = self._step_surface()
        for forbidden in (
            "install_smoke",
            "vnext_live_dogfood",
            "design-io",
            "dogfood",
            "marketplace",
            "plugin install",
            "design-playbook@",
            "preview",
            "confirm-round",
            "scripts/release",
            "gh release",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, surface)

    def test_slices_receive_api_key_secret_without_hardcoding(self) -> None:
        for step_name in (UX_SPEC_STEP, UI_PICKER_STEP):
            with self.subTest(step=step_name):
                self.assertEqual(
                    self.steps[step_name]["env"]["ANTHROPIC_API_KEY"],
                    "${{ secrets.ANTHROPIC_API_KEY }}",
                )
        self.assertNotIn("sk-ant", self.workflow)

    def test_setup_steps_install_the_host_cli(self) -> None:
        self.assertEqual(self.steps["Checkout"]["uses"], "actions/checkout@v7")
        self.assertEqual(self.steps["Setup Python"]["uses"], "actions/setup-python@v7")
        self.assertEqual(self.steps["Setup Python"]["with"]["python-version"], "3.13")
        self.assertEqual(self.steps["Setup Node"]["uses"], "actions/setup-node@v7")
        self.assertEqual(self.steps["Setup Node"]["with"]["node-version"], "22.14.0")
        self.assertIn(
            "npm install --global @anthropic-ai/claude-code",
            self.steps["Install Claude Code CLI (npm)"]["run"],
        )

    def test_job_shape_timeout_and_concurrency(self) -> None:
        self.assertEqual(self.document["name"], "Nightly host scenarios")
        self.assertEqual(self.document["permissions"], {"contents": "read"})
        self.assertEqual(
            self.document["concurrency"]["group"], "nightly-host-scenarios"
        )
        self.assertFalse(self.document["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.job["runs-on"], "ubuntu-latest")
        # 75 minutes absorbs the 2400s ux-spec-slice worst case plus the
        # handshake, ui-picker slice, and evidence upload.
        self.assertEqual(self.job["timeout-minutes"], 75)

    def test_ci_still_runs_only_the_deterministic_suites(self) -> None:
        host_line = "python3 tests/test_host_scenario.py"
        nightly_line = "python3 tests/test_nightly_host_scenarios.py"
        self.assertIn(host_line, self.ci_workflow)
        self.assertIn(nightly_line, self.ci_workflow)
        between = self.ci_workflow.split(host_line, 1)[1].split(nightly_line, 1)[0]
        self.assertEqual(between.strip(), "")
        self.assertIn("python3 tests/test_plugin_dir_smoke.py", self.ci_workflow)
        for script in (
            "scripts/plugin_dir_smoke.py",
            "scripts/host_scenario.py",
            "scripts/install_smoke.py",
        ):
            with self.subTest(script=script):
                self.assertNotIn(script, self.ci_workflow)


if __name__ == "__main__":
    unittest.main()
