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
    "@media (prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;" +
    "transition-duration:1ms!important;transition-delay:0ms!important}" +
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
  function clearHover() {
    if (hoverEl) {
      hoverEl.classList.remove("dpb-pin-hover");
      hoverEl = null;
    }
  }
  document.addEventListener("mousemove", function (e) {
    if (!pinOn) return;  // #56: no dashed hover outline outside pin mode
    var el = e.target;
    if (!el || el === document.body || el === document.documentElement) {
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
    var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
    e.preventDefault();
    e.stopPropagation();
    // highlight reconciliation is syncAnchors' job — the parent echoes the
    // full list back after recording the anchor, so every pinned element
    // stays highlighted (not just the latest click).
    el.classList.add("dpb-pin-target");
    var selector = cssPath(el);
    if (!selector) return;
    parent.postMessage({ dpbPinAnchor: { selector: selector, tag: el.tagName.toLowerCase() } }, "*");
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
  window.addEventListener("scroll", repositionBadges, true);
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
