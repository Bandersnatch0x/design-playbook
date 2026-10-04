# Offline Vue 3 bridge host

This is **real Vue 3.5.39**, not a Vue-like proxy. `app.js` uses Vue's template
compiler, reactive data, event handling, and DOM patching. The vendored production
global browser build was copied unchanged from a locally installed `vue@3.5.39`
package; its MIT license is retained in `vendor/LICENSE.vue`. No install, CDN,
network download, bundler, or React host is needed.

Run `python packages/design-playbook/tests/fixtures/visual-edit-vue-host/server.py`
from the repository root. The printed loopback route embeds the product's
`build_visual_edit_bridge_script()` verbatim. The server exposes only the page
and its two fixed JavaScript assets; there is no source writer.

The e2e test selects a Vue-rendered heading through the plugin's live-route
iframe, edits its text color, advances Vue's reactive counter, and checks both
DOM and pending batch through undo/redo. Vue owns the heading's text, render-count
attribute, and letter spacing; it does not own the edited text color. This proves
coexistence for stable mounted elements, **not** persistence through a remount or
a framework update that overwrites the same CSS property.
