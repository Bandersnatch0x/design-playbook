"""The bridge's DOM-bound helpers, executed from the shipped file.

`pin_bridge.js` runs inside the prototype frame, so only the browser suites
could see a locator that lost its `:nth-of-type`, a guide that stopped hiding,
or a colour channel swapped for a rect channel. Those helpers need a document,
not a real one: this extracts their source text from the shipped file and runs
them in node against a small fake DOM. It needs node, which the repository
already requires for its JavaScript checks; node 24 has no `document`, `window`
or `CSS`, so the harness below supplies all three.

Deliberately absent: `isTextElement`, `updateOverlayPositions`,
`syncToolbarState`, `beginManipulation` and the event/listener helpers. Their
surface is computed-style interplay and event wiring that a fake DOM would only
exercise as fake, so the browser suites keep owning them.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
BRIDGE = PKG_ROOT / "mcp" / "preview" / "pin_bridge.js"

DOM_HELPERS = (
    "cssPath", "visualStyleSnapshot", "ensureFloatRoot",
    "checkGuides", "hideGuides", "inlineValues",
)

# Extraction counts braces, which is enough for these six: none of them holds a
# brace inside a string or a comment. A helper that gains one needs a real parse.
# `guideV`, `guideH` and `floatRoot` are bridge state the shipped file declares
# outside these bodies, so the harness re-declares them in the same scope.
CHECKS = r"""
var guideV = null;
var guideH = null;
var floatRoot = null;

var escapeCalls = 0;
var CSS = { escape: function (value) {
  escapeCalls++;
  return String(value).replace(/([^A-Za-z0-9_-])/g, "\\$1");
} };

function styleWith(values) {
  var style = { values: values || {} };
  style.getPropertyValue = function (name) {
    return Object.prototype.hasOwnProperty.call(style.values, name) ? style.values[name] : "";
  };
  return style;
}

function makeElement(tagName, opts) {
  opts = opts || {};
  return {
    nodeType: 1,
    tagName: tagName,
    id: opts.id || "",
    classList: opts.classes || [],
    children: [],
    parentElement: null,
    style: opts.style || styleWith(null),
    computed: opts.computed || null,
    rect: opts.rect || null,
    scrollHeight: opts.scrollHeight || 0,
    scrollWidth: opts.scrollWidth || 0,
    getBoundingClientRect: function () { return this.rect; },
    appendChild: function (child) { return append(this, child); }
  };
}

function append(parent, child) {
  child.parentElement = parent;
  parent.children.push(child);
  return child;
}

var html = makeElement("HTML", { scrollHeight: 1000, scrollWidth: 900 });
var body = append(html, makeElement("BODY"));
var created = [];
var document = {
  documentElement: html,
  body: body,
  createElement: function (tagName) {
    var node = makeElement(String(tagName).toUpperCase());
    created.push(node);
    return node;
  }
};
var window = {
  scrollX: 7,
  scrollY: 11,
  innerWidth: 1200,
  innerHeight: 600,
  getComputedStyle: function (el) { return el.computed; }
};

// Fixture tree; every cssPath case runs before anything below adds children.
var wrap = append(body, makeElement("DIV"));
append(wrap, makeElement("P"));
var secondP = append(wrap, makeElement("P"));
var mainEl = append(wrap, makeElement("MAIN"));
var classy = append(wrap, makeElement("SECTION", { classes: ["card", "dpb-pin-badge", "dropped"] }));
var spaced = append(wrap, makeElement("SPAN", { classes: ["grid item", "a", "b", "c"] }));
var floatRootHost = append(html, makeElement("DIV", { id: "dpb-float-root" }));
var insideRoot = append(floatRootHost, makeElement("SPAN"));
var headerEl = append(html, makeElement("HEADER"));
var idEl = makeElement("DIV", { id: "my id" });
// A BODY that is not the document's own, so the walk has somewhere to keep
// going and the BODY stop is the only thing that ends it.
var detachedWrap = makeElement("DIV");
var detachedBody = append(detachedWrap, makeElement("BODY"));
var detachedSpan = append(detachedBody, makeElement("SPAN"));
var chain = [];
for (var d = 0; d < 10; d++) {
  var node = makeElement("DIV");
  if (chain.length) append(chain[chain.length - 1], node);
  chain.push(node);
}

var failures = [];
var runs = 0;
function eq(got, want, label) {
  runs++;
  var g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) failures.push(label + ": got " + g + ", want " + w);
}
function ok(cond, label) {
  runs++;
  if (!cond) failures.push(label + ": false");
}

// cssPath: the shape of a locator.
eq(cssPath(null), "", "no element");
eq(cssPath({ nodeType: 3 }), "", "text node");
eq(cssPath(idEl), "#my\\ id", "id path escapes");
ok(escapeCalls > 0, "CSS.escape consulted");
eq(cssPath(secondP), "body > div > p:nth-of-type(2)", "ambiguous sibling indexed");
eq(cssPath(mainEl), "body > div > main", "unique sibling not indexed");
eq(cssPath(classy), "body > div > section.card", "dpb- class filtered, rest truncated");
eq(cssPath(spaced), "body > div > span.grid\\ item.a", "class escaped, truncated to two");
eq(cssPath(insideRoot), "span", "walk stops under the float root id");
eq(cssPath(headerEl), "header", "walk stops at documentElement");
eq(cssPath(detachedSpan), "body > span", "walk stops after a BODY");
eq(cssPath(chain[9]).split(" > ").length, 8, "depth cap is eight elements");

// visualStyleSnapshot: computed channels plus the rect projection.
var SNAP_KEYS = [
  "color", "backgroundColor", "fontFamily", "fontSize", "fontWeight", "fontStyle",
  "textDecoration", "lineHeight", "letterSpacing", "margin", "padding", "marginTop",
  "marginRight", "marginBottom", "marginLeft", "paddingTop", "paddingRight",
  "paddingBottom", "paddingLeft", "width", "height", "display", "position",
  "flexDirection", "justifyContent", "alignItems", "gap", "borderRadius",
  "borderWidth", "borderColor", "transform"
];
var snapComputed = {};
for (var k = 0; k < SNAP_KEYS.length; k++) snapComputed[SNAP_KEYS[k]] = "v_" + SNAP_KEYS[k];
var snapEl = makeElement("DIV", { computed: snapComputed, rect: { x: 1, y: 2, width: 3, height: 4 } });
var snap = visualStyleSnapshot(snapEl);
eq(Object.keys(snap).length, SNAP_KEYS.length + 1, "snapshot key count");
for (var s = 0; s < SNAP_KEYS.length; s++) {
  eq(snap[SNAP_KEYS[s]], "v_" + SNAP_KEYS[s], "snapshot " + SNAP_KEYS[s]);
}
eq(snap.rect, { x: 1, y: 2, width: 3, height: 4 }, "snapshot rect channels");

// inlineValues: one entry per property, old value from the inline style.
var styled = makeElement("DIV", { style: styleWith({ color: "red", width: "10px" }) });
eq(inlineValues(styled, ["color", "width", "font-size"]),
  [{ property: "color", oldValue: "red" }, { property: "width", oldValue: "10px" },
   { property: "font-size", oldValue: "" }], "inline values read");
eq(inlineValues(styled, []), [], "no properties");

// checkGuides: snap geometry and the guide style writes.
var target = { left: 100, top: 200, width: 50, height: 20 };
guideV = null;
guideH = null;
eq(checkGuides(target, [{ left: 100, top: 200, width: 50, height: 20 }]), { dx: 0, dy: 0 },
  "no guides snaps nothing");
eq(created.length, 0, "no guides touches the DOM");

function newGuides() { guideV = makeElement("DIV"); guideH = makeElement("DIV"); }

newGuides();
eq(checkGuides(target, [{ left: 100, top: 200, width: 50, height: 20 }]), { dx: 0, dy: 0 },
  "exact overlap needs no delta");
eq([guideV.style.left, guideV.style.top, guideV.style.height, guideV.style.display],
  ["107px", "0px", "1000px", "block"], "vertical guide spans the scroll height");
eq([guideH.style.top, guideH.style.left, guideH.style.width, guideH.style.display],
  ["211px", "0px", "1200px", "block"], "horizontal guide spans the viewport");

newGuides();
eq(checkGuides(target, [{ left: 96, top: 196, width: 50, height: 20 }]), { dx: -4, dy: -4 },
  "four pixels is inside the threshold");
eq([guideV.style.left, guideH.style.top], ["103px", "207px"], "snapped guides follow the match");

newGuides();
eq(checkGuides(target, [{ left: 95, top: 195, width: 50, height: 20 }]), { dx: 0, dy: 0 },
  "five pixels is outside the threshold");
eq([guideV.style.display, guideH.style.display], ["none", "none"], "both guides hide on no match");

newGuides();
eq(checkGuides(target, [{ left: 103, top: 230, width: 40, height: 60 }]), { dx: 3, dy: 0 },
  "x snaps, y does not");
eq([guideV.style.display, guideH.style.display], ["block", "none"], "one guide shows, one hides");

newGuides();
eq(checkGuides(target, [{ left: 600, top: 213, width: 100, height: 100 }]), { dx: 0, dy: 3 },
  "y snaps, x does not");
eq([guideV.style.display, guideH.style.display], ["none", "block"], "the other guide shows");

// A match at edge zero is a match, not a missing guide: the search stops on the
// first edge instead of falling through to the centre.
newGuides();
eq(checkGuides({ left: 0, top: 0, width: 50, height: 20 },
  [{ left: 0, top: 0, width: 50, height: 20 }]), { dx: 0, dy: 0 }, "a zero edge snaps");
eq([guideV.style.left, guideV.style.display, guideH.style.top, guideH.style.display],
  ["7px", "block", "11px", "block"], "the zero match draws both guides at the edge");

// hideGuides: both off, and a missing guide is not an error.
newGuides();
guideV.style.display = "block";
guideH.style.display = "block";
hideGuides();
eq([guideV.style.display, guideH.style.display], ["none", "none"], "hideGuides hides both");
guideV = null;
guideH.style.display = "block";
hideGuides();
eq(guideH.style.display, "none", "hideGuides tolerates a missing guide");

// ensureFloatRoot: created once, reused after.
var root1 = ensureFloatRoot();
eq(root1.id, "dpb-float-root", "float root id");
eq(body.children[body.children.length - 1] === root1, true, "float root appended to body");
var root2 = ensureFloatRoot();
eq(root2 === root1, true, "second call reuses the root");
eq(created.length, 1, "second call appends nothing");

// buildDrawBadge: the badge the shell and the bridge both draw. One shared
// builder, so a drift in the clamp or the class name shows up here.
document.createElementNS = function (ns, tag) {
  var node = makeElement(String(tag).toUpperCase());
  node.attrs = {};
  node.setAttribute = function (k, v) { this.attrs[k] = String(v); };
  return node;
};
var badgeSvg = makeElement("SVG");
var badge = DPBUI.pure.buildDrawBadge(badgeSvg, "dpb-draw-badge", 10, 4, 3);
eq(badge.attrs["class"], "dpb-draw-badge", "badge class");
eq(badge.attrs.transform, "translate(10.0,9.0)", "badge y clamps above the point");
eq(badge.children[0].attrs.r, "9", "badge circle radius");
eq(badge.children[1].textContent, "3", "badge label");
eq(badgeSvg.children[badgeSvg.children.length - 1] === badge, true, "badge appended to the svg");

if (failures.length) {
  console.error(failures.length + " failure(s):\n" + failures.join("\n"));
  process.exit(1);
}
console.log("PIN BRIDGE DOM UNIT OK " + runs);
"""


def _extract(name: str, source: str) -> str:
    start = source.index("function " + name + "(")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unterminated function {name}")


def test_the_bridges_dom_bound_helpers_keep_their_contracts(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    source = BRIDGE.read_text(encoding="utf-8")
    # `cssPath` and the badge builder delegate to DPBUI.pure, so the shared
    # core ships first in the extracted payload. It ends with `(window)` and
    # the fake window below is declared inside CHECKS, so a pre-stub keeps the
    # core's IIFE call resolvable.
    core = (PKG_ROOT / "mcp" / "_shared" / "dpbui-core.js")
    preamble = (
        "var window = globalThis;\n"
        "var document = { documentElement: {}, getElementById: function () { return null; } };\n"
        + core.read_text(encoding="utf-8")
        # Bridge-scope constants the extracted bodies read (declared next to
        # cssPath in the shipped file, outside the extracted function text).
        + "\nvar CAPTURE_STOP_IDS = ['dpb-preview-bar', 'dpb-float-root'];\n"
    )
    extracted = preamble + "\n" + "\n".join(_extract(name, source) for name in DOM_HELPERS)
    for name in DOM_HELPERS:
        assert "function " + name + "(" in extracted
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "pin_bridge_dom_units.js"
    script_path.write_text(extracted + CHECKS, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "PIN BRIDGE DOM UNIT OK" in result.stdout, result.stdout
    captured = int(result.stdout.split()[-1])
    assert captured > 40, f"expected the case table to run, got {captured} checks"
