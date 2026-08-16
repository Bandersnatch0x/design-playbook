#!/usr/bin/env python3
"""Unit tests for the deep release transaction module."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_transaction import (  # noqa: E402
    ReleaseTransactionError,
    resolve_identity,
    verify_provenance,
    wait_registry,
)


class ReleaseIdentityTests(unittest.TestCase):
    def test_normal_and_recovery_identity(self) -> None:
        manifest = {"name": "design-playbook", "version": "1.2.3"}
        normal = resolve_identity(
            tag="v1.2.3", manifest=manifest,
            head_commit="a", tag_commit="a", main_commit="a",
            recovery=False, head_is_ancestor=True,
        )
        self.assertEqual((normal.tag, normal.version, normal.package_name),
                         ("v1.2.3", "1.2.3", "design-playbook"))
        recovered = resolve_identity(
            tag="v1.2.3", manifest=manifest,
            head_commit="a", tag_commit="a", main_commit="b",
            recovery=True, head_is_ancestor=True,
        )
        self.assertEqual(recovered.version, "1.2.3")

    def test_identity_fails_closed(self) -> None:
        manifest = {"name": "design-playbook", "version": "1.2.3"}
        cases = (
            dict(tag="latest", head_commit="a", tag_commit="a", main_commit="a",
                 recovery=False, head_is_ancestor=True),
            dict(tag="v1.2.4", head_commit="a", tag_commit="a", main_commit="a",
                 recovery=False, head_is_ancestor=True),
            dict(tag="v1.2.3", head_commit="a", tag_commit="b", main_commit="a",
                 recovery=False, head_is_ancestor=True),
            dict(tag="v1.2.3", head_commit="a", tag_commit="a", main_commit="b",
                 recovery=False, head_is_ancestor=True),
            dict(tag="v1.2.3", head_commit="a", tag_commit="a", main_commit="b",
                 recovery=True, head_is_ancestor=False),
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ReleaseTransactionError):
                resolve_identity(manifest=manifest, **kwargs)


class ReleaseVerificationTests(unittest.TestCase):
    def test_retry_budget_is_fail_closed(self) -> None:
        for function in (wait_registry, verify_provenance):
            with self.subTest(function=function.__name__), self.assertRaises(
                ReleaseTransactionError
            ):
                function("design-playbook", "1.2.3", attempts=0, interval=20)
            with self.subTest(function=function.__name__), self.assertRaises(
                ReleaseTransactionError
            ):
                function("design-playbook", "1.2.3", attempts=1, interval=-1)

    @mock.patch("release_transaction.time.sleep", return_value=None)
    @mock.patch("release_transaction.subprocess.run")
    def test_registry_retries_then_passes(self, run, _sleep) -> None:
        run.side_effect = [
            subprocess.CompletedProcess([], 1, "", "missing"),
            subprocess.CompletedProcess([], 0, "1.2.3\n", ""),
        ]
        wait_registry("design-playbook", "1.2.3", attempts=3, interval=20)
        self.assertEqual(run.call_count, 2)

    @mock.patch("release_transaction.time.sleep", return_value=None)
    @mock.patch("release_transaction.subprocess.run")
    def test_provenance_retries_with_fresh_installs(self, run, _sleep) -> None:
        verified = json.dumps({
            "verified": [{
                "name": "design-playbook", "version": "1.2.3",
                "attestations": [{}],
            }]
        })
        run.side_effect = [
            subprocess.CompletedProcess([], 1, "", "install failed"),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, verified, ""),
        ]
        verify_provenance("design-playbook", "1.2.3", attempts=3, interval=20)
        self.assertEqual(run.call_count, 3)

    @mock.patch("release_transaction.time.sleep", return_value=None)
    @mock.patch("release_transaction.subprocess.run")
    def test_provenance_exhaustion_fails_closed(self, run, _sleep) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, "", "failed")
        with self.assertRaises(ReleaseTransactionError):
            verify_provenance("design-playbook", "1.2.3", attempts=3, interval=20)


if __name__ == "__main__":
    unittest.main()
