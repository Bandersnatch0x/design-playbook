#!/usr/bin/env python3
"""Process-boundary tests for persistent contract v1 lifecycle."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contract_v1 as cv  # noqa: E402


def _field(value: str, *, provenance: str = "inferred", resolution: str = "assumed",
           source_hash: str | None = None) -> dict:
    out = {
        "value": value,
        "provenance": provenance,
        "resolution": resolution,
    }
    if source_hash is not None:
        out["source_hash"] = source_hash
    return out


class ContractV1Tests(unittest.TestCase):
    def test_normalize_orders_fields_and_rejects_unknown_version(self) -> None:
        raw = {
            "schemaVersion": 1,
            "fields": {
                "b.theme": _field("dark"),
                "a.goal": _field("ship", resolution="open"),
            },
            "changelog": [{"at": "2026-08-08T00:00:00Z", "summary": "seed"}],
        }
        normalized = cv.normalize_contract(raw)
        self.assertEqual(list(normalized["fields"]), ["a.goal", "b.theme"])
        sha1 = cv.contract_sha(raw)
        sha2 = cv.contract_sha({
            "schemaVersion": 1,
            "fields": {
                "a.goal": _field("ship", resolution="open"),
                "b.theme": _field("dark"),
            },
            "changelog": [{"at": "2026-08-08T00:00:00Z", "summary": "seed"}],
        })
        self.assertEqual(sha1, sha2)

        with self.assertRaises(cv.ContractError) as ctx:
            cv.normalize_contract({"schemaVersion": 99, "fields": {"x": _field("y")}})
        self.assertIn("unsupported contract schemaVersion", str(ctx.exception))

    def test_omitted_resolution_and_inheritance_fail(self) -> None:
        with self.assertRaises(cv.ContractError):
            cv.normalize_contract({
                "schemaVersion": 1,
                "fields": {
                    "a.goal": {"value": "x", "provenance": "observed"},
                },
            })
        with self.assertRaises(cv.ContractError) as ctx:
            cv.normalize_contract({
                "schemaVersion": 1,
                "extends": "other",
                "fields": {"a.goal": _field("x")},
            })
        self.assertIn("layered inheritance", str(ctx.exception))

    def test_promote_does_not_create_decided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with self.assertRaises(cv.ContractError) as ctx:
                cv.promote_fields(
                    {"a.goal": _field("x", resolution="decided")},
                    project_dir=project,
                    changelog_summary="accept",
                    at="2026-08-08T00:00:00Z",
                )
            self.assertIn("cannot create decided", str(ctx.exception))

            contract = cv.promote_fields(
                {
                    "a.goal": _field("ship", resolution="assumed"),
                    "b.open": _field("?", resolution="open"),
                },
                project_dir=project,
                changelog_summary="first accept",
                at="2026-08-08T00:00:00Z",
            )
            self.assertEqual(contract["fields"]["a.goal"]["resolution"], "assumed")
            self.assertTrue((project / cv.CONTRACT_FILENAME).is_file())

    def test_bind_first_blocks_open_and_unacked_assumed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            run = root / "run"
            cv.promote_fields(
                {
                    "a.goal": _field("ship", resolution="assumed"),
                    "b.risk": _field("unknown", resolution="open"),
                },
                project_dir=project,
                changelog_summary="seed",
                at="2026-08-08T00:00:00Z",
            )
            blocked = cv.bind_first(project, run)
            self.assertFalse(blocked.ok)
            self.assertIn("b.risk", blocked.open_fields)
            self.assertTrue(any("open field blocks" in item for item in blocked.blockers))
            self.assertTrue(
                any("assumed field requires acknowledgement" in item for item in blocked.blockers)
            )
            self.assertTrue((run / cv.BIND_SNAPSHOT_FILENAME).is_file())

            ok = cv.bind_first(project, run, acknowledgements=["a.goal"])
            # still blocked by open field
            self.assertFalse(ok.ok)
            self.assertTrue(any("b.risk" in item for item in ok.blockers))

    def test_decision_append_supersession_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            cv.promote_fields(
                {"a.goal": _field("draft", resolution="assumed")},
                project_dir=project,
                changelog_summary="seed",
                at="2026-08-08T00:00:00Z",
            )
            log = project / cv.DECISIONS_FILENAME
            cv.append_decision(log, {
                "id": "d1",
                "field": "a.goal",
                "decision": "ship v1",
                "rationale": "user confirmed in chat",
                "confirmed_at": "2026-08-08T01:00:00Z",
            })
            with self.assertRaises(cv.ContractError):
                cv.append_decision(log, {
                    "id": "d1",
                    "field": "a.goal",
                    "decision": "rewrite",
                    "rationale": "illegal rewrite",
                    "confirmed_at": "2026-08-08T02:00:00Z",
                })
            cv.append_decision(log, {
                "id": "d2",
                "field": "a.goal",
                "decision": "ship v2",
                "rationale": "user supersession",
                "confirmed_at": "2026-08-08T03:00:00Z",
                "supersedes": "d1",
            })
            decisions = cv.load_decisions(log)
            applied = cv.apply_decisions(cv.load_contract(project / cv.CONTRACT_FILENAME), decisions)
            self.assertEqual(applied["fields"]["a.goal"]["value"], "ship v2")
            self.assertEqual(applied["fields"]["a.goal"]["resolution"], "decided")

            bind = cv.bind_first(project, project / "run")
            self.assertTrue(bind.ok)
            self.assertEqual(bind.decision_log_sha, cv.decision_log_sha(log))
            self.assertEqual(bind.contract["fields"]["a.goal"]["resolution"], "decided")

    def test_source_drift_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            cv.promote_fields(
                {"a.goal": _field("ship", resolution="assumed", source_hash="aaa")},
                project_dir=project,
                changelog_summary="seed",
                at="2026-08-08T00:00:00Z",
            )
            # acknowledge assumed so only drift remains
            result = cv.bind_first(
                project,
                run,
                acknowledgements=["a.goal"],
                source_hashes={"a.goal": "bbb"},
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.stale_fields, ["a.goal"])
            self.assertTrue(any("drift" in item for item in result.blockers))

    def test_verify_rejects_unknown_version_and_bad_decisions(self) -> None:
        errs = cv.verify_contract({"schemaVersion": 2, "fields": {"a": _field("x")}})
        self.assertTrue(errs)
        good = {
            "schemaVersion": 1,
            "fields": {"a.goal": _field("x", resolution="open")},
            "changelog": [],
        }
        self.assertEqual(cv.verify_contract(good), [])
        errs = cv.verify_contract(good, decisions=[{
            "id": "d1",
            "field": "missing.path",
            "decision": "y",
            "rationale": "n/a",
            "confirmed_at": "2026-08-08T00:00:00Z",
        }])
        self.assertTrue(any("unknown field" in item for item in errs))

    def test_whole_contract_scope_only(self) -> None:
        """Bind-first always loads the full project contract document."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            cv.promote_fields(
                {
                    "a.goal": _field("one", resolution="assumed"),
                    "b.scope": _field("two", resolution="assumed"),
                },
                project_dir=project,
                changelog_summary="seed",
                at="2026-08-08T00:00:00Z",
            )
            result = cv.bind_first(
                project, run, acknowledgements=["a.goal", "b.scope"]
            )
            self.assertTrue(result.ok)
            self.assertEqual(
                set(result.contract["fields"]),
                {"a.goal", "b.scope"},
            )
            snap = json.loads((run / cv.BIND_SNAPSHOT_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(snap["schemaVersion"], 1)
            self.assertIn("contract_sha", snap)
            self.assertIn("decision_log_sha", snap)


if __name__ == "__main__":
    unittest.main()
