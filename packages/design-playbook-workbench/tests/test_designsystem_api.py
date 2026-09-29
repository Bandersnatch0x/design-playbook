#!/usr/bin/env python3
"""A07 over the real API: token views, edits, publication, baseline proposal.

The domain rules are covered directly in ``test_designsystem.py``; these
tests prove the *distributed surface* is the same contract -- the routes
exist, the capability scopes hold, error codes are the documented ones,
and the baseline still lands in an ordinary R06 proposal that only the
maintainer can authorize.
"""
from __future__ import annotations

import json
import unittest

from design_playbook_workbench.blobs import digest_bytes

from tests.harness import WorkbenchHarness, http_request

TOKENS = {
    "color": {"brand": "#1f4fd8", "ink": "#16181d"},
    "space": {"gap": "8px"},
    "radius": {"control": "8px"},
    "theme": {"dark": {"color": {"ink": "#eceff4"}}},
}


class DesignSystemApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.project_dir = self.h.make_directory("project")
        self.other_dir = self.h.make_directory("other")
        self.registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.other = self.h.register(self.other_dir, name="Other").json["result"]
        self.project_id = self.registered["projectId"]
        self.other_id = self.other["projectId"]
        self.grant(self.project_id, ["read", "write"])
        self.grant(self.other_id, ["read", "write"])
        (self.project_dir / "DESIGN.md").write_bytes(b"# Design baseline\n")
        folder = self.project_dir / "tokens"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "brand.json").write_bytes(
            json.dumps(TOKENS, ensure_ascii=False, indent=2).encode("utf-8")
        )
        self.baseline_before = digest_bytes((folder / "brand.json").read_bytes())
        imported = self.h.import_assets(self.project_id, ["tokens/brand.json"])
        assert imported.status == 200, imported.text
        self.asset_id = imported.json["result"]["asset"]["assetId"]

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = self.h.project_target(project_id)["counter"]
        response = self.h.grant(project_id, scopes, expected_counter=counter)
        assert response.status == 200, response.text

    def capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )

    def view(
        self,
        view: str,
        *,
        project_id: str | None = None,
        asset_id: str | None = None,
        query: str = "",
        capability: str | None = None,
    ):
        suffix = "?" + query if query else ""
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{project_id or self.project_id}"
            f"/assets/{asset_id or self.asset_id}/tokens/{view}{suffix}",
            token=None if capability else self.h.token,
            capability=capability,
        )

    def publish(self, *, operation_id: str | None = None, asset_id: str | None = None):
        return self.h.asset_action(
            self.project_id,
            asset_id or self.asset_id,
            "tokens-publish",
            operation_id=operation_id,
        )

    def edit(
        self,
        document: object,
        *,
        operation_id: str | None = None,
        capability: str | None = None,
    ):
        return self.h.asset_action(
            self.project_id,
            self.asset_id,
            "tokens-update",
            payload={"document": document},
            operation_id=operation_id,
            capability=capability,
        )

    def history(self, *, project_id: str | None = None, asset_id: str | None = None) -> dict:
        response = http_request(
            self.h.runtime,
            f"/api/v1/projects/{project_id or self.project_id}"
            f"/assets/{asset_id or self.asset_id}/history",
            token=self.h.token,
        )
        assert response.status == 200, response.text
        return response.json


class TokenViewApiTest(DesignSystemApiTestCase):
    def test_validation_preview_diff_and_affected_are_readable(self) -> None:
        self.assertEqual(self.publish().status, 200)

        document = self.view("document")
        self.assertEqual(document.status, 200, document.text)
        self.assertEqual(document.json["source"]["kind"], "revision")
        self.assertEqual(document.json["source"]["revisionNumber"], 1)
        # The editor starts from the stored text, not from a rebuild of it.
        self.assertEqual(json.loads(document.json["text"]), TOKENS)

        validation = self.view("validation")
        self.assertEqual(validation.status, 200, validation.text)
        self.assertTrue(validation.json["valid"])
        self.assertEqual(
            validation.json["categories"], ["color", "radius", "space"]
        )
        self.assertEqual(validation.json["tokenCount"], 4)

        preview = self.view("preview", query="theme=dark")
        self.assertEqual(preview.status, 200, preview.text)
        self.assertEqual(preview.json["theme"], "dark")
        self.assertEqual(
            preview.json["previewOrigin"], self.h.preview_origin
        )
        self.assertTrue(preview.json["previewUrl"].startswith(self.h.preview_origin))
        self.assertIn("样例由同一份 token 解析结果渲染", preview.json["note"])

        diff = self.view("diff")
        self.assertEqual(diff.status, 200, diff.text)
        self.assertEqual(diff.json["from"]["revisionNumber"], 1)
        self.assertEqual(diff.json["to"]["revisionNumber"], 1)
        self.assertEqual(diff.json["counts"], {"added": 0, "removed": 0, "changed": 0})

        affected = self.view("affected")
        self.assertEqual(affected.status, 200, affected.text)
        self.assertEqual(affected.json["components"], [])
        self.assertIn("不会自动升级", affected.json["note"])

    def test_a_second_revision_produces_a_real_diff(self) -> None:
        self.assertEqual(self.publish().status, 200)
        edited = self.edit({"color": {"brand": "#0b5fce", "ink": "#16181d"}, "space": {"gap": "12px"}})
        self.assertEqual(edited.status, 200, edited.text)
        self.assertEqual(self.publish().status, 200)

        diff = self.view("diff")
        self.assertEqual(diff.status, 200, diff.text)
        self.assertEqual(diff.json["from"]["revisionNumber"], 1)
        self.assertEqual(diff.json["to"]["revisionNumber"], 2)
        changed = {entry["path"]: entry for entry in diff.json["changed"]}
        self.assertEqual(sorted(changed), ["color.brand", "space.gap"])
        self.assertEqual(changed["color.brand"]["from"], "#1f4fd8")
        self.assertEqual(changed["color.brand"]["to"], "#0b5fce")

    def test_the_routes_refuse_unknown_views_parameters_and_foreign_assets(self) -> None:
        unknown = self.view("nonsense")
        self.assertEqual(unknown.status, 404)
        extra = self.view("validation", query="theme=dark")
        self.assertEqual(extra.status, 400)
        self.assertEqual(extra.error_code, "invalid-input")
        foreign = self.view("validation", project_id=self.other_id)
        self.assertEqual(foreign.status, 400)
        self.assertEqual(foreign.error_code, "invalid-target")
        for theme in ("nope", "dark&x=1"):
            with self.subTest(theme=theme):
                refused = self.view("preview", query=f"theme={theme}")
                self.assertIn(refused.status, (400,))

    def test_a_token_view_needs_a_published_or_drafted_document(self) -> None:
        # Nothing has been published yet, but the imported draft still holds
        # the tokens, so the views answer from the draft and say so.
        validation = self.view("validation")
        self.assertEqual(validation.status, 200, validation.text)
        self.assertTrue(validation.json["valid"])
        document = self.view("document")
        self.assertEqual(document.status, 200, document.text)
        self.assertEqual(document.json["source"], {"kind": "draft"})
        diff = self.view("diff")
        self.assertEqual(diff.status, 422)
        self.assertEqual(diff.error_code, "missing-dependency")


class TokenEditApiTest(DesignSystemApiTestCase):
    def test_edits_validate_before_they_write_and_replay_by_operation_id(self) -> None:
        broken = {"color": {"a": {"$ref": "color.b"}, "b": {"$ref": "color.a"}}}
        refused = self.edit(broken, operation_id="op_api_tokens_0001")
        self.assertEqual(refused.status, 400)
        self.assertEqual(refused.error_code, "invalid-input")
        self.assertEqual(self.history()["revisions"], [])

        valid = {"color": {"brand": "#1f4fd8"}, "space": {"gap": "12px"}}
        first = self.edit(valid, operation_id="op_api_tokens_0002")
        self.assertEqual(first.status, 200, first.text)
        self.assertTrue(first.json["result"]["validation"]["valid"])
        self.assertFalse(first.json["replayed"])

        replay = self.edit(valid, operation_id="op_api_tokens_0002")
        self.assertEqual(replay.status, 200, replay.text)
        self.assertTrue(replay.json["replayed"])
        self.assertEqual(replay.json["result"], first.json["result"])

        conflicting = self.edit(
            {"color": {"brand": "#000000"}}, operation_id="op_api_tokens_0002"
        )
        self.assertEqual(conflicting.status, 409)
        self.assertEqual(conflicting.error_code, "conflict")

    def test_publishing_validates_the_draft_and_only_touches_token_assets(self) -> None:
        (self.project_dir / "notes.md").write_bytes(b"# notes\n")
        markdown = self.h.import_assets(self.project_id, ["notes.md"]).json["result"][
            "asset"
        ]
        refused = self.publish(asset_id=markdown["assetId"])
        self.assertEqual(refused.status, 400)
        self.assertEqual(refused.error_code, "unsupported")

        self.assertEqual(self.edit({"color": {"brand": "#1f4fd8"}}).status, 200)
        published = self.publish()
        self.assertEqual(published.status, 200, published.text)
        self.assertEqual(published.json["result"]["revisionNumber"], 1)
        self.assertTrue(published.json["result"]["validation"]["valid"])
        self.assertEqual(
            [row["revisionNumber"] for row in self.history()["revisions"]], [1]
        )
        # Publishing never rewrites the project baseline file by itself.
        self.assertEqual(
            digest_bytes((self.project_dir / "tokens/brand.json").read_bytes()),
            self.baseline_before,
        )

    def test_a_read_capability_cannot_edit_or_publish(self) -> None:
        read_only = self.capability(self.project_id, ["read"])
        readable = self.view("validation", capability=read_only)
        self.assertEqual(readable.status, 200, readable.text)
        denied_edit = self.edit(
            {"color": {"brand": "#1f4fd8"}}, capability=read_only
        )
        self.assertEqual(denied_edit.status, 401)
        denied_publish = self.h.asset_action(
            self.project_id,
            self.asset_id,
            "tokens-publish",
            capability=read_only,
        )
        self.assertEqual(denied_publish.status, 401)
        denied_proposal = self.h.asset_action(
            self.project_id,
            self.asset_id,
            "propose-baseline",
            payload={"path": "tokens/brand.json"},
            capability=read_only,
        )
        self.assertEqual(denied_proposal.status, 401)


class BaselineProposalApiTest(DesignSystemApiTestCase):
    def propose(self, path: str = "tokens/brand.json"):
        return self.h.asset_action(
            self.project_id,
            self.asset_id,
            "propose-baseline",
            payload={"path": path},
        )

    def test_the_baseline_proposal_is_an_ordinary_maintainer_decision(self) -> None:
        self.assertEqual(self.publish().status, 200)
        response = self.propose()
        self.assertEqual(response.status, 200, response.text)
        proposal = response.json["result"]
        self.assertEqual(proposal["state"], "awaiting-authorization")
        self.assertEqual(proposal["changes"][0]["path"], "tokens/brand.json")
        self.assertEqual(proposal["changes"][0]["baseHash"], self.baseline_before)
        self.assertEqual(proposal["sourceLocator"]["assetId"], self.asset_id)
        self.assertEqual(proposal["sourceLocator"]["objectType"], "revision")
        self.assertIn("baseline owner", proposal["baselineOwner"])
        self.assertEqual(
            digest_bytes((self.project_dir / "tokens/brand.json").read_bytes()),
            self.baseline_before,
        )

        listed = self.h.proposals(self.project_id)
        self.assertEqual(listed.status, 200, listed.text)
        self.assertEqual(
            [row["proposalId"] for row in listed.json["proposals"]],
            [proposal["proposalId"]],
        )

        # A capability cannot authorize the write even with the write scope.
        capability = self.capability(self.project_id, ["read", "write"])
        refused = self.h.proposal_action(
            self.project_id,
            proposal["proposalId"],
            "apply",
            digest=proposal["digest"],
            capability=capability,
        )
        self.assertEqual(refused.status, 401)

        applied = self.h.proposal_action(
            self.project_id,
            proposal["proposalId"],
            "apply",
            digest=proposal["digest"],
        )
        self.assertEqual(applied.status, 200, applied.text)
        self.assertEqual(applied.json["result"]["status"], "applied")
        written = json.loads((self.project_dir / "tokens/brand.json").read_bytes())
        self.assertEqual(written, TOKENS)

    def test_an_external_edit_makes_the_proposal_stale(self) -> None:
        self.assertEqual(self.publish().status, 200)
        proposal = self.propose().json["result"]
        (self.project_dir / "tokens/brand.json").write_bytes(
            b'{"color": {"brand": "#000"}}'
        )
        refused = self.h.proposal_action(
            self.project_id,
            proposal["proposalId"],
            "apply",
            digest=proposal["digest"],
        )
        self.assertEqual(refused.status, 409)
        self.assertEqual(refused.error_code, "conflict")
        self.assertEqual(
            (self.project_dir / "tokens/brand.json").read_bytes(),
            b'{"color": {"brand": "#000"}}',
        )

    def test_an_unpublished_draft_and_a_missing_path_are_refused(self) -> None:
        unpublished = self.propose()
        self.assertEqual(unpublished.status, 422)
        self.assertEqual(unpublished.error_code, "missing-dependency")
        self.assertEqual(self.publish().status, 200)
        missing = self.propose(path="tokens/absent.json")
        self.assertEqual(missing.status, 422)
        self.assertEqual(missing.error_code, "missing-dependency")


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
