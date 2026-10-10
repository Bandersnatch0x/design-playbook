"""Source-text contracts for the preview control shell.

These assert on the shipped ``control.css`` text and on the control HTML the
server builds. Neither has a runtime equivalent, so the checks need no browser
and run in the no-chromium CI job instead of the browser-marked regression
module.
"""
import re
from pathlib import Path

PREVIEW = Path(__file__).resolve().parents[2] / "mcp" / "preview"
CSS = (PREVIEW / "control.css").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    assert match, selector
    return match.group(1)


# The pending class, the count and the badge class are asserted at runtime in
# test_visual_ui_regressions.test_rendered_editor_state_changes; grepping the
# shipped JS for the lines that set them only proved the text still existed.
# These keep the rule half, which has no runtime equivalent.
def test_pending_tab_uses_batch_count_and_accent() -> None:
    style = rule(".dpb-rail-tab.is-pending .dpb-filter-n")
    assert "color: var(--dpb-accent)" in style
    assert "font-weight: 700" in style


def test_webmcp_badge_activates_success_style() -> None:
    assert "color: var(--dpb-success)" in rule(".dpb-react-badge.is-on")


def test_computed_fields_clip_long_values_and_use_readable_labels() -> None:
    assert "font-size: 11px" in rule(".dpb-react-field")
    style = rule(".dpb-react-field input")
    assert "overflow: hidden" in style
    assert "text-overflow: ellipsis" in style


def test_popover_scrolls_within_viewport() -> None:
    style = rule(".dpb-anno-popover")
    assert "max-height: calc(100vh - 24px)" in style
    assert "overflow-y: auto" in style


def test_criteria_chip_does_not_repeat_the_tab_label() -> None:
    """The count chip sits beside the "验收准判" label, so it carries numbers only."""
    from design_playbook.mcp.preview import i18n
    from design_playbook.mcp.preview.control import _build_control

    for locale in (i18n.ZH, i18n.EN):
        assert i18n._STRINGS[locale]["criteria_count"] == "{checked}/{total}"

    html = _build_control(
        1, "criteria chip", ["Confirm"],
        criteria=[{"id": "AC-1", "title": "Title", "then": "Visible"}],
    )
    short = i18n.t("criteria_title_short")
    assert short in html
    assert "0/1" in html
    # "<short> <short> 0/1" is the defect this pins.
    assert f"{short}</span> <span class=\"dpb-filter-n\" id=\"dpb-criteria-count\">{short}" not in html


def test_next_step_copy_names_the_decision_not_the_feedback_only() -> None:
    """Visual edits ride along with the round decision, so the copy must say so.

    Pending visual edits alone do not satisfy the ADR-0008 floor, so the muted
    approve label still asks for a note or an annotation - and stays short,
    because the 768px header test owns that budget. The ride-along fact and the
    submit shortcut ride in the always-visible tooltip and the rendered
    visual-panel help instead.
    """
    from design_playbook.mcp.preview import i18n

    zh, en = i18n._STRINGS[i18n.ZH], i18n._STRINGS[i18n.EN]
    # The visual-panel help is rendered (`dpb-react-help`) and names the action.
    for table in (zh, en):
        assert "Ctrl" in table["visual_help"]
        assert "⌘" in table["visual_help"]
    # The approve tooltip is always reachable and states that pending edits
    # travel along with the decision, in both locales.
    assert "视觉修改" in zh["confirm_desc"]
    assert "一并提交" in zh["confirm_desc"]
    assert "visual edit" in en["confirm_desc"].lower()
    assert "ride along" in en["confirm_desc"].lower()


# A CSS-wide keyword is not a valid value inside the `font` shorthand, so a
# declaration like `font: 500 12px/1 inherit` is dropped whole and the control
# falls back to the browser's own control font. Controls inherit the shell font
# through one reset and size themselves with longhands.
FONT_SHORTHAND = re.compile(r"(?<![-\w])font\s*:\s*([^;}]+)")


def test_font_shorthand_never_carries_a_css_wide_keyword() -> None:
    bad = [
        value.strip()
        for value in FONT_SHORTHAND.findall(CSS)
        if value.strip() != "inherit"
        and re.search(r"\b(inherit|initial|unset|revert)\b", value)
    ]
    assert bad == []


def test_form_controls_inherit_the_shell_font() -> None:
    # Zero specificity, so every longhand on a control class still wins.
    reset = ":where(#dpb-root, #dpb-float-root) :where(button, input, textarea, select)"
    assert "font: inherit" in rule(reset)


# Focus indicators are drawn with one solid token. A translucent ring tint
# disappears on light surfaces, so `--dpb-ring-*` stays a decoration token.
FOCUS_RULE = re.compile(r"([^{}]*:focus[^{}]*)\{([^}]*)\}")


def test_focus_outlines_use_the_solid_focus_token() -> None:
    outlines = [
        (sel.strip(), decl.strip())
        for sel, body in FOCUS_RULE.findall(CSS)
        for decl in re.findall(r"outline\s*:[^;]*", body)
    ]
    assert outlines
    assert [o for o in outlines if "2px solid var(--dpb-focus)" not in o[1]] == []


def test_focus_token_is_opaque_in_both_themes() -> None:
    values = re.findall(r"--dpb-focus\s*:\s*([^;]+);", CSS)
    assert values and all(v.strip() == "var(--dpb-accent)" for v in values)
    for accent in re.findall(r"--dpb-accent\s*:\s*([^;]+);", CSS):
        assert "rgba" not in accent and "/" not in accent


def test_suppressed_outlines_fall_back_to_the_shell_focus_rule() -> None:
    shell = rule(
        ":is(#dpb-root, #dpb-float-root) "
        ":is(button, input, textarea, select, a[href], [tabindex]):focus-visible"
    )
    assert "outline: 2px solid var(--dpb-focus)" in shell


REVIEW_JS = (PREVIEW / "control.review.js").read_text(encoding="utf-8")
HTML = (PREVIEW / "control.html").read_text(encoding="utf-8")


# The runtime half (the key opens the popover, focus lands on "keep
# reviewing", Esc closes it without a decision) is S21 and
# test_shift_escape_asks_before_skipping. This keeps the branch itself from
# regaining a direct submit while the browser job is unavailable.
def test_shift_escape_opens_the_skip_confirmation_without_submitting() -> None:
    start = REVIEW_JS.index('if (e.shiftKey && e.key === "Escape") {')
    branch = REVIEW_JS[start:REVIEW_JS.index("return;", start)]
    assert "showSkipPopover()" in branch
    assert "requestSubmit" not in branch


def test_skip_confirmation_defaults_to_keep_reviewing() -> None:
    popover = HTML[HTML.index('id="dpb-skip-popover"'):]
    popover = popover[:popover.index("</div>\n        </div>")]
    assert popover.index('id="dpb-skip-cancel"') < popover.index('id="dpb-skip-confirm"')
    assert 'type="button" class="dpb-btn dpb-btn-quiet" id="dpb-skip-cancel"' in popover
    assert 'type="submit" name="choice" value="{skip_val}"' in popover
    show = REVIEW_JS[REVIEW_JS.index("function showSkipPopover()"):]
    assert "skipCancel.focus()" in show[:show.index("\n  }\n")]


# Implicit submission picks the form's first submit button. A disabled one in
# that slot means Return in any text field submits nothing. The runtime half
# (no POST /decide after Return in an anchor note) is a browser case.
def test_form_opens_with_a_disabled_default_submit() -> None:
    form = HTML[HTML.index('<form method="POST" action="/decide"'):]
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'type="submit"' in first
    for attr in ("disabled", "hidden", 'aria-hidden="true"', 'tabindex="-1"'):
        assert attr in first
    assert 'name="choice"' not in first


def test_return_in_an_anchor_note_blurs_instead_of_submitting() -> None:
    start = REVIEW_JS.index('listEl.addEventListener("keydown"')
    handler = REVIEW_JS[start:REVIEW_JS.index("});", start)]
    assert 'e.key !== "Enter"' in handler
    assert "e.preventDefault()" in handler and "input.blur()" in handler


# Shell copy and comments describe behavior in the project's own words; a
# vendor or an outside publication is never named there. Font stacks in CSS
# are fallback lists, not copy, so they are out of scope.
EXTERNAL_NAMES = re.compile(r"apple|\bHIG\b|refactoring ui|human interface", re.I)


def _comments_and_strings(text: str) -> list[str]:
    parts = re.findall(r"<!--(.*?)-->", text, re.S)
    parts += re.findall(r"/\*(.*?)\*/", text, re.S)
    parts += re.findall(r"//([^\n]*)", text)
    parts += re.findall(r'"([^"\n]*)"', text)
    return parts


def test_shell_copy_and_comments_name_no_external_product() -> None:
    hits = []
    for name in ("control.html", "control.css", "control.js", "control.review.js",
                 "control.react.js", "i18n.py"):
        for part in _comments_and_strings((PREVIEW / name).read_text(encoding="utf-8")):
            if EXTERNAL_NAMES.search(part) and "font-family" not in part:
                hits.append((name, part.strip()[:80]))
    assert hits == []


def test_font_family_dropdown_lists_generic_families_only() -> None:
    react = (PREVIEW / "control.react.js").read_text(encoding="utf-8")
    start = react.index("var fontFamilyOpts = [")
    opts = re.findall(r'"([^"]*)"', react[start:react.index("];", start)])
    generic = {"", "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
               "ui-rounded", "sans-serif", "serif", "monospace"}
    assert set(opts) <= generic


# Chord glyphs depend on the reviewer's keyboard, so the template names the
# chord and the shell draws it. Single-letter tool keys stay literal.
def test_template_carries_no_hard_coded_chord_glyphs() -> None:
    caps = re.findall(r"<kbd([^>]*)>(.*?)</kbd>", HTML, re.S)
    drawn = [text for attrs, text in caps if "data-kbd" not in attrs]
    assert [t for t in drawn if re.search(r"⌘|⇧|↵|Ctrl|Esc|Del", t)] == []
    names = {re.search(r'data-kbd="([^"]+)"', attrs).group(1)
             for attrs, _ in caps if "data-kbd" in attrs}
    for table in ("KEYCAPS_COMMAND", "KEYCAPS_CTRL"):
        start = REVIEW_JS.index(f"var {table} = {{")
        body = REVIEW_JS[start:REVIEW_JS.index("};", start)]
        assert names <= set(re.findall(r"(\w+):", body))


def test_italic_button_is_styled_by_action_not_by_its_english_label() -> None:
    assert 'aria-label="Italic"' not in CSS
    assert '.dpb-compact-text-toolbar button[data-action="italic"]' in CSS
    react = (PREVIEW / "control.react.js").read_text(encoding="utf-8")
    assert '"data-action": action[4]' in react
