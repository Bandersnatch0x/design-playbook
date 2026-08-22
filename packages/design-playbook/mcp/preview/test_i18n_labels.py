#!/usr/bin/env python3
"""Label-set contract tests for the preview control i18n seam (ADR-0008)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview import control as preview_control  # noqa: E402
from design_playbook.mcp.preview import i18n  # noqa: E402


class LabelSetTests(unittest.TestCase):
    def test_skip_labels_are_disjoint_from_confirm_labels(self) -> None:
        # A skip is an explicit non-confirm disposition (ADR-0008 amendment):
        # it must never be recognised as a confirm.
        self.assertFalse(i18n.SKIP_LABELS & i18n.CONFIRM_LABELS)

    def test_pass_remains_a_confirm_and_is_not_a_skip(self) -> None:
        self.assertIn("pass", i18n.CONFIRM_LABELS)
        self.assertNotIn("pass", i18n.SKIP_LABELS)

    def test_locale_skip_labels_are_in_the_skip_set(self) -> None:
        for locale in (i18n.ZH, i18n.EN):
            self.assertIn(i18n._STRINGS[locale]["skip"], i18n.SKIP_LABELS)

    def test_new_drawer_keys_exist_in_every_locale(self) -> None:
        for key in (
            "skip",
            "skip_desc",
            "zoom_fit",
            "draw_toggle",
            "draw_on",
            "draw_label",
            "drawer_title",
            "drawer_empty_title",
            "drawer_empty_desc",
        ):
            for locale in (i18n.ZH, i18n.EN):
                value = i18n._STRINGS[locale].get(key)
                self.assertTrue(
                    value and value.strip(), f"{key} missing in {locale}"
                )

    def test_control_page_renders_skip_button_with_locale_label(self) -> None:
        html = preview_control._build_control(
            round_n=1, summary="评审", options=["确认通过", "需要修改"]
        )
        self.assertIn('id="dpb-skip"', html)
        self.assertIn(i18n._STRINGS[i18n.ZH]["skip"], html)

    def test_control_page_renders_pill_skip_and_topbar(self) -> None:
        # fixes-matrix #01/#04: skip lives in the pill; the 48px topbar hosts
        # pin mode + zoom controls and starts hidden.
        html = preview_control._build_control(
            round_n=1, summary="评审", options=["确认通过", "需要修改"]
        )
        self.assertIn('id="dpb-pill-skip"', html)
        self.assertIn('id="dpb-topbar" hidden', html)
        self.assertIn('id="dpb-zoom-fit"', html)
        self.assertIn('id="dpb-pin-toggle"', html)
        self.assertIn('id="dpb-draw-toggle"', html)
        # drawer skip stays hidden - the pill owns the skip channel
        self.assertIn('class="dpb-btn dpb-hidden" id="dpb-skip"', html)


if __name__ == "__main__":
    unittest.main()
