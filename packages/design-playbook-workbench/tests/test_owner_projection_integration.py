#!/usr/bin/env python3
"""Cross-package wiring test: the owner publisher feeds this reader (R12).

Specification R12 lets an existing owner gain a thin typed entry rather than
having the web side re-implement owner judgement. The owner side ships that
entry as ``packages/design-playbook/scripts/publish_owner_projection.py``; this
test drives it for real and then reads the result back through the workbench's
own HTTP surface, so the contract between the two packages is locked by CI
rather than by a comment.

The owner package is a separate distribution, so the test skips when it is not
present in this tree instead of failing on an environment it does not control.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from tests.harness import WorkbenchHarness, http_request

PACKAGE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_DIR.parents[1]
PUBLISHER = (
    REPO_ROOT / "packages" / "design-playbook" / "scripts"
    / "publish_owner_projection.py"
)
OWNER_PACKAGE = REPO_ROOT / "packages" / "design-playbook"


def _load_publisher():
    """Load the owner-side publisher by path, or skip when it is absent."""
    if not PUBLISHER.is_file():
        raise unittest.SkipTest("owner package is not in this tree")
    spec = importlib.util.spec_from_file_location("dp_owner_publisher", PUBLISHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = (
    "criterion: L6.1\n"
    "required: evidence/L6.1.png\n"
    "observed: evidence/L6.1.png\n"
    "result: pass\n"
    "\n"
    "criterion: L6.2\n"
    "required: evidence/L6.2.png\n"
    "observed: evidence/L6.2.png\n"
    "result: N/A\n"
)


class OwnerProjectionIntegrationTest(unittest.TestCase):
    """The publisher's document, read back through the workbench API."""

    def setUp(self) -> None:
        self.publisher = _load_publisher()
        self.h = WorkbenchHarness(consume_bootstrap=False)
        self.addCleanup(self.h.stop)
        self.project = self.h.make_directory("owner-integration")
        registered = self.h.register(self.project, name="OwnerIntegration")
        assert registered.status == 200, registered.text
        self.project_id = registered.json["result"]["projectId"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=0).status
            == 200
        )

        self.run_root = self.project / ".design-playbook" / "runs" / "run-1"
        (self.run_root / "evidence").mkdir(parents=True)
        self.artifact = self.run_root / "evidence" / "L6.1.png"
        self.ledger = self.project / "ledger.md"
        self.ledger.write_text(LEDGER, encoding="utf-8")
        self.publish(b"first-capture")

    # -- helpers ---------------------------------------------------------

    def publish(self, artifact_bytes: bytes) -> int:
        self.artifact.write_bytes(artifact_bytes)
        manifest = {
            "ts": "2026-09-26T12:00:00+00:00",
            "criterion": "L6.1",
            "artifact": "L6.1.png",
            "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            "request": {"schemaVersion": 1},
        }
        (self.run_root / "evidence" / "manifest.jsonl").write_text(
            json.dumps(manifest) + "\n", encoding="utf-8"
        )
        return self.publisher.main([
            str(self.run_root),
            "--project-root",
            str(self.project),
            "--run-id",
            "run-1",
            "--owner",
            "ui-evaluator",
            "--ledger",
            str(self.ledger),
            "--project-id",
            self.project_id,
            "--runner",
            "design-playbook ui-evaluator",
        ])

    def _get(self, path: str):
        return http_request(
            self.h.runtime, f"/api/v1/projects/{self.project_id}{path}",
            token=self.h.token,
        )

    @staticmethod
    def _digest(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    # -- tests -----------------------------------------------------------

    def test_the_published_run_is_listed_and_read_without_a_second_verdict(
        self,
    ) -> None:
        listing = self._get("/runs")
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual([row["runId"] for row in listing.json["runs"]], ["run-1"])
        summary = listing.json["runs"][0]
        self.assertEqual(summary["owner"], "ui-evaluator")
        self.assertEqual(summary["runner"], "design-playbook ui-evaluator")
        # The workbench reports the owner's verdict; it never authors one.
        self.assertEqual(summary["verdictSource"], "owner")
        self.assertEqual(summary["criteria"], 2)
        self.assertEqual(summary["evidence"], 1)

    def test_ledger_verdicts_survive_the_crossing_including_not_applicable(
        self,
    ) -> None:
        detail = self._get("/runs/run-1")
        self.assertEqual(detail.status, 200, detail.text)
        verdicts = {row["objectId"]: row["verdict"] for row in detail.json["criteria"]}
        self.assertEqual(verdicts, {"L6.1": "pass", "L6.2": "unknown"})
        # N/A must never arrive as a pass.
        self.assertNotIn("pass", {verdicts["L6.2"]})
        evidence = detail.json["evidence"]
        self.assertEqual(evidence[0]["objectId"], "L6.1.png")
        self.assertEqual(evidence[0]["hash"], self._digest(b"first-capture"))

    def test_a_referenced_fact_is_fresh_while_the_source_is_unchanged(self) -> None:
        status = self._get(
            "/runs/run-1/freshness"
            f"?objectType=criterion&objectId=L6.1"
            f"&sourceHash={self._digest(b'first-capture')}"
        )
        self.assertEqual(status.status, 200, status.text)
        self.assertEqual(status.json["state"], "fresh")

    def test_recapturing_the_source_makes_the_old_reference_stale(self) -> None:
        old = self._digest(b"first-capture")
        self.assertEqual(self.publish(b"second-capture"), 0)
        status = self._get(
            f"/runs/run-1/freshness?objectType=criterion&objectId=L6.1"
            f"&sourceHash={old}"
        )
        self.assertEqual(status.json["state"], "stale")
        self.assertEqual(
            status.json["currentSourceHash"], self._digest(b"second-capture")
        )

    def test_a_criterion_the_owner_bound_nothing_to_is_not_reported_fresh(
        self,
    ) -> None:
        # L6.2 has no manifest binding, so the publisher omits its source hash;
        # the workbench must answer "unknown" rather than claim freshness.
        status = self._get(
            "/runs/run-1/freshness"
            f"?objectType=criterion&objectId=L6.2&sourceHash=sha256:{'0' * 64}"
        )
        self.assertEqual(status.json["state"], "unknown")

    def test_an_owner_refusal_leaves_the_reader_with_nothing_to_read(self) -> None:
        self.ledger.write_text(
            "criterion: L6.1\nobserved: evidence/L6.1.png\nresult: probably\n",
            encoding="utf-8",
        )
        self.assertEqual(self.publish(b"third-capture"), 2)
        # The previous projection is untouched: a refusal never half-writes,
        # so the reader still sees exactly the two rows it saw before.
        detail = self._get("/runs/run-1")
        self.assertEqual(detail.status, 200, detail.text)
        rows = detail.json["criteria"]
        self.assertEqual(
            {row["objectId"]: row["verdict"] for row in rows},
            {"L6.1": "pass", "L6.2": "unknown"},
        )


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
