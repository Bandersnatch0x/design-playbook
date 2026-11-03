"""The stored-row decoding rule and the asset identity guard (R03, R04).

Every caller used to decode the same columns its own way, with its own
fallback. These tests pin the one rule: the decoded value keeps its stored
JSON type, a missing or corrupt column falls back to the caller's shape, and
the identity guard refuses missing, foreign, and wrong-kind targets.
"""
from __future__ import annotations

import unittest

from design_playbook_workbench import rows
from design_playbook_workbench.errors import (
    INVALID_TARGET,
    UNSUPPORTED,
    WorkbenchError,
)


class _RowStore:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    def asset(self, asset_id: str) -> dict | None:
        return self._row


class DecodeRuleTest(unittest.TestCase):
    def test_a_column_keeps_the_json_type_it_stored(self) -> None:
        # A proposal payload is a list; a draft's attributes are an object.
        self.assertEqual(rows.load('{"a": 1}', {}), {"a": 1})
        self.assertEqual(rows.load("[1, 2]", []), [1, 2])
        self.assertEqual(rows.load('"text"', None), "text")

    def test_a_missing_or_corrupt_column_falls_back(self) -> None:
        self.assertEqual(rows.load(None, {}), {})
        self.assertEqual(rows.load("", []), [])
        self.assertEqual(rows.load("{not json", {"fallback": True}), {"fallback": True})

    def test_an_already_decoded_value_is_returned_as_is(self) -> None:
        self.assertEqual(rows.load({"a": 1}, {}), {"a": 1})
        self.assertEqual(rows.load([1], []), [1])

    def test_named_decoders_fall_back_to_their_own_shape(self) -> None:
        # The stored shape is ours, so a mismatch is corruption; the caller's
        # expected shape wins instead of leaking a surprise type.
        self.assertEqual(rows.attributes({"attributes_json": "[1]"}), {})
        self.assertEqual(rows.tags({"tags_json": '{"a": 1}'}), [])
        self.assertEqual(rows.manifest(None), [])
        self.assertEqual(rows.origin({"origin_json": "[]"}), {})
        self.assertEqual(rows.capabilities({"capabilities_json": '{"a": 1}'}), [])

    def test_named_decoders_read_the_stored_columns(self) -> None:
        draft = {
            "attributes_json": '{"manifest": []}',
            "tags_json": '["brand"]',
        }
        self.assertEqual(rows.attributes(draft), {"manifest": []})
        self.assertEqual(rows.tags(draft), ["brand"])


class OwnedAssetGuardTest(unittest.TestCase):
    def test_a_missing_row_is_a_bad_target(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            rows.owned_asset(_RowStore(None), "p1", "a1")
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_a_row_from_another_project_is_a_bad_target(self) -> None:
        store = _RowStore({"asset_id": "a1", "project_id": "other", "kind": "component"})
        with self.assertRaises(WorkbenchError) as caught:
            rows.owned_asset(store, "p1", "a1")
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_a_wrong_kind_is_unsupported(self) -> None:
        store = _RowStore({"asset_id": "a1", "project_id": "p1", "kind": "component"})
        with self.assertRaises(WorkbenchError) as caught:
            rows.owned_asset(store, "p1", "a1", kind="tokens")
        self.assertEqual(caught.exception.code, UNSUPPORTED)

    def test_the_matching_row_is_returned(self) -> None:
        row = {"asset_id": "a1", "project_id": "p1", "kind": "tokens"}
        self.assertIs(rows.owned_asset(_RowStore(row), "p1", "a1", kind="tokens"), row)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
