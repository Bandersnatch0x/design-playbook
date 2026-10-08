"""Interrupted bridge requests remain editable drafts, not permanent drain blockers."""
import json

import pytest
from playwright.sync_api import expect

from tests.preview.conftest import expand_inspector_section
from tests.preview.test_visual_ui_regressions import editor_page as editor_page


@pytest.mark.parametrize(("disconnect", "lost_message", "edit_source"), [
    ("load", "request", "inspector"),
    ("load", "request", "offline-submit"),
    ("load", "acknowledgment", "inspector"),
    ("heartbeat", "request", "newer-draft"),
    ("heartbeat", "acknowledgment", "inspector"),
    ("load", "request", "tool"),
    ("heartbeat", "acknowledgment", "tool"),
])
def test_disconnect_mid_edit_reconnect_submit_preserves_pending_edits(
    editor_page, disconnect, lost_message, edit_source,
):
    page = editor_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Install before either bridge starts, then drop requests or their acknowledgments.
    page.add_init_script("""
        window.__previewTools = {};
        document.modelContext = {
            registerTool(tool) { window.__previewTools[tool.name] = tool; },
            unregisterTool(name) { delete window.__previewTools[name]; },
        };
        window.__blockReady = false;
        window.__dropRequest = false;
        window.__dropAck = false;
        window.__lostRequest = false;
        window.__lostAck = false;
        window.addEventListener('message', event => {
            if (window.parent === window) {
                const frame = document.querySelector('iframe.dpb-proto-frame');
                if (!frame || event.source !== frame.contentWindow) return;
                if (window.__blockReady && event.data.dpbVisualEditReady) event.stopImmediatePropagation();
                if (window.__dropAck &&
                    (event.data.dpbVisualEditChange || event.data.dpbVisualEditSelection?.requestId)) {
                    window.__lostAck = true;
                    event.stopImmediatePropagation();
                }
            } else if (window.__dropRequest && event.data.dpbVisualEdit?.type === 'set-style') {
                window.__lostRequest = true;
                event.stopImmediatePropagation();
            }
        }, true);
    """)
    page.reload()
    from preview_e2e_helpers import dismiss_onboarding
    dismiss_onboarding(page)
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    if edit_source == "tool":
        target.evaluate("el => { el.style.padding = '9px'; }")
    original_padding = target.evaluate("el => el.style.padding")
    original_width = target.evaluate("el => el.style.width")
    # A load-disconnect reloads the iframe below, so for four of the seven
    # parametrisations these baselines are empty strings and the two assertions
    # at the end cannot distinguish a correct baseline from an empty one. That
    # is structural, not a missing fixture style: the reload re-parses the
    # prototype and the element's inline styles are gone. Recorded rather than
    # papered over with a baseline that does not survive the reload.
    target.evaluate("el => el.click()")
    page.locator("#dpb-tab-visual").click()
    page.locator("#dpb-feedback").fill("Keep the requested spacing and width changes.")
    expand_inspector_section(page, "padding")
    expand_inspector_section(page, "width")
    padding = page.locator('.dpb-react-field[data-property="padding"] input')
    width = page.locator('.dpb-react-field[data-property="width"] input')
    expect(padding).to_be_enabled()

    page.evaluate("""lost => {
        window.__dropAck = lost === 'acknowledgment';
        window.__submissions = [];
        document.getElementById('dpb-decide-form').addEventListener('submit', event => {
            if (!event.defaultPrevented) {
                window.__submissions.push(document.getElementById('dpb-visual-edits-json').value);
            }
            event.preventDefault();
        });
    }""", lost_message)
    target.evaluate("(_, lost) => { window.__dropRequest = lost === 'request'; }", lost_message)
    if edit_source == "tool":
        page.evaluate("""() => {
            window.__previewTools.preview_set_style.execute({property: 'padding', value: '31px'});
        }""")
    else:
        padding.fill("31px")
        padding.press("Enter")
    if lost_message == "request":
        frame = page.locator("iframe.dpb-proto-frame").element_handle().content_frame()
        frame.wait_for_function("window.__lostRequest")
    else:
        page.wait_for_function("window.__lostAck")
        expect(target).to_have_css("padding", "31px")

    expected_padding = "47px" if edit_source == "newer-draft" else "31px"
    if edit_source == "newer-draft":
        padding.fill(expected_padding)

    # A second draft is waiting behind the interrupted request when the bridge disconnects.
    width.fill("333px")
    page.evaluate("""disconnect => {
        window.__blockReady = true;
        if (disconnect === 'load') {
            const frame = document.querySelector('iframe.dpb-proto-frame');
            frame.srcdoc = frame.srcdoc;
        }
    }""", disconnect)
    expect(padding).to_be_disabled()
    expect(padding).to_have_value(expected_padding)
    # The unit renders beside the field now, so the input holds the number.
    expect(width).to_have_value("333")
    if edit_source == "offline-submit":
        page.locator("#dpb-btn-approve").click()
        page.wait_for_function("""() => window.__submissions.length ||
            Object.values(window.DPB_I18N_DUAL.visual_drain_failed).some(text =>
                document.getElementById('dpb-toasts').textContent.includes(text))""")
        assert page.evaluate("window.__submissions") == []
        assert page.evaluate("window.dpbHasPendingVisualEdits()")
        expect(padding).to_have_value(expected_padding)
        expect(width).to_have_value("333")
        # The refusal must be visible. The old assertion here required zero
        # toasts, which contradicted the wait above and the no-submission
        # assertion, so it could not pass through the branch it was testing.
        failure_labels = page.evaluate("Object.values(window.DPB_I18N_DUAL.visual_drain_failed)")
        toast_text = page.locator("#dpb-toasts").text_content()
        assert any(label in toast_text for label in failure_labels), toast_text
        # Clear the toasts so the retry assertion below measures the retry and
        # not this deliberate failure, which would otherwise still be on screen.
        page.evaluate("() => { document.getElementById('dpb-toasts').textContent = ''; }")
    target.evaluate("() => { window.__dropRequest = false; }")
    page.evaluate("() => { window.__dropAck = false; window.__blockReady = false; }")
    expect(padding).to_be_enabled()
    expect(page.locator('.dpb-react-diagnostic')).to_have_attribute("data-stale", "false")

    page.evaluate("""() => {
        document.getElementById('dpb-decide-form').requestSubmit(document.getElementById('dpb-btn-approve'));
    }""")
    page.wait_for_function("""() => window.__submissions.length ||
        Object.values(window.DPB_I18N_DUAL.visual_drain_failed).some(text =>
            document.getElementById('dpb-toasts').textContent.includes(text))""")
    toast = page.locator("#dpb-toasts").text_content()
    failure_labels = page.evaluate("Object.values(window.DPB_I18N_DUAL.visual_drain_failed)")
    assert not any(label in toast for label in failure_labels), toast
    submissions = page.evaluate("window.__submissions")
    assert len(submissions) == 1
    edits = json.loads(submissions[0])["edits"]
    assert any(edit["property"] == "padding" and edit["newValue"] == expected_padding for edit in edits), edits
    assert any(edit["property"] == "width" and edit["newValue"] == "333px" for edit in edits), edits
    assert next(edit for edit in edits if edit["property"] == "padding")["oldValue"] == original_padding
    assert next(edit for edit in edits if edit["property"] == "width")["oldValue"] == original_width
    expect(target).to_have_css("padding", expected_padding)
    expect(target).to_have_css("width", "333px")
    assert not page.evaluate("window.dpbHasPendingVisualEdits()")
    assert errors == []
