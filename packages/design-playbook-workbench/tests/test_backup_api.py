#!/usr/bin/env python3
"""A14 over the real API: backup create/verify/restore as settings actions.

The domain rules live in ``test_backup.py``; these tests prove the transport
surface: the route is maintainer-only, create returns a sealed archive,
verify and restore go through the real HTTP boundary, and a capability
cannot reach the backup surface.
"""
from __future__ import annotations

import unittest
import zipfile
from hashlib import sha256
from pathlib import Path

from tests.harness import WorkbenchHarness, http_request


class BackupApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.project_dir = self.h.make_directory("backup")
        registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.project_id = registered["projectId"]
        counter = self.h.project_target(self.project_id)["counter"]
        assert self.h.grant(self.project_id, ["read", "write"], expected_counter=counter).status == 200
        (self.project_dir / "brand.md").write_bytes(b"# Brand\n")
        asset = self.h.import_assets(self.project_id, ["brand.md"]).json["result"]["asset"]
        assert self.h.asset_action(self.project_id, asset["assetId"], "publish").status == 200
        self._operations = 0

    def capability(self, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=self.project_id, scopes=scopes
        )

    def backup_post(self, body: dict, *, capability=None):
        self._operations += 1
        operation = {
            "operationId": f"op_backup_api_{self._operations}",
            "payload": {"action": body.get("action")},
        }
        return http_request(
            self.h.runtime,
            "/api/v1/backup",
            method="POST",
            body={"operation": operation, **body},
            token=None if capability else self.h.token,
            capability=capability,
            origin=None if capability else self.h.runtime.origin,
        )

    def backup_get(self, path: str, *, capability=None):
        return http_request(
            self.h.runtime,
            f"/api/v1/backup?path={path}",
            token=None if capability else self.h.token,
            capability=capability,
        )


class BackupApiTest(BackupApiTestCase):
    def test_restored_service_replays_reuse_and_writeback_without_touching_original(self) -> None:
        archive = self.h.base / "replay.dpwb.zip"
        created = self.backup_post({"action": "create", "destination": str(archive)})
        self.assertEqual(created.status, 200, created.text)
        restore_dir = self.h.base / "replay-restored"
        restored = self.backup_post(
            {"action": "restore", "path": str(archive), "target": str(restore_dir)}
        )
        self.assertEqual(restored.status, 200, restored.text)
        self.assertTrue(restored.json["result"]["reauthorizationRequired"])
        original_dir = self.h.runtime.data_dir.root
        self.h.runtime.stop()

        def snapshot() -> dict:
            return {str(path.relative_to(original_dir)): sha256(path.read_bytes()).hexdigest()
                    for path in original_dir.rglob("*") if path.is_file()}

        original = snapshot()
        replay = WorkbenchHarness(data_dir=restore_dir)
        self.addCleanup(replay.stop)
        self.assertEqual(replay.runtime.data_dir.root, restore_dir)
        project = replay.project_target(self.project_id)
        replay_dir = replay.make_directory("restored-project")
        (replay_dir / "brand.md").write_bytes(b"# Brand\n")
        probed = replay.probe(replay_dir, exclude_project_id=self.project_id)
        self.assertEqual(probed.status, 200, probed.text)
        candidate = probed.json["candidate"]
        rebound = replay.action(
            self.project_id, "rebind", expected_counter=project["counter"],
            payload={"path": candidate["canonicalPath"], "candidateId": candidate["candidateId"]},
        )
        self.assertEqual(rebound.status, 200, rebound.text)
        granted = replay.grant(
            self.project_id, ["read", "write"],
            expected_counter=replay.project_target(self.project_id)["counter"],
        )
        self.assertEqual(granted.status, 200, granted.text)
        assets = replay.assets(self.project_id)
        self.assertEqual(assets.status, 200, assets.text)
        asset_id = assets.json["assets"][0]["assetId"]
        before = replay.asset_detail(self.project_id, asset_id)
        self.assertEqual(before.status, 200, before.text)
        self.assertEqual(before.json["asset"]["revisionNumber"], 1)
        (replay_dir / "brand.md").write_bytes(b"# Brand restored revision\n")
        for verb in ("refresh-draft", "publish"):
            response = replay.asset_action(
                self.project_id, asset_id, verb,
                expected_counter=replay.asset_counter(self.project_id, asset_id),
            )
            self.assertEqual(response.status, 200, response.text)
        after = replay.asset_detail(self.project_id, asset_id)
        self.assertEqual(after.status, 200, after.text)
        self.assertEqual(after.json["asset"]["revisionNumber"], 2)
        reused = {}
        for verb in ("reference", "derive", "copy"):
            response = replay.asset_action(
                self.project_id, asset_id, verb,
                expected_counter=replay.asset_counter(self.project_id, asset_id),
            )
            self.assertEqual(response.status, 200, response.text)
            reused[verb] = response.json["result"]
        self.assertEqual(reused["reference"]["assetId"], asset_id)
        self.assertEqual(len({asset_id, reused["derive"]["assetId"], reused["copy"]["assetId"]}), 3)
        for verb in ("derive", "copy"):
            detail = replay.asset_detail(self.project_id, reused[verb]["assetId"])
            self.assertEqual(detail.status, 200, detail.text)
            self.assertTrue(detail.json["asset"]["revisionId"])

        content = (replay_dir / "brand.md").read_bytes()
        proposal = replay.create_proposal(
            self.project_id,
            [{"path": "brand.md", "operation": "update",
              "baseHash": "sha256:" + sha256(content).hexdigest(),
              "content": "# Restored writeback\n"}],
            summary="Write back after restore",
        )
        self.assertEqual(proposal.status, 200, proposal.text)
        self.assertEqual((replay_dir / "brand.md").read_bytes(), content)
        result = proposal.json["result"]
        applied = replay.proposal_action(
            self.project_id, result["proposalId"], "apply", digest=result["digest"]
        )
        self.assertEqual(applied.status, 200, applied.text)
        self.assertEqual(applied.json["result"]["status"], "applied")
        self.assertEqual((replay_dir / "brand.md").read_bytes(), b"# Restored writeback\n")
        self.assertEqual((self.project_dir / "brand.md").read_bytes(), b"# Brand\n")
        self.assertEqual(snapshot(), original)

    def test_create_verify_and_restore_over_the_api(self) -> None:
        dest = str(self.h.base / "api-backup.dpwb.zip")
        created = self.backup_post({"action": "create", "destination": dest})
        self.assertEqual(created.status, 200, created.text)
        result = created.json["result"]
        self.assertEqual(result["path"], dest)
        self.assertFalse(result["containsCredentials"])
        self.assertTrue(Path(dest).is_file())
        with zipfile.ZipFile(dest, "r") as archive:
            self.assertIn("manifest.json", archive.namelist())

        verified = self.backup_get(dest)
        self.assertEqual(verified.status, 200, verified.text)
        self.assertTrue(verified.json["valid"])

        restore_dir = str(self.h.base / "api-restored")
        restored = self.backup_post(
            {"action": "restore", "path": dest, "target": restore_dir}
        )
        self.assertEqual(restored.status, 200, restored.text)
        self.assertFalse(restored.json["result"]["switched"])
        self.assertTrue(restored.json["result"]["reauthorizationRequired"])
        self.assertTrue((Path(restore_dir) / "workbench.db").is_file())

    def test_unknown_action_and_bad_paths(self) -> None:
        unknown = self.backup_post({"action": "nonsense"})
        self.assertEqual(unknown.status, 404)
        missing = self.backup_get(str(self.h.base / "nope.zip"))
        self.assertEqual(missing.status, 400)
        self.assertEqual(missing.error_code, "invalid-target")

    def test_a_capability_cannot_reach_the_backup_surface(self) -> None:
        cap = self.capability(["read", "write"])
        dest = str(self.h.base / "cap-backup.zip")
        denied = self.backup_post({"action": "create", "destination": dest}, capability=cap)
        self.assertEqual(denied.status, 401)
        denied_get = self.backup_get(dest, capability=cap)
        self.assertEqual(denied_get.status, 401)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
