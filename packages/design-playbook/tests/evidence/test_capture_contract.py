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

The seam between the provider schema and the parser is the shared module
constants, not a second mirror implementation. That is not enough on its own:
one accepted/rejected corpus is pushed through all four readers (parser,
advertised input schema, snapshot validator, manifest schema) in
``DesignBindingCorpusTests``, so a field whose *acceptance* drifts between
layers fails here even when each layer is internally consistent.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp._schema import violations  # noqa: E402
from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    CAPTURE_SCHEMA_VERSION,
    COLOR_SCHEMES,
    DESIGN_AXES,
    MIN_VIEWPORT_DPR,
    RECAPTURE_HINT,
    capture_contract_schema_fragment,
    parse_capture_contract,
    validate_capture_snapshot,
)
from design_playbook.mcp.evidence.manifest_schema import (  # noqa: E402
    validate_manifest_entry,
)
from design_playbook.mcp.evidence.page_defects import (  # noqa: E402
    probe_render_tokens,
)
from design_playbook.mcp.evidence.server import _tool_schema  # noqa: E402
from design_playbook.scripts.evidence_manifest import (  # noqa: E402
    ManifestAppendError,
    append_entry,
)

_FULL_VIEWPORT = {
    "width": 1280,
    "height": 800,
    "devicePixelRatio": 1.0,
    "colorScheme": "light",
}

# The same declaration shape the render-token fixtures are bound to.
_DESIGN = {
    "fontSizes": [14, 16, 20, 24],
    "colors": ["#1a1a1a", "#ffffff"],
    "radii": [4, 8, 12, 20],
}
_FULL_FREEZE = {"enabled": True, "waitFonts": True, "networkIdle": False}


class _Absent:
    """Corpus marker: the ``design`` key is not present at all."""


_ABSENT = _Absent()


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

    def test_design_absent_is_the_only_unbound_shape(self) -> None:
        # Absence of the key is the one way to say "no binding".
        self.assertNotIn("design", parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
        }))
        # An explicit null is a present-but-unreadable binding: rejected, not
        # read as unbound.
        with self.assertRaises(ValueError) as ctx:
            parse_capture_contract({
                "schemaVersion": 1,
                "viewport": dict(_FULL_VIEWPORT),
                "design": None,
            })
        self.assertIn("design must be an object", str(ctx.exception))

    def test_declared_axes_are_echoed_as_array_literals(self) -> None:
        parsed = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
            "design": _DESIGN,
        })
        self.assertEqual(parsed["design"], _DESIGN)
        self.assertIsNot(parsed["design"]["radii"], _DESIGN["radii"])
        # A partial declaration carries only the axes the caller declared, so
        # the probe reports the rest undecidable rather than reading a default.
        partial = parse_capture_contract({
            "schemaVersion": 1,
            "viewport": dict(_FULL_VIEWPORT),
            "design": {"radii": [12]},
        })
        self.assertEqual(partial["design"], {"radii": [12]})

    def test_malformed_design_fails_the_capture_closed(self) -> None:
        cases = [
            ("always", "design must be an object"),
            (None, "design must be an object"),
            ([16], "design must be an object"),
            ({"spacing": [8]}, "design.spacing is not a declared token axis"),
            ({"fontSizes": 16}, "design.fontSizes must be an array of literals"),
            ({"fontSizes": "16px"}, "design.fontSizes must be an array"),
            ({"colors": {"text": "#000"}}, "design.colors must be an array"),
            ({"radii": None}, "design.radii must be an array of literals"),
        ]
        for design, expected in cases:
            with self.subTest(design=design):
                with self.assertRaises(ValueError) as ctx:
                    parse_capture_contract({
                        "schemaVersion": 1,
                        "viewport": dict(_FULL_VIEWPORT),
                        "design": design,
                    })
                self.assertIn(expected, str(ctx.exception))


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

    def test_optional_design_binding_reads_back_or_fails_closed(self) -> None:
        self.assertEqual(validate_capture_snapshot(_full_request()), [])
        self.assertEqual(
            validate_capture_snapshot(_full_request(design=_DESIGN)),
            [],
        )
        # Provider-echoed parse output must always validate, declaration
        # included (one directional seam pin; no lockstep mirror).
        self.assertEqual(
            validate_capture_snapshot(parse_capture_contract({
                "schemaVersion": 1,
                "viewport": dict(_FULL_VIEWPORT),
                "design": _DESIGN,
            })),
            [],
        )
        for design in ("always", None, [16], {"spacing": [8]}, {"colors": 7},
                       {"fontSizes": {"px": 16}}):
            with self.subTest(design=design):
                facts = validate_capture_snapshot(_full_request(design=design))
                self.assertEqual(facts[0].code, "bad_design_shape")


class CaptureContractSchemaFragmentTests(unittest.TestCase):
    """JSON Schema fragment: const/enum/required shared with the parser."""

    def test_fragment_is_composable_object(self) -> None:
        fragment = capture_contract_schema_fragment()
        self.assertIn("properties", fragment)
        self.assertIn("required", fragment)
        self.assertEqual(set(fragment["required"]), {"schemaVersion", "viewport"})
        self.assertEqual(
            set(fragment["properties"]),
            {"schemaVersion", "viewport", "freeze", "design"},
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

    def test_design_axes_in_schema_match_parser_constants(self) -> None:
        design = capture_contract_schema_fragment()["properties"]["design"]
        self.assertEqual(design["type"], "object")
        self.assertIs(design["additionalProperties"], False)
        self.assertEqual(set(design["properties"]), set(DESIGN_AXES))
        for axis, schema in design["properties"].items():
            with self.subTest(axis=axis):
                self.assertEqual(schema["type"], "array")
        # Optional, like freeze's defaults: the request is valid without it.
        self.assertNotIn("design", capture_contract_schema_fragment()["required"])

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


def _corpus_args(design: object) -> dict[str, Any]:
    """A complete capture call carrying one corpus ``design`` value."""
    args: dict[str, Any] = {
        "schemaVersion": 1,
        "url": "about:blank",
        "type": "screenshot",
        "state": "ok",
        "actions": [],
        "artifact_path": "evidence/x.png",
        "viewport": dict(_FULL_VIEWPORT),
    }
    if design is not _ABSENT:
        args["design"] = design
    return args


def _corpus_snapshot(design: object) -> dict[str, Any]:
    """A complete request snapshot carrying one corpus ``design`` value."""
    snapshot: dict[str, Any] = {
        "schemaVersion": 1,
        "viewport": dict(_FULL_VIEWPORT),
        "freeze": dict(_FULL_FREEZE),
    }
    if design is not _ABSENT:
        snapshot["design"] = design
    return snapshot


def _appended_entry(request: dict[str, Any]) -> dict[str, Any]:
    """Write one real manifest line for ``request`` and read it back."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "evidence").mkdir()
        (run_dir / "evidence" / "capture.png").write_bytes(b"png-bytes")
        append_entry(
            run_dir,
            criterion="L6.1",
            artifact="capture.png",
            request=request,
            source="decision-1",
            observed_state="ok",
            result="captured",
            error="",
            method="runtime-observation",
            observation="the button rendered",
            scope="one run",
        )
        line = (run_dir / "evidence" / "manifest.jsonl").read_text(encoding="utf-8")
    return json.loads(line)


# One accept/reject corpus. ``True`` = every layer must accept the value,
# ``False`` = every layer must reject it. An array whose *items* are unreadable
# literals is still a readable declaration: the boundary does not type the
# items, so a token reference stays a probe fact instead of a caller error.
_DESIGN_CORPUS: tuple[tuple[str, object, bool], ...] = (
    ("omitted key", _ABSENT, True),
    ("empty object declares nothing", {}, True),
    ("legal three axes", _DESIGN, True),
    ("one axis only", {"radii": [4, 8]}, True),
    ("unreadable literals in an array", {"fontSizes": ["var(--x)", "1rem"]}, True),
    ("non-literal nested in an array", {"fontSizes": [{"px": 16}]}, True),
    ("explicit null", None, False),
    ("scalar axis", {"fontSizes": 16}, False),
    ("string axis", {"radii": "12px"}, False),
    ("name->literal object axis", {"colors": {"text": "#000"}}, False),
    ("object nested where an array belongs", {"fontSizes": {"px": [16]}}, False),
    ("unknown axis", {"spacing": [8]}, False),
    ("non-object binding", ["#000"], False),
    ("one good axis beside a scalar", {"fontSizes": [16], "colors": 7}, False),
)


class DesignBindingCorpusTests(unittest.TestCase):
    """One corpus, four readers: parser, inputSchema, snapshot, manifest."""

    def test_every_layer_agrees_on_the_same_corpus(self) -> None:
        input_schema = _tool_schema()["inputSchema"]
        # A valid written entry, to mutate into the rejected shapes below.
        valid_entry = _appended_entry(_corpus_snapshot(_DESIGN))

        for name, design, accepted in _DESIGN_CORPUS:
            with self.subTest(design=name):
                args = _corpus_args(design)

                # 1. Parser (write authority).
                try:
                    parsed = parse_capture_contract(args)
                except ValueError as exc:
                    self.assertFalse(accepted, f"parser rejected a legal {name}: {exc}")
                    parsed = None
                else:
                    self.assertTrue(accepted, f"parser accepted an illegal {name}")

                # 2. Advertised tool input schema.
                schema_violations = violations(args, input_schema)
                self.assertEqual(
                    schema_violations == [], accepted,
                    f"inputSchema disagrees on {name}: {schema_violations}",
                )

                # 3. Snapshot validator (read authority: empty = valid).
                facts = validate_capture_snapshot(_corpus_snapshot(design))
                self.assertEqual(
                    facts == [], accepted,
                    f"snapshot reader disagrees on {name}: {[f.code for f in facts]}",
                )

                # 4. Manifest layer: the real writer refuses a snapshot the
                #    read side rejects, and the schema rejects it on read-back.
                broken = json.loads(json.dumps(valid_entry))
                if design is _ABSENT:
                    broken["request"].pop("design", None)
                else:
                    broken["request"]["design"] = design
                entry_violations = validate_manifest_entry(broken)
                self.assertEqual(
                    entry_violations == [], accepted,
                    f"manifest schema disagrees on {name}: {entry_violations}",
                )
                if accepted:
                    # The bound snapshot is what the manifest records, and the
                    # writer takes it verbatim.
                    assert parsed is not None
                    written = _appended_entry(parsed)
                    self.assertEqual(validate_manifest_entry(written), [])
                    self.assertEqual(
                        written["request"].get("design"),
                        parsed.get("design"),
                    )
                else:
                    with self.assertRaises(ManifestAppendError):
                        _appended_entry(_corpus_snapshot(design))

    def test_unreadable_literals_stay_undecidable_not_clean(self) -> None:
        # The boundary accepts these arrays; the probe must then refuse to call
        # the page clean for an axis it could not read.
        def clean_page(_js: str) -> dict[str, Any]:
            return {"findings": [], "undecidable": [], "distinctFontSizes": [16.0]}

        for design, axes in (
            ({"fontSizes": ["var(--x)", "1rem"]}, {"font-size", "radius", "color"}),
            ({"fontSizes": [{"px": 16}]}, {"font-size", "radius", "color"}),
            ({}, {"font-size", "radius", "color"}),
        ):
            with self.subTest(design=design):
                facts = probe_render_tokens(clean_page, design)
                self.assertEqual(facts.findings, ())
                self.assertEqual(facts.measurement_status, "measured")
                self.assertEqual({note["axis"] for note in facts.undecidable}, axes)


if __name__ == "__main__":
    unittest.main()
