#!/usr/bin/env python3
"""A12 / A08 backflow: owner projections, freshness, confirmations, publish.

The rules under test are the ones R12 names: the workbench shows the
original owner's facts and never re-decides them; a fact is located by run
plus object plus hash, so a same-name object in another run is never joined;
a confirmation is bound to the object hash it was given for and stops
applying when the source changes; a verified capability needs that
confirmation, and a source with recorded failures stays unverified.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore, digest_bytes
from design_playbook_workbench.components import ComponentService
from design_playbook_workbench.errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    MISSING_DEPENDENCY,
    STALE_EVIDENCE,
    WorkbenchError,
)
from design_playbook_workbench.owners import (
    PROJECTION_ROOT,
    PROJECTION_VERSION,
    OwnerProjectionService,
)
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory


def projection(
    run_id: str,
    *,
    project_id: str | None = None,
    criteria: list[dict] | None = None,
    findings: list[dict] | None = None,
    evidence: list[dict] | None = None,
    owner: str = "run-console",
) -> dict:
    return {
        "version": PROJECTION_VERSION,
        "runId": run_id,
        "owner": owner,
        "projectId": project_id,
        "runner": "design-playbook run-console",
        "generatedAt": "2026-09-26T12:00:00Z",
        "artifacts": [{"path": "index.html", "hash": "sha256:" + "c" * 64}],
        "criteria": criteria
        if criteria is not None
        else [
            {
                "criterionId": "c-1",
                "role": "owner-verified",
                "verdict": "pass",
                "sourceHash": "sha256:" + "1" * 64,
                "evidenceHashes": ["sha256:" + "a" * 64],
            }
        ],
        "evidence": evidence
        if evidence is not None
        else [
            {
                "evidenceId": "e-1",
                "kind": "screenshot",
                "hash": "sha256:" + "a" * 64,
                "mediaType": "image/png",
                "criterionId": "c-1",
                "role": "owner-evidence",
                "capturedAt": "2026-09-26T11:59:00Z",
            }
        ],
        "findings": findings or [],
    }


class OwnerProjectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = WorkbenchDataDirectory(self.base / "data").ensure()
        self.store = Store(self.data_dir.database_path)
        self.service = WorkbenchService(store=self.store, data_dir=self.data_dir)
        self.blobs = BlobStore(self.data_dir.blob_dir)
        self.assets = AssetService(
            store=self.store, service=self.service, blobs=self.blobs
        )
        self.reuse = ReuseService(
            store=self.store, service=self.service, assets=self.assets, blobs=self.blobs
        )
        self.components = ComponentService(
            store=self.store,
            service=self.service,
            assets=self.assets,
            reuse=self.reuse,
            blobs=self.blobs,
        )
        self.owners = OwnerProjectionService(
            store=self.store,
            service=self.service,
            assets=self.assets,
            components=self.components,
            blobs=self.blobs,
        )
        self._operations = 0
        self.project_dir = self.base / "project"
        self.project_dir.mkdir()
        candidate = self.service.probe_folder(self.project_dir)
        self.target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Design",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        self.project_id = self.target["projectId"]
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=["read", "write"],
            operation=Operation(
                operation_id="op_grant_owner",
                payload={"scopes": ["read", "write"]},
                expected_counter=counter,
            ),
        )

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None) -> Operation:
        self._operations += 1
        return Operation(
            operation_id=f"op_owner_{self._operations:08d}",
            payload=payload,
            expected_counter=expected,
        )

    def publish_projection(self, run_id: str, document: dict) -> Path:
        path = self.project_dir / PROJECTION_ROOT / run_id
        path.mkdir(parents=True, exist_ok=True)
        target = path / "projection.json"
        target.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target


class ProjectionReadTest(OwnerProjectionTestCase):
    def test_runs_are_listed_and_read_without_a_second_verdict(self) -> None:
        self.publish_projection("run-1", projection("run-1", project_id=self.project_id))
        listing = self.owners.list_runs(self.project_id)
        self.assertEqual([row["runId"] for row in listing["runs"]], ["run-1"])
        summary = listing["runs"][0]
        self.assertEqual(summary["owner"], "run-console")
        self.assertEqual(summary["verdictSource"], "owner")
        self.assertEqual(summary["criteria"], 1)

        detail = self.owners.run(self.project_id, "run-1")
        criterion = detail["criteria"][0]
        self.assertEqual(criterion["verdict"], "pass")
        self.assertEqual(criterion["verdictSource"], "owner")
        self.assertIsNone(criterion["confirmation"])
        self.assertIn("工作台不重新裁决", detail["note"])
        self.assertEqual(detail["evidence"][0]["kind"], "screenshot")
        # The projection document hash identifies exactly this read.
        self.assertEqual(
            detail["projectionHash"],
            digest_bytes(
                (self.project_dir / PROJECTION_ROOT / "run-1" / "projection.json").read_bytes()
            ),
        )

    def test_an_incomplete_projection_is_refused_rather_than_guessed(self) -> None:
        self.publish_projection("run-owner", {"version": PROJECTION_VERSION, "runId": "x"})
        listing = self.owners.list_runs(self.project_id)
        self.assertEqual(listing["runs"][0]["state"], "unknown")
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.run(self.project_id, "run-owner")
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)

        self.publish_projection(
            "run-verdict",
            projection(
                "run-verdict",
                criteria=[{"criterionId": "c-2", "verdict": "looks-good"}],
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.run(self.project_id, "run-verdict")
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertIn("verdict", str(caught.exception))

        self.publish_projection(
            "run-version", {"version": "owner-projection/v99", "runId": "run-version"}
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.run(self.project_id, "run-version")
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)

        with self.assertRaises(WorkbenchError) as caught:
            self.owners.run(self.project_id, "missing-run")
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_same_named_objects_in_two_runs_are_not_joined(self) -> None:
        self.publish_projection(
            "run-a",
            projection(
                "run-a",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": "sha256:" + "1" * 64}
                ],
            ),
        )
        self.publish_projection(
            "run-b",
            projection(
                "run-b",
                criteria=[
                    {"criterionId": "c-1", "verdict": "fail",
                     "sourceHash": "sha256:" + "2" * 64}
                ],
            ),
        )
        run_a = self.owners.run(self.project_id, "run-a")
        run_b = self.owners.run(self.project_id, "run-b")
        self.assertEqual(run_a["criteria"][0]["verdict"], "pass")
        self.assertEqual(run_b["criteria"][0]["verdict"], "fail")
        # A confirmation given for run-a's object does not apply to run-b's.
        confirmed = self.owners.confirm(
            self.project_id,
            run_id="run-a",
            object_type="criterion",
            object_id="c-1",
            source_hash="sha256:" + "1" * 64,
            role="owner-verified",
            operation=self.operation({"action": "confirmations"}),
        )["result"]
        self.assertTrue(confirmed["confirmationId"])
        self.assertIsNotNone(
            self.owners.run(self.project_id, "run-a")["criteria"][0]["confirmation"]
        )
        self.assertIsNone(
            self.owners.run(self.project_id, "run-b")["criteria"][0]["confirmation"]
        )

    def test_a_changed_object_makes_the_old_reference_stale(self) -> None:
        path = self.publish_projection(
            "run-1",
            projection(
                "run-1",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": "sha256:" + "1" * 64}
                ],
            ),
        )
        locator = {
            "runId": "run-1",
            "objectType": "criterion",
            "objectId": "c-1",
            "sourceHash": "sha256:" + "1" * 64,
        }
        self.assertEqual(self.owners.freshness(self.project_id, locator)["state"], "fresh")
        digest = self.owners.locator_digest(locator)
        self.assertTrue(digest.startswith("sha256:"))
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.locator_digest({"runId": "run-1"})
        self.assertEqual(caught.exception.code, INVALID_INPUT)

        # The owner re-runs and the object changes.
        path.write_text(
            json.dumps(
                projection(
                    "run-1",
                    criteria=[
                        {"criterionId": "c-1", "verdict": "fail",
                         "sourceHash": "sha256:" + "9" * 64}
                    ],
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        status = self.owners.freshness(self.project_id, locator)
        self.assertEqual(status["state"], "stale")
        self.assertEqual(status["currentSourceHash"], "sha256:" + "9" * 64)
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.require_fresh(self.project_id, locator)
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)
        # The history is kept: the object is still readable, now failing.
        self.assertEqual(self.owners.run(self.project_id, "run-1")["criteria"][0]["verdict"], "fail")

        path.unlink()
        gone = self.owners.freshness(self.project_id, locator)
        self.assertEqual(gone["state"], "unknown")


class ConfirmationTest(OwnerProjectionTestCase):
    def test_confirming_requires_the_hash_the_owner_currently_states(self) -> None:
        self.publish_projection("run-1", projection("run-1"))
        for kwargs, code in (
            ({"source_hash": "sha256:" + "0" * 64}, STALE_EVIDENCE),
            ({"source_hash": ""}, INVALID_INPUT),
            ({"role": "self-approved"}, INVALID_INPUT),
            ({"object_type": "guess"}, INVALID_INPUT),
            ({"object_id": "missing"}, INVALID_TARGET),
            ({"run_id": "missing-run"}, INVALID_TARGET),
        ):
            body = {
                "run_id": "run-1",
                "object_type": "criterion",
                "object_id": "c-1",
                "source_hash": "sha256:" + "1" * 64,
                "role": "owner-verified",
                **kwargs,
            }
            with self.subTest(kwargs=sorted(kwargs)):
                with self.assertRaises(WorkbenchError) as caught:
                    self.owners.confirm(
                        self.project_id,
                        operation=self.operation({"action": "confirmations"}),
                        **body,
                    )
                self.assertEqual(caught.exception.code, code)

        confirmed = self.owners.confirm(
            self.project_id,
            run_id="run-1",
            object_type="criterion",
            object_id="c-1",
            source_hash="sha256:" + "1" * 64,
            role="owner-verified",
            note="人工核对截图与源码后确认",
            operation=self.operation({"action": "confirmations"}),
        )["result"]
        self.assertEqual(confirmed["verdictSource"], "owner")
        self.assertFalse(confirmed["noteOverride"])
        listing = self.owners.list_confirmations(self.project_id)
        self.assertEqual(len(listing["confirmations"]), 1)
        self.assertEqual(listing["confirmations"][0]["role"], "owner-verified")

        # A confirmation taken on an old hash cannot be reused.
        self.publish_projection(
            "run-1",
            projection(
                "run-1",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": "sha256:" + "7" * 64}
                ],
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.confirm(
                self.project_id,
                run_id="run-1",
                object_type="criterion",
                object_id="c-1",
                source_hash="sha256:" + "1" * 64,
                role="owner-verified",
                operation=self.operation({"action": "confirmations"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)


class VerifiedPublishTest(OwnerProjectionTestCase):
    def make_asset(self, capabilities: list[str]) -> str:
        (self.project_dir / "index.html").write_bytes("<h1>首页</h1>\n".encode("utf-8"))
        asset = self.assets.import_selection(
            self.project_id,
            selections=["index.html"],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        draft = self.store.draft(asset["assetId"])
        attributes = json.loads(draft["attributes_json"])
        attributes["capabilities"] = capabilities
        self.store.update_draft(
            asset_id=asset["assetId"],
            tags=[],
            attributes=attributes,
            now="2026-09-26T12:00:00Z",
        )
        return asset["assetId"]

    def test_a_verified_capability_needs_a_confirmation_for_that_content(self) -> None:
        asset_id = self.make_asset(["reference", "static-preview", "runnable-verified"])
        content_hash = json.loads(self.store.draft(asset_id)["attributes_json"])[
            "manifest"
        ][0]["contentHash"]
        # The owner verified exactly this content: that is what the criterion
        # hash means, so the projection names the same hash.
        self.publish_projection(
            "run-1",
            projection(
                "run-1",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": content_hash}
                ],
            ),
        )

        # Without a confirmation the verified capability cannot publish.
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.publish_verified(
                self.project_id, asset_id, run_id="run-1", object_id="c-1",
                operation=self.operation({"action": "publish-verified"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)
        self.assertEqual(self.store.asset_revisions(asset_id), [])

        # A confirmation is bound to one content hash: it does not carry
        # over to another asset, whatever the criterion is called.
        (self.project_dir / "other.html").write_bytes(b"<h1>other</h1>\n")
        other = self.assets.import_selection(
            self.project_id,
            selections=["other.html"],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        other_attributes = json.loads(self.store.draft(other["assetId"])["attributes_json"])
        other_attributes["capabilities"] = ["reference", "runnable-verified"]
        self.store.update_draft(
            asset_id=other["assetId"], tags=[], attributes=other_attributes,
            now="2026-09-26T12:00:00Z",
        )
        self.owners.confirm(
            self.project_id,
            run_id="run-1",
            object_type="criterion",
            object_id="c-1",
            source_hash=content_hash,
            role="owner-verified",
            operation=self.operation({"action": "confirmations"}),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.publish_verified(
                self.project_id, other["assetId"], run_id="run-1", object_id="c-1",
                operation=self.operation({"action": "publish-verified"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)

        # The confirmation that names the published content succeeds and the
        # revision records who verified it.
        published = self.owners.publish_verified(
            self.project_id, asset_id, run_id="run-1", object_id="c-1",
            operation=self.operation({"action": "publish-verified"}),
        )["result"]
        self.assertEqual(published["revisionNumber"], 1)
        self.assertEqual(published["verifiedBy"]["runId"], "run-1")
        revision = self.store.latest_revision(asset_id)
        verified = json.loads(revision["verified_json"])
        self.assertEqual(verified[0]["role"], "owner-verified")
        self.assertEqual(verified[0]["sourceHash"], content_hash)

    def test_a_re_run_that_moves_the_owner_fact_makes_the_confirmation_stale(self) -> None:
        asset_id = self.make_asset(["reference", "static-preview", "runnable-verified"])
        content_hash = json.loads(self.store.draft(asset_id)["attributes_json"])[
            "manifest"
        ][0]["contentHash"]
        self.publish_projection(
            "run-9",
            projection(
                "run-9",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": content_hash}
                ],
            ),
        )
        self.owners.confirm(
            self.project_id,
            run_id="run-9",
            object_type="criterion",
            object_id="c-1",
            source_hash=content_hash,
            role="owner-verified",
            operation=self.operation({"action": "confirmations"}),
        )
        # The owner re-runs and flips the verdict: the earlier confirmation no
        # longer describes the current owner fact, so publish is refused.
        self.publish_projection(
            "run-9",
            projection(
                "run-9",
                criteria=[
                    {"criterionId": "c-1", "verdict": "fail",
                     "sourceHash": content_hash}
                ],
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.publish_verified(
                self.project_id, asset_id, run_id="run-9", object_id="c-1",
                operation=self.operation({"action": "publish-verified"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)

        # The same holds when the re-run keeps Pass but moves the source hash
        # away from the content being published.
        self.publish_projection(
            "run-9",
            projection(
                "run-9",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": "sha256:" + "9" * 64}
                ],
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.publish_verified(
                self.project_id, asset_id, run_id="run-9", object_id="c-1",
                operation=self.operation({"action": "publish-verified"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)
        self.assertEqual(self.store.asset_revisions(asset_id), [])

        # Restoring the matching fact lets the same confirmation publish.
        self.publish_projection(
            "run-9",
            projection(
                "run-9",
                criteria=[
                    {"criterionId": "c-1", "verdict": "pass",
                     "sourceHash": content_hash}
                ],
            ),
        )
        published = self.owners.publish_verified(
            self.project_id, asset_id, run_id="run-9", object_id="c-1",
            operation=self.operation({"action": "publish-verified"}),
        )["result"]
        self.assertEqual(published["revisionNumber"], 1)

    def test_a_source_with_failure_records_stays_unverified(self) -> None:
        self.publish_projection(
            "run-2",
            projection(
                "run-2",
                criteria=[
                    {"criterionId": "c-1", "verdict": "fail",
                     "sourceHash": "sha256:" + "3" * 64}
                ],
                findings=[
                    {
                        "findingId": "f-1",
                        "severity": "blocker",
                        "summary": "主操作不可键盘到达",
                        "criterionId": "c-1",
                        "sourceHash": "sha256:" + "4" * 64,
                        "pointBack": {
                            "kind": "source",
                            "path": "index.html",
                            "note": "补 keyboard 焦点顺序",
                            "repairOwner": "craft-guard",
                        },
                    }
                ],
            ),
        )
        asset_id = self.make_asset(["reference", "source-unverified"])
        published = self.assets.publish_revision(
            self.project_id, asset_id,
            operation=self.operation({"action": "publish"}),
        )["result"]
        self.assertNotIn("runnable-verified", published["capabilities"])
        self.assertEqual(
            json.loads(self.store.latest_revision(asset_id)["verified_json"]), []
        )
        # The finding keeps its point-back to the repair owner and the run's
        # own verdict is untouched by publishing the asset.
        run = self.owners.run(self.project_id, "run-2")
        self.assertEqual(run["findings"][0]["pointBack"]["repairOwner"], "craft-guard")
        self.assertEqual(run["criteria"][0]["verdict"], "fail")

        # A failing criterion cannot be published as verified even with a
        # confirmation role it does not hold.
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.publish_verified(
                self.project_id, asset_id, run_id="run-2", object_id="c-1",
                operation=self.operation({"action": "publish-verified"}),
            )
        self.assertEqual(caught.exception.code, STALE_EVIDENCE)


class BackflowTest(OwnerProjectionTestCase):
    def test_a_candidate_is_a_draft_with_a_typed_locator(self) -> None:
        self.publish_projection(
            "run-3",
            projection(
                "run-3",
                criteria=[
                    {"criterionId": "c-1", "verdict": "fail",
                     "sourceHash": "sha256:" + "5" * 64}
                ],
                findings=[
                    {
                        "findingId": "f-1",
                        "severity": "major",
                        "summary": "详情页缺少返回路径",
                        "sourceHash": "sha256:" + "6" * 64,
                        "pointBack": {"kind": "design", "path": "canvas:b1",
                                      "repairOwner": "design-playbook"},
                    }
                ],
            ),
        )
        candidate = self.owners.backflow_candidate(
            self.project_id,
            run_id="run-3",
            object_type="finding",
            object_id="f-1",
            name="详情返回入口",
            operation=self.operation({"action": "backflow"}),
        )["result"]
        self.assertEqual(candidate["lifecycle"], "draft")
        locator = candidate["sourceLocator"]
        self.assertEqual(locator["kind"], "owner-run")
        self.assertEqual(locator["runId"], "run-3")
        self.assertEqual(locator["objectType"], "finding")
        self.assertEqual(locator["sourceHash"], "sha256:" + "6" * 64)
        self.assertEqual(locator["verdict"], None)
        self.assertTrue(candidate["runVerdictUnchanged"])
        self.assertIn("回流候选", candidate["warnings"][0])

        # Publishing the candidate is a separate, later decision; the run's
        # own facts are unchanged by its existence.
        run = self.owners.run(self.project_id, "run-3")
        self.assertEqual(run["findings"][0]["summary"], "详情页缺少返回路径")
        self.assertEqual(run["criteria"][0]["verdict"], "fail")

        # A failing criterion is itself a legitimate backflow source.
        from_criterion = self.owners.backflow_candidate(
            self.project_id,
            run_id="run-3",
            object_type="criterion",
            object_id="c-1",
            name="失败判据回流",
            operation=self.operation({"action": "backflow"}),
        )["result"]
        self.assertEqual(from_criterion["sourceLocator"]["verdict"], "fail")

        # A passing criterion is not: there is nothing to fix.
        self.publish_projection("run-4", projection("run-4"))
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.backflow_candidate(
                self.project_id,
                run_id="run-4",
                object_type="criterion",
                object_id="c-1",
                name="不应创建",
                operation=self.operation({"action": "backflow"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        with self.assertRaises(WorkbenchError) as caught:
            self.owners.backflow_candidate(
                self.project_id, run_id="run-3", object_type="finding",
                object_id="missing", name="x",
                operation=self.operation({"action": "backflow"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
