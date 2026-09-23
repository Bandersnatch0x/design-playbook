#!/usr/bin/env python3
"""T-068 unit tests: promotion governance log.

Append-only discipline, the user-only decisive boundary (an agent may never
write ``promotion_decided``), schema validation, and the ``user_promotions``
write gate consumed by T-070. In-process over the module's public functions.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts import promotion_governance as pg  # noqa: E402

TS = "2026-09-22T00:00:00Z"


def _opened(event_id="evt-1", target="src/ui/Button.tsx", **over):
    event = {
        "id": event_id, "event": "promotion_candidate_opened",
        "decided_by": "agent", "confirmed_at": TS,
        "kind": "component", "target": target,
        "candidate_id": "COMP-001",
        "rationale": "recurs across 3 runs / 2 scenes",
        "evidence_refs": ["run-1", "run-2", "run-3"],
    }
    event.update(over)
    return event


def _decided(event_id="evt-2", target="src/ui/Button.tsx",
             decision="promote", decided_by="user", **over):
    event = {
        "id": event_id, "event": "promotion_decided",
        "decided_by": decided_by, "confirmed_at": TS,
        "kind": "component", "target": target, "decision": decision,
        "rationale": "stable enough to enter the baseline",
    }
    event.update(over)
    return event


class ValidationTests(unittest.TestCase):
    def test_valid_open_and_decide(self):
        errors = pg.validate_promotion_events([_opened(), _decided()])
        self.assertEqual(errors, [])

    def test_agent_may_never_write_decisive_event(self):
        errors = pg.validate_promotion_events([_decided(decided_by="agent")])
        self.assertTrue(any("user-decisive" in e for e in errors))

    def test_open_requires_evidence_refs(self):
        errors = pg.validate_promotion_events([_opened(evidence_refs=[])])
        self.assertTrue(any("evidence_refs" in e for e in errors))

    def test_decision_enum_enforced(self):
        errors = pg.validate_promotion_events([_decided(decision="shipit")])
        self.assertTrue(any("decision" in e for e in errors))

    def test_kind_enum_enforced(self):
        errors = pg.validate_promotion_events([_opened(kind="vibe")])
        self.assertTrue(any("kind" in e for e in errors))

    def test_token_kind_accepted(self):
        errors = pg.validate_promotion_events(
            [_opened(kind="token", target="--color-primary"),
             _decided(kind="token", target="--color-primary")])
        self.assertEqual(errors, [])

    def test_duplicate_id_rejected(self):
        errors = pg.validate_promotion_events(
            [_opened(event_id="evt-1"), _decided(event_id="evt-1")])
        self.assertTrue(any("duplicate event id" in e for e in errors))

    def test_bad_timestamp_rejected(self):
        errors = pg.validate_promotion_events([_opened(confirmed_at="tomorrow")])
        self.assertTrue(any("ISO-8601" in e for e in errors))

    def test_supersedes_must_point_back(self):
        events = [_decided(event_id="a", supersedes="b"),
                  _opened(event_id="b")]
        errors = pg.validate_promotion_events(events)
        self.assertTrue(any("earlier event" in e for e in errors))


class AppendTests(unittest.TestCase):
    def test_append_only_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-governance.jsonl"
            pg.append_event(path, _opened())
            pg.append_event(path, _decided())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            events = pg.parse_promotion_log(path.read_text(encoding="utf-8"))
            self.assertEqual([e["event"] for e in events],
                             ["promotion_candidate_opened", "promotion_decided"])

    def test_append_rejects_invalid_event_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-governance.jsonl"
            pg.append_event(path, _opened())
            before = path.read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                pg.append_event(path, _decided(decided_by="agent"))
            self.assertEqual(path.read_text(encoding="utf-8"), before)


class WriteGateTests(unittest.TestCase):
    def test_user_promotions_keys_by_kind_and_target(self):
        events = [_opened(),
                  _decided(decision="reject"),
                  _decided(event_id="evt-3", decision="promote")]
        accepted = pg.user_promotions(events)
        self.assertIn("component::src/ui/Button.tsx", accepted)
        self.assertEqual(accepted["component::src/ui/Button.tsx"]["decision"],
                         "promote")

    def test_agent_promote_never_counts(self):
        accepted = pg.user_promotions([_decided(decided_by="agent")])
        self.assertEqual(accepted, {})

    def test_reject_does_not_promote(self):
        accepted = pg.user_promotions([_decided(decision="reject")])
        self.assertEqual(accepted, {})


if __name__ == "__main__":
    unittest.main()
