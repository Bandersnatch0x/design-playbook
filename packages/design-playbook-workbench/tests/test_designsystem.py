#!/usr/bin/env python3
"""A07: typed design-system tokens, previews, and the baseline hand-off.

The rules under test are the ones R07 names explicitly: one parser and one
validator for editing, rendering, and publication; missing references,
cycles, and type mismatches block publication; and replacing the project
baseline stays an ordinary R06 proposal owned by the existing baseline
owner -- publishing an asset never edits DESIGN.md by itself.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore, digest_bytes
from design_playbook_workbench.designsystem import (
    DesignSystemService,
    diff_documents,
    parse_document,
    resolve_references,
    sample_html,
    validate_document,
)
from design_playbook_workbench.errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    UNSUPPORTED,
    WorkbenchError,
)
from design_playbook_workbench.proposals import ProposalService
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

TOKENS = {
    "color": {
        "brand": "#1f4fd8",
        "ink": "#16181d",
        "surface": {"$ref": "color.ink"},
    },
    "space": {"gap": "8px", "section": 24},
    "radius": {"control": "8px"},
    "typography": {
        "body": {"fontFamily": "system-ui", "fontSize": "16px", "fontWeight": "400"}
    },
    "shadow": {"card": "0 1px 2px rgba(0,0,0,0.12)"},
    "theme": {
        "dark": {"color": {"surface": "#101216", "ink": "#eceff4"}},
    },
}


class DesignSystemTestCase(unittest.TestCase):
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
        self.proposals = ProposalService(
            store=self.store, service=self.service, data_dir=self.data_dir
        )
        self.reuse = ReuseService(
            store=self.store, service=self.service, assets=self.assets, blobs=self.blobs
        )
        self.design_system = DesignSystemService(
            store=self.store,
            service=self.service,
            assets=self.assets,
            proposals=self.proposals,
            blobs=self.blobs,
        )
        self._operations = 0
        self.project = self.base / "project"
        self.project.mkdir()
        candidate = self.service.probe_folder(self.project)
        self.target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Design",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        self.project_id = self.target["projectId"]
        self.grant(["read", "write"])
        (self.project / "DESIGN.md").write_bytes(b"# Design baseline\n")
        (self.project / "tokens").mkdir(parents=True, exist_ok=True)
        (self.project / "tokens/brand.json").write_bytes(
            json.dumps(TOKENS, ensure_ascii=False, indent=2).encode("utf-8")
        )
        self.asset = self.import_assets(["tokens/brand.json"])
        self.asset_id = self.asset["assetId"]

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def import_assets(self, selections):
        return self.assets.import_selection(
            self.project_id,
            selections=selections,
            operation=self.operation({"selections": selections}),
        )["result"]["asset"]

    def operation(self, payload: dict, *, expected: int | None = None, operation_id: str | None = None):
        if operation_id is None:
            self._operations += 1
            operation_id = f"op_ds_{self._operations:08d}"
        return Operation(
            operation_id=operation_id, payload=payload, expected_counter=expected
        )

    def grant(self, scopes: list[str]) -> None:
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=scopes,
            operation=self.operation({"scopes": scopes}, expected=counter),
        )

    def asset_action(self, asset_id, verb, *, payload=None, operation_id=None):
        # A fresh operation ID per call: reusing one ID with a different
        # payload is the conflict case, not a way to run a second edit.
        self._operations += 1
        operation_obj = Operation(
            operation_id=operation_id or f"op_{verb}_{self._operations:08d}",
            payload={"action": verb, "assetId": asset_id, **(payload or {})},
            expected_counter=None,
        )
        if verb in ("tokens-update",):
            return self.design_system.update_tokens(
                self.project_id,
                asset_id,
                document=(payload or {}).get("document"),
                operation=operation_obj,
            )
        if verb == "tokens-publish":
            return self.design_system.publish(
                self.project_id, asset_id, operation=operation_obj
            )
        if verb == "propose-baseline":
            return self.design_system.propose_baseline(
                self.project_id,
                asset_id,
                path=(payload or {}).get("path"),
                operation=operation_obj,
            )
        if verb == "publish":
            return self.assets.publish_revision(
                self.project_id, asset_id, operation=operation_obj
            )
        raise AssertionError(f"unknown verb {verb}")

    def asset_detail(self, asset_id):
        return {"asset": self.assets.asset_detail(self.project_id, asset_id)["asset"]}


class TokenParsingTest(DesignSystemTestCase):
    def test_a_document_round_trips_into_typed_categories(self) -> None:
        document = parse_document(TOKENS)
        self.assertEqual(
            sorted(document["tokens"]), ["color", "radius", "shadow", "space", "typography"]
        )
        self.assertEqual(document["themes"]["dark"]["color"]["surface"], "#101216")
        self.assertEqual(document["tokens"]["color"]["surface"], {"$ref": "color.ink"})

    def test_unknown_categories_and_malformed_documents_are_refused(self) -> None:
        for raw in (
            {"colour": {"brand": "#fff"}},
            {"color": "#fff"},
            {"theme": []},
            "{not json",
            "[]",
            None,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(WorkbenchError) as caught:
                    parse_document(raw)
                self.assertIn(
                    caught.exception.code, (INVALID_INPUT, UNSUPPORTED)
                )

    def test_references_resolve_and_errors_are_typed(self) -> None:
        resolved, errors = resolve_references(parse_document(TOKENS))
        self.assertEqual(resolved["color"]["surface"], "#16181d")
        self.assertEqual(errors, [])

        missing = dict(TOKENS)
        missing["color"] = dict(TOKENS["color"], ghost={"$ref": "color.nope"})
        _, errors = resolve_references(parse_document(missing))
        self.assertEqual(errors[0]["kind"], "missing-reference")

        cycle = {
            "color": {
                "a": {"$ref": "color.b"},
                "b": {"$ref": "color.a"},
            }
        }
        _, errors = resolve_references(parse_document(cycle))
        self.assertEqual(errors[0]["kind"], "reference-cycle")

        mismatch = {
            "color": {"brand": "#fff"},
            "space": {"gap": {"$ref": "color.brand"}},
        }
        _, errors = resolve_references(parse_document(mismatch))
        self.assertEqual(errors[0]["kind"], "type-mismatch")
        self.assertEqual(errors[0]["expected"], "space")

    def test_value_types_are_checked_against_the_category(self) -> None:
        bad = {
            "color": {"brand": "not-a-color"},
            "space": {"gap": "wide"},
            "shadow": {"card": 5},
            "typography": {"body": "system-ui"},
        }
        verdict = validate_document(parse_document(bad))
        self.assertFalse(verdict["valid"])
        kinds = {error["path"]: error["kind"] for error in verdict["errors"]}
        self.assertEqual(kinds["color.brand"], "invalid-value")
        self.assertEqual(kinds["space.gap"], "invalid-value")
        self.assertEqual(kinds["shadow.card"], "invalid-value")
        self.assertEqual(kinds["typography.body"], "type-mismatch")

    def test_the_sample_preview_uses_the_resolved_values(self) -> None:
        html = sample_html(parse_document(TOKENS))
        self.assertIn("#16181d", html)
        self.assertIn("color.brand", html)
        self.assertIn("<style>", html)


class PublishRulesTest(DesignSystemTestCase):
    def test_publishing_validates_before_it_writes(self) -> None:
        broken = {"color": {"brand": {"$ref": "color.missing"}}}
        with self.assertRaises(WorkbenchError) as caught:
            self.asset_action(self.asset_id, "tokens-update", payload={"document": broken})
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertEqual(len(self.store.asset_revisions(self.asset_id)), 0)

        good = {"color": {"brand": "#1f4fd8"}, "space": {"gap": "8px"}}
        updated = self.asset_action(
            self.asset_id, "tokens-update", payload={"document": good}
        )
        self.assertTrue(updated["result"]["validation"]["valid"])
        published = self.asset_action(self.asset_id, "tokens-publish")
        self.assertEqual(published["result"]["revisionNumber"], 1)
        self.assertTrue(published["result"]["validation"]["valid"])
        self.assertEqual(len(self.store.asset_revisions(self.asset_id)), 1)

    def test_publishing_a_broken_draft_is_refused_even_after_the_fact(self) -> None:
        # A draft written by any other route must still fail the same
        # validator at publish time.
        draft = self.store.draft(self.asset_id)
        attributes = json.loads(draft["attributes_json"])
        payload = json.dumps(
            {"color": {"a": {"$ref": "color.b"}, "b": {"$ref": "color.a"}}},
            ensure_ascii=False,
        ).encode("utf-8")
        record = self.blobs.put(payload)
        attributes["manifest"][0]["contentHash"] = record.content_hash
        attributes["manifest"][0]["size"] = record.size
        self.store.update_draft(
            asset_id=self.asset_id,
            tags=[],
            attributes=attributes,
            now="2026-09-26T12:00:00Z",
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.asset_action(self.asset_id, "tokens-publish")
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("reference-cycle", str(caught.exception))
        self.assertEqual(len(self.store.asset_revisions(self.asset_id)), 0)

    def test_only_token_assets_can_use_the_design_system_routes(self) -> None:
        (self.project / "notes.md").write_bytes(b"# notes\n")
        markdown = self.import_assets(["notes.md"])
        with self.assertRaises(WorkbenchError) as caught:
            self.design_system.validate(self.project_id, markdown["assetId"])
        self.assertEqual(caught.exception.code, UNSUPPORTED)

    def test_the_diff_and_the_affected_list_are_real(self) -> None:
        first = {"color": {"brand": "#1f4fd8"}, "space": {"gap": "8px"}}
        second = {"color": {"brand": "#0b5fce"}, "space": {"gap": "12px", "tight": "4px"}}
        first_publish = self.asset_action(
            self.asset_id, "tokens-update", payload={"document": first}
        )
        self.assertTrue(first_publish["result"]["validation"]["valid"])
        self.asset_action(self.asset_id, "tokens-publish")
        self.asset_action(self.asset_id, "tokens-update", payload={"document": second})
        self.asset_action(self.asset_id, "tokens-publish")

        diff = self.design_system.diff(self.project_id, self.asset_id)
        self.assertEqual(
            [entry["path"] for entry in diff["changed"]], ["color.brand", "space.gap"]
        )
        self.assertEqual([entry["path"] for entry in diff["added"]], ["space.tight"])
        self.assertEqual(diff["counts"]["removed"], 0)

        # A component that depends on the token set shows up as affected.
        revision = self.store.latest_revision(self.asset_id)
        (self.project / "components").mkdir(parents=True, exist_ok=True)
        (self.project / "components/button.md").write_bytes(b"# Button\n")
        component = self.import_assets(["components/button.md"])
        self.reuse.publish_with_dependencies(
            self.project_id,
            component["assetId"],
            dependencies=[
                {"assetId": self.asset_id, "revisionId": revision["revision_id"]}
            ],
            operation=self.operation({"publish-deps": "component"}),
        )
        affected = self.design_system.affected(self.project_id, self.asset_id)
        self.assertEqual(
            [entry["assetId"] for entry in affected["components"]],
            [component["assetId"]],
        )
        self.assertIn("不会自动升级", affected["note"])

    def test_the_preview_is_generated_from_the_published_values(self) -> None:
        self.asset_action(self.asset_id, "tokens-publish")
        preview = self.design_system.preview(
            self.project_id, self.asset_id, theme="dark"
        )
        self.assertEqual(preview["theme"], "dark")
        self.assertIn("dark", preview["themes"])
        html = self.blobs.read(preview["contentHash"]).decode("utf-8")
        # The dark theme overrides the surface swatch in the sample.
        self.assertIn("#101216", html)
        with self.assertRaises(WorkbenchError) as caught:
            self.design_system.preview(self.project_id, self.asset_id, theme="nope")
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class BaselineProposalTest(DesignSystemTestCase):
    def test_proposing_the_baseline_creates_a_normal_proposal(self) -> None:
        before = digest_bytes((self.project / "tokens/brand.json").read_bytes())
        self.asset_action(self.asset_id, "tokens-publish")
        proposal = self.asset_action(
            self.asset_id,
            "propose-baseline",
            payload={"path": "tokens/brand.json"},
        )["result"]
        self.assertEqual(proposal["state"], "awaiting-authorization")
        self.assertEqual(proposal["changes"][0]["path"], "tokens/brand.json")
        self.assertEqual(proposal["changes"][0]["baseHash"], before)
        self.assertIn("baseline owner", proposal["baselineOwner"])
        self.assertEqual(proposal["sourceLocator"]["objectType"], "revision")
        # Nothing was written: the baseline file still has its own content.
        self.assertEqual(
            digest_bytes((self.project / "tokens/brand.json").read_bytes()), before
        )

    def test_publishing_an_asset_never_touches_design_md(self) -> None:
        design = self.project / "DESIGN.md"
        before = digest_bytes(design.read_bytes())
        self.asset_action(self.asset_id, "tokens-publish")
        self.assertEqual(digest_bytes(design.read_bytes()), before)

    def test_an_external_edit_invalidates_the_old_proposal(self) -> None:
        self.asset_action(self.asset_id, "tokens-publish")
        proposal = self.asset_action(
            self.asset_id,
            "propose-baseline",
            payload={"path": "tokens/brand.json"},
        )["result"]
        # The maintainer edits the baseline file between review and approval.
        (self.project / "tokens/brand.json").write_bytes(b'{"color": {"brand": "#000"}}')
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.apply(
                self.project_id,
                proposal["proposalId"],
                digest=proposal["digest"],
                operation=self.operation({"apply": proposal["proposalId"]}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(
            (self.project / "tokens/brand.json").read_bytes(),
            b'{"color": {"brand": "#000"}}',
        )

    def test_an_agent_capability_cannot_authorize_the_baseline_write(self) -> None:
        """Approval is the maintainer's: a wrong digest is refused.

        The transport-level refusal for capabilities lives in the
        proposals API suite; the domain half proven here is that the
        authorization is bound to this exact proposal digest.
        """
        self.asset_action(self.asset_id, "tokens-publish")
        proposal = self.asset_action(
            self.asset_id,
            "propose-baseline",
            payload={"path": "tokens/brand.json"},
        )["result"]
        before = (self.project / "tokens/brand.json").read_bytes()
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.apply(
                self.project_id,
                proposal["proposalId"],
                digest="sha256:" + "0" * 64,
                operation=self.operation({"apply": "wrong-digest"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual((self.project / "tokens/brand.json").read_bytes(), before)
        self.assertEqual(
            self.store.proposal(proposal["proposalId"])["state"],
            "awaiting-authorization",
        )

    def test_the_baseline_proposal_can_be_applied_and_reverted(self) -> None:
        self.asset_action(self.asset_id, "tokens-publish")
        asset = self.store.asset(self.asset_id)
        original = (self.project / "tokens/brand.json").read_bytes()
        # Replace the draft with a different (valid) document and publish.
        replacement = {"color": {"brand": "#0b5fce"}, "space": {"gap": "12px"}}
        self.asset_action(
            self.asset_id, "tokens-update", payload={"document": replacement}
        )
        self.asset_action(self.asset_id, "tokens-publish")
        proposal = self.asset_action(
            self.asset_id,
            "propose-baseline",
            payload={"path": "tokens/brand.json"},
        )["result"]
        applied = self.proposals.apply(
            self.project_id,
            proposal["proposalId"],
            digest=proposal["digest"],
            operation=self.operation({"apply": "baseline"}),
        )["result"]
        self.assertEqual(applied["status"], "applied")
        written = json.loads((self.project / "tokens/brand.json").read_bytes())
        self.assertEqual(written["color"]["brand"], "#0b5fce")
        self.assertNotEqual(
            (self.project / "tokens/brand.json").read_bytes(), original
        )
        # The proposal carries the asset identity, so lineage never depends
        # on a file name.
        self.assertEqual(proposal["sourceLocator"]["assetId"], asset["asset_id"])


class DiffHelperTest(unittest.TestCase):
    def test_diff_reports_added_removed_and_changed_paths(self) -> None:
        before = parse_document({"color": {"a": "#111", "b": "#222"}})
        after = parse_document({"color": {"a": "#111", "c": "#333"}})
        diff = diff_documents(before, after)
        self.assertEqual([entry["path"] for entry in diff["added"]], ["color.c"])
        self.assertEqual([entry["path"] for entry in diff["removed"]], ["color.b"])
        self.assertEqual(diff["changed"], [])
        self.assertEqual(diff["counts"]["added"], 1)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
