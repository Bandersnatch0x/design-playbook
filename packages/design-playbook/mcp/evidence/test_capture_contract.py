#!/usr/bin/env python3
"""Contract tests for the package-internal capture-contract interface.

Covers the three capture_contract.py surfaces (ADR-0018 enforcement site 1):
  * ``parse_capture_contract`` — write authority: normalized request or
    fail-closed ValueError with recapture hint;
  * ``validate_capture_snapshot`` — read authority: host-neutral full-shape
    facts over bound manifest request snapshots (no raises, empty = valid);
  * ``capture_contract_schema_fragment`` — the contract-fields JSON Schema
    fragment the provider tool schema composes (const/enum/required shared
    with parse, so schema and parser cannot drift).

Deliberately no lockstep test: the seam between the provider schema and the
parser is the shared module constants, not a second mirror implementation.
The one directional check (validate accepts parse output) pins the read side
to the write side's normalization.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    CAPTURE_SCHEMA_VERSION,
    COLOR_SCHEMES,
    MIN_VIEWPORT_DPR,
    RECAPTURE_HINT,
    capture_contract_schema_fragment,
    parse_capture_contract,
    validate_capture_snapshot,
)

_FULL_VIEWPORT = {
    "width": 1280,
    "height": 800,
    "devicePixelRatio": 1.0,
    "colorScheme": "light",
}


def _full_request(**overrides):
    request = {
        "schemaVersion": 1,
        "viewport": dict(_FULL_VIEWPORT),
        "freeze": {
            "enabled": True,
            "waitFonts": True,
            "networkIdle": False,
        },
    }
    request.update(overrides)
    return request


class CaptureContractParseTests(unittest.TestCase):
    """Write side: normalized request or fail-closed ValueError."""

    def test_requires_schema_version_with_recapture_hint(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({"url": "about:blank"})
        self.assertIn("schemaVersion is required", str(ctx.exception))
        self.assertIn(RECAPTURE_HINT, str(ctx.exception))

    def test_unsupported_version_fails_closed(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({
                "schemaVersion": 99,
                "viewport": dict(_FULL_VIEWPORT),
            })
        self.assertIn("unsupported capture schemaVersion 99", str(ctx.exception))
        self.assertIn(RECAPTURE_HINT, str(ctx.exception))

    def test_schema_version_rejects_boolean(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({
                "schemaVersion": True,
                "viewport": dict(_FULL_VIEWPORT),
            })
        self.assertIn("unsupported capture schemaVersion True", str(ctx.exception))

    def test_viewport_object_required(self) -> None:
        for bad in (None, 42, "1280x800", [], True):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    parse_capture_contract({"schemaVersion": 1, "viewport": bad})
                self.assertIn("viewport object is required", str(ctx.exception))

    def test_viewport_field_validation_mirrors_schema(self) -> None:
        cases = [
            ({"width": 0, "height": 800, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.width must be a positive integer"),
            ({"width": "wide", "height": 800, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.width must be a positive integer"),
            ({"width": 1280, "height": -1, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.height must be a positive integer"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 0, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": True, "height": 800, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.width must be a positive integer"),
            ({"width": 1280, "height": True, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.height must be a positive integer"),
            ({"width": 1280, "height": 800, "devicePixelRatio": True, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 0.01, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": math.nan, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": math.inf, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 1, "colorScheme": "sepia"},
             "viewport.colorScheme must be one of"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 1, "colorScheme": []},
             "viewport.colorScheme must be one of"),
        ]
        for viewport, expected in cases:
            with self.subTest(viewport=viewport):
                with self.assertRaises(ValueError) as ctx:
                    parse_capture_contract({"schemaVersion": 1, "viewport": viewport})
                self.assertIn(expected, str(ctx.exception))

    def test_freeze_defaults_applied_when_absent(self) -> None:
        parsed = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
        })
        self.assertEqual(parsed["freeze"], {
            "enabled": True,
            "waitFonts": True,
            "networkIdle": False,
        })

    def test_freeze_partial_defaults_and_booleans(self) -> None:
        parsed = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
            "freeze": {"networkIdle": True},
        })
        self.assertEqual(parsed["freeze"], {
            "enabled": True,
            "waitFonts": True,
            "networkIdle": True,
        })
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({
                "schemaVersion": 1,
                "viewport": dict(_FULL_VIEWPORT),
                "freeze": {"enabled": "yes"},
            })
        self.assertIn("freeze.enabled must be a boolean", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({
                "schemaVersion": 1,
                "viewport": dict(_FULL_VIEWPORT),
                "freeze": "always",
            })
        self.assertIn("freeze must be an object", str(ctx.exception))

    def test_normalized_request_shape(self) -> None:
        parsed = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": {
                "width": 390,
                "height": 844,
                "devicePixelRatio": 2,
                "colorScheme": "dark",
            },
        })
        self.assertEqual(parsed["schemaVersion"], 1)
        self.assertEqual(parsed["viewport"], {
            "width": 390,
            "height": 844,
            "devicePixelRatio": 2.0,
            "colorScheme": "dark",
        })
        self.assertEqual(
            sorted(parsed),
            ["freeze", "schemaVersion", "viewport"],
        )


class CaptureContractValidateTests(unittest.TestCase):
    """Read side: full-shape facts, empty list = valid, never raises."""

    def test_valid_snapshot_yields_no_facts(self) -> None:
        self.assertEqual(validate_capture_snapshot(_full_request()), [])
        # Provider-echoed normalize output must always validate (one
        # directional seam pin; no lockstep mirror).
        self.assertEqual(
            validate_capture_snapshot(parse_capture_contract({
                "schemaVersion": 1,
                "viewport": dict(_FULL_VIEWPORT),
            })),
            [],
        )

    def test_non_object_snapshot_is_missing_schema_fact(self) -> None:
        for snapshot in (None, "no-request", 1, [], True):
            with self.subTest(snapshot=snapshot):
                facts = validate_capture_snapshot(snapshot)
                self.assertEqual(len(facts), 1)
                self.assertEqual(facts[0].code, "missing_schema_version")
                self.assertEqual(facts[0].actual, "None" if snapshot is None
                                 else type(snapshot).__name__)

    def test_missing_and_unsupported_schema_version_facts(self) -> None:
        request = _full_request()
        del request["schemaVersion"]
        facts = validate_capture_snapshot(request)
        self.assertEqual(facts[0].code, "missing_schema_version")
        self.assertEqual(facts[0].actual, "None")

        facts = validate_capture_snapshot(_full_request(schemaVersion=99))
        self.assertEqual(facts[0].code, "unsupported_schema_version")
        self.assertEqual(facts[0].actual, "99")

        facts = validate_capture_snapshot(_full_request(schemaVersion=True))
        self.assertEqual(facts[0].code, "unsupported_schema_version")
        self.assertEqual(facts[0].actual, "True")

    def test_missing_or_non_dict_viewport_is_missing_viewport_fact(self) -> None:
        for viewport in (None, "1280x800", 42, []):
            with self.subTest(viewport=viewport):
                request = _full_request(viewport=viewport)
                facts = validate_capture_snapshot(request)
                self.assertEqual(facts[0].code, "missing_viewport")

    def test_malformed_viewport_shape_fails_closed(self) -> None:
        # Was lax: viewport dict with partial fields passed the old G6 check.
        cases = [
            ({"width": 1280, "height": 800},  # missing dpr + colorScheme
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 0, "height": 800, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.width must be a positive integer"),
            ({"width": True, "height": 800, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.width must be a positive integer"),
            ({"width": 1280, "height": True, "devicePixelRatio": 1, "colorScheme": "light"},
             "viewport.height must be a positive integer"),
            ({"width": 1280, "height": 800, "devicePixelRatio": True, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 0.01, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": math.nan, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": math.inf, "colorScheme": "light"},
             "viewport.devicePixelRatio must be a number greater than or equal to"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 1, "colorScheme": "sepia"},
             "viewport.colorScheme must be one of"),
            ({"width": 1280, "height": 800, "devicePixelRatio": 1, "colorScheme": {}},
             "viewport.colorScheme must be one of"),
        ]
        for viewport, expected in cases:
            with self.subTest(viewport=viewport):
                facts = validate_capture_snapshot(_full_request(viewport=viewport))
                self.assertEqual(facts[0].code, "bad_viewport_shape")
                self.assertIn(expected, facts[0].detail)

    def test_missing_or_non_dict_freeze_is_missing_freeze_fact(self) -> None:
        for freeze in (None, "always", 42, []):
            with self.subTest(freeze=freeze):
                request = _full_request(freeze=freeze)
                facts = validate_capture_snapshot(request)
                self.assertEqual(facts[0].code, "missing_freeze")

    def test_partial_or_bad_freeze_shape_fails_closed(self) -> None:
        # Was lax: freeze absent entirely was accepted on the read side.
        cases = [
            {},
            {"enabled": True},          # waitFonts/networkIdle missing
            {"enabled": True, "waitFonts": True, "networkIdle": "no"},
        ]
        for freeze in cases:
            with self.subTest(freeze=freeze):
                facts = validate_capture_snapshot(_full_request(freeze=freeze))
                self.assertEqual(facts[0].code, "bad_freeze_shape")

    def test_partial_freeze_reports_first_bad_key(self) -> None:
        facts = validate_capture_snapshot(_full_request(
            freeze={"enabled": True, "waitFonts": True, "networkIdle": "no"}))
        self.assertIn("freeze.networkIdle must be a boolean", facts[0].detail)

    def test_extra_snapshot_keys_are_tolerated(self) -> None:
        # Read side stays host-neutral: unknown extra keys do not invalidate
        # a v1 full-shape snapshot (forward compatibility).
        request = _full_request(note="future-field")
        self.assertEqual(validate_capture_snapshot(request), [])


class CaptureContractSchemaFragmentTests(unittest.TestCase):
    """JSON Schema fragment: const/enum/required shared with the parser."""

    def test_fragment_is_composable_object(self) -> None:
        fragment = capture_contract_schema_fragment()
        self.assertIn("properties", fragment)
        self.assertIn("required", fragment)
        self.assertEqual(set(fragment["required"]), {"schemaVersion", "viewport"})
        self.assertEqual(
            set(fragment["properties"]),
            {"schemaVersion", "viewport", "freeze"},
        )

    def test_schema_version_const_matches_parser(self) -> None:
        fragment = capture_contract_schema_fragment()
        self.assertEqual(
            fragment["properties"]["schemaVersion"]["const"],
            CAPTURE_SCHEMA_VERSION,
        )
        self.assertEqual(
            fragment["properties"]["schemaVersion"]["type"],
            "integer",
        )
        self.assertEqual(
            fragment["properties"]["viewport"]["properties"]["devicePixelRatio"]["minimum"],
            MIN_VIEWPORT_DPR,
        )

    def test_viewport_full_shape_required_and_closed(self) -> None:
        fragment = capture_contract_schema_fragment()
        viewport = fragment["properties"]["viewport"]
        self.assertEqual(viewport["type"], "object")
        self.assertEqual(
            set(viewport["required"]),
            {"width", "height", "devicePixelRatio", "colorScheme"},
        )
        self.assertIs(viewport["additionalProperties"], False)
        self.assertEqual(viewport["properties"]["width"]["minimum"], 1)

    def test_color_scheme_enum_matches_parser_constants(self) -> None:
        fragment = capture_contract_schema_fragment()
        enum = fragment["properties"]["viewport"]["properties"]["colorScheme"]["enum"]
        self.assertEqual(enum, sorted(COLOR_SCHEMES))

    def test_freeze_defaults_in_schema_match_parse_defaults(self) -> None:
        fragment = capture_contract_schema_fragment()
        freeze = fragment["properties"]["freeze"]
        self.assertEqual(freeze["type"], "object")
        self.assertIs(freeze["additionalProperties"], False)
        parsed = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
        })
        for key, value in parsed["freeze"].items():
            with self.subTest(key=key):
                self.assertEqual(freeze["properties"][key]["default"], value)


if __name__ == "__main__":
    unittest.main()
