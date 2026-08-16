#!/usr/bin/env python3
"""Executable contract tests for the GitHub Actions release transaction."""
from __future__ import annotations

import sys
import unittest
from itertools import product
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
DSH_WORKFLOW = ROOT / ".github" / "workflows" / "release-dsh-bundle.yml"
sys.path.insert(0, str(ROOT / "scripts"))

from release_state import (  # noqa: E402
    ReleaseStateError,
    package_release_action,
    release_action,
    require_verified_provenance,
)


class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.dsh_workflow = DSH_WORKFLOW.read_text(encoding="utf-8")

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
        cls.dsh_document = yaml.load(cls.dsh_workflow, Loader=GithubActionsLoader)
        cls.publish = cls.document["jobs"]["publish"]
        cls.publish_steps = {
            step["name"]: step for step in cls.publish["steps"]
        }
        cls.dsh_publish = cls.dsh_document["jobs"]["publish"]
        cls.dsh_publish_steps = {
            step["name"]: step for step in cls.dsh_publish["steps"]
        }

    def test_one_stable_tag_drives_both_publishers_and_one_release(self) -> None:
        self.assertEqual(self.document["on"]["push"]["tags"], ["v*"])
        self.assertEqual(self.dsh_document["on"]["push"]["tags"], ["v*"])
        self.assertNotIn("dsh-v*", self.dsh_workflow)
        self.assertNotIn("github-release", self.dsh_document["jobs"])

    def test_companion_publish_and_shared_release_are_ordered(self) -> None:
        dsh_steps = list(self.dsh_publish_steps)
        self.assertLess(
            dsh_steps.index("Wait for design-playbook registry"),
            dsh_steps.index("Publish npm package with OIDC"),
        )

        main_steps = list(self.publish_steps)
        self.assertLess(
            main_steps.index("Verify dsh-design-playbook registry"),
            main_steps.index("Verify dsh-design-playbook provenance"),
        )
        self.assertLess(
            self.workflow.index("Verify dsh-design-playbook provenance"),
            self.workflow.index("gh release create"),
        )

    def test_dsh_release_group_gate_precedes_registry_wait(self) -> None:
        dsh_steps = list(self.dsh_publish_steps)
        self.assertLess(
            dsh_steps.index("Run release group gate"),
            dsh_steps.index("Wait for design-playbook registry"),
        )
        self.assertEqual(
            self.dsh_publish_steps["Run release group gate"]["run"],
            "python3 scripts/release.py --checks release-group",
        )

    def test_release_is_tag_driven_with_explicit_recovery(self) -> None:
        for document in (self.document, self.dsh_document):
            with self.subTest(workflow=document["name"]):
                self.assertEqual(document["on"]["push"]["tags"], ["v*"])
                self.assertIn("workflow_dispatch", document["on"])
                recovery_input = document["on"]["workflow_dispatch"]["inputs"][
                    "recovery"
                ]
                self.assertEqual(recovery_input["type"], "boolean")
                self.assertFalse(recovery_input["default"])
                self.assertFalse(document["concurrency"]["cancel-in-progress"])

    def test_publish_job_uses_only_trusted_publishing(self) -> None:
        self.assertEqual(self.document["permissions"], {"contents": "read"})
        self.assertEqual(
            self.publish["permissions"],
            {"contents": "read", "id-token": "write"},
        )
        self.assertEqual(self.publish["environment"], "npm")
        self.assertEqual(set(self.publish["outputs"]), {"tag", "title"})
        self.assertEqual(
            self.publish_steps["Setup Node"]["with"]["node-version"],
            "22.14.0",
        )
        self.assertIn(
            "npm@11.19.0",
            self.publish_steps["Pin Trusted Publishing npm CLI"]["run"],
        )
        self.assertIn("npm publish --access public", self.workflow)
        self.assertNotIn("NPM_TOKEN", self.workflow)
        self.assertNotIn("NODE_AUTH_TOKEN", self.workflow)
        self.assertNotIn("--provenance", self.workflow)

    def test_dsh_publish_job_uses_only_trusted_publishing(self) -> None:
        self.assertEqual(self.dsh_document["permissions"], {"contents": "read"})
        self.assertEqual(
            self.dsh_publish["permissions"],
            {"contents": "read", "id-token": "write"},
        )
        self.assertEqual(self.dsh_publish["environment"], "npm")
        self.assertEqual(
            self.dsh_publish_steps["Setup Node"]["with"]["node-version"],
            "22.14.0",
        )
        self.assertIn(
            "npm@11.19.0",
            self.dsh_publish_steps["Pin Trusted Publishing npm CLI"]["run"],
        )
        self.assertIn("npm publish --access public", self.dsh_workflow)
        self.assertNotIn("NPM_TOKEN", self.dsh_workflow)
        self.assertNotIn("NODE_AUTH_TOKEN", self.dsh_workflow)
        self.assertNotIn("--provenance", self.dsh_workflow)

    def test_setup_actions_use_node24_runtime(self) -> None:
        self.assertEqual(
            self.publish_steps["Setup Python"]["uses"],
            "actions/setup-python@v7",
        )
        self.assertEqual(
            self.publish_steps["Setup Node"]["uses"],
            "actions/setup-node@v7",
        )

    def test_public_state_matrix_is_enforced_before_publish(self) -> None:
        valid_cases = {
            ("push", False, False, False): "publish",
            ("workflow_dispatch", True, True, False): "recover",
        }
        for event_name, recovery, npm_exists, release_exists in product(
            ("push", "workflow_dispatch"),
            (False, True),
            (False, True),
            (False, True),
        ):
            with self.subTest(
                event_name=event_name,
                recovery=recovery,
                npm_exists=npm_exists,
                release_exists=release_exists,
            ):
                result = valid_cases.get(
                    (event_name, recovery, npm_exists, release_exists)
                )
                if result is not None:
                    self.assertEqual(
                        release_action(
                            event_name=event_name,
                            recovery=recovery,
                            npm_exists=npm_exists,
                            github_release_exists=release_exists,
                        ),
                        result,
                    )
                    continue
                with self.assertRaises(ReleaseStateError):
                    release_action(
                        event_name=event_name,
                        recovery=recovery,
                        npm_exists=npm_exists,
                        github_release_exists=release_exists,
                    )

        state_step = self.publish_steps["Validate public release state transition"]
        self.assertIn("scripts/release_state.py state", state_step["run"])
        self.assertIn('>> "${GITHUB_OUTPUT}"', state_step["run"])
        self.assertEqual(
            self.publish_steps["Publish npm package with OIDC"]["if"],
            "steps.state.outputs.action == 'publish'",
        )

    def test_package_only_state_matrix_is_enforced_before_publish(self) -> None:
        valid_cases = {
            ("push", False, False): "publish",
            ("workflow_dispatch", True, True): "verify",
        }
        for event_name, recovery, npm_exists in product(
            ("push", "workflow_dispatch"),
            (False, True),
            (False, True),
        ):
            with self.subTest(
                event_name=event_name,
                recovery=recovery,
                npm_exists=npm_exists,
            ):
                result = valid_cases.get((event_name, recovery, npm_exists))
                if result is not None:
                    self.assertEqual(
                        package_release_action(
                            event_name=event_name,
                            recovery=recovery,
                            npm_exists=npm_exists,
                        ),
                        result,
                    )
                    continue
                with self.assertRaises(ReleaseStateError):
                    package_release_action(
                        event_name=event_name,
                        recovery=recovery,
                        npm_exists=npm_exists,
                    )

        state_step = self.dsh_publish_steps[
            "Validate public release state transition"
        ]
        self.assertIn("scripts/release_state.py package-state", state_step["run"])
        self.assertNotIn("github-release-exists", state_step["run"])
        self.assertEqual(
            self.dsh_publish_steps["Publish npm package with OIDC"]["if"],
            "steps.state.outputs.action == 'publish'",
        )

    def test_registry_waits_are_bounded_and_name_the_missing_artifact(self) -> None:
        waits = (
            (self.dsh_publish_steps["Wait for design-playbook registry"], 180, 10),
            (self.publish_steps["Verify dsh-design-playbook registry"], 180, 10),
        )
        for step, attempts, interval in waits:
            with self.subTest(step=step["name"]):
                self.assertGreaterEqual(step["timeout-minutes"], 25)
                self.assertIn("release_transaction.py wait-registry", step["run"])
                self.assertIn(f"--attempts {attempts}", step["run"])
                self.assertIn(f"--interval {interval}", step["run"])

    def test_provenance_verification_retries_are_bounded_and_fail_closed(self) -> None:
        verifies = (
            self.publish_steps["Verify npm provenance"],
            self.publish_steps["Verify dsh-design-playbook provenance"],
            self.dsh_publish_steps["Verify npm provenance"],
        )
        for step in verifies:
            with self.subTest(step=step["name"]):
                self.assertIn("release_transaction.py verify-provenance", step["run"])
                self.assertIn("--attempts 3", step["run"])
                self.assertIn("--interval 20", step["run"])

    def test_both_publishers_pin_python_and_inspect_their_npm_artifacts(self) -> None:
        self.assertEqual(
            self.dsh_publish_steps["Setup Python"]["with"]["python-version"],
            "3.13",
        )
        for steps, package_dir in (
            (self.publish_steps, "packages/design-playbook"),
            (self.dsh_publish_steps, "packages/dsh-design-playbook"),
        ):
            with self.subTest(package_dir=package_dir):
                inspection = steps["Inspect npm artifact"]
                self.assertEqual(inspection["working-directory"], package_dir)
                self.assertEqual(inspection["run"], "npm pack --dry-run")

    def test_github_release_follows_registry_and_provenance(self) -> None:
        github_release = self.document["jobs"]["github-release"]
        self.assertEqual(github_release["needs"], "publish")
        self.assertEqual(github_release["permissions"], {"contents": "write"})
        self.assertIn("gh release create", self.workflow)
        self.assertLess(
            self.workflow.index("npm publish --access public"),
            self.workflow.index("gh release create"),
        )
        self.assertLess(
            self.workflow.index("Check GitHub Release state"),
            self.workflow.index("npm publish --access public"),
        )
        self.assertLess(
            self.workflow.index("Verify npm provenance"),
            self.workflow.index("gh release create"),
        )
        self.assertIn("Verify npm provenance", self.publish_steps)
        self.assertIn(
            "release_transaction.py verify-provenance",
            self.publish_steps["Verify npm provenance"]["run"],
        )
        self.assertNotIn(
            "gh release view",
            github_release["steps"][1]["run"],
        )

    def test_package_name_comes_from_manifest(self) -> None:
        identity = self.publish_steps["Resolve and bind release identity"]["run"]
        self.assertIn("release_transaction.py identity", identity)
        self.assertIn("--manifest packages/design-playbook/package.json", identity)
        self.assertNotIn("node -p", identity)
        self.assertIn("steps.release.outputs.package_name", self.workflow)

    def test_provenance_contract_requires_exact_package(self) -> None:
        require_verified_provenance(
            {
                "invalid": [],
                "missing": [],
                "verified": [
                    {
                        "name": "design-playbook",
                        "version": "0.12.0",
                        "attestations": [{}],
                    }
                ],
            },
            package_name="design-playbook",
            version="0.12.0",
        )
        with self.assertRaises(ReleaseStateError):
            require_verified_provenance(
                {"invalid": [], "missing": [], "verified": []},
                package_name="design-playbook",
                version="0.12.0",
            )


if __name__ == "__main__":
    unittest.main()
