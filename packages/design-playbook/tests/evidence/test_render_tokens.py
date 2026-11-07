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


class LiteralSemanticsTests(unittest.TestCase):
    """A literal that cannot be faithfully compared is undecidable, never clean."""

    def test_non_finite_px_literals_are_rejected_not_scale_entries(self) -> None:
        axes, notes = declared_token_axes(
            {"fontSizes": [16, "20px", "NaNpx", "Infinitypx", "1e309px"]}
        )
        self.assertEqual(axes["fontSizes"], [16.0, 20.0])
        reasons = " ".join(note["reason"] for note in notes)
        for literal in ("NaNpx", "Infinitypx", "1e309px"):
            self.assertIn(repr(literal), reasons)

    def test_numeric_overflow_px_entry_is_rejected_not_raised(self) -> None:
        # int -> float conversion overflows; the entry must come back as
        # undecidable text instead of escaping the normalizer.
        overflow = 10**400
        axes, notes = declared_token_axes({"radii": [8, overflow]})
        self.assertEqual(axes["radii"], [8.0])
        self.assertTrue(
            any(str(overflow) in note["reason"] for note in notes), notes
        )

    def test_probe_js_never_carries_non_finite_numbers(self) -> None:
        # json.dumps emits bare NaN/Infinity, which the browser would run as a
        # scale entry; a rejected literal must not reach the page at all.
        js = render_token_probe_js(
            {"fontSizes": ["NaNpx", "Infinitypx"], "radii": ["1e309px"]}
        )
        self.assertNotIn("NaN", js)
        self.assertNotIn("Infinity", js)

    def test_underscore_and_non_ascii_digits_are_not_css_numbers(self) -> None:
        # float() accepts PEP-515 underscores and Unicode digits; CSS does not.
        axes, notes = declared_token_axes(
            {
                "fontSizes": ["1_6px", "１６px", "16 px", "+ 16px"],
                "colors": ["rgb(2_6,26,26)", "rgb(１２,26,26)"],
            }
        )
        self.assertIsNone(axes["fontSizes"])
        self.assertIsNone(axes["colors"])
        reasons = " ".join(note["reason"] for note in notes)
        for literal in ("1_6px", "１６px", "16 px", "+ 16px",
                        "rgb(2_6,26,26)", "rgb(１２,26,26)"):
            self.assertIn(repr(literal), reasons)

    def test_supported_css_number_forms_are_accepted_completely(self) -> None:
        axes, notes = declared_token_axes(
            {
                "fontSizes": ["+16px", "-0px", ".5px", "1e2px", "16.0px"],
                "colors": ["rgb(+26, 26, 26e0)", "rgb(26 26 26 / 1)"],
            }
        )
        self.assertEqual(axes["fontSizes"], [0.0, 0.5, 16.0, 100.0])
        self.assertEqual(axes["colors"], ["rgb(26, 26, 26)"])
        self.assertEqual([n for n in notes if n["axis"] in ("font-size", "color")], [])

    def test_fractional_color_channels_follow_browser_rounding(self) -> None:
        # The browser serializes a fractional channel by rounding to the
        # nearest integer with ties toward +infinity; Python's round() is
        # banker's rounding and would map 12.5 to 12 where the browser paints 13.
        axes, notes = declared_token_axes(
            {"colors": ["rgb(12.5,12.5,12.5)", "rgb(12.4,0,0)", "rgb(12.6,0,0)"]}
        )
        self.assertEqual(
            axes["colors"],
            ["rgb(12, 0, 0)", "rgb(13, 0, 0)", "rgb(13, 13, 13)"],
        )
        self.assertEqual([n for n in notes if n["axis"] == "color"], [])

    def test_non_css_whitespace_is_not_stripped_from_literals(self) -> None:
        # CSS whitespace is space/tab/LF/CR/form-feed only. NBSP and vertical
        # tab belong to the token, so the whole literal is not a valid number.
        bad = (
            "\u00a016px",
            "16px\u000b",
            "rgb(26\u00a026 26)",
            "rgb(26\u000b26 26)",
            "rgb(26, \u00a026, 26)",
        )
        axes, notes = declared_token_axes(
            {"fontSizes": list(bad[:2]), "colors": list(bad[2:])}
        )
        self.assertIsNone(axes["fontSizes"])
        self.assertIsNone(axes["colors"])
        reasons = " ".join(note["reason"] for note in notes)
        for literal in bad:
            self.assertIn(repr(literal), reasons)

    def test_css_whitespace_forms_are_accepted(self) -> None:
        axes, notes = declared_token_axes(
            {
                "fontSizes": ["\t16px\n", "\r\n20px\f"],
                "colors": ["rgb( 26\t26\r\n26 )", "rgb(26 , 26 , 26)"],
            }
        )
        self.assertEqual(axes["fontSizes"], [16.0, 20.0])
        self.assertEqual(axes["colors"], ["rgb(26, 26, 26)"])
        self.assertEqual(
            [n for n in notes if n["axis"] in ("font-size", "color")], []
        )

    def test_opaque_color_forms_keep_their_computed_key(self) -> None:
        axes, notes = declared_token_axes(
            {
                "colors": [
                    "#1a1a1a",
                    "rgb(26, 26, 26)",
                    "rgb(26 26 26)",
                    "rgba(26, 26, 26, 1)",
                    "rgb(26, 26, 26, 1)",
                    "rgb(26 26 26 / 100%)",
                ]
            }
        )
        self.assertEqual(axes["colors"], ["rgb(26, 26, 26)"])
        self.assertEqual([note for note in notes if note["axis"] == "color"], [])

    def test_unreadable_colors_are_rejected_never_compared_opaque(self) -> None:
        rejected = (
            # Translucent: the painted value composes over what is behind it.
            "rgba(26, 26, 26, 0.5)",
            "rgb(26 26 26 / 10%)",
            # Malformed: extra, missing, or unseparated channels.
            "rgb(26, 26, 26, 1, 1)",
            "rgb(26 26 26 1)",
            "rgb(26, 26)",
            # Non-finite channel: int(round(inf)) used to raise OverflowError.
            "rgb(1e309, 0, 0)",
        )
        axes, notes = declared_token_axes({"colors": ["#ffffff", *rejected]})
        self.assertEqual(axes["colors"], ["rgb(255, 255, 255)"])
        reasons = " ".join(note["reason"] for note in notes)
        for literal in rejected:
            self.assertIn(repr(literal), reasons)


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
class CssGrammarBrowserTests(unittest.TestCase):
    """The browser is the authority on what a literal means; the owner must agree."""

    CASES = (
        ("font-size", "16px", True),
        ("font-size", "1_6px", False),
        ("font-size", "１６px", False),
        ("font-size", "16 px", False),
        ("font-size", "+16px", True),
        ("font-size", ".5px", True),
        ("font-size", "1e2px", True),
        ("color", "rgb(26, 26, 26)", True),
        ("color", "rgb(2_6,26,26)", False),
        ("color", "rgb(12.5,12.5,12.5)", True),
        # CSS whitespace is space/tab/LF/CR/form-feed only.
        ("font-size", "\t16px\n", True),
        ("font-size", "\u00a016px", False),
        ("font-size", "16px\u000b", False),
        ("color", "rgb(26\t26\t26)", True),
        ("color", "rgb(26\u00a026 26)", False),
        ("color", "rgb(26\u000b26 26)", False),
    )

    @staticmethod
    def _owner_accepts(prop: str, value: str) -> bool:
        key = "fontSizes" if prop == "font-size" else "colors"
        axes, _ = declared_token_axes({key: [value]})
        return axes[key] is not None

    def test_owner_acceptance_matches_css_supports(self) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content("<!doctype html><html><body><p id='t'>x</p></body></html>")
                for prop, value, expected in self.CASES:
                    with self.subTest(prop=prop, value=value):
                        browser_answer = page.evaluate(
                            "([p, v]) => CSS.supports(p, v)", [prop, value]
                        )
                        self.assertEqual(browser_answer, expected)
                        self.assertEqual(self._owner_accepts(prop, value), expected)
            finally:
                browser.close()

    def test_fractional_color_key_matches_computed_value(self) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content("<!doctype html><html><body><p id='t'>x</p></body></html>")
                page.evaluate(
                    "() => { document.getElementById('t').style.color ="
                    " 'rgb(12.5,12.5,12.5)'; }"
                )
                computed = page.evaluate(
                    "() => getComputedStyle(document.getElementById('t')).color"
                )
                axes, _ = declared_token_axes({"colors": ["rgb(12.5,12.5,12.5)"]})
                self.assertEqual(computed, "rgb(13, 13, 13)")
                self.assertEqual(axes["colors"], [computed])
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
