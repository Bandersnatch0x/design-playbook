"""Public-seam tests for safe Run Console metadata projections."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.run_metadata import (  # noqa: E402
    LimitationProjectionError,
    SelectedRunSelectionError,
    project_limitations,
    project_package_metadata,
    project_selected_run,
)


class PackageMetadataProjectionTests(unittest.TestCase):
    def test_installed_manifest_projects_frozen_known_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "installed-package"
            manifest = package_root / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps({"name": "design-playbook", "version": "1.2.3"}),
                encoding="utf-8",
            )

            projection = project_package_metadata(package_root)

            self.assertEqual(projection.availability, "known")
            self.assertEqual(projection.value.name, "design-playbook")
            self.assertEqual(projection.value.version, "1.2.3")
            self.assertIsNone(projection.reason)
            with self.assertRaises(FrozenInstanceError):
                projection.value.version = "9.9.9"

    def test_missing_installed_manifest_is_typed_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projection = project_package_metadata(Path(tmp) / "missing-package")

            self.assertEqual(projection.availability, "unknown")
            self.assertIsNone(projection.value)
            self.assertEqual(projection.reason, "source-missing")

    def test_malformed_manifest_and_versions_are_typed_unknown(self) -> None:
        cases = (
            ("not json", "source-malformed"),
            (json.dumps({"name": "design-playbook", "version": "1.2"}),
             "source-malformed"),
            (json.dumps({"name": "not-design-playbook", "version": "1.2.3"}),
             "source-malformed"),
            (json.dumps({"name": "design-playbook", "version": 123}),
             "source-malformed"),
        )
        for contents, expected_reason in cases:
            with self.subTest(contents=contents):
                with tempfile.TemporaryDirectory() as tmp:
                    manifest = (
                        Path(tmp)
                        / "installed-package"
                        / ".claude-plugin"
                        / "plugin.json"
                    )
                    manifest.parent.mkdir(parents=True)
                    manifest.write_text(contents, encoding="utf-8")

                    projection = project_package_metadata(manifest.parents[1])

                    self.assertEqual(projection.availability, "unknown")
                    self.assertIsNone(projection.value)
                    self.assertEqual(projection.reason, expected_reason)

    def test_unreadable_installed_manifest_is_typed_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "installed-package"
            manifest = package_root / ".claude-plugin" / "plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")

            with patch.object(Path, "read_text", side_effect=OSError("denied")):
                projection = project_package_metadata(package_root)

            self.assertEqual(projection.availability, "unknown")
            self.assertIsNone(projection.value)
            self.assertEqual(projection.reason, "source-unreadable")


class SelectedRunProjectionTests(unittest.TestCase):
    def test_selected_root_projects_session_scoped_path_free_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alice-private-root-") as tmp:
            selected_root = Path(tmp) / "client-secret-project" / "run-alice"
            selected_root.mkdir(parents=True)
            first = project_selected_run(selected_root, b"session-a-secret")
            second = project_selected_run(selected_root, b"session-b-secret")

            self.assertRegex(first.run_id, r"^run_[a-f0-9]{32}$")
            self.assertNotEqual(first.run_id, second.run_id)
            self.assertIsNone(first.label)
            exposed = repr(first)
            for secret_part in ("alice", "client", "project", str(selected_root)):
                self.assertNotIn(secret_part, exposed)
            with self.assertRaises(FrozenInstanceError):
                first.label = "run-alice"

    def test_invalid_root_or_secret_fails_with_fixed_path_free_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alice-private-root-") as tmp:
            missing = Path(tmp) / "client-secret-project" / "missing-run"
            cases = (
                (missing, b"private-token-value", "selected-run-invalid"),
                (Path(tmp), b"", "session-secret-invalid"),
            )
            for selected_root, secret, expected_code in cases:
                with self.subTest(expected_code=expected_code):
                    with self.assertRaises(SelectedRunSelectionError) as caught:
                        project_selected_run(selected_root, secret)

                    self.assertEqual(caught.exception.code, expected_code)
                    exposed = repr(caught.exception) + str(caught.exception)
                    for secret_part in (
                        "alice",
                        "client",
                        "project",
                        "private-token-value",
                        str(selected_root),
                    ):
                        self.assertNotIn(secret_part, exposed)


class LimitationProjectionTests(unittest.TestCase):
    def test_disabled_capabilities_are_closed_frozen_limitations(self) -> None:
        limitations = project_limitations()

        self.assertEqual(
            tuple(item.code for item in limitations),
            (
                "role-attestation-owner-unmapped",
                "diagnostic-export-contract-unavailable",
            ),
        )
        self.assertEqual(
            limitations[0].summary,
            "Role attestation is unavailable until an existing owner is mapped.",
        )
        self.assertEqual(
            limitations[1].summary,
            "Diagnostic export is unavailable until its contract is accepted.",
        )
        self.assertEqual(limitations[0].affects_assertion_ids, ())
        self.assertEqual(limitations[1].affects_assertion_ids, ())
        with self.assertRaises(FrozenInstanceError):
            limitations[0].summary = "arbitrary"

    def test_owner_unmapped_limitation_preserves_valid_affected_assertions(
        self,
    ) -> None:
        limitations = project_limitations(
            owner_unmapped_assertion_ids=(
                "intent.summary",
                "evaluation.findings.finding-a",
            )
        )

        owner_unmapped = limitations[0]
        self.assertEqual(owner_unmapped.code, "owner-unmapped")
        self.assertEqual(
            owner_unmapped.summary,
            "No existing authority owner is mapped for the affected assertions.",
        )
        self.assertEqual(
            owner_unmapped.affects_assertion_ids,
            (
                "evaluation.findings.finding-a",
                "intent.summary",
            ),
        )

    def test_free_form_or_invalid_limitation_input_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            project_limitations(summary="run `rm -rf` next")  # type: ignore[call-arg]

        for assertion_ids in (("not a domain id",), ("intent.summary", "intent.summary")):
            with self.subTest(assertion_ids=assertion_ids):
                with self.assertRaises(LimitationProjectionError):
                    project_limitations(
                        owner_unmapped_assertion_ids=assertion_ids,
                    )


if __name__ == "__main__":
    unittest.main()
