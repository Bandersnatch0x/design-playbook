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
