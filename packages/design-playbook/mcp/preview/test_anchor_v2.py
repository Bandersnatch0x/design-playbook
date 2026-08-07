#!/usr/bin/env python3
"""Contract tests for anchor schema v2 (node_id + features, browser._parse_anchors)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser  # noqa: E402
from browser import _anchor_node_id, _parse_anchors  # noqa: E402


class AnchorV2Tests(unittest.TestCase):
    def test_v2_fields_added_when_round_known(self) -> None:
        raw = json.dumps([{
            "selector": "div.card > h2",
            "label": 'h2 "标题"',
            "comment": "太挤",
            "tag": "h2",
        }])
        anchors = _parse_anchors(raw, round_n=3)
        self.assertEqual(len(anchors), 1)
        a = anchors[0]
        self.assertEqual(a["node_id"], _anchor_node_id(3, 0, "div.card > h2"))
        self.assertEqual(a["features"]["tag"], "h2")
        self.assertEqual(a["features"]["text"], "标题")
        self.assertEqual(a["features"]["classes"], ["card"])

    def test_node_id_deterministic_and_round_scoped(self) -> None:
        sel = "div.card > h2"
        self.assertEqual(_anchor_node_id(3, 0, sel), _anchor_node_id(3, 0, sel))
        self.assertNotEqual(_anchor_node_id(3, 0, sel), _anchor_node_id(4, 0, sel))
        self.assertNotEqual(_anchor_node_id(3, 0, sel), _anchor_node_id(3, 1, sel))

    def test_no_v2_fields_when_round_unknown(self) -> None:
        anchors = _parse_anchors(
            '[{"selector":"p","label":"p \\"x\\"","comment":"y","tag":"p"}]',
            round_n=0)
        self.assertNotIn("node_id", anchors[0])
        self.assertNotIn("features", anchors[0])

    def test_read_side_compat_fields_are_additive(self) -> None:
        # validate_run-style consumers read selector/comment/label/tag only;
        # v2 fields must not disturb the base contract.
        raw = json.dumps([{
            "selector": "p",
            "label": "p",
            "comment": "y",
            "tag": "p",
            "node_id": "ab12cd34",
            "features": {"tag": "p"},
        }])
        anchors = _parse_anchors(raw, round_n=1)
        self.assertEqual(anchors[0]["selector"], "p")
        self.assertEqual(anchors[0]["comment"], "y")
        self.assertEqual(anchors[0]["label"], "p")
        self.assertEqual(anchors[0]["tag"], "p")

    def test_quoted_label_only(self) -> None:
        raw = json.dumps([{"selector": "#chart svg", "label": "svg", "tag": "svg"}])
        anchors = _parse_anchors(raw, round_n=2)
        self.assertEqual(anchors[0]["node_id"], _anchor_node_id(2, 0, "#chart svg"))
        self.assertNotIn("text", anchors[0]["features"])


if __name__ == "__main__":
    unittest.main()
