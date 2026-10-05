"""Pin-to-annotate bridge injected into the sandboxed prototype iframe (G5).

G5 isolated the prototype inside ``<iframe sandbox="allow-scripts" srcdoc=...>``
with allow-same-origin DELIBERATELY omitted, so the iframe is an opaque
origin and prototype scripts cannot reach the parent DOM (where the decision
token lives). That broke pin-to-annotate: the parent's document.click +
cssPath(e.target) can no longer see clicks inside the iframe or traverse the
iframe DOM (cross-origin). This bridge runs INSIDE the iframe document and
restores anchor collection by postMessaging {selector, tag} to the parent.

Pin-state sync (#56): the parent owns pinOn and pushes it down via
postMessage {dpbPinState:{on}} (on every toggle + iframe load). The bridge
gates its capture-phase click/mousemove listeners on that state: while pin
is OFF the prototype receives clicks and hover exactly as if the bridge were
not injected (no preventDefault/stopPropagation, no dashed outline); while
ON it keeps the capture behaviour (anchor + highlight + dashed hover).

Cross-origin locate + numbered badges (#57, scheme A): the parent drives
{dpbPinLocate:{selector}} (scrollIntoView + flash), {dpbPinFlash:{selector}}
(duplicate-pick feedback) and {dpbPinAnchors:[{selector,n,comment}]} (in-
frame numbered badges mirroring the same-origin float-notes) into the iframe.

G5 safety contract (verified by test_browser_control.PinAnnotationBridgeTests):
  - the bridge only postMessages anchor DATA ({selector, tag}) — it never
    reads parent.document, parent.location, the token, or storage, and it
    never fetches/XHRs. postMessage is its only outbound channel.
  - the parent additionally records anchors only while pin mode is on
    (control.js message listener filters on pinOn) — defense in depth.
  - the iframe highlights the clicked element itself (dpb-pin-target) since
    the parent cannot reach into the iframe DOM to do it.

Raw string + single braces: this is plain string concatenation (not .format),
so JS braces stay literal (no {{ doubling). cssPath is a faithful copy of
control.py's cssPath so selectors match the same-origin path.
"""

from __future__ import annotations

import json

from design_playbook.mcp.preview.i18n import ZH, _STRINGS

BRIDGE_SCRIPT = r"""<script>
(function () {
  var labels = __DPB_VISUAL_LABELS__;
  function text(key, values) {
    var result = labels[key] || key;
    Object.keys(values || {}).forEach(function (name) { result = result.replace("{" + name + "}", values[name]); });
    return result;
  }
  function label(control, key) {
    control.setAttribute("data-dpb-label", key);
    control.setAttribute("aria-label", text(key, { handle: control.getAttribute("data-handle") || "" }));
    if (control.hasAttribute("title")) control.title = control.getAttribute("aria-label");
  }
  function localize(values) {
    if (!values || typeof values !== "object") return;
    Object.keys(labels).forEach(function (key) { if (typeof values[key] === "string") labels[key] = values[key]; });
    document.querySelectorAll("[data-dpb-label]").forEach(function (control) { label(control, control.getAttribute("data-dpb-label")); });
    if (visualSelectedEl) updateOverlayPositions(visualSelectedEl);
  }
  // Inject the pin highlight + badge CSS into the iframe document. The
  // parent's control-bar stylesheet does not cross the iframe boundary, so the
  // bridge brings its own copy of .dpb-pin-target / .dpb-pin-hover (the same
  // rules control.py renders in the parent) plus the numbered annotation
  // badges (.dpb-pin-badge*, #57 scheme A) to render them in-frame.
  var style = document.createElement("style");
  style.textContent =
    "#dpb-selection-overlay :focus-visible,#dpb-text-toolbar :focus-visible,#dpb-color-picker :focus-visible{outline:2px solid #2563eb!important;outline-offset:2px;box-shadow:0 0 0 2px white!important;}" +
    ".dpb-pin-badge.dpb-resolved,.dpb-pin-badge-note.dpb-resolved{opacity:.5;text-decoration:line-through;}" +
    ".dpb-pin-target{outline:1.5px solid rgba(20,184,166,.9)!important;" +
    "outline-offset:1px!important;background-color:rgba(20,184,166,.06)!important;" +
    "cursor:crosshair!important}" +
    ".dpb-pin-hover{outline:1px dashed rgba(20,184,166,.45)!important;" +
    "outline-offset:1px!important}" +
    ".dpb-visual-edit-selected{outline:2px solid #2563EB!important;outline-offset:3px!important;" +
    "box-shadow:0 0 0 4px rgba(37,99,235,.18)!important}" +
    "#dpb-selection-overlay{position:absolute;z-index:2147483000;box-sizing:border-box;" +
    "border:1.5px solid #2563EB;border-radius:2px;pointer-events:none}" +
    ".dpb-move-body{position:absolute;inset:0;cursor:grab;pointer-events:auto;touch-action:none}" +
    ".dpb-move-body:active{cursor:grabbing}" +
    "#dpb-float-root{position:static;pointer-events:none}" +
    "#dpb-dimension-hud{position:absolute;top:calc(100% + 10px);left:50%;transform:translateX(-50%);" +
    "padding:4px 8px;border-radius:4px;background:#0f172a;color:#fff;white-space:nowrap;font:12px/1.4 system-ui}" +
    ".dpb-resize-handle:focus-visible,.dpb-move-body:focus-visible,#dpb-color-picker :focus-visible{" +
    "outline:2px solid #f59e0b;outline-offset:3px}" +
    ".dpb-resize-handle{position:absolute;width:10px;height:10px;border-radius:50%;background:#fff;" +
    "border:2px solid #2563EB;box-shadow:0 1px 3px rgba(0,0,0,.25);pointer-events:auto;touch-action:none;" +
    "box-sizing:border-box;transition:transform 140ms ease}" +
    ".dpb-resize-handle:hover{transform:scale(1.25)}" +
    ".dpb-handle-nw{left:-5px;top:-5px;cursor:nwse-resize}" +
    ".dpb-handle-n{left:calc(50% - 5px);top:-5px;cursor:ns-resize}" +
    ".dpb-handle-ne{right:-5px;top:-5px;cursor:nesw-resize}" +
    ".dpb-handle-e{right:-5px;top:calc(50% - 5px);cursor:ew-resize}" +
    ".dpb-handle-se{right:-5px;bottom:-5px;cursor:nwse-resize}" +
    ".dpb-handle-s{left:calc(50% - 5px);bottom:-5px;cursor:ns-resize}" +
    ".dpb-handle-sw{left:-5px;bottom:-5px;cursor:nesw-resize}" +
    ".dpb-handle-w{left:-5px;top:calc(50% - 5px);cursor:ew-resize}" +
    ".dpb-guide-line{position:absolute;pointer-events:none;z-index:2147483005;display:none}" +
    ".dpb-guide-v{width:0;border-left:1.5px dashed #EF4444}" +
    ".dpb-guide-h{height:0;border-top:1.5px dashed #EF4444}" +
    "#dpb-text-toolbar{max-width:calc(100vw - 16px);box-sizing:border-box;flex-wrap:wrap;position:absolute;z-index:2147483010;display:flex;align-items:center;gap:3px;" +
    "padding:3px 6px;border-radius:8px;background:#1e293b;color:#f8fafc;border:1px solid #334155;" +
    "box-shadow:0 4px 16px rgba(0,0,0,.3);pointer-events:auto;user-select:none;font:12px/1 system-ui,sans-serif}" +
    ".dpb-tb-btn{background:transparent;border:1px solid transparent;color:#e2e8f0;border-radius:4px;" +
    "width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;padding:0}" +
    ".dpb-tb-btn:hover{background:rgba(255,255,255,.1)}" +
    ".dpb-tb-btn.is-active{background:#2563EB;color:#fff}" +
    ".dpb-tb-italic{font-family:Georgia,'Times New Roman',serif;font-style:italic}" +
    ".dpb-tb-select{height:24px;font-size:11px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;padding:0 3px}" +
    ".dpb-tb-color-btn{position:relative;width:24px;height:24px;display:inline-flex;flex-direction:column;" +
    "align-items:center;justify-content:center;background:transparent;border:1px solid transparent;color:#e2e8f0;border-radius:4px;cursor:pointer;padding:0;font-size:11px;font-weight:700}" +
    ".dpb-tb-color-bar{width:14px;height:3px;border-radius:1px;background:#2563EB;margin-top:1px}" +
    "#dpb-color-picker{position:absolute;top:calc(100% + 6px);left:0;background:#1e293b;border:1px solid #334155;" +
    "border-radius:8px;padding:8px;box-shadow:0 8px 24px rgba(0,0,0,.4);display:none;flex-direction:column;gap:8px;width:190px;max-width:calc(100vw - 32px);pointer-events:auto;z-index:2147483015}" +
    "#dpb-color-picker.is-open{display:flex}" +
    ".dpb-cp-sv{position:relative;width:100%;height:90px;border-radius:6px;cursor:crosshair;background:#f00;" +
    "background-image:linear-gradient(to top,#000,rgba(0,0,0,0)),linear-gradient(to right,#fff,rgba(255,255,255,0));touch-action:none}" +
    ".dpb-cp-sv-thumb{position:absolute;width:10px;height:10px;border-radius:50%;border:2px solid #fff;" +
    "box-shadow:0 0 2px rgba(0,0,0,.5);transform:translate(-50%,-50%);pointer-events:none}" +
    ".dpb-cp-hue,.dpb-cp-alpha{position:relative;height:10px;border-radius:5px;cursor:pointer;touch-action:none}" +
    ".dpb-cp-hue{background:linear-gradient(to right,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)}" +
    ".dpb-cp-alpha{background:linear-gradient(to right,rgba(255,255,255,0),#2563EB)}" +
    ".dpb-cp-hue-thumb,.dpb-cp-alpha-thumb{position:absolute;top:50%;width:10px;height:10px;border-radius:50%;" +
    "border:2px solid #fff;box-shadow:0 0 2px rgba(0,0,0,.5);transform:translate(-50%,-50%);pointer-events:none}" +
    ".dpb-cp-inputs{display:flex;gap:6px;align-items:center}" +
    ".dpb-cp-hex{flex:1;min-width:0;padding:3px 5px;font-size:11px;font-family:monospace;border:1px solid #334155;border-radius:4px;background:#0f172a;color:#f8fafc}" +
    ".dpb-cp-opacity{width:44px;padding:3px 4px;font-size:11px;text-align:right;border:1px solid #334155;border-radius:4px;background:#0f172a;color:#f8fafc}" +
    ".dpb-cp-swatches{display:flex;flex-wrap:wrap;gap:4px}" +
    ".dpb-cp-swatch.is-active{outline:2px solid #fff;outline-offset:2px;box-shadow:0 0 0 4px #2563eb}" +
    ".dpb-cp-swatch{width:16px;height:16px;border-radius:3px;border:1px solid rgba(255,255,255,.2);cursor:pointer;padding:0}" +
    ".dpb-pin-badge{position:absolute;z-index:2147483000;min-width:18px;height:18px;" +
    "padding:0 5px;border-radius:999px;background:#14b8a6;color:#042f2e;" +
    "font:700 11px/18px system-ui,sans-serif;text-align:center;pointer-events:none;" +
    "box-shadow:0 1px 3px rgba(0,0,0,.3);transform-origin:center;" +
    "transition:transform .2s cubic-bezier(.16,1,.3,1),box-shadow .2s cubic-bezier(.16,1,.3,1)}" +
    ".dpb-pin-badge.dpb-pin-drop{animation:dpb-pin-drop .38s cubic-bezier(.16,1,.3,1) both}" +
    ".dpb-pin-badge.dpb-active::after{content:'';position:absolute;inset:-4px;border-radius:999px;" +
    "border:2px solid rgba(20,184,166,.35);animation:dpb-pulse-ring 1.8s cubic-bezier(.24,0,.38,1) infinite}" +
    ".dpb-pin-badge-note{position:absolute;z-index:2147483000;max-width:220px;" +
    "padding:4px 8px;border-radius:8px;background:#1f2430;color:#f3f4f6;" +
    "border:1px solid #2c3444;font:11px/1.4 system-ui,sans-serif;" +
    "word-break:break-word;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.25)}" +
    ".dpb-pin-flash{animation:dpb-pin-flash .9s ease-out 1}" +
    "@keyframes dpb-pin-drop{0%{transform:translateY(-16px) scale(1.3);opacity:0}" +
    "60%{transform:translateY(2px) scale(.95);opacity:1}" +
    "80%{transform:translateY(-1px) scale(1.02)}100%{transform:translateY(0) scale(1);opacity:1}}" +
    "@keyframes dpb-pulse-ring{0%{transform:scale(.9);opacity:.72}100%{transform:scale(1.9);opacity:0}}" +
    "@keyframes dpb-pin-flash{0%{box-shadow:0 0 0 0 rgba(20,184,166,.55)}" +
    "50%{box-shadow:0 0 0 8px rgba(20,184,166,.25)}" +
    "100%{box-shadow:0 0 0 0 rgba(20,184,166,0)}}" +
    // Draw mode: stroke layer + crosshair while capturing. The sandboxed frame
    // cannot read the parent's custom properties, so the light-theme values of
    // --dpb-draw-stroke (#E11D48) and --dpb-draw-ink (#FFFFFF) are inlined
    // here. Keep them and the dash pattern in step with control.css: this is
    // the production path, so a mismatch here is what the reviewer actually
    // sees (spec §3.1 requires a dashed stroke).
    "#dpb-draw-layer{position:absolute;top:0;left:0;z-index:2147482999;" +
    "pointer-events:none;overflow:visible}" +
    "html.dpb-draw-mode{cursor:crosshair}" +
    "#dpb-draw-layer .dpb-draw-path{fill:none;stroke:#E11D48;" +
    "stroke-width:2.4;stroke-dasharray:8 4;" +
    "stroke-linecap:round;stroke-linejoin:round;opacity:.92}" +
    "#dpb-draw-layer .dpb-draw-live{opacity:.65;stroke-dasharray:6 3}" +
    "#dpb-draw-layer .dpb-draw-badge-c{fill:#E11D48}" +
    "#dpb-draw-layer .dpb-draw-badge text{fill:#FFFFFF;" +
    "font:700 11px/1 system-ui,sans-serif}" +
    ".dpb-ruler-hover-target{outline:1.5px dashed #2563EB!important;" +
    "outline-offset:1px!important;background-color:rgba(37,99,235,.08)!important}" +
    "#dpb-ruler-layer{position:absolute;top:0;left:0;z-index:2147482998;" +
    "pointer-events:none;overflow:visible}" +
    "#dpb-ruler-layer .dpb-ruler-line{stroke:#2563EB;stroke-width:2;stroke-linecap:round}" +
    "#dpb-ruler-layer .dpb-ruler-point{fill:#2563EB;stroke:#FFFFFF;stroke-width:2}" +
    "#dpb-ruler-layer .dpb-ruler-badge rect{fill:#2563EB;stroke:rgba(255,255,255,.45);stroke-width:1}" +
    "#dpb-ruler-layer .dpb-ruler-badge text{fill:#FFFFFF;font:700 11px/1 ui-monospace,Consolas,monospace}" +
    ".dpb-draw-flash{animation:dpb-draw-flash .9s ease-out 1}" +
    "@keyframes dpb-draw-flash{0%{stroke-width:2.5px;filter:drop-shadow(0 0 0 rgba(244,96,42,0))}" +
    "50%{stroke-width:5px;filter:drop-shadow(0 0 8px rgba(244,96,42,.85))}" +
    "100%{stroke-width:2.5px;filter:drop-shadow(0 0 0 rgba(244,96,42,0))}}" +
    // W5: honor reduced-motion inside the iframe too (host control.css only
    // covers the parent document).
    "@media (prefers-reduced-motion:reduce){.dpb-pin-badge,.dpb-pin-badge::before,.dpb-pin-badge::after," +
    ".dpb-pin-badge-note,#dpb-draw-layer,#dpb-draw-layer *,#dpb-ruler-layer,#dpb-ruler-layer *{" +
    "scroll-behavior:auto!important;transition-duration:1ms!important;transition-delay:0ms!important}" +
    ".dpb-pin-badge.dpb-pin-drop,.dpb-pin-badge.dpb-active::after,.dpb-pin-flash,.dpb-draw-flash{animation:none!important}}";
  (document.head || document.documentElement).appendChild(style);

  // #56: pin state is owned by the parent control bar and synced down via
  // postMessage. OFF (the initial state) means the bridge is fully passive:
  // clicks and hover pass through to the prototype untouched.
  var pinOn = false;

  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    var cur = el;
    var depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {
      if (cur.id === "dpb-preview-bar" || cur.id === "dpb-float-root") break;
      var part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) {
        var cls = Array.prototype.slice.call(cur.classList, 0, 2)
          .filter(function (c) { return c && c.indexOf("dpb-") !== 0; })
          .map(function (c) { return "." + CSS.escape(c); })
          .join("");
        part += cls;
      }
      var parent = cur.parentElement;
      if (parent) {
        var kids = parent.children;
        var n = 0, idx = 0, i;
        for (i = 0; i < kids.length; i++) {
          if (kids[i].tagName === cur.tagName) {
            n++;
            if (kids[i] === cur) idx = n;
          }
        }
        if (n > 1) part += ":nth-of-type(" + idx + ")";
      }
      parts.unshift(part);
      if (cur.tagName === "BODY") break;
      cur = parent;
      depth++;
    }
    return parts.join(" > ");
  }
  var hoverEl = null;
  var visualSelectedEl = null;
  function visualStyleSnapshot(el) {
    var computed = window.getComputedStyle(el);
    var rect = el.getBoundingClientRect();
    return {
      color: computed.color,
      backgroundColor: computed.backgroundColor,
      fontFamily: computed.fontFamily,
      fontSize: computed.fontSize,
      fontWeight: computed.fontWeight,
      fontStyle: computed.fontStyle,
      textDecoration: computed.textDecoration,
      lineHeight: computed.lineHeight,
      letterSpacing: computed.letterSpacing,
      margin: computed.margin,
      padding: computed.padding,
      marginTop: computed.marginTop,
      marginRight: computed.marginRight,
      marginBottom: computed.marginBottom,
      marginLeft: computed.marginLeft,
      paddingTop: computed.paddingTop,
      paddingRight: computed.paddingRight,
      paddingBottom: computed.paddingBottom,
      paddingLeft: computed.paddingLeft,
      width: computed.width,
      height: computed.height,
      display: computed.display,
      position: computed.position,
      flexDirection: computed.flexDirection,
      justifyContent: computed.justifyContent,
      alignItems: computed.alignItems,
      gap: computed.gap,
      borderRadius: computed.borderRadius,
      borderWidth: computed.borderWidth,
      borderColor: computed.borderColor,
      transform: computed.transform,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    };
  }
  var overlayEl = null;
  var toolbarEl = null;
  var compactEditor = false;
  var guideV = null;
  var guideH = null;
  var colorPickerEl = null;
  var openColorPicker = null;
  var closeColorPicker = null;
  var dimensionHud = null;
  var floatRoot = null;
  function ensureFloatRoot() {
    if (!floatRoot) {
      floatRoot = document.createElement("div");
      floatRoot.id = "dpb-float-root";
      (document.body || document.documentElement).appendChild(floatRoot);
    }
    return floatRoot;
  }

  function hsvToRgb(h, s, v) {
    var c = v * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = v - c;
    var r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; }
    else if (h < 120) { r = x; g = c; }
    else if (h < 180) { g = c; b = x; }
    else if (h < 240) { g = x; b = c; }
    else if (h < 300) { r = x; b = c; }
    else { r = c; b = x; }
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
  }

  function rgbToHex(r, g, b) {
    return "#" + [r, g, b].map(function (v) {
      var s = v.toString(16);
      return s.length === 1 ? "0" + s : s;
    }).join("");
  }

  function checkGuides(targetRect, candidates) {
    if (!guideV || !guideH) return;


    var matchV = null;
    var matchH = null;
    var threshold = 6;
    var targetEdgesX = [targetRect.left, targetRect.left + targetRect.width / 2, targetRect.right];
    var targetEdgesY = [targetRect.top, targetRect.top + targetRect.height / 2, targetRect.bottom];

    for (var i = 0; i < candidates.length; i++) {
      var cr = candidates[i];
      var candEdgesX = [cr.left, cr.left + cr.width / 2, cr.right];
      var candEdgesY = [cr.top, cr.top + cr.height / 2, cr.bottom];

      for (var tx = 0; tx < targetEdgesX.length; tx++) {
        for (var cx = 0; cx < candEdgesX.length; cx++) {
          if (Math.abs(targetEdgesX[tx] - candEdgesX[cx]) <= threshold) {
            matchV = candEdgesX[cx];
            break;
          }
        }
        if (matchV !== null) break;
      }
      for (var ty = 0; ty < targetEdgesY.length; ty++) {
        for (var cy = 0; cy < candEdgesY.length; cy++) {
          if (Math.abs(targetEdgesY[ty] - candEdgesY[cy]) <= threshold) {
            matchH = candEdgesY[cy];
            break;
          }
        }
        if (matchH !== null) break;
      }
    }

    if (matchV !== null) {
      guideV.style.left = (window.scrollX + matchV) + "px";
      guideV.style.top = "0px";
      guideV.style.height = Math.max(document.documentElement.scrollHeight, window.innerHeight) + "px";
      guideV.style.display = "block";
    } else {
      guideV.style.display = "none";
    }

    if (matchH !== null) {
      guideH.style.top = (window.scrollY + matchH) + "px";
      guideH.style.left = "0px";
      guideH.style.width = Math.max(document.documentElement.scrollWidth, window.innerWidth) + "px";
      guideH.style.display = "block";
    } else {
      guideH.style.display = "none";
    }
  }

  function hideGuides() {
    if (guideV) guideV.style.display = "none";
    if (guideH) guideH.style.display = "none";
  }

  var gestureSequence = 0;
  function inlineValues(el, properties) {
    return properties.map(function (property) {
      return { property: property, oldValue: el.style.getPropertyValue(property) };
    });
  }
  function finishVisualChange(el, changes, requestId, replay) {
    var id = requestId || "gesture-" + (++gestureSequence);
    changes.forEach(function (change) { change.newValue = el.style.getPropertyValue(change.property); });
    if (!requestId) changes = changes.filter(function (change) { return change.oldValue !== change.newValue; });
    if (!requestId && !changes.length) return;
    reportVisualSelection(el, replay, id);
    parent.postMessage({ dpbVisualEditChange: {
      requestId: id, selector: cssPath(el), changes: changes, replay: !!replay
    } }, "*");
  }
  function translated(transform, dx, dy) {
    return "translate(" + dx + "px, " + dy + "px)" +
      (transform && transform !== "none" ? " " + transform : "");
  }
  function beginManipulation(el, handle) {
    var rect = el.getBoundingClientRect(), computed = getComputedStyle(el);
    var transform = el.style.transform || computed.transform;
    var changes = inlineValues(el, handle ? ["width", "height", "transform"] : ["transform"]);
    // Rect dimensions are border-box; CSS width/height may still be content-box.
    var extraW = computed.boxSizing === "border-box" ? 0 :
      parseFloat(computed.paddingLeft) + parseFloat(computed.paddingRight) +
      parseFloat(computed.borderLeftWidth) + parseFloat(computed.borderRightWidth);
    var extraH = computed.boxSizing === "border-box" ? 0 :
      parseFloat(computed.paddingTop) + parseFloat(computed.paddingBottom) +
      parseFloat(computed.borderTopWidth) + parseFloat(computed.borderBottomWidth);
    var siblings = Array.from(el.parentElement.children).filter(function (candidate) {
      return candidate !== el && !candidate.closest("#dpb-float-root");
    }).map(function (candidate) { return candidate.getBoundingClientRect(); })
      .filter(function (r) { return r.width > 0 && r.height > 0; });
    function update(dx, dy) {
      if (!dx && !dy) {
        changes.forEach(function (c) { el.style.setProperty(c.property, c.oldValue); });
        updateOverlayPositions(el); hideGuides(); dimensionHud.style.display = "none";
        return;
      }
      if (!handle) {
        el.style.transform = translated(transform, Math.round(dx), Math.round(dy));
      } else {
        var west = handle.indexOf("w") >= 0, north = handle.indexOf("n") >= 0;
        if (/[ew]/.test(handle)) el.style.width = Math.max(10, Math.round(rect.width + (west ? -dx : dx) - extraW)) + "px";
        if (/[ns]/.test(handle)) el.style.height = Math.max(10, Math.round(rect.height + (north ? -dy : dy) - extraH)) + "px";
        el.style.setProperty("transform", changes[2].oldValue);
        var resized = el.getBoundingClientRect();
        var offsetX = west ? rect.right - resized.right : rect.left - resized.left;
        var offsetY = north ? rect.bottom - resized.bottom : rect.top - resized.top;
        if (offsetX || offsetY) el.style.transform = translated(transform, offsetX, offsetY);
        dimensionHud.textContent = Math.round(resized.width) + " × " + Math.round(resized.height);
        dimensionHud.style.display = "block";
      }
      updateOverlayPositions(el);
      checkGuides(el.getBoundingClientRect(), siblings);
    }
    return { update: update, finish: function (cancel) {
      if (cancel) changes.forEach(function (c) { el.style.setProperty(c.property, c.oldValue); });
      else finishVisualChange(el, changes);
      hideGuides();
      dimensionHud.style.display = "none";
      updateOverlayPositions(el);
    } };
  }
  function setupManipulation(control, handle) {
    control.tabIndex = 0;
    control.setAttribute("role", "slider");
    label(control, handle ? "visual_resize" : "visual_move");
    control.setAttribute("aria-valuemin", "0");
    control.setAttribute("aria-valuenow", "0");
    control.addEventListener("keydown", function (e) {
      if (!visualSelectedEl || !/^Arrow(Left|Right|Up|Down)$/.test(e.key)) return;
      e.preventDefault(); e.stopPropagation();
      var step = e.shiftKey ? 10 : 1;
      var dx = e.key === "ArrowRight" ? step : e.key === "ArrowLeft" ? -step : 0;
      var dy = e.key === "ArrowDown" ? step : e.key === "ArrowUp" ? -step : 0;
      var gesture = beginManipulation(visualSelectedEl, handle);
      gesture.update(dx, dy); gesture.finish(false);
    });
    control.addEventListener("pointerdown", function (e) {
      if (!visualSelectedEl || e.button !== 0) return;
      e.preventDefault(); e.stopPropagation(); control.focus();
      control.setPointerCapture(e.pointerId);
      var gesture = beginManipulation(visualSelectedEl, handle);
      var frame = 0, dx = 0, dy = 0;
      function draw() { frame = 0; gesture.update(dx, dy); }
      function move(ev) {
        dx = ev.clientX - e.clientX; dy = ev.clientY - e.clientY;
        if (!frame) frame = requestAnimationFrame(draw);
      }
      function finish(ev) {
        if (frame) cancelAnimationFrame(frame);
        if (ev.type === "pointerup") { dx = ev.clientX - e.clientX; dy = ev.clientY - e.clientY; draw(); }
        control.removeEventListener("pointermove", move);
        control.removeEventListener("pointerup", finish);
        control.removeEventListener("pointercancel", finish);
        if (control.hasPointerCapture(e.pointerId)) control.releasePointerCapture(e.pointerId);
        gesture.finish(ev.type === "pointercancel");
      }
      control.addEventListener("pointermove", move);
      control.addEventListener("pointerup", finish);
      control.addEventListener("pointercancel", finish);
    });
  }

  function setupToolbarActions(btnB, btnI, btnU, btnS, selectSize, colorBtn, colorPickerEl) {
    function applyStyleChange(prop, val) {
      if (!visualSelectedEl) return;
      var el = visualSelectedEl;
      if (!CSS.supports(prop, val)) return;
      var changes = inlineValues(el, [prop]);
      el.style.setProperty(prop, val);
      finishVisualChange(el, changes);
    }

    btnB.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!visualSelectedEl) return;
      var computed = window.getComputedStyle(visualSelectedEl);
      var isBold = (computed.fontWeight >= 600 || visualSelectedEl.style.fontWeight === "bold" || visualSelectedEl.style.fontWeight === "700");
      var next = isBold ? "normal" : "bold";
      applyStyleChange("font-weight", next);
      btnB.classList.toggle("is-active", !isBold);
    });

    btnI.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!visualSelectedEl) return;
      var computed = window.getComputedStyle(visualSelectedEl);
      var isItalic = (computed.fontStyle === "italic" || visualSelectedEl.style.fontStyle === "italic");
      var next = isItalic ? "normal" : "italic";
      applyStyleChange("font-style", next);
      btnI.classList.toggle("is-active", !isItalic);
    });

    btnU.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!visualSelectedEl) return;
      var computed = window.getComputedStyle(visualSelectedEl);
      var hasU = (computed.textDecorationLine.indexOf("underline") >= 0 || (visualSelectedEl.style.textDecoration || "").indexOf("underline") >= 0);
      var next = hasU ? "none" : "underline";
      applyStyleChange("text-decoration", next);
      btnU.classList.toggle("is-active", !hasU);
    });

    btnS.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!visualSelectedEl) return;
      var computed = window.getComputedStyle(visualSelectedEl);
      var hasS = (computed.textDecorationLine.indexOf("line-through") >= 0 || (visualSelectedEl.style.textDecoration || "").indexOf("line-through") >= 0);
      var next = hasS ? "none" : "line-through";
      applyStyleChange("text-decoration", next);
      btnS.classList.toggle("is-active", !hasS);
    });

    selectSize.addEventListener("change", function (e) {
      if (!visualSelectedEl) return;
      applyStyleChange("font-size", e.target.value + "px");
    });

    var hexInput = colorPickerEl.querySelector(".dpb-cp-hex");
    var opacityInput = colorPickerEl.querySelector(".dpb-cp-opacity");
    var svArea = colorPickerEl.querySelector(".dpb-cp-sv");
    var hueSlider = colorPickerEl.querySelector(".dpb-cp-hue");
    var alphaSlider = colorPickerEl.querySelector(".dpb-cp-alpha");
    var swatches = Array.from(colorPickerEl.querySelectorAll(".dpb-cp-swatch"));
    var hue = 0, saturation = 0, brightness = 0, alpha = 1, property = "color";
    var colorDraft = null, colorTarget = null, opener = null;
    function clamp(value, max) { return Math.max(0, Math.min(max, value)); }
    function readColor(value) {
      if (!CSS.supports("color", value)) return false;
      var canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
      var context = canvas.getContext("2d");
      context.fillStyle = value; context.fillRect(0, 0, 1, 1);
      var rgba = context.getImageData(0, 0, 1, 1).data;
      var r = rgba[0] / 255, g = rgba[1] / 255, b = rgba[2] / 255;
      var max = Math.max(r, g, b), min = Math.min(r, g, b), delta = max - min;
      hue = delta === 0 ? 0 : max === r ? 60 * (((g - b) / delta + 6) % 6) :
        max === g ? 60 * ((b - r) / delta + 2) : 60 * ((r - g) / delta + 4);
      saturation = max === 0 ? 0 : delta / max; brightness = max; alpha = rgba[3] / 255;
      return true;
    }
    function refreshColor() {
      var rgb = hsvToRgb(hue, saturation, brightness), hex = rgbToHex(rgb[0], rgb[1], rgb[2]);
      hexInput.value = hex;
      opacityInput.value = Math.round(alpha * 100) + "%";
      svArea.style.backgroundColor = "hsl(" + hue + ",100%,50%)";
      svArea.firstElementChild.style.left = saturation * 100 + "%";
      svArea.firstElementChild.style.top = (1 - brightness) * 100 + "%";
      hueSlider.firstElementChild.style.left = hue / 360 * 100 + "%";
      alphaSlider.firstElementChild.style.left = alpha * 100 + "%";
      alphaSlider.style.background = "linear-gradient(to right, transparent, " + hex + ")";
      svArea.setAttribute("aria-valuenow", Math.round(saturation * 100));
      svArea.setAttribute("aria-valuetext", "Saturation " + Math.round(saturation * 100) + "%, brightness " + Math.round(brightness * 100) + "%");
      hueSlider.setAttribute("aria-valuenow", Math.round(hue));
      alphaSlider.setAttribute("aria-valuenow", Math.round(alpha * 100));
      swatches.forEach(function (swatch) {
        var active = alpha === 1 && swatch.dataset.color === hex;
        swatch.classList.toggle("is-active", active); swatch.setAttribute("aria-pressed", String(active));
      });
      return alpha === 1 ? hex : "rgba(" + rgb.join(", ") + ", " + Number(alpha.toFixed(3)) + ")";
    }
    function previewColor() {
      if (!colorTarget) return;
      if (!colorDraft) colorDraft = inlineValues(colorTarget, [property]);
      colorTarget.style.setProperty(property, refreshColor());
      syncToolbarState(colorTarget);
    }
    function commitColor() {
      if (!colorDraft) return;
      var changes = colorDraft; colorDraft = null;
      finishVisualChange(colorTarget, changes);
    }
    closeColorPicker = function (restoreFocus) {
      if (colorDraft) colorTarget.style.setProperty(property, colorDraft[0].oldValue);
      colorDraft = null;
      colorPickerEl.classList.remove("is-open");
      if (restoreFocus && opener) opener.focus();
    };
    openColorPicker = function (nextProperty, source) {
      closeColorPicker(false);
      colorTarget = visualSelectedEl; property = nextProperty; opener = source;
      readColor(getComputedStyle(colorTarget).getPropertyValue(property)); refreshColor();
      colorPickerEl.classList.add("is-open");
      var rect = (source || colorTarget).getBoundingClientRect();
      var width = colorPickerEl.offsetWidth, height = colorPickerEl.offsetHeight;
      colorPickerEl.style.left = clamp(rect.left, Math.max(0, innerWidth - width - 8)) + scrollX + "px";
      colorPickerEl.style.top = clamp(rect.bottom + 8 + height <= innerHeight ? rect.bottom + 8 : rect.top - height - 8,
        Math.max(0, innerHeight - height - 8)) + scrollY + "px";
      hexInput.focus();
    };
    colorBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (colorPickerEl.classList.contains("is-open")) closeColorPicker(false);
      else openColorPicker("color", colorBtn);
    });
    document.addEventListener("pointerdown", function (e) {
      if (!colorPickerEl.contains(e.target) && !colorBtn.contains(e.target)) closeColorPicker(false);
    }, true);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && colorPickerEl.classList.contains("is-open")) {
        e.preventDefault(); closeColorPicker(true);
      }
    });
    function commitHex() {
      if (!readColor(hexInput.value)) { hexInput.setAttribute("aria-invalid", "true"); return; }
      hexInput.removeAttribute("aria-invalid"); previewColor(); commitColor();
    }
    hexInput.addEventListener("change", commitHex);
    hexInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); commitHex(); } });
    function updateOpacity() {
      if (!/^\d+(?:\.\d+)?%?$/.test(opacityInput.value.trim())) {
        opacityInput.setAttribute("aria-invalid", "true"); return;
      }
      opacityInput.removeAttribute("aria-invalid");
      alpha = clamp(parseFloat(opacityInput.value) / 100, 1); previewColor();
    }
    opacityInput.addEventListener("input", updateOpacity);
    opacityInput.addEventListener("change", function () { updateOpacity(); commitColor(); });
    opacityInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); updateOpacity(); commitColor(); }
    });
    swatches.forEach(function (swatch) {
      swatch.addEventListener("click", function () { readColor(swatch.dataset.color); previewColor(); commitColor(); });
    });
    [svArea, hueSlider, alphaSlider].forEach(function (slider) {
      slider.tabIndex = 0; slider.setAttribute("role", "slider");
      label(slider, slider === svArea ? "visual_saturation" : slider === hueSlider ? "visual_hue" : "visual_alpha");
      slider.setAttribute("aria-valuemin", "0"); slider.setAttribute("aria-valuemax", slider === hueSlider ? "360" : "100");
      slider.addEventListener("keydown", function (e) {
        if (!/^Arrow(Left|Right|Up|Down)$/.test(e.key)) return;
        e.preventDefault();
        var step = (e.shiftKey ? 10 : 1) * (/Right|Up/.test(e.key) ? 1 : -1);
        if (slider === hueSlider) hue = clamp(hue + step, 360);
        else if (slider === alphaSlider) alpha = clamp(alpha + step / 100, 1);
        else if (/Left|Right/.test(e.key)) saturation = clamp(saturation + step / 100, 1);
        else brightness = clamp(brightness + step / 100, 1);
        previewColor(); commitColor();
      });
      slider.addEventListener("pointerdown", function (e) {
        e.preventDefault(); slider.focus(); slider.setPointerCapture(e.pointerId);
        var rect = slider.getBoundingClientRect();
        function move(ev) {
          var x = clamp((ev.clientX - rect.left) / rect.width, 1);
          if (slider === hueSlider) hue = x * 360;
          else if (slider === alphaSlider) alpha = x;
          else { saturation = x; brightness = 1 - clamp((ev.clientY - rect.top) / rect.height, 1); }
          previewColor();
        }
        function finish(ev) {
          slider.removeEventListener("pointermove", move);
          slider.removeEventListener("pointerup", finish);
          slider.removeEventListener("pointercancel", finish);
          if (slider.hasPointerCapture(e.pointerId)) slider.releasePointerCapture(e.pointerId);
          if (ev.type === "pointercancel") closeColorPicker(false);
          else { move(ev); commitColor(); }
        }
        move(e);
        slider.addEventListener("pointermove", move);
        slider.addEventListener("pointerup", finish);
        slider.addEventListener("pointercancel", finish);
      });
    });
  }

  function ensureVisualOverlay() {
    if (overlayEl && overlayEl.isConnected) return;
    overlayEl = document.createElement("div");
    overlayEl.id = "dpb-selection-overlay";
    overlayEl.style.display = "none";
    var moveBody = document.createElement("div");
    moveBody.className = "dpb-move-body";
    overlayEl.appendChild(moveBody);

    var handles = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
    handles.forEach(function (h) {
      var handle = document.createElement("div");
      handle.className = "dpb-resize-handle dpb-handle-" + h;
      handle.setAttribute("data-handle", h);
      overlayEl.appendChild(handle);
      setupManipulation(handle, h);
    });

    guideV = document.createElement("div");
    guideV.id = "dpb-guide-v";
    guideV.className = "dpb-guide-line dpb-guide-v";
    guideH = document.createElement("div");
    guideH.id = "dpb-guide-h";
    guideH.className = "dpb-guide-line dpb-guide-h";

    dimensionHud = document.createElement("output");
    dimensionHud.id = "dpb-dimension-hud";
    dimensionHud.style.display = "none";
    overlayEl.appendChild(dimensionHud);
    ensureFloatRoot().appendChild(overlayEl);
    ensureFloatRoot().appendChild(guideV);
    ensureFloatRoot().appendChild(guideH);
    setupManipulation(moveBody, "");
  }

  function ensureTextToolbar() {
    if (toolbarEl && toolbarEl.isConnected) return;
    toolbarEl = document.createElement("div");
    toolbarEl.id = "dpb-text-toolbar";
    toolbarEl.style.display = "none";

    var btnB = document.createElement("button");
    btnB.type = "button";
    btnB.className = "dpb-tb-btn dpb-tb-bold";
    btnB.setAttribute("data-action", "bold");
    btnB.title = "";
    label(btnB, "visual_bold");
    btnB.innerHTML = "<b>B</b>";

    var btnI = document.createElement("button");
    btnI.type = "button";
    btnI.className = "dpb-tb-btn dpb-tb-italic";
    btnI.setAttribute("data-action", "italic");
    btnI.title = "";
    label(btnI, "visual_italic");
    btnI.innerHTML = "<i>I</i>";

    var btnU = document.createElement("button");
    btnU.type = "button";
    btnU.className = "dpb-tb-btn dpb-tb-underline";
    btnU.setAttribute("data-action", "underline");
    btnU.title = "";
    label(btnU, "visual_underline");
    btnU.innerHTML = "<u>U</u>";

    var btnS = document.createElement("button");
    btnS.type = "button";
    btnS.className = "dpb-tb-btn dpb-tb-strike";
    btnS.setAttribute("data-action", "strike");
    btnS.title = "";
    label(btnS, "visual_strikethrough");
    btnS.innerHTML = "<s>S</s>";

    var selectSize = document.createElement("select");
    selectSize.className = "dpb-tb-select";
    selectSize.setAttribute("data-action", "font-size");
    label(selectSize, "visual_fontSize");
    [12, 14, 16, 18, 20, 24, 32, 48].forEach(function (sz) {
      var opt = document.createElement("option");
      opt.value = String(sz);
      opt.textContent = String(sz);
      selectSize.appendChild(opt);
    });

    var colorBtn = document.createElement("button");
    colorBtn.type = "button";
    colorBtn.className = "dpb-tb-color-btn";
    colorBtn.setAttribute("data-action", "color");
    colorBtn.title = "";
    label(colorBtn, "visual_color");
    colorBtn.innerHTML = "<span>A</span><span class=\"dpb-tb-color-bar\"></span>";

    colorPickerEl = document.createElement("div");
    colorPickerEl.id = "dpb-color-picker";
    colorPickerEl.innerHTML =
      '<div class="dpb-cp-sv"><div class="dpb-cp-sv-thumb"></div></div>' +
      '<div class="dpb-cp-hue"><div class="dpb-cp-hue-thumb"></div></div>' +
      '<div class="dpb-cp-alpha"><div class="dpb-cp-alpha-thumb"></div></div>' +
      '<div class="dpb-cp-inputs">' +
      '<input class="dpb-cp-hex" value="#000000" data-dpb-label="visual_hex" />' +
      '<input class="dpb-cp-opacity" value="100%" data-dpb-label="visual_opacity" />' +
      '</div>' +
      '<div class="dpb-cp-swatches"></div>';

    colorPickerEl.querySelectorAll("[data-dpb-label]").forEach(function (control) { label(control, control.getAttribute("data-dpb-label")); });
    var swatchesContainer = colorPickerEl.querySelector(".dpb-cp-swatches");
    var swatches = ["#000000", "#ffffff", "#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#6366f1", "#8b5cf6"];
    swatches.forEach(function (c) {
      var sw = document.createElement("button");
      sw.type = "button";
      sw.className = "dpb-cp-swatch";
      sw.style.backgroundColor = c;
      sw.setAttribute("data-color", c);
      sw.setAttribute("aria-label", c);
      swatchesContainer.appendChild(sw);
    });

    toolbarEl.appendChild(btnB);
    toolbarEl.appendChild(btnI);
    toolbarEl.appendChild(btnU);
    toolbarEl.appendChild(btnS);
    toolbarEl.appendChild(selectSize);
    toolbarEl.appendChild(colorBtn);
    ensureFloatRoot().appendChild(colorPickerEl);

    ensureFloatRoot().appendChild(toolbarEl);
    setupToolbarActions(btnB, btnI, btnU, btnS, selectSize, colorBtn, colorPickerEl);
  }

  function syncToolbarState(el) {
    if (!toolbarEl || !el) return;
    var computed = window.getComputedStyle(el);
    var isBold = computed.fontWeight >= 600 || el.style.fontWeight === "bold" || el.style.fontWeight === "700";
    var isItalic = computed.fontStyle === "italic" || el.style.fontStyle === "italic";
    var hasU = (computed.textDecorationLine || "").indexOf("underline") >= 0 || (el.style.textDecoration || "").indexOf("underline") >= 0;
    var hasS = (computed.textDecorationLine || "").indexOf("line-through") >= 0 || (el.style.textDecoration || "").indexOf("line-through") >= 0;

    var btnB = toolbarEl.querySelector(".dpb-tb-bold");
    var btnI = toolbarEl.querySelector(".dpb-tb-italic");
    var btnU = toolbarEl.querySelector(".dpb-tb-underline");
    var btnS = toolbarEl.querySelector(".dpb-tb-strike");
    var sel = toolbarEl.querySelector(".dpb-tb-select");
    var bar = toolbarEl.querySelector(".dpb-tb-color-bar");

    if (btnB) btnB.classList.toggle("is-active", isBold);
    if (btnI) btnI.classList.toggle("is-active", isItalic);
    if (btnU) btnU.classList.toggle("is-active", hasU);
    if (btnS) btnS.classList.toggle("is-active", hasS);
    if (bar) bar.style.backgroundColor = computed.color;
    if (sel) {
      var pxVal = parseInt(computed.fontSize, 10);
      if (pxVal) sel.value = String(pxVal);
    }
  }

  function isTextElement(el) {
    var textKind = /^(P|SPAN|H[1-6]|A|BUTTON|LABEL|LI|BLOCKQUOTE|SMALL|STRONG|EM|B|I|U|S|TD|TH|DIV)$/;
    var hasDirectText = Array.from(el.childNodes).some(function (node) { return node.nodeType === 3 && node.textContent.trim(); });
    var hasBlockChildren = Array.from(el.children).some(function (child) {
      return !/^(inline|contents)/.test(getComputedStyle(child).display);
    });
    return textKind.test(el.tagName) && hasDirectText && !hasBlockChildren;
  }
  function updateOverlayPositions(el) {
    if (!el || !overlayEl) return;
    var rect = el.getBoundingClientRect();
    overlayEl.style.left = (window.scrollX + rect.left) + "px";
    overlayEl.style.top = (window.scrollY + rect.top) + "px";
    overlayEl.style.width = rect.width + "px";
    overlayEl.style.height = rect.height + "px";
    overlayEl.style.display = "block";

    if (toolbarEl) {
      var textOnly = !compactEditor && isTextElement(el);
      toolbarEl.style.display = textOnly ? "flex" : "none";
      if (textOnly) {
        var width = toolbarEl.offsetWidth, height = toolbarEl.offsetHeight;
        toolbarEl.style.left = (scrollX + Math.max(8, Math.min(innerWidth - width - 8, rect.left + (rect.width - width) / 2))) + "px";
        toolbarEl.style.top = (scrollY + (rect.top >= height + 12 ? rect.top - height - 12 : rect.bottom + 12)) + "px";
        syncToolbarState(el);
      }
      overlayEl.querySelectorAll('[role="slider"]').forEach(function (control) {
        var handle = control.getAttribute("data-handle");
        control.setAttribute("aria-valuemin", handle ? 10 : Math.min(0, rect.x));
        control.setAttribute("aria-valuemax", Math.max(innerWidth, innerHeight, rect.width, rect.height, rect.x));
        control.setAttribute("aria-valuenow", Math.round(handle && /[ew]/.test(handle) ? rect.width : handle ? rect.height : rect.x));
        control.setAttribute("aria-valuetext", handle ? text("visual_size_value", { w: Math.round(rect.width), h: Math.round(rect.height) }) :
          text("visual_position_value", { x: Math.round(rect.x), y: Math.round(rect.y) }));
      });
    }
  }
  function reportVisualSelection(el, replay, requestId) {
    if (!el) return;
    var selector = cssPath(el);
    if (!selector) return;
    if (visualSelectedEl && visualSelectedEl !== el) {
      if (closeColorPicker) closeColorPicker(false);
      visualSelectedEl.classList.remove("dpb-visual-edit-selected");
    }
    visualSelectedEl = el;
    el.classList.add("dpb-visual-edit-selected");
    ensureVisualOverlay();
    ensureTextToolbar();
    updateOverlayPositions(el);
    parent.postMessage({ dpbVisualEditSelection: {
      selector: selector, tag: el.tagName.toLowerCase(), textEditable: isTextElement(el),
      style: visualStyleSnapshot(el), replay: !!replay, requestId: requestId
    } }, "*");
  }
  function clearHover() {
    if (hoverEl) {
      hoverEl.classList.remove("dpb-pin-hover");
      hoverEl = null;
    }
  }
  document.addEventListener("mousemove", function (e) {
    if (!pinOn) return;  // #56: no dashed hover outline outside pin mode
    var el = e.target;
    if (!el || el === document.body || el === document.documentElement ||
        (el.closest && el.closest("#dpb-float-root"))) {
      clearHover();
      return;
    }
    if (hoverEl !== el) {
      clearHover();
      hoverEl = el;
      hoverEl.classList.add("dpb-pin-hover");
    }
  }, true);
  document.addEventListener("click", function (e) {
    // #56: outside pin mode the bridge must not swallow clicks — links,
    // buttons, tabs and forms inside the prototype stay fully interactive.
    if (!pinOn) return;
    var raw = e.target;
    if (!raw || raw === document.body || raw === document.documentElement) return;
    if (raw.closest && raw.closest("#dpb-float-root")) return;
    var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
    e.preventDefault();
    e.stopPropagation();
    // highlight reconciliation is syncAnchors' job — the parent echoes the
    // full list back after recording the anchor, so every pinned element
    // stays highlighted (not just the latest click).
    el.classList.add("dpb-pin-target");
    var selector = cssPath(el);
    if (!selector) return;
    // T-083 REC-01: report the element rect (iframe viewport coords) so the
    // parent can anchor the in-context draft popover next to the click.
    // Data-only (no parent DOM access) — the G5 safety contract is unchanged.
    var er = el.getBoundingClientRect();
    parent.postMessage({
      dpbPinAnchor: {
        selector: selector,
        tag: el.tagName.toLowerCase(),
        rect: { x: er.left, y: er.top, w: er.width, h: er.height },
      },
    }, "*");
    reportVisualSelection(el, false);
  }, true);

  // ---- #57 scheme A: cross-origin locate, flash and numbered badges ----
  function findEl(selector) {
    try { return document.querySelector(selector); } catch (err) { return null; }
  }
  function flashEl(el) {
    el.classList.remove("dpb-pin-flash");
    void el.offsetWidth;  // force reflow so the animation can restart
    el.classList.add("dpb-pin-flash");
  }
  function locateEl(el) {
    try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (err) {}
    flashEl(el);
  }
  var badgeMap = {};  // selector -> { n: span, note: div }
  function clearBadges() {
    for (var sel in badgeMap) {
      if (badgeMap[sel].n.parentNode) badgeMap[sel].n.parentNode.removeChild(badgeMap[sel].n);
      if (badgeMap[sel].note.parentNode) badgeMap[sel].note.parentNode.removeChild(badgeMap[sel].note);
    }
    badgeMap = {};
  }
  function placeBadge(entry) {
    var pair = badgeMap[entry.selector];
    var el = findEl(entry.selector);
    if (!el || !pair) return;
    var rect = el.getBoundingClientRect();
    var left = window.scrollX + rect.right + 6;
    var top = window.scrollY + rect.top - 9;
    // flip to the left side when the badge would run past the right edge
    if (rect.right + 40 > document.documentElement.clientWidth) {
      left = Math.max(window.scrollX + 4, window.scrollX + rect.left - 30);
    }
    pair.n.style.left = left + "px";
    pair.n.style.top = top + "px";
    pair.note.style.left = left + "px";
    pair.note.style.top = (top + 22) + "px";
  }
  function syncAnchors(list) {
    clearBadges();
    // Draw anchors have no cssPath to resolve — they render as strokes on
    // the in-frame draw layer instead of element outlines/badges.
    lastAnchorEcho = list || [];
    renderDrawItems(lastAnchorEcho);
    // #57: the parent's list is the single owner of the cross-origin
    // highlight too — removals and undo/redo must drop the teal outline
    // from elements whose anchor is gone (el is null cross-origin, so the
    // parent cannot clear them itself) and restore it for kept anchors,
    // mirroring the same-origin behavior.
    var keepEls = [];
    list.forEach(function (item) {
      if (item.tag === "draw") return;  // stroke anchors never match an element
      var keepEl = findEl(item.selector);
      if (keepEl) keepEls.push(keepEl);
    });
    var stale = document.querySelectorAll(".dpb-pin-target");
    for (var si = 0; si < stale.length; si++) {
      if (keepEls.indexOf(stale[si]) < 0) {
        stale[si].classList.remove("dpb-pin-target");
      }
    }
    keepEls.forEach(function (keepEl) {
      keepEl.classList.add("dpb-pin-target");
    });
    var body = document.body || document.documentElement;
    list.forEach(function (item) {
      if (item.tag === "draw") return;  // rendered by renderDrawItems
      var el = findEl(item.selector);
      if (!el) return;
      var n = document.createElement("span");
      n.className = "dpb-pin-badge" + (item.resolved ? " dpb-resolved" : "") + (item.active ? " dpb-active" : "") + (item.fresh ? " dpb-pin-drop" : "");
      n.setAttribute("aria-hidden", "true");
      n.textContent = String(item.n);
      if (item.fresh) {
        n.addEventListener("animationend", function () { this.classList.remove("dpb-pin-drop"); }, { once: true });
      }
      body.appendChild(n);
      var note = document.createElement("div");
      note.className = "dpb-pin-badge-note" + (item.resolved ? " dpb-resolved" : "");
      note.textContent = String(item.comment || "");
      note.style.display = item.comment ? "block" : "none";
      body.appendChild(note);
      badgeMap[item.selector] = { n: n, note: note };
      placeBadge({ selector: item.selector });
    });
  }
  var badgeTick = false;
  function repositionBadges() {
    if (badgeTick) return;
    badgeTick = true;
    window.requestAnimationFrame(function () {
      badgeTick = false;
      for (var sel in badgeMap) placeBadge({ selector: sel });
    });
  }
  window.addEventListener("scroll", function () {
    repositionBadges();
    if (visualSelectedEl) updateOverlayPositions(visualSelectedEl);
  }, true);
  window.addEventListener("resize", function () {
    if (visualSelectedEl) updateOverlayPositions(visualSelectedEl);
  });
  window.addEventListener("resize", repositionBadges);

  // ---- draw mode (圈画标注): freehand strokes captured in-frame ----
  // The stroke is drawn live on an in-frame SVG overlay (coordinates stay
  // local to this document); on pointerup the points travel to the parent,
  // which records the draw anchor and echoes it back via dpbPinAnchors for
  // the durable in-frame rendering below (renderDrawItems).
  var drawOn = false;
  var drawSvg = null;
  var livePts = null;
  var livePathEl = null;
  var rulerOn = false;
  var rulerSvg = null;
  var rulerHoverEl = null;
  var rulerPinnedPoint = null;
  var rulerSizeLabel = "{w}×{h} px";
  var rulerDistanceLabel = "{d} px";

  function ensureDrawLayer() {
    if (drawSvg && drawSvg.isConnected) return drawSvg;
    drawSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    drawSvg.setAttribute("id", "dpb-draw-layer");
    drawSvg.setAttribute("aria-hidden", "true");
    sizeDrawLayer();
    (document.body || document.documentElement).appendChild(drawSvg);
    return drawSvg;
  }
  function sizeDrawLayer() {
    if (!drawSvg) return;
    var d = document.documentElement;
    drawSvg.setAttribute("width", String(Math.max(d.scrollWidth, window.innerWidth)));
    drawSvg.setAttribute("height", String(Math.max(d.scrollHeight, window.innerHeight)));
    drawSvg.setAttribute("viewBox", "0 0 " + drawSvg.getAttribute("width") + " " + drawSvg.getAttribute("height"));
    drawSvg.setAttribute("preserveAspectRatio", "none");
  }
  window.addEventListener("resize", function () {
    if (drawSvg) { sizeDrawLayer(); renderDrawItems(lastAnchorEcho); }
    if (rulerSvg) sizeRulerLayer();
  });

  function ensureRulerLayer() {
    if (rulerSvg && rulerSvg.isConnected) return rulerSvg;
    rulerSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    rulerSvg.setAttribute("id", "dpb-ruler-layer");
    rulerSvg.setAttribute("aria-hidden", "true");
    sizeRulerLayer();
    (document.body || document.documentElement).appendChild(rulerSvg);
    return rulerSvg;
  }
  function sizeRulerLayer() {
    if (!rulerSvg) return;
    var d = document.documentElement;
    rulerSvg.setAttribute("width", String(Math.max(d.scrollWidth, window.innerWidth)));
    rulerSvg.setAttribute("height", String(Math.max(d.scrollHeight, window.innerHeight)));
    rulerSvg.setAttribute("viewBox", "0 0 " + rulerSvg.getAttribute("width") + " " + rulerSvg.getAttribute("height"));
    rulerSvg.setAttribute("preserveAspectRatio", "none");
  }
  function clearRuler() {
    rulerPinnedPoint = null;
    if (rulerHoverEl) rulerHoverEl.classList.remove("dpb-ruler-hover-target");
    rulerHoverEl = null;
    if (rulerSvg) rulerSvg.innerHTML = "";
  }
  function rulerText(key, values) {
    var text = key === "size" ? rulerSizeLabel : rulerDistanceLabel;
    Object.keys(values).forEach(function (k) { text = text.replace("{" + k + "}", String(values[k])); });
    return text;
  }
  function drawRulerBadge(x, y, label, className) {
    ensureRulerLayer();
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", className || "dpb-ruler-badge");
    var w = Math.max(34, String(label).length * 7 + 12);
    var bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", String(Math.max(0, x))); bg.setAttribute("y", String(Math.max(0, y)));
    bg.setAttribute("width", String(w)); bg.setAttribute("height", "18"); bg.setAttribute("rx", "9");
    var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", String(Math.max(0, x) + w / 2)); t.setAttribute("y", String(Math.max(14, y + 11)));
    t.setAttribute("text-anchor", "middle"); t.setAttribute("dy", "3.2"); t.textContent = String(label);
    g.appendChild(bg); g.appendChild(t); rulerSvg.appendChild(g);
    return g;
  }
  function showRulerHover(el) {
    ensureRulerLayer();
    var stale = rulerSvg.querySelectorAll(".dpb-ruler-badge.is-hover");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    if (rulerHoverEl && rulerHoverEl !== el) rulerHoverEl.classList.remove("dpb-ruler-hover-target");
    rulerHoverEl = el;
    if (!el || el === document.body || el === document.documentElement) return;
    el.classList.add("dpb-ruler-hover-target");
    var r = el.getBoundingClientRect();
    drawRulerBadge(window.scrollX + r.left + 6, Math.max(0, window.scrollY + r.top - 24), rulerText("size", {
      w: Math.round(r.width), h: Math.round(r.height)
    }), "dpb-ruler-badge is-hover");
  }
  function drawRulerLine(a, b) {
    ensureRulerLayer();
    var stale = rulerSvg.querySelectorAll(".dpb-ruler-line, .dpb-ruler-point, .dpb-ruler-badge.is-line");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(a[0])); line.setAttribute("y1", String(a[1]));
    line.setAttribute("x2", String(b[0])); line.setAttribute("y2", String(b[1]));
    line.setAttribute("class", "dpb-ruler-line"); rulerSvg.appendChild(line);
    [a, b].forEach(function (p) {
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(p[0])); c.setAttribute("cy", String(p[1])); c.setAttribute("r", "4");
      c.setAttribute("class", "dpb-ruler-point"); rulerSvg.appendChild(c);
    });
    var dx = b[0] - a[0], dy = b[1] - a[1];
    drawRulerBadge((a[0] + b[0]) / 2 + 6, (a[1] + b[1]) / 2 - 24, rulerText("distance", {
      d: Math.round(Math.sqrt(dx * dx + dy * dy))
    }), "dpb-ruler-badge is-line");
  }

  function drawPathD(points) {
    if (!points || !points.length) return "";
    var d = "";
    for (var i = 0; i < points.length; i++) {
      d += (i ? "L" : "M") + Number(points[i][0]).toFixed(1) + " " + Number(points[i][1]).toFixed(1);
    }
    return d + (points.length > 2 ? " Z" : "");
  }

  function cancelLiveStroke() {
    livePts = null;
    if (livePathEl && livePathEl.parentNode) livePathEl.parentNode.removeChild(livePathEl);
    livePathEl = null;
  }

  document.addEventListener("pointerdown", function (e) {
    if (!drawOn) return;  // passive outside draw mode
    e.preventDefault();
    e.stopPropagation();
    ensureDrawLayer();
    livePts = [[e.clientX + window.scrollX, e.clientY + window.scrollY]];
    livePathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    livePathEl.setAttribute("class", "dpb-draw-path dpb-draw-live");
    drawSvg.appendChild(livePathEl);
  }, true);
  document.addEventListener("pointermove", function (e) {
    if (!drawOn || !livePts) return;
    e.preventDefault();
    var p = [e.clientX + window.scrollX, e.clientY + window.scrollY];
    var last = livePts[livePts.length - 1];
    var dx = p[0] - last[0], dy = p[1] - last[1];
    if (dx * dx + dy * dy < 4) return;  // sub-2px moves add no shape
    if (livePts.length >= 512) return;  // keep the anchors JSON lean
    livePts.push(p);
    if (livePathEl) livePathEl.setAttribute("d", drawPathD(livePts));
  }, true);
  document.addEventListener("pointerup", function (e) {
    if (!drawOn || !livePts) return;
    e.preventDefault();
    var pts = livePts;
    cancelLiveStroke();
    if (pts.length >= 4) {
      parent.postMessage({ dpbDrawStroke: { points: pts } }, "*");
    }
  }, true);

  document.addEventListener("mousemove", function (e) {
    if (!rulerOn) return;
    showRulerHover(e.target);
  }, true);
  document.addEventListener("click", function (e) {
    if (!rulerOn) return;
    e.preventDefault();
    e.stopPropagation();
    var pt = [e.clientX + window.scrollX, e.clientY + window.scrollY];
    if (!rulerPinnedPoint) {
      rulerPinnedPoint = pt;
      drawRulerLine(pt, pt);
    } else {
      drawRulerLine(rulerPinnedPoint, pt);
      rulerPinnedPoint = null;
    }
  }, true);

  function setDrawOn(on) {
    drawOn = !!on;
    if (!on) cancelLiveStroke();
    document.documentElement.classList.toggle("dpb-draw-mode", drawOn);
  }

  // Durable rendering of the parent's draw anchors (echoed via dpbPinAnchors).
  var lastAnchorEcho = [];
  function renderDrawItems(list) {
    lastAnchorEcho = list || [];
    var items = (list || []).filter(function (it) {
      return it.tag === "draw" && it.points && it.points.length;
    });
    if (!items.length && !drawSvg) return;
    ensureDrawLayer();
    var stale = drawSvg.querySelectorAll(".dpb-draw-path, .dpb-draw-badge, .dpb-draw-live");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    (list || []).forEach(function (item) {
      if (item.tag !== "draw" || !item.points || !item.points.length) return;
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", drawPathD(item.points));
      path.setAttribute("class", "dpb-draw-path");
      path.setAttribute("data-draw-n", String(item.n));
      drawSvg.appendChild(path);
      var p0 = item.points[0];
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "dpb-draw-badge");
      g.setAttribute("transform", "translate(" + Number(p0[0]).toFixed(1) + "," + Math.max(9, Number(p0[1]) - 12).toFixed(1) + ")");
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "9");
      c.setAttribute("class", "dpb-draw-badge-c");
      var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("dy", "3.2");
      t.textContent = String(item.n);
      g.appendChild(c); g.appendChild(t);
      drawSvg.appendChild(g);
    });
  }

  document.addEventListener("keydown", function (e) {
    var el = e.target;
    if (e.isComposing || e.keyCode === 229 || e.repeat || e.altKey || e.defaultPrevented) return;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    var key = e.key === "Escape" ? e.key : e.key.toLowerCase();
    if (e.ctrlKey || e.metaKey) {
      if (["enter", "z", "y"].indexOf(key) < 0) return;
    } else if (["Escape", "b", "d", "h", "p", "r", "v", "l", "[", "]", "?", "j", "k", "s", "delete", "backspace", "=", "+", "-", "_", "0", "1", "2", "3"].indexOf(key) < 0) return;
    e.preventDefault();
    // Only key metadata crosses; the parent's decision token never does.
    parent.postMessage({ dpbReviewShortcut: { key: /^(enter|delete|backspace)$/.test(key) ? e.key : key,
      ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey } }, "*");
  });

  window.addEventListener("message", function (e) {
    // W3: only the parent window may drive the bridge. The prototype scripts
    // share this window and must not be able to spoof pin state or badges.
    if (e.source !== window.parent) return;
    var data = e.data;
    if (!data) return;
    if (data.dpbPinState) {
      // #56: parent is the single owner of the pin state.
      pinOn = !!data.dpbPinState.on;
      if (!pinOn) clearHover();
      return;
    }
    if (data.dpbVisualEdit) {
      var edit = data.dpbVisualEdit;
      if (edit.type === "localize") { localize(edit.labels); return; }
      if (edit.type === "ping") {
        localize(edit.labels);
        if (compactEditor !== !!edit.compact) {
          compactEditor = !!edit.compact;
          if (visualSelectedEl) updateOverlayPositions(visualSelectedEl);
        }
        parent.postMessage({ dpbVisualEditReady: { bridgeVersion: 1, nonce: edit.nonce, routeUrl: location.href } }, "*");
        return;
      }
      if (edit.type === "select") {
        var selected = findEl(String(edit.selector || ""));
        if (selected) reportVisualSelection(selected, !!edit.replay);
        return;
      }
      if (edit.type === "close-color-picker") { if (closeColorPicker) closeColorPicker(false); return; }
      if (edit.type === "open-color-picker") {
        var colorTarget = findEl(String(edit.selector || ""));
        if (colorTarget && ["color", "background-color", "border-color"].indexOf(edit.property) >= 0) {
          if (visualSelectedEl !== colorTarget) reportVisualSelection(colorTarget, false);
          openColorPicker(edit.property, null);
        }
        return;
      }
      if (edit.type === "set-style" || edit.type === "resize" || edit.type === "move") {
        var target = edit.selector ? findEl(String(edit.selector)) : visualSelectedEl;
        var mutations = edit.changes || [{ property: String(edit.property || ""), value: String(edit.value == null ? "" : edit.value) }];
        if (edit.type === "resize") {
          mutations = ["width", "height"].filter(function (p) { return edit[p] != null; }).map(function (p) {
            var value = String(edit[p]);
            return { property: p, value: /^-?(?:\d+\.?\d*|\.\d+)$/.test(value) ? value + "px" : value };
          });
        }
        if (edit.type === "move") {
          var dx = Number(edit.dx || 0), dy = Number(edit.dy || 0);
          mutations = [{ property: "transform", value: Number.isFinite(dx) && Number.isFinite(dy) && target ?
            translated(target.style.transform || getComputedStyle(target).transform, dx, dy) : "invalid" }];
        }
        var valid = Array.isArray(mutations) && mutations.length > 0 && mutations.length <= 32 && mutations.every(function (m) {
          return m && typeof m.property === "string" && /^[A-Za-z-]{1,64}$/.test(m.property) &&
            typeof m.value === "string" && (m.value === "" || CSS.supports(m.property, m.value));
        });
        if (!target || !valid) {
          parent.postMessage({ dpbVisualEditRejected: { requestId: edit.requestId,
            code: !target ? "visual_target_missing" : "visual_rejected" } }, "*");
          return;
        }
        var changes = inlineValues(target, mutations.map(function (m) { return m.property; }));
        mutations.forEach(function (m) { target.style.setProperty(m.property, m.value); });
        finishVisualChange(target, changes, edit.requestId, edit.replay);
        return;
      }
      return;
    }
    if (data.dpbDrawState) {
      // Draw mode mirrors pin ownership: the parent flips it, the bridge
      // only obeys. OFF means fully passive - pointer events pass through.
      setDrawOn(!!data.dpbDrawState.on);
      return;
    }
    if (data.dpbRulerState) {
      rulerOn = !!data.dpbRulerState.on;
      if (data.dpbRulerState.sizeLabel) rulerSizeLabel = String(data.dpbRulerState.sizeLabel);
      if (data.dpbRulerState.distanceLabel) rulerDistanceLabel = String(data.dpbRulerState.distanceLabel);
      if (!rulerOn) clearRuler();
      return;
    }
    if (data.dpbPinLocate) {
      var locEl = findEl(String(data.dpbPinLocate.selector || ""));
      if (locEl) locateEl(locEl);
      return;
    }
    if (data.dpbDrawLocate) {
      var targetN = String(data.dpbDrawLocate.n || "");
      var targetPath = drawSvg ? drawSvg.querySelector('.dpb-draw-path[data-draw-n="' + targetN + '"]') : null;
      if (targetPath) {
        targetPath.classList.remove("dpb-draw-flash");
        void targetPath.offsetWidth;
        targetPath.classList.add("dpb-draw-flash");
      }
      for (var di = 0; di < (lastAnchorEcho || []).length; di++) {
        var dItem = lastAnchorEcho[di];
        if (dItem.tag === "draw" && String(dItem.n) === targetN && dItem.points && dItem.points[0]) {
          try {
            window.scrollTo({
              left: Math.max(0, Number(dItem.points[0][0]) - 100),
              top: Math.max(0, Number(dItem.points[0][1]) - 100),
              behavior: "smooth"
            });
          } catch (err) {}
          break;
        }
      }
      return;
    }
    if (data.dpbPinFlash) {
      var flashTarget = findEl(String(data.dpbPinFlash.selector || ""));
      if (flashTarget) flashEl(flashTarget);
      return;
    }
    if (data.dpbPinNote) {
      // #57: one badge note updated in place — per-keystroke comment edits
      // must not clear and rebuild the whole badge set.
      var noteSel = String(data.dpbPinNote.selector || "");
      var pair = badgeMap[noteSel];
      if (pair) {
        var noteText = String(data.dpbPinNote.comment || "");
        pair.note.textContent = noteText;
        pair.note.style.display = noteText ? "block" : "none";
        placeBadge({ selector: noteSel });
      }
      return;
    }
    if (Array.isArray(data.dpbPinAnchors)) {
      syncAnchors(data.dpbPinAnchors);
    }
  });
  // Ask the parent for a pin-state resend after (re)load so a refresh never
  // strands the bridge in the wrong mode.
  parent.postMessage({ dpbPinHello: true }, "*");
})();
</script>"""


BRIDGE_SCRIPT = BRIDGE_SCRIPT.replace("__DPB_VISUAL_LABELS__", json.dumps(
    {key: value for key, value in _STRINGS[ZH].items() if key.startswith("visual_")},
    ensure_ascii=True,
))

def build_visual_edit_bridge_script() -> str:
    """Host opt-in: embed this script in the loopback page used as live_route_url.

    Only the sandbox parent can issue preview commands. This never writes host
    source; include the bridge before starting a review so served bytes stay stable.
    """
    return BRIDGE_SCRIPT
