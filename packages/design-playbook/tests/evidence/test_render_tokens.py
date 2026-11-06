#!/usr/bin/env python3
"""Rendered-token probe: parser contract plus a real-browser positive/negative pair.

One declaration binds two pages. ``render-tokens-legal.html`` resolves every
computed value to a declared value and yields no findings.
``render-tokens-deviant.html`` declares only declared tokens and relative
units, so nothing in its source reads as off-scale; only the rendered values
deviate. Both assertions run in the same suite.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.page_defects import (  # noqa: E402
    RENDER_TOKEN_SCHEMA,
    declared_token_axes,
    probe_render_tokens,
    render_token_probe_js,
)

try:
    from playwright.sync_api import sync_playwright  # noqa: E402
except ImportError:  # pragma: no cover - only the browser tests need it
    sync_playwright = None

_FIXTURES = _PKG_ROOT / "mcp" / "evidence" / "fixtures"
DECLARED = {
    "fontSizes": [14, 16, 20, 24],
    "colors": {
        "canvas": "#f5f5f5",
        "surface": "#ffffff",
        "text": "#1a1a1a",
        "primary": "#0b6bcb",
    },
    "radii": [4, 8, 12, 20],
}


class DeclaredAxesTests(unittest.TestCase):
    def test_normalizes_hex_and_px_and_names_unreadable_entries(self) -> None:
        axes, notes = declared_token_axes(
            {
                "fontSizes": [16, "20px", "1rem", "abcpx"],
                "colors": {"text": "#1A1A1A", "surface": "#fff", "bad": "var(--x)"},
                "radii": ["12px"],
            }
        )
        self.assertEqual(axes["fontSizes"], [16.0, 20.0])
        self.assertEqual(
            set(axes["colors"]), {"rgb(26, 26, 26)", "rgb(255, 255, 255)"}
        )
        self.assertEqual(axes["radii"], [12.0])
        reasons = " ".join(note["reason"] for note in notes)
        self.assertIn("'1rem'", reasons)
        self.assertIn("'abcpx'", reasons)
        self.assertIn("'var(--x)'", reasons)

    def test_hostile_declaration_shapes_do_not_raise(self) -> None:
        for declared in ({"fontSizes": {"px": 16}, "colors": 7, "radii": [None]},
                         {"fontSizes": "16px", "colors": "#fff"}):
            with self.subTest(declared=declared):
                axes, notes = declared_token_axes(
                    declared if isinstance(declared, dict) else None
                )
                self.assertIn("fontSizes", axes)
                self.assertTrue(notes)

    def test_absent_declaration_is_undecidable_not_clean(self) -> None:
        axes, notes = declared_token_axes(None)
        self.assertEqual(axes, {"fontSizes": None, "radii": None, "colors": None})
        self.assertEqual(
            {note["axis"] for note in notes}, {"font-size", "radius", "color"}
        )
        facts = probe_render_tokens(
            lambda _js: {"findings": [], "undecidable": [], "distinctFontSizes": []},
            None,
        )
        self.assertEqual(facts.measurement_status, "measured")
        self.assertEqual(facts.findings, ())
        self.assertEqual(len(facts.undecidable), 3)


class ProbeParserTests(unittest.TestCase):
    def test_maps_findings_and_merges_page_notes(self) -> None:
        facts = probe_render_tokens(
            lambda _js: {
                "findings": [
                    {
                        "axis": "radius",
                        "kind": "inner-radius-exceeds-outer",
                        "value": "20",
                        "detail": "outer 12",
                        "count": 2,
                    }
                ],
                "undecidable": [{"axis": "color", "reason": "translucent color"}],
                "distinctFontSizes": [17, 24],
            },
            {},
        )
        self.assertEqual(facts.measurement_status, "measured")
        self.assertEqual(facts.measurement_error, "")
        self.assertEqual(facts.findings[0]["kind"], "inner-radius-exceeds-outer")
        self.assertEqual(facts.findings[0]["count"], 2)
        self.assertEqual(facts.distinct_font_sizes, (17.0, 24.0))
        self.assertIn("translucent color", [n["reason"] for n in facts.undecidable])

    def test_unknown_axis_kind_or_count_blocks(self) -> None:
        rows = (
            {"axis": "spacing", "kind": "off-scale-size", "value": "1",
             "detail": "x", "count": 1},
            {"axis": "color", "kind": "off-scale-size", "value": "#fff",
             "detail": "x", "count": 1},
            {"axis": "color", "kind": "off-palette-color", "value": "#fff",
             "detail": "x", "count": 0},
        )
        for row in rows:
            with self.subTest(row=row):
                facts = probe_render_tokens(
                    lambda _js, row=row: {
                        "findings": [row],
                        "undecidable": [],
                        "distinctFontSizes": [],
                    },
                    {},
                )
                self.assertEqual(facts.measurement_status, "blocked")
                self.assertEqual(facts.findings, ())
                self.assertTrue(facts.measurement_error)

    def test_missing_keys_and_evaluate_error_block_with_notes_intact(self) -> None:
        self.assertEqual(probe_render_tokens(lambda _js: {}, {}).measurement_status,
                         "blocked")
        self.assertEqual(probe_render_tokens(lambda _js: None, {}).measurement_status,
                         "blocked")

        def boom(_js: str) -> None:
            raise RuntimeError("evaluate failed")

        facts = probe_render_tokens(boom, None)
        self.assertEqual(facts.measurement_status, "blocked")
        self.assertIn("evaluate failed", facts.measurement_error)
        self.assertEqual(len(facts.undecidable), 3)

    def test_js_carries_the_declaration_and_no_python_names(self) -> None:
        js = render_token_probe_js(DECLARED)
        self.assertEqual(RENDER_TOKEN_SCHEMA, "page-render-tokens/v1")
        self.assertTrue(js.startswith("() => {"))
        self.assertNotIn("__DECLARED__", js)
        self.assertNotIn("__TOL__", js)
        self.assertIn("rgb(26, 26, 26)", js)
        self.assertNotIn("</script>", js)


def _render(fixture: str) -> tuple[str, object]:
    """Return the fixture source and its facts through real layout."""
    path = _FIXTURES / fixture
    source = path.read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(path.resolve().as_uri(), wait_until="load")
            return source, probe_render_tokens(page.evaluate, DECLARED)
        finally:
            browser.close()


@pytest.mark.browser
@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class RenderedTokenBrowserTests(unittest.TestCase):
    """The positive and negative examples, under one declaration."""

    def test_legal_page_yields_no_findings(self) -> None:
        _source, facts = _render("render-tokens-legal.html")
        self.assertEqual(facts.measurement_status, "measured", facts.measurement_error)
        self.assertEqual(facts.undecidable, ())
        self.assertEqual(facts.findings, ())
        self.assertEqual(facts.distinct_font_sizes, (16.0, 20.0))

    def test_source_legal_page_deviates_only_after_layout(self) -> None:
        source, facts = _render("render-tokens-deviant.html")
        self.assertEqual(facts.measurement_status, "measured", facts.measurement_error)
        # Nothing in the source reads as off-scale: no px outside the token
        # block, no literal rgb, and the two nested radii use declared tokens.
        self.assertNotIn("17px", source)
        self.assertNotIn("rgb(", source)
        for token in ("--font-body: 1rem", "--radius-outer: 12px", "--radius-xl: 20px"):
            self.assertIn(token, source)
        self.assertEqual(facts.undecidable, ())
        self.assertEqual(facts.distinct_font_sizes, (17.0, 24.0))
        found = {(row["axis"], row["kind"], row["value"]) for row in facts.findings}
        self.assertEqual(
            found,
            {
                ("font-size", "off-scale-size", "17"),
                ("color", "off-palette-color", "rgb(0, 0, 238)"),
                ("radius", "inner-radius-not-concentric", "12"),
                ("radius", "inner-radius-exceeds-outer", "20"),
            },
        )


if __name__ == "__main__":
    unittest.main()
