"""U-07: one shared token file feeds the Preview shell and the Run Console.

The palette, type, radius and motion tokens live in ``mcp/_shared/tokens.css``.
Preview inlines it ahead of ``control.css``; the Run Console serves it as its
own same-origin stylesheet. Neither surface keeps a private ``--dpb-*`` block,
the light theme defines every token the dark theme defines (the hover and
overlay layers included), and the two dark blocks (system preference and
explicit choice) carry the same values.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_PKG_ROOT / "scripts"))

from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.run_console.ui import UIResources  # noqa: E402
import self_audit  # noqa: E402

MCP = _PKG_ROOT / "mcp"
TOKENS = MCP / "_shared" / "tokens.css"
SURFACE_SHEETS = (MCP / "preview" / "control.css", MCP / "run_console" / "app.css")
_DEF = re.compile(r"(--dpb-[\w-]+)\s*:")


def _token_blocks() -> list[tuple[str, str, dict[str, str]]]:
    css = TOKENS.read_text(encoding="utf-8")
    out = []
    for context, selector, body in self_audit._blocks(css):  # noqa: SLF001
        props = {k: v.strip() for k, v in self_audit._PROP.findall(body)}  # noqa: SLF001
        if props and not selector.startswith("@"):
            out.append((context, selector, props))
    return out


class SharedTokenFileTest(unittest.TestCase):
    def test_shared_token_file_ships_beside_the_surfaces(self) -> None:
        self.assertTrue(TOKENS.is_file(), TOKENS)

    def test_surfaces_keep_no_private_palette(self) -> None:
        for sheet in SURFACE_SHEETS:
            with self.subTest(sheet=sheet.name):
                self.assertEqual(_DEF.findall(sheet.read_text(encoding="utf-8")), [])

    def test_light_theme_defines_every_dark_token(self) -> None:
        light: set[str] = set()
        dark: set[str] = set()
        for context, selector, props in _token_blocks():
            target = dark if "dark" in selector or "dark" in context else light
            target.update(props)
        self.assertIn("--dpb-elev-hover", light)
        self.assertIn("--dpb-overlay", light)
        self.assertNotIn("--dpb-line-active", light | dark)
        self.assertEqual(sorted(dark - light), [])

    def test_system_and_explicit_dark_blocks_match(self) -> None:
        darks = [props for context, selector, props in _token_blocks()
                 if "dark" in selector or "dark" in context]
        self.assertEqual(len(darks), 2)
        self.assertEqual(darks[0], darks[1])


WORKBENCH_CSS = (_PKG_ROOT.parent / "design-playbook-workbench" / "design_playbook_workbench"
                 / "web" / "app.css")
LITERAL_SHEETS = (MCP / "preview" / "control.css", MCP / "run_console" / "app.css", WORKBENCH_CSS)


class LiteralValueTest(unittest.TestCase):
    """G-6: colour, millisecond and easing literals live only in tokens.css."""

    def test_surface_sheets_hold_no_literal_values(self) -> None:
        for sheet in LITERAL_SHEETS:
            with self.subTest(sheet=sheet.name):
                found = self_audit.literal_values(sheet.read_text(encoding="utf-8"))
                self.assertEqual(found, [])

    def test_literal_scanner_sees_each_kind_and_ignores_comments(self) -> None:
        css = ("/* #123456 400ms */ a{color:#abc;background:rgba(0,0,0,.1);"
               "transition:x 120ms cubic-bezier(0,0,1,1);border-color:rgb(1 2 3)}")
        self.assertEqual(self_audit.literal_values(css),
                         ["#abc", "rgba(0,0,0,.1)", "120ms", "cubic-bezier(0,0,1,1)", "rgb(1 2 3)"])
        self.assertEqual(self_audit.literal_values("a{color:var(--dpb-ink);width:#id;animation:x 1s}"), [])

    def test_tokens_carry_the_motion_and_canvas_values_the_surfaces_read(self) -> None:
        light: set[str] = set()
        for context, selector, props in _token_blocks():
            if not ("dark" in selector or "dark" in context):
                light.update(props)
        for name in ("--dpb-duration-press", "--dpb-duration-base", "--dpb-duration-settle",
                     "--dpb-duration-enter", "--dpb-duration-slow", "--dpb-duration-emphasis",
                     "--dpb-duration-flash", "--dpb-duration-instant",
                     "--dpb-canvas-grid-1", "--dpb-canvas-node-bg", "--dpb-canvas-node-line",
                     "--dpb-shadow-hairline", "--dpb-shadow-canvas"):
            self.assertIn(name, light)


class FontNameTest(unittest.TestCase):
    """G-7: vendor font names appear only in the three font tokens."""

    def test_font_tokens_hold_the_vendor_names(self) -> None:
        light: dict[str, str] = {}
        for context, selector, props in _token_blocks():
            if not ("dark" in selector or "dark" in context):
                light.update(props)
        for name in ("--dpb-font-ui", "--dpb-font-cn", "--dpb-font-mono"):
            self.assertIn(name, light)
        self.assertIn("Microsoft YaHei", light["--dpb-font-cn"])
        self.assertIn("PingFang SC", light["--dpb-font-cn"])
        self.assertIn("JetBrains Mono", light["--dpb-font-mono"])

    def test_surface_sheets_name_no_vendor_font(self) -> None:
        for sheet in LITERAL_SHEETS:
            with self.subTest(sheet=sheet.name):
                found = self_audit.vendor_fonts(sheet.read_text(encoding="utf-8"))
                self.assertEqual(found, [])

    def test_injected_css_names_no_vendor_font(self) -> None:
        css = self_audit.bridge_css((MCP / "preview" / "pin_bridge.js").read_text(encoding="utf-8"))
        self.assertEqual(self_audit.vendor_fonts(css), [])

    def test_scanner_reads_family_and_shorthand_values(self) -> None:
        css = ('a{font-family:var(--dpb-font-ui),sans-serif}'
               'b{font-family:Georgia,"Times New Roman",serif;font:600 var(--dpb-text-xs)/1.2 ui-monospace,"JetBrains Mono",Consolas,monospace}'
               'c{font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}'
               'd{font:inherit}e{font:italic 12px Menlo}f{font-family:inherit}')
        self.assertEqual(self_audit.vendor_fonts(css),
                         ["Georgia", '"Times New Roman"', '"JetBrains Mono"', "Consolas",
                          "-apple-system", '"Segoe UI"', "Menlo"])


WORKBENCH_TOKENS = (_PKG_ROOT.parent / "design-playbook-workbench" / "design_playbook_workbench"
                    / "web" / "tokens.css")


class ContrastPreferenceTest(unittest.TestCase):
    """U-02: increased-contrast and forced-colors branches, and the table behind G-3."""

    css = TOKENS.read_text(encoding="utf-8")

    def _media(self, query: str) -> list[dict[str, str]]:
        out = []
        for context, selector, body in self_audit._blocks(self.css):  # noqa: SLF001
            if query in context:
                out.append({k: v.strip() for k, v in self_audit._PROP.findall(body)})  # noqa: SLF001
        return out

    def test_increased_contrast_block_raises_ink_roles_and_lines(self) -> None:
        blocks = self._media("prefers-contrast: more")
        self.assertEqual(len(blocks), 1)
        more = blocks[0]
        for name in ("--dpb-muted", "--dpb-soft", "--dpb-line", "--dpb-line-strong"):
            self.assertEqual(more.get(name), "var(--dpb-ink)", name)
        self.assertEqual(more.get("--dpb-focus-width"), "3px")

    def test_increased_contrast_block_outranks_the_dark_blocks(self) -> None:
        # Same-element specificity: the dark blocks are at most (1,1,0), so the
        # override selector has to reach an id plus an attribute-level piece.
        selectors = [sel for context, sel, _ in self_audit._blocks(self.css)  # noqa: SLF001
                     if "prefers-contrast: more" in context]
        self.assertEqual(len(selectors), 1)
        self.assertIn("#dpb-root", selectors[0])
        self.assertIn("[data-theme]", selectors[0])
        self.assertLess(self.css.index("@media (prefers-color-scheme: dark)"),
                        self.css.index("@media (prefers-contrast: more)"))
        self.assertLess(self.css.rindex('[data-theme="dark"]'),
                        self.css.index("@media (prefers-contrast: more)"))

    def test_forced_colors_block_hands_focus_to_the_system_colour(self) -> None:
        blocks = self._media("forced-colors: active")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].get("--dpb-focus"), "Highlight")

    def test_focus_width_token_and_native_control_accent(self) -> None:
        self.assertIn("--dpb-focus-width: 2px;", self.css)
        self.assertIn("accent-color: var(--dpb-accent);", self.css)

    def test_appearance_tokens_expose_the_increased_contrast_appearances(self) -> None:
        tokens = self_audit.appearance_tokens(self.css)
        self.assertEqual(sorted(tokens), ["dark", "dark-more", "light", "light-more"])
        for appearance in ("light-more", "dark-more"):
            self.assertEqual(tokens[appearance]["--dpb-muted"], tokens[appearance]["--dpb-ink"])
            self.assertEqual(tokens[appearance]["--dpb-focus-width"], "3px")
        self.assertEqual(tokens["light"]["--dpb-focus-width"], "2px")
        self.assertNotEqual(tokens["dark"]["--dpb-muted"], tokens["dark"]["--dpb-ink"])
        self.assertNotEqual(tokens["light"]["--dpb-focus"], "Highlight")

    def test_contrast_table_covers_every_layer_in_every_appearance(self) -> None:
        ledger = self_audit.load_ledger(
            _PKG_ROOT / "examples" / "self-audit" / "baseline.json")
        floors = {"text-contrast": 4.5, "nontext-contrast": 3.0, "text-min": 12.0}
        self.assertEqual(self_audit.audit(_PKG_ROOT.parent.parent, ledger, floors), [])
        text_pairs = {tuple(pair) for pair in ledger["text_pairs"]}
        for text in ("--dpb-ink", "--dpb-soft", "--dpb-muted", "--dpb-accent-text",
                     "--dpb-danger", "--dpb-success", "--dpb-tertiary"):
            for layer in ("--dpb-bg", "--dpb-surface", "--dpb-elev",
                          "--dpb-elev-hover", "--dpb-overlay"):
                self.assertIn((text, layer), text_pairs)
        self.assertIn(("--dpb-accent-ink", "--dpb-accent"), text_pairs)
        nontext = {tuple(pair) for pair in ledger["nontext_pairs"]}
        for layer in ("--dpb-elev-hover", "--dpb-overlay"):
            self.assertIn(("--dpb-focus", layer), nontext)

    def test_workbench_loads_the_same_branches(self) -> None:
        self.assertEqual(WORKBENCH_TOKENS.read_bytes(), TOKENS.read_bytes())

    def test_surface_sheets_draw_focus_with_the_width_token(self) -> None:
        for sheet in (*SURFACE_SHEETS, LITERAL_SHEETS[2]):
            text = sheet.read_text(encoding="utf-8")
            with self.subTest(sheet=sheet.name):
                self.assertEqual(re.findall(r"outline\s*:\s*\d+(?:\.\d+)?px solid var\(--(?:dpb-)?focus\)", text), [])


class SurfaceWiringTest(unittest.TestCase):
    def test_preview_inlines_the_shared_tokens_first(self) -> None:
        preview_control._load_resources.cache_clear()  # noqa: SLF001
        css = preview_control._load_resources()[1]  # noqa: SLF001
        self.assertTrue(css.startswith(TOKENS.read_text(encoding="utf-8")))
        self.assertIn((MCP / "preview" / "control.css").read_text(encoding="utf-8"), css)

    def test_run_console_serves_the_shared_tokens(self) -> None:
        resource = UIResources().lookup("/tokens.css")
        assert resource is not None
        self.assertEqual(resource.body, TOKENS.read_bytes())
        self.assertEqual(resource.content_type, "text/css; charset=utf-8")
        self.assertIn("default-src 'none'", resource.content_security_policy)
        html = (MCP / "run_console" / "app.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en" class="dpb-ui">', html)
        self.assertLess(html.index('href="tokens.css"'), html.index('href="app.css"'))


if __name__ == "__main__":
    unittest.main()


BRIDGE_JS = MCP / "preview" / "pin_bridge.js"


class BridgeStyleTest(unittest.TestCase):
    """G-6b: the CSS the bridge injects into the reviewed page reads tokens too.

    The reviewed page does not load tokens.css, so the bridge carries the
    frame tokens from the shared file into a ``:root`` block of its own.
    """

    def test_injected_css_holds_no_literal_values(self) -> None:
        css = self_audit.bridge_css(BRIDGE_JS.read_text(encoding="utf-8"))
        self.assertGreater(len(css), 1000)
        self.assertEqual(self_audit.literal_values(css), [])

    def test_bridge_css_extractor_joins_the_string_pieces(self) -> None:
        js = 'var style = x;\nstyle.textContent =\n  "a{color:" +\n  // note\n  "red}";\nfoo("b{x:y}");'
        self.assertEqual(self_audit.bridge_css(js), "a{color:red}")

    def test_served_bridge_defines_every_token_its_css_reads(self) -> None:
        from design_playbook.mcp.preview import pin_bridge
        script = pin_bridge.BRIDGE_SCRIPT
        self.assertNotIn("__DPB_FRAME_TOKENS__", script)
        css = self_audit.bridge_css(script)
        self.assertIn(":root{", css)
        defined = set(_DEF.findall(css))
        read = set(re.findall(r"var\(\s*(--dpb-[\w-]+)", css))
        self.assertGreater(len(read), 20)
        self.assertEqual(sorted(read - defined), [])

    def test_served_bridge_carries_the_mono_font_token_in_one_string_piece(self) -> None:
        from design_playbook.mcp.preview import pin_bridge
        css = self_audit.bridge_css(pin_bridge.BRIDGE_SCRIPT)
        self.assertRegex(css, r"--dpb-font-mono:ui-monospace, 'Cascadia Mono', 'JetBrains Mono', Consolas, Menlo;")

    def test_frame_tokens_come_from_the_shared_file(self) -> None:
        from design_playbook.mcp.preview import pin_bridge
        css = self_audit.bridge_css(pin_bridge.BRIDGE_SCRIPT)
        shared = TOKENS.read_text(encoding="utf-8")
        for name, value in re.findall(r"(--dpb-frame-[\w-]+)\s*:\s*([^;]+);", css):
            with self.subTest(token=name):
                self.assertIn(f"{name}: {value.strip()};", shared)


class TypeScaleTest(unittest.TestCase):
    """G-8 (U-08): font sizes come from six scale tokens, nothing else."""

    SCALE = {"--dpb-text-2xs": "11px", "--dpb-text-xs": "12px", "--dpb-text-sm": "13px",
             "--dpb-text-md": "15px", "--dpb-text-lg": "17px", "--dpb-text-xl": "22px"}

    def test_tokens_define_the_six_step_scale(self) -> None:
        light: dict[str, str] = {}
        for context, selector, props in _token_blocks():
            if not ("dark" in selector or "dark" in context):
                light.update(props)
        self.assertEqual({k: v for k, v in light.items() if k.startswith("--dpb-text-")}, self.SCALE)

    def test_surface_sheets_read_only_scale_tokens(self) -> None:
        for sheet in LITERAL_SHEETS:
            with self.subTest(sheet=sheet.name):
                self.assertEqual(self_audit.font_size_literals(sheet.read_text(encoding="utf-8")), [])

    def test_injected_css_reads_only_scale_tokens(self) -> None:
        css = self_audit.bridge_css(BRIDGE_JS.read_text(encoding="utf-8"))
        self.assertEqual(self_audit.font_size_literals(css), [])

    def test_scanner_reads_size_and_shorthand_values(self) -> None:
        css = ("a{font-size:var(--dpb-text-sm);font:inherit}b{font-size:inherit}"
               "c{font-size:13.5px}d{font-size:.9rem}e{font-size:0.85em}"
               "f{font:600 12px/1 var(--dpb-font-mono),monospace}"
               "g{font:var(--dpb-text-xs)/1.4 var(--dpb-font-mono),monospace}"
               "h{font:16px/1.55 var(--dpb-font-ui)}i{font-size:clamp(1rem,3vw,2rem)}"
               "j{font:italic 700 var(--dpb-text-lg)/1 serif}k{font-size:larger}")
        self.assertEqual(self_audit.font_size_literals(css),
                         ["13.5px", ".9rem", "0.85em", "12px", "16px", "clamp(1rem,3vw,2rem)", "larger"])

    def test_scale_floors(self) -> None:
        css = ".dpb-ui{--dpb-text-2xs:11px;--dpb-text-xs:12px;--dpb-text-sm:13px;}"
        self.assertEqual(self_audit.type_scale_gaps(css, 11, 12), [])
        low = ".dpb-ui{--dpb-text-2xs:10px;--dpb-text-xs:11px;--dpb-text-sm:13px;}"
        self.assertEqual(self_audit.type_scale_gaps(low, 11, 12),
                         ["--dpb-text-2xs:10px under 11px", "--dpb-text-xs:11px under 12px"])
        self.assertEqual(self_audit.type_scale_gaps(".dpb-ui{--dpb-text-sm:1rem;}", 11, 12),
                         ["--dpb-text-sm:1rem is not a px size"])

    def test_bridge_carries_the_small_size_token(self) -> None:
        from design_playbook.mcp.preview import pin_bridge
        css = self_audit.bridge_css(pin_bridge.BRIDGE_SCRIPT)
        self.assertIn("--dpb-text-2xs:11px;", css)

    def test_body_text_is_the_dense_console_size(self) -> None:
        for sheet in (MCP / "run_console" / "app.css", WORKBENCH_CSS):
            with self.subTest(sheet=sheet.name):
                css = sheet.read_text(encoding="utf-8")
                body = next(b for _, sel, b in self_audit._blocks(css) if sel.strip() == "body")  # noqa: SLF001
                self.assertRegex(body, r"font(?:-size)?:\s*var\(--dpb-text-sm\)")
