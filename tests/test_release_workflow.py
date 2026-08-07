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
sys.path.insert(0, str(ROOT / "scripts"))

from release_state import (  # noqa: E402
    ReleaseStateError,
    release_action,
    require_verified_provenance,
)


class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

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
        cls.publish = cls.document["jobs"]["publish"]
        cls.publish_steps = {
            step["name"]: step for step in cls.publish["steps"]
        }

    def test_release_is_tag_driven_with_explicit_recovery(self) -> None:
        self.assertEqual(self.document["on"]["push"]["tags"], ["v*"])
        self.assertIn("workflow_dispatch", self.document["on"])
        recovery_input = self.document["on"]["workflow_dispatch"]["inputs"]["recovery"]
        self.assertEqual(recovery_input["type"], "boolean")
        self.assertFalse(recovery_input["default"])
        self.assertFalse(self.document["concurrency"]["cancel-in-progress"])

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
            "npm audit signatures",
            self.publish_steps["Verify npm provenance"]["run"],
        )
        self.assertNotIn(
            "gh release view",
            github_release["steps"][1]["run"],
        )

    def test_package_name_comes_from_manifest(self) -> None:
        self.assertNotIn("PACKAGE_NAME: design-playbook", self.workflow)
        self.assertIn(
            "package_name=${PACKAGE_NAME}",
            self.publish_steps["Resolve and bind release identity"]["run"],
        )
        self.assertIn(
            'PACKAGE_NAME="${{ steps.release.outputs.package_name }}"',
            self.workflow,
        )

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
