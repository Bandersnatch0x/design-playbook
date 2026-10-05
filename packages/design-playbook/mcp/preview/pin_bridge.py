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

BRIDGE_SCRIPT = r"""<script>
(function () {
  // Inject the pin highlight + badge CSS into the iframe document. The
  // parent's control-bar stylesheet does not cross the iframe boundary, so the
  // bridge brings its own copy of .dpb-pin-target / .dpb-pin-hover (the same
  // rules control.py renders in the parent) plus the numbered annotation
  // badges (.dpb-pin-badge*, #57 scheme A) to render them in-frame.
  var style = document.createElement("style");
  style.textContent =
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
    "#dpb-text-toolbar{position:absolute;z-index:2147483010;display:flex;align-items:center;gap:3px;" +
    "padding:3px 6px;border-radius:8px;background:#1e293b;color:#f8fafc;border:1px solid #334155;" +
    "box-shadow:0 4px 16px rgba(0,0,0,.3);pointer-events:auto;user-select:none;font:12px/1 system-ui,sans-serif}" +
    ".dpb-tb-btn{background:transparent;border:1px solid transparent;color:#e2e8f0;border-radius:4px;" +
    "width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;padding:0}" +
    ".dpb-tb-btn:hover{background:rgba(255,255,255,.1)}" +
    ".dpb-tb-btn.is-active{background:#2563EB;color:#fff}" +
    ".dpb-tb-select{height:24px;font-size:11px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;padding:0 3px}" +
    ".dpb-tb-color-btn{position:relative;width:24px;height:24px;display:inline-flex;flex-direction:column;" +
    "align-items:center;justify-content:center;background:transparent;border:1px solid transparent;color:#e2e8f0;border-radius:4px;cursor:pointer;padding:0;font-size:11px;font-weight:700}" +
    ".dpb-tb-color-bar{width:14px;height:3px;border-radius:1px;background:#2563EB;margin-top:1px}" +
    "#dpb-color-picker{position:absolute;top:calc(100% + 6px);left:0;background:#1e293b;border:1px solid #334155;" +
    "border-radius:8px;padding:8px;box-shadow:0 8px 24px rgba(0,0,0,.4);display:none;flex-direction:column;gap:8px;width:190px;z-index:2147483015}" +
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
  var guideV = null;
  var guideH = null;
  var colorPickerEl = null;

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

  function checkGuides(targetRect) {
    if (!guideV || !guideH) return;
    var candidates = Array.prototype.slice.call(document.body.querySelectorAll("*")).filter(function (cand) {
      if (cand === visualSelectedEl) return false;
      if (cand.id === "dpb-selection-overlay" || cand.closest("#dpb-selection-overlay, #dpb-text-toolbar, #dpb-draw-layer, #dpb-ruler-layer")) return false;
      return cand.nodeType === 1 && cand.offsetWidth > 0 && cand.offsetHeight > 0;
    });

    var matchV = null;
    var matchH = null;
    var threshold = 6;
    var targetEdgesX = [targetRect.left, targetRect.left + targetRect.width / 2, targetRect.right];
    var targetEdgesY = [targetRect.top, targetRect.top + targetRect.height / 2, targetRect.bottom];

    for (var i = 0; i < candidates.length; i++) {
      var cr = candidates[i].getBoundingClientRect();
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

  function setupHandleDrag() {
    overlayEl.addEventListener("pointerdown", function (e) {
      var handle = e.target.getAttribute("data-handle");
      if (!handle || !visualSelectedEl) return;
      e.preventDefault();
      e.stopPropagation();
      e.target.setPointerCapture(e.pointerId);

      var el = visualSelectedEl;
      var startX = e.clientX, startY = e.clientY;
      var rect = el.getBoundingClientRect();
      var startW = rect.width, startH = rect.height;
      var oldW = el.style.width || window.getComputedStyle(el).width;
      var oldH = el.style.height || window.getComputedStyle(el).height;

      function onPointerMove(ev) {
        ev.preventDefault();
        var dx = ev.clientX - startX;
        var dy = ev.clientY - startY;
        var newW = startW, newH = startH;

        if (handle === "e" || handle === "se" || handle === "ne") newW = startW + dx;
        if (handle === "w" || handle === "sw" || handle === "nw") newW = startW - dx;
        if (handle === "s" || handle === "se" || handle === "sw") newH = startH + dy;
        if (handle === "n" || handle === "ne" || handle === "nw") newH = startH - dy;

        newW = Math.max(10, Math.round(newW));
        newH = Math.max(10, Math.round(newH));

        el.style.width = newW + "px";
        el.style.height = newH + "px";

        updateOverlayPositions(el);
        checkGuides(el.getBoundingClientRect());
      }

      function onPointerUp(ev) {
        ev.preventDefault();
        hideGuides();
        e.target.removeEventListener("pointermove", onPointerMove);
        e.target.removeEventListener("pointerup", onPointerUp);
        try { e.target.releasePointerCapture(e.pointerId); } catch (err) {}

        reportVisualSelection(el, false);
        parent.postMessage({ dpbVisualEditChange: {
          requestId: 0, selector: cssPath(el), property: "width",
          oldValue: oldW, newValue: el.style.width
        } }, "*");
        parent.postMessage({ dpbVisualEditChange: {
          requestId: 0, selector: cssPath(el), property: "height",
          oldValue: oldH, newValue: el.style.height
        } }, "*");
      }

      e.target.addEventListener("pointermove", onPointerMove);
      e.target.addEventListener("pointerup", onPointerUp);
    });
  }

  function setupMoveDrag(moveBody) {
    moveBody.addEventListener("pointerdown", function (e) {
      if (!visualSelectedEl) return;
      e.preventDefault();
      e.stopPropagation();
      moveBody.setPointerCapture(e.pointerId);

      var el = visualSelectedEl;
      var startX = e.clientX, startY = e.clientY;
      var oldTransform = el.style.transform || window.getComputedStyle(el).transform;
      var curMatch = (el.style.transform || "").match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/);
      var initDx = curMatch ? parseFloat(curMatch[1]) : 0;
      var initDy = curMatch ? parseFloat(curMatch[2]) : 0;

      function onMove(ev) {
        ev.preventDefault();
        var dx = ev.clientX - startX;
        var dy = ev.clientY - startY;
        el.style.transform = "translate(" + Math.round(initDx + dx) + "px, " + Math.round(initDy + dy) + "px)";
        updateOverlayPositions(el);
        checkGuides(el.getBoundingClientRect());
      }

      function onUp(ev) {
        ev.preventDefault();
        hideGuides();
        moveBody.removeEventListener("pointermove", onMove);
        moveBody.removeEventListener("pointerup", onUp);
        try { moveBody.releasePointerCapture(e.pointerId); } catch (err) {}

        reportVisualSelection(el, false);
        parent.postMessage({ dpbVisualEditChange: {
          requestId: 0, selector: cssPath(el), property: "transform",
          oldValue: oldTransform, newValue: el.style.transform
        } }, "*");
      }

      moveBody.addEventListener("pointermove", onMove);
      moveBody.addEventListener("pointerup", onUp);
    });
  }

  function setupToolbarActions(btnB, btnI, btnU, btnS, selectSize, colorBtn, colorPickerEl) {
    function applyStyleChange(prop, val) {
      if (!visualSelectedEl) return;
      var el = visualSelectedEl;
      var oldVal = el.style.getPropertyValue(prop) || window.getComputedStyle(el).getPropertyValue(prop);
      el.style.setProperty(prop, val);
      reportVisualSelection(el, false);
      parent.postMessage({ dpbVisualEditChange: {
        requestId: 0, selector: cssPath(el), property: prop,
        oldValue: oldVal, newValue: val
      } }, "*");
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

    colorBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      colorPickerEl.classList.toggle("is-open");
    });

    var hexInput = colorPickerEl.querySelector(".dpb-cp-hex");
    function commitHex(hex) {
      if (!visualSelectedEl || !hex) return;
      applyStyleChange("color", hex);
      var bar = toolbarEl.querySelector(".dpb-tb-color-bar");
      if (bar) bar.style.backgroundColor = hex;
    }

    hexInput.addEventListener("change", function (e) { commitHex(e.target.value); });
    hexInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); commitHex(e.target.value); }
    });

    var swatches = colorPickerEl.querySelectorAll(".dpb-cp-swatch");
    for (var i = 0; i < swatches.length; i++) {
      swatches[i].addEventListener("click", function (e) {
        var c = this.getAttribute("data-color");
        hexInput.value = c;
        commitHex(c);
      });
    }

    var svArea = colorPickerEl.querySelector(".dpb-cp-sv");
    var svThumb = colorPickerEl.querySelector(".dpb-cp-sv-thumb");
    var currentHue = 0;

    function updateColorFromSV(x, y, w, h) {
      var s = Math.max(0, Math.min(1, x / w));
      var v = Math.max(0, Math.min(1, 1 - y / h));
      var rgb = hsvToRgb(currentHue, s, v);
      var hex = rgbToHex(rgb[0], rgb[1], rgb[2]);
      hexInput.value = hex;
      svThumb.style.left = (s * 100) + "%";
      svThumb.style.top = ((1 - v) * 100) + "%";
      commitHex(hex);
    }

    svArea.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var r = svArea.getBoundingClientRect();
      updateColorFromSV(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
      function onMove(ev) {
        updateColorFromSV(ev.clientX - r.left, ev.clientY - r.top, r.width, r.height);
      }
      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });

    var hueSlider = colorPickerEl.querySelector(".dpb-cp-hue");
    var hueThumb = colorPickerEl.querySelector(".dpb-cp-hue-thumb");
    function updateHue(x, w) {
      currentHue = Math.max(0, Math.min(360, (x / w) * 360));
      hueThumb.style.left = (currentHue / 360 * 100) + "%";
      var rgb = hsvToRgb(currentHue, 1, 1);
      svArea.style.backgroundColor = "rgb(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ")";
      var curS = parseFloat(svThumb.style.left || "100") / 100;
      var curV = 1 - parseFloat(svThumb.style.top || "0") / 100;
      var finalRgb = hsvToRgb(currentHue, curS, curV);
      var hex = rgbToHex(finalRgb[0], finalRgb[1], finalRgb[2]);
      hexInput.value = hex;
      commitHex(hex);
    }

    hueSlider.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      var r = hueSlider.getBoundingClientRect();
      updateHue(e.clientX - r.left, r.width);
      function onMove(ev) { updateHue(ev.clientX - r.left, r.width); }
      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
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
    });

    guideV = document.createElement("div");
    guideV.id = "dpb-guide-v";
    guideV.className = "dpb-guide-line dpb-guide-v";
    guideH = document.createElement("div");
    guideH.id = "dpb-guide-h";
    guideH.className = "dpb-guide-line dpb-guide-h";

    (document.body || document.documentElement).appendChild(overlayEl);
    (document.body || document.documentElement).appendChild(guideV);
    (document.body || document.documentElement).appendChild(guideH);

    setupHandleDrag();
    setupMoveDrag(moveBody);
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
    btnB.setAttribute("aria-label", "Bold");
    btnB.title = "Bold";
    btnB.innerHTML = "<b>B</b>";

    var btnI = document.createElement("button");
    btnI.type = "button";
    btnI.className = "dpb-tb-btn dpb-tb-italic";
    btnI.setAttribute("data-action", "italic");
    btnI.setAttribute("aria-label", "Italic");
    btnI.title = "Italic";
    btnI.innerHTML = "<i>I</i>";

    var btnU = document.createElement("button");
    btnU.type = "button";
    btnU.className = "dpb-tb-btn dpb-tb-underline";
    btnU.setAttribute("data-action", "underline");
    btnU.setAttribute("aria-label", "Underline");
    btnU.title = "Underline";
    btnU.innerHTML = "<u>U</u>";

    var btnS = document.createElement("button");
    btnS.type = "button";
    btnS.className = "dpb-tb-btn dpb-tb-strike";
    btnS.setAttribute("data-action", "strike");
    btnS.setAttribute("aria-label", "Strikethrough");
    btnS.title = "Strikethrough";
    btnS.innerHTML = "<s>S</s>";

    var selectSize = document.createElement("select");
    selectSize.className = "dpb-tb-select";
    selectSize.setAttribute("data-action", "font-size");
    selectSize.setAttribute("aria-label", "Font size");
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
    colorBtn.setAttribute("aria-label", "Text color");
    colorBtn.title = "Text color";
    colorBtn.innerHTML = "<span>A</span><span class=\"dpb-tb-color-bar\"></span>";

    colorPickerEl = document.createElement("div");
    colorPickerEl.id = "dpb-color-picker";
    colorPickerEl.innerHTML =
      '<div class="dpb-cp-sv"><div class="dpb-cp-sv-thumb"></div></div>' +
      '<div class="dpb-cp-hue"><div class="dpb-cp-hue-thumb"></div></div>' +
      '<div class="dpb-cp-alpha"><div class="dpb-cp-alpha-thumb"></div></div>' +
      '<div class="dpb-cp-inputs">' +
      '<input class="dpb-cp-hex" value="#000000" aria-label="Hex color" />' +
      '<input class="dpb-cp-opacity" value="100%" aria-label="Opacity" />' +
      '</div>' +
      '<div class="dpb-cp-swatches"></div>';

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
    toolbarEl.appendChild(colorPickerEl);

    (document.body || document.documentElement).appendChild(toolbarEl);
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
    var hexInput = toolbarEl.querySelector(".dpb-cp-hex");

    if (btnB) btnB.classList.toggle("is-active", isBold);
    if (btnI) btnI.classList.toggle("is-active", isItalic);
    if (btnU) btnU.classList.toggle("is-active", hasU);
    if (btnS) btnS.classList.toggle("is-active", hasS);
    if (bar) bar.style.backgroundColor = computed.color;
    if (hexInput) hexInput.value = computed.color;
    if (sel) {
      var pxVal = parseInt(computed.fontSize, 10);
      if (pxVal) sel.value = String(pxVal);
    }
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
      toolbarEl.style.left = (window.scrollX + rect.left + rect.width / 2) + "px";
      toolbarEl.style.top = Math.max(window.scrollY + 4, window.scrollY + rect.top - 42) + "px";
      toolbarEl.style.transform = "translateX(-50%)";
      toolbarEl.style.display = "flex";
      syncToolbarState(el);
    }
  }
  function reportVisualSelection(el, replay, requestId) {
    if (!el) return;
    var selector = cssPath(el);
    if (!selector) return;
    if (visualSelectedEl && visualSelectedEl !== el) {
      visualSelectedEl.classList.remove("dpb-visual-edit-selected");
    }
    visualSelectedEl = el;
    el.classList.add("dpb-visual-edit-selected");
    ensureVisualOverlay();
    ensureTextToolbar();
    updateOverlayPositions(el);
    parent.postMessage({ dpbVisualEditSelection: {
      selector: selector, tag: el.tagName.toLowerCase(),
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
        (el.closest && el.closest("#dpb-selection-overlay, #dpb-text-toolbar"))) {
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
    if (raw.closest && raw.closest("#dpb-selection-overlay, #dpb-text-toolbar")) return;
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
      n.className = "dpb-pin-badge" + (item.active ? " dpb-active" : "") + (item.fresh ? " dpb-pin-drop" : "");
      n.setAttribute("aria-hidden", "true");
      n.textContent = String(item.n);
      if (item.fresh) {
        n.addEventListener("animationend", function () { this.classList.remove("dpb-pin-drop"); }, { once: true });
      }
      body.appendChild(n);
      var note = document.createElement("div");
      note.className = "dpb-pin-badge-note";
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
    if (e.isComposing || e.keyCode === 229 || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    var key = e.key === "Escape" ? e.key : e.key.toLowerCase();
    if ((key === "Escape" && e.shiftKey) || ["Escape", "b", "d", "h", "p", "r", "v"].indexOf(key) < 0) return;
    e.preventDefault();
    parent.postMessage({ dpbToolShortcut: key }, "*");
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
      if (edit.type === "ping") {
        parent.postMessage({ dpbVisualEditReady: { bridgeVersion: 1, nonce: edit.nonce, routeUrl: location.href } }, "*");
        return;
      }
      if (edit.type === "select") {
        var selected = findEl(String(edit.selector || ""));
        if (selected) reportVisualSelection(selected, !!edit.replay);
        return;
      }
      if (edit.type === "set-style") {
        var target = edit.selector ? findEl(String(edit.selector)) : visualSelectedEl;
        var property = String(edit.property || "");
        var newValue = String(edit.value == null ? "" : edit.value);
        var code = !target ? "visual_target_missing" : "visual_rejected";
        if (!target || !/^[A-Za-z-]{1,64}$/.test(property) ||
            (newValue !== "" && !CSS.supports(property, newValue))) {
          parent.postMessage({ dpbVisualEditRejected: { requestId: edit.requestId, code: code } }, "*");
          return;
        }
        var oldValue = target.style.getPropertyValue(property);
        target.style.setProperty(property, newValue);
        var acceptedValue = target.style.getPropertyValue(property);
        reportVisualSelection(target, !!edit.replay, edit.requestId);
        parent.postMessage({ dpbVisualEditChange: {
          requestId: edit.requestId, selector: cssPath(target), property: property,
          oldValue: oldValue, newValue: acceptedValue, replay: !!edit.replay
        } }, "*");
        return;
      }
      if (edit.type === "resize") {
        var target = edit.selector ? findEl(String(edit.selector)) : visualSelectedEl;
        if (!target) {
          parent.postMessage({ dpbVisualEditRejected: { requestId: edit.requestId, code: "visual_target_missing" } }, "*");
          return;
        }
        var oldW = target.style.width || window.getComputedStyle(target).width;
        var oldH = target.style.height || window.getComputedStyle(target).height;
        var newW = edit.width == null ? "" : String(edit.width);
        var newH = edit.height == null ? "" : String(edit.height);
        if (newW && !/px|%|em|rem|vw|vh|auto$/.test(newW)) newW += "px";
        if (newH && !/px|%|em|rem|vw|vh|auto$/.test(newH)) newH += "px";
        if (newW) target.style.setProperty("width", newW);
        if (newH) target.style.setProperty("height", newH);
        reportVisualSelection(target, !!edit.replay, edit.requestId);
        if (newW) {
          parent.postMessage({ dpbVisualEditChange: {
            requestId: edit.requestId, selector: cssPath(target), property: "width",
            oldValue: oldW, newValue: target.style.width, replay: !!edit.replay
          } }, "*");
        }
        if (newH) {
          parent.postMessage({ dpbVisualEditChange: {
            requestId: edit.requestId, selector: cssPath(target), property: "height",
            oldValue: oldH, newValue: target.style.height, replay: !!edit.replay
          } }, "*");
        }
        return;
      }
      if (edit.type === "move") {
        var target = edit.selector ? findEl(String(edit.selector)) : visualSelectedEl;
        if (!target) {
          parent.postMessage({ dpbVisualEditRejected: { requestId: edit.requestId, code: "visual_target_missing" } }, "*");
          return;
        }
        var oldTransform = target.style.transform || window.getComputedStyle(target).transform;
        var newTransform = "translate(" + (edit.dx || 0) + "px, " + (edit.dy || 0) + "px)";
        target.style.setProperty("transform", newTransform);
        reportVisualSelection(target, !!edit.replay, edit.requestId);
        parent.postMessage({ dpbVisualEditChange: {
          requestId: edit.requestId, selector: cssPath(target), property: "transform",
          oldValue: oldTransform, newValue: target.style.transform, replay: !!edit.replay
        } }, "*");
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


def build_visual_edit_bridge_script() -> str:
    """Host opt-in: embed this script in the loopback page used as live_route_url.

    Only the sandbox parent can issue preview commands. This never writes host
    source; include the bridge before starting a review so served bytes stay stable.
    """
    return BRIDGE_SCRIPT
