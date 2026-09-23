(function () {
  "use strict";

  // ---- theme bootstrap (host preference, stored choice, system fallback) ----
  var root = document.getElementById("dpb-root");
  var floatRoot = document.getElementById("dpb-float-root");
  var toastsRoot = document.getElementById("dpb-toasts");
  var THEME_STORAGE_KEY = "dpb.preview.theme";

  var colorScheme = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  function explicitTheme(el) {
    if (!el) return null;
    var v = el.getAttribute("data-theme");
    if (v === "light" || v === "dark") return v;
    if (el.classList.contains("theme-light")) return "light";
    if (el.classList.contains("theme-dark")) return "dark";
    return null;
  }

  function storedTheme() {
    try {
      var v = localStorage.getItem(THEME_STORAGE_KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) { return null; }
  }

  var THEME_ICONS = {
    light: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.2 10.6A5.6 5.6 0 0 1 5.4 2.8 6.1 6.1 0 1 0 13.2 10.6Z"/></svg>',
    dark: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="3.1"/><path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1"/></svg>',
  };

  function updateThemeIcon(theme) {
    var icon = document.getElementById("dpb-theme-icon");
    if (icon) icon.innerHTML = THEME_ICONS[theme === "dark" ? "dark" : "light"];
  }

  function applyTheme(theme, persist) {
    if (!root) return;
    root.setAttribute("data-theme", theme);
    if (floatRoot) floatRoot.setAttribute("data-theme", theme);
    if (toastsRoot) toastsRoot.setAttribute("data-theme", theme);
    updateThemeIcon(theme);
    if (persist) {
      try { localStorage.setItem(THEME_STORAGE_KEY, theme); } catch (e) {}
    }
  }

  function syncTheme() {
    var html = document.documentElement;
    var body = document.body;
    var theme = explicitTheme(html) || explicitTheme(body) || storedTheme()
      || (colorScheme && colorScheme.matches ? "dark" : "light");
    applyTheme(theme, false);
  }
  syncTheme();

  // ---- i18n: active table + dual dict (v9 L toggle) ----
  var DUAL = window.DPB_I18N_DUAL || {};
  var langState = root.getAttribute("lang").indexOf("zh") === 0 ? "zh" : "en";
  var I18N = window.DPB_I18N || {};
  function tt(key) { return I18N[key] || (DUAL[key] && DUAL[key][langState]) || key; }
  function ttN(key, n) { return String(tt(key)).replace("{n}", String(n)); }

  function chromeLabels(surface, selector) {
    var labels = [];
    var walker = document.createTreeWalker(surface, NodeFilter.SHOW_ELEMENT, {
      acceptNode: function (element) {
        if (element.id === "dpb-artboard-inner") return NodeFilter.FILTER_REJECT;
        return element.matches(selector) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }
    });
    while (walker.nextNode()) labels.push(walker.currentNode);
    return labels;
  }

  function applyLanguage() {
    var locale = langState === "zh" ? "zh-CN" : "en";
    if (document.documentElement.hasAttribute("data-dpb-shell")) {
      document.documentElement.lang = locale;
      document.title = tt("app_title");
      var shellFrame = document.querySelector("iframe.dpb-proto-frame");
      if (shellFrame) shellFrame.title = tt("prototype_label");
    }
    [root, floatRoot, toastsRoot].forEach(function (surface) {
      if (!surface) return;
      surface.setAttribute("lang", locale);
      chromeLabels(surface, "[data-i18n]").forEach(function (el) {
        var key = el.getAttribute("data-i18n");
        el.textContent = key === "round_n" ? ttN(key, root.dataset.round) : tt(key);
      });
      ["title", "aria-label", "aria-description", "placeholder"].forEach(function (attribute) {
        chromeLabels(surface, "[data-i18n-" + attribute + "]").forEach(function (el) {
          var key = el.getAttribute("data-i18n-" + attribute);
          var suffix = el.getAttribute("data-i18n-" + attribute + "-suffix") || "";
          el.setAttribute(attribute, tt(key) + suffix);
        });
      });
    });
    syncCriteriaHidden();
    syncRulerToFrame();
    updateStatus();
  }

  // ---- element refs ----
  var bar = root;  // #dpb-root owns the shell
  var form = document.getElementById("dpb-decide-form");
  var hidden = document.getElementById("dpb-anchors-json");
  var listEl = document.getElementById("dpb-anchors");
  var field = document.getElementById("dpb-feedback");
  var hint = document.getElementById("dpb-feedback-hint");
  var approveBtn = document.getElementById("dpb-btn-approve");
  var approveLabel = document.getElementById("dpb-approve-label");
  var countBadge = document.getElementById("dpb-count-badge");
  var reopenBadge = document.getElementById("dpb-reopen-badge");
  var canvas = document.getElementById("dpb-canvas");
  canvas.setAttribute("tabindex", "-1");  // R4: Enter-save refocuses the canvas
  var wrap = document.getElementById("dpb-artboard-wrap");
  var artboard = document.getElementById("dpb-artboard");
  var artboardInner = document.getElementById("dpb-artboard-inner");
  var drawLayer = document.getElementById("dpb-draw-layer");
  var pinsLayer = document.getElementById("dpb-pins-layer");
  var inspector = document.getElementById("dpb-inspector");
  var compactWorkspace = window.matchMedia("(max-width: 1100px)");
  var reopenTab = document.getElementById("dpb-reopen-tab");
  var zoomIndicator = document.getElementById("dpb-zoom-indicator");
  var announceEl = document.getElementById("dpb-announce");
  var modal = document.getElementById("dpb-shortcut-modal");
  var pinBtn = document.getElementById("dpb-pin-toggle");
  var drawBtn = document.getElementById("dpb-draw-toggle");
  var boxBtn = document.getElementById("dpb-box-toggle");
  var rulerBtn = document.getElementById("dpb-ruler-toggle");
  var handBtn = document.getElementById("dpb-hand-toggle");
  var modePreviewBtn = document.getElementById("dpb-mode-preview");
  var modeAnnotateBtn = document.getElementById("dpb-mode-annotate");
  var criteriaHidden = document.getElementById("dpb-criteria-json");
  var criteriaPanel = document.getElementById("dpb-spec-view");
  var criteriaToggle = document.getElementById("dpb-tab-spec");
  var criteriaCount = document.getElementById("dpb-criteria-count");
  var criteriaChecks = document.querySelectorAll(".dpb-criterion-check");
  var tabAnnotations = document.getElementById("dpb-tab-annotations");
  var annotationsView = document.getElementById("dpb-annotations-view");
  var themeToggle = document.getElementById("dpb-theme-toggle");

  // ---- state ----
  var anchors = [];
  var historyStack = [];
  var redoStack = [];
  var DRAFT_KEY = window.DPB_DRAFT_KEY || "";
  var drawSeq = 0, boxSeq = 0, freePinSeq = 0;
  var activeIdx = -1;
  var resolvedSet = {};          // selector -> true (local resolve state)
  var filter = "all";
  var activeTag = "copy";
  var tool = "select";           // 'select' | 'draw' | 'box' | 'ruler' | 'hand'
  var mode = "annotate";         // 'preview' | 'annotate'
  var viewport = "desktop";
  var zoom = 1, panX = 0, panY = 0;
  var isPanning = false, isSpaceDown = false, panStartX = 0, panStartY = 0;
  var livePts = null, livePathEl = null;
  var liveBoxStart = null, liveBoxEl = null;
  var rulerPinnedPoint = null;

  // ---- criteria review state (human record only) ----
  function criteriaCountLabel(checked, total) {
    return String(tt("criteria_count"))
      .replace("{checked}", String(checked))
      .replace("{total}", String(total));
  }
  function criteriaSnapshot() {
    var items = [];
    for (var i = 0; i < criteriaChecks.length; i++) {
      var check = criteriaChecks[i];
      var id = (check.getAttribute("data-criterion-id") || "").trim();
      if (!id) continue;
      items.push({
        id: id,
        title: check.getAttribute("data-criterion-title") || "",
        checked: check.checked === true,
      });
    }
    return items;
  }
  function syncCriteriaCards() {
    for (var i = 0; i < criteriaChecks.length; i++) {
      var check = criteriaChecks[i];
      var card = check.closest ? check.closest(".dpb-spec-card") : null;
      if (card) card.classList.toggle("dpb-checked", check.checked === true);
    }
  }
  function syncCriteriaHidden() {
    var items = criteriaSnapshot();
    if (criteriaHidden) criteriaHidden.value = JSON.stringify(items);
    if (criteriaCount) {
      var checked = items.filter(function (item) { return item.checked; }).length;
      criteriaCount.textContent = criteriaCountLabel(checked, items.length);
    }
    if (criteriaToggle) criteriaToggle.hidden = items.length === 0;
    syncCriteriaCards();
  }
  // REC-02: the spec criteria live in the unified rail as a tab, not a
  // separate left panel. "open" = show the spec view (and keep the rail open);
  // close returns to the annotations view.
  function specViewActive() {
    return !criteriaPanel.hidden;
  }
  function setSpecPanel(open) {
    if (!criteriaPanel) return;
    criteriaPanel.hidden = !open;
    annotationsView.hidden = open;
    if (tabAnnotations) {
      tabAnnotations.classList.toggle("is-on", !open);
      tabAnnotations.setAttribute("aria-selected", open ? "false" : "true");
    }
    if (criteriaToggle) {
      criteriaToggle.classList.toggle("is-on", open);
      criteriaToggle.setAttribute("aria-selected", open ? "true" : "false");
    }
  }
  for (var ci = 0; ci < criteriaChecks.length; ci++) {
    criteriaChecks[ci].addEventListener("change", syncCriteriaHidden);
  }
  if (criteriaToggle) {
    criteriaToggle.addEventListener("click", function () { setSpecPanel(true); });
  }
  if (tabAnnotations) {
    tabAnnotations.addEventListener("click", function () { setSpecPanel(false); });
  }
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(current === "dark" ? "light" : "dark", true);
    });
  }

  // ---- utils ----
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function announce(msg) {
    if (announceEl) announceEl.textContent = String(msg || "");
  }
  function toast(msg) {
    if (!toastsRoot) return;
    var el = document.createElement("div");
    el.className = "dpb-toast";
    el.textContent = String(msg || "");
    toastsRoot.appendChild(el);
    setTimeout(function () {
      el.classList.add("dpb-out");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }, 2400);
  }

  // ---- artboard population: relocate the served iframe / same-doc content ----
  // Deferred to DOMContentLoaded: on served pages the control script runs
  // BEFORE the prototype iframe tag is parsed, and on same-doc pages the
  // prototype markup may also trail the injected control html.
  function populateArtboard() {
    var frame = document.querySelector("iframe.dpb-proto-frame");
    if (frame) {
      // served page: the sandboxed prototype iframe moves into the artboard
      frame.style.position = "";
      frame.style.inset = "";
      frame.style.top = ""; frame.style.left = "";
      frame.style.right = ""; frame.style.bottom = "";
      frame.style.width = ""; frame.style.height = "";
      frame.style.display = "block";  // served-page css hides it until moved
      artboardInner.appendChild(frame);
      return;
    }
    // same-doc page: every body child that is not control chrome moves in
    var keep = { "dpb-root": 1, "dpb-float-root": 1, "dpb-toasts": 1 };
    var body = document.body;
    var moved = [];
    for (var i = 0; i < body.children.length; i++) {
      var el = body.children[i];
      if (keep[el.id] || el.tagName === "SCRIPT" || el.tagName === "STYLE") continue;
      moved.push(el);
    }
    for (var j = 0; j < moved.length; j++) artboardInner.appendChild(moved[j]);
  }
  document.body.classList.add("dpb-shell");
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      populateArtboard();
      sizeDrawLayer();
      fitCanvas();
      syncPinToFrame();
      syncDrawToFrame();
      syncRulerToFrame();
      syncAnchorsToFrame();
    });
  } else {
    populateArtboard();
  }

  // ---- viewport modes (v9: desktop / tablet / mobile) ----
  var VP_WIDTHS = { desktop: 1024, tablet: 768, mobile: 375 };
  function setViewport(vp, quiet) {
    viewport = vp;
    artboard.style.width = VP_WIDTHS[vp] + "px";
    var ids = { desktop: "dpb-vp-desktop", tablet: "dpb-vp-tablet", mobile: "dpb-vp-mobile" };
    Object.keys(ids).forEach(function (k) {
      var b = document.getElementById(ids[k]);
      if (b) b.setAttribute("aria-pressed", k === vp ? "true" : "false");
    });
    sizeDrawLayer();
    if (!quiet) toast(tt("toast_vp"));
  }
  ["desktop", "tablet", "mobile"].forEach(function (vp) {
    var b = document.getElementById("dpb-vp-" + vp);
    if (b) b.addEventListener("click", function () { setViewport(vp); });
  });

  // ---- zoom / pan engine (v9) ----
  function applyTransform(smooth) {
    wrap.classList.toggle("dpb-no-anim", !smooth);
    wrap.style.transform = "translate(" + panX + "px," + panY + "px) scale(" + zoom + ")";
    if (zoomIndicator) zoomIndicator.textContent = Math.round(zoom * 100) + "%";
  }
  function handleZoom(delta) {
    zoom = Math.min(2.5, Math.max(0.3, Math.round((zoom + delta) * 100) / 100));
    applyTransform(true);
  }
  function fitCanvas() {
    var availW = canvas.clientWidth - 96;
    var availH = canvas.clientHeight - 96;
    var w = artboard.offsetWidth || VP_WIDTHS[viewport];
    var h = artboard.offsetHeight || 720;
    zoom = Math.min(1, Math.min(availW / w, availH / h));
    zoom = Math.max(0.3, Math.round(zoom * 100) / 100);
    panX = 0; panY = 0;
    applyTransform(true);
  }
  document.getElementById("dpb-zoom-in").addEventListener("click", function () { handleZoom(0.1); });
  document.getElementById("dpb-zoom-out").addEventListener("click", function () { handleZoom(-0.1); });
  document.getElementById("dpb-zoom-fit").addEventListener("click", fitCanvas);

  canvas.addEventListener("mousedown", function (e) {
    if (tool === "hand" || isSpaceDown || e.button === 1) {
      e.preventDefault();
      isPanning = true;
      panStartX = e.clientX - panX;
      panStartY = e.clientY - panY;
      canvas.style.cursor = "grabbing";
    }
  });
  window.addEventListener("mousemove", function (e) {
    if (isPanning) {
      e.preventDefault();
      panX = e.clientX - panStartX;
      panY = e.clientY - panStartY;
      applyTransform(false);
    }
  });
  window.addEventListener("mouseup", function () {
    if (isPanning) {
      isPanning = false;
      canvas.style.cursor = tool === "hand" ? "grab" : ((tool === "draw" || tool === "box" || tool === "ruler") ? "crosshair" : "default");
    }
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      var d = -e.deltaY * 0.0015;
      zoom = Math.min(2.5, Math.max(0.3, Math.round((zoom + d) * 100) / 100));
      applyTransform(false);
    } else {
      panX -= e.deltaX * 0.85;
      panY -= e.deltaY * 0.85;
      applyTransform(false);
    }
  }, { passive: false });

  // pointer → artboard-local coordinates (undo zoom/pan)
  function toArtboardPoint(e) {
    var r = artboard.getBoundingClientRect();
    return [
      (e.clientX - r.left) / zoom,
      (e.clientY - r.top) / zoom,
    ];
  }
  function normalRect(a, b) {
    var x1 = Math.min(a[0], b[0]);
    var y1 = Math.min(a[1], b[1]);
    var x2 = Math.max(a[0], b[0]);
    var y2 = Math.max(a[1], b[1]);
    return {
      x: Math.round(x1 * 10) / 10,
      y: Math.round(y1 * 10) / 10,
      width: Math.round((x2 - x1) * 10) / 10,
      height: Math.round((y2 - y1) * 10) / 10,
    };
  }
  function rulerLabel(key, values) {
    var text = String(tt(key));
    Object.keys(values).forEach(function (k) {
      text = text.replace("{" + k + "}", String(values[k]));
    });
    return text;
  }

  // ---- mode: preview (clean) vs annotate (v9) ----
  function setMode(m, quiet) {
    mode = m;
    modePreviewBtn.setAttribute("aria-pressed", m === "preview" ? "true" : "false");
    modeAnnotateBtn.setAttribute("aria-pressed", m === "annotate" ? "true" : "false");
    var show = m === "annotate";
    if (drawLayer) drawLayer.style.opacity = show ? "" : "0";
    if (pinsLayer) pinsLayer.style.opacity = show ? "" : "0";
    root.classList.toggle("dpb-preview-mode", !show);
    // mode gates the pick channel (pinOn = select tool + annotate mode) —
    // the bridge must learn the new state immediately.
    syncPinToFrame();
    syncDrawToFrame();
    if (!quiet) toast(tt(m === "preview" ? "toast_mode_preview" : "toast_mode_annotate"));
  }
  modePreviewBtn.addEventListener("click", function () { setMode("preview"); setTool("select", true); });
  modeAnnotateBtn.addEventListener("click", function () { setMode("annotate"); });

  // ---- tools ----
  function setTool(t, quiet) {
    var prev = tool;
    tool = t;
    if ((t === "draw" || t === "box" || t === "ruler") && mode === "preview") setMode("annotate", true);
    if (t !== "box") cancelLiveBox();
    if (t !== "ruler" && prev === "ruler") clearRuler();
    pinBtn.setAttribute("aria-pressed", t === "select" ? "true" : "false");
    drawBtn.setAttribute("aria-pressed", t === "draw" ? "true" : "false");
    if (boxBtn) boxBtn.setAttribute("aria-pressed", t === "box" ? "true" : "false");
    if (rulerBtn) rulerBtn.setAttribute("aria-pressed", t === "ruler" ? "true" : "false");
    handBtn.setAttribute("aria-pressed", t === "hand" ? "true" : "false");
    document.body.classList.toggle("dpb-tool-draw", t === "draw");
    document.body.classList.toggle("dpb-tool-box", t === "box");
    document.body.classList.toggle("dpb-tool-ruler", t === "ruler");
    document.body.classList.toggle("dpb-tool-select", t === "select");
    canvas.style.cursor = t === "hand" ? "grab" : ((t === "draw" || t === "box" || t === "ruler") ? "crosshair" : "default");
    if (drawLayer) drawLayer.style.pointerEvents = (t === "ruler" && protoFrame()) ? "none" : "";
    if (!quiet) {
      if (t === "draw") toast(tt("tool_draw"));
      else if (t === "box") toast(tt("tool_box"));
      else if (t === "ruler") toast(tt("tool_ruler"));
      else if (t === "hand") toast(tt("tool_hand"));
    }
    syncPinToFrame();
    syncDrawToFrame();
    syncRulerToFrame();
  }
  pinBtn.addEventListener("click", function () { setTool("select"); });
  drawBtn.addEventListener("click", function () { setTool(tool === "draw" ? "select" : "draw"); });
  if (boxBtn) boxBtn.addEventListener("click", function () { setTool(tool === "box" ? "select" : "box"); });
  if (rulerBtn) rulerBtn.addEventListener("click", function () { setTool(tool === "ruler" ? "select" : "ruler"); });
  handBtn.addEventListener("click", function () { setTool(tool === "hand" ? "select" : "hand"); });

  // ---- sandbox iframe bridge channel (#56/#57 + draw) ----
  function protoFrame() {
    return artboardInner.querySelector("iframe.dpb-proto-frame");
  }
  function postToFrame(msg) {
    var f = protoFrame();
    if (f && f.contentWindow) {
      try { f.contentWindow.postMessage(msg, "*"); } catch (e) {}
    }
  }
  var pinOn = false;  // tool === 'select' && mode === 'annotate'
  function syncPinToFrame() {
    pinOn = tool === "select" && mode === "annotate";
    postToFrame({ dpbPinState: { on: pinOn } });
  }
  function syncDrawToFrame() {
    postToFrame({ dpbDrawState: { on: tool === "draw" && mode === "annotate" } });
  }
  function syncRulerToFrame() {
    postToFrame({ dpbRulerState: {
      on: tool === "ruler" && mode === "annotate",
      sizeLabel: tt("ruler_size"),
      distanceLabel: tt("ruler_distance"),
    } });
  }
  function syncAnchorsToFrame() {
    // #57 scheme A: mirror the anchor list into the iframe as numbered
    // badges; draw anchors carry stroke points for in-frame rendering.
    postToFrame({ dpbPinAnchors: anchors.map(function (a, i) {
      var o = { selector: a.selector, n: i + 1, comment: a.comment || "" };
      if (a.tag) o.tag = a.tag;
      if (a.points) o.points = a.points;
      if (a.rect) o.rect = a.rect;
      if (i === activeIdx) o.active = true;
      if (a.__fresh) o.fresh = true;
      return o;
    }) });
  }

  // ---- same-doc element pin capture (v9 keeps the classic pick flow) ----
  // Inside the sandboxed iframe the bridge owns capture; on same-doc pages
  // the parent captures directly: pin active + click on a prototype element
  // -> cssPath anchor + outline highlight.
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    var cur = el;
    var depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {
      if (cur.id === "dpb-root" || cur.id === "dpb-float-root" || cur.id === "dpb-toasts") break;
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
    if (hoverEl) { hoverEl.classList.remove("dpb-pin-hover"); hoverEl = null; }
  }
  document.addEventListener("mousemove", function (e) {
    if (!pinOn) { clearHover(); return; }
    var el = e.target;
    if (!el || !el.closest || !el.closest("#dpb-artboard-inner")) { clearHover(); return; }
    if (hoverEl !== el) { clearHover(); hoverEl = el; hoverEl.classList.add("dpb-pin-hover"); }
  }, true);
  document.addEventListener("click", function (e) {
    if (!pinOn) return;
    var el = e.target;
    if (!el || !el.closest || !el.closest("#dpb-artboard-inner")) return;
    if (protoFrame()) return;  // iframe pages capture inside the bridge
    e.preventDefault();
    e.stopPropagation();
    var selector = cssPath(el);
    if (!selector) return;
    for (var i = 0; i < anchors.length; i++) {
      if (anchors[i].selector === selector) {
        el.classList.remove("dpb-pin-flash"); void el.offsetWidth;
        el.classList.add("dpb-pin-flash");
        announce(ttN("duplicate_anchor", i + 1));
        return;
      }
    }
    // REC-01: two-phase commit — the click only opens the in-context draft
    // popover; the anchor enters the list on Enter with a non-empty comment.
    var r = el.getBoundingClientRect();
    openDraft({
      kind: "element",
      selector: selector,
      label: labelFor(el),
      domTag: el.tagName.toLowerCase(),
      el: el,
      rect: { x: r.left, y: r.top, w: r.width, h: r.height },
    });
  }, true);

  function markFresh(a) {
    a.__fresh = true;
    return a;
  }
  function clearEntranceClass(el, className) {
    if (!el) return;
    el.addEventListener("animationend", function () { el.classList.remove(className); }, { once: true });
  }

  // ---- anchor pipeline (kept from the pre-v9 control, points-aware) ----
  function anchorSnapshot() {
    return JSON.stringify(anchors.map(function (a) {
      var o = { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
      if (a.dom_tag) o.dom_tag = a.dom_tag;
      if (a.points) o.points = a.points;
      if (a.rect) o.rect = a.rect;
      if (a.kind) o.kind = a.kind;
      if (resolvedSet[a.selector]) o.resolved = true;
      return o;
    }));
  }
  function pushHistorySnapshot(snapshot) {
    historyStack.push(snapshot);
    if (historyStack.length > 50) historyStack.shift();
    redoStack.length = 0;
  }
  function pushHistory() { pushHistorySnapshot(anchorSnapshot()); }
  function restoreAnchorsFromData(list) {
    anchors.forEach(function (a) {
      if (a.el) a.el.classList.remove("dpb-pin-target");
    });
    resolvedSet = {};
    anchors = (list || []).map(function (p) {
      var el = null;
      try {
        if (p.selector && String(p.selector).charAt(0) !== "@") el = document.querySelector(p.selector);
      } catch (e) {}
      var a = { selector: p.selector, label: p.label, comment: p.comment, tag: p.tag, el: el };
      if (p.dom_tag) a.dom_tag = p.dom_tag;
      if (p.points) a.points = p.points;
      if (p.rect) a.rect = p.rect;
      if (p.resolved) resolvedSet[p.selector] = true;
      return a;
    }).filter(function (a) { return a.selector; });
    anchors.forEach(function (a) { if (a.el) a.el.classList.add("dpb-pin-target"); });
  }
  function undo() {
    if (!historyStack.length) return;
    var prev = null;
    try { prev = JSON.parse(historyStack.pop()); } catch (e) { return; }
    redoStack.push(anchorSnapshot());
    restoreAnchorsFromData(prev);
    render();
  }
  function redo() {
    if (!redoStack.length) return;
    var next = null;
    try { next = JSON.parse(redoStack.pop()); } catch (e) { return; }
    historyStack.push(anchorSnapshot());
    restoreAnchorsFromData(next);
    render();
  }
  document.getElementById("dpb-undo-btn").addEventListener("click", function () { undo(); });

  // ---- draft persistence (wayfinder 07) ----
  function saveDraft() {
    if (!DRAFT_KEY) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        feedback: field ? field.value : "",
        anchors: JSON.parse(anchorSnapshot()),
      }));
    } catch (e) { /* quota / private-mode: draft is best-effort */ }
  }
  function loadDraft() {
    if (!DRAFT_KEY) return;
    var raw = null;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return; }
    if (!raw) return;
    var data = null;
    try { data = JSON.parse(raw); } catch (e) { return; }
    if (!data || typeof data !== "object") return;
    if (typeof data.feedback === "string" && field) field.value = data.feedback;
    if (Array.isArray(data.anchors)) {
      restoreAnchorsFromData(data.anchors);
      render();
    }
  }
  function clearDraft() {
    if (!DRAFT_KEY) return;
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }
  function syncHidden() {
    // Must carry the same fields anchorSnapshot() keeps: this is the channel
    // the decision is submitted through, and a field present in the undo
    // snapshot but absent here is silently lost at submit time.
    hidden.value = JSON.stringify(anchors.map(function (a) {
      var o = { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
      if (a.dom_tag) o.dom_tag = a.dom_tag;
      if (a.points) o.points = a.points;
      if (a.rect) o.rect = a.rect;
      if (resolvedSet[a.selector]) o.resolved = true;
      return o;
    }));
  }
  // Draft writes are synchronous (wayfinder 07 semantics): a debounced save
  // races quick fill-then-reload, and an unload flush would re-persist state
  // the caller just cleared.
  function scheduleDraft() { saveDraft(); }
  if (field) field.addEventListener("input", scheduleDraft);

  // ---- labels ----
  function labelFor(el) {
    var txt = (el.innerText || el.getAttribute("aria-label") || "").trim();
    if (txt) txt = txt.replace(/\s+/g, " ").slice(0, 18);
    var name = el.tagName.toLowerCase();
    return txt ? name + " " + txt : name;
  }
  function labelForTag(tag, selector) {
    var parts = String(selector || "").split(/\s*>\s*/);
    var leaf = parts.length ? parts[parts.length - 1] : String(selector || "");
    if (leaf.charAt(0) === "#") return leaf;
    return (tag || "element") + " " + leaf;
  }

  // ---- float bubbles (same-doc element pins) ----
  var floatMap = {};
  function ensureFloatRoot() { return floatRoot; }
  function removeBubble(sel) {
    var b = floatMap[sel];
    if (b && b.parentNode) b.parentNode.removeChild(b);
    delete floatMap[sel];
  }
  function ensureBubble(a, idx) {
    if (!a.el) return;
    var rootEl = ensureFloatRoot();
    if (!rootEl) return;
    var bubble = floatMap[a.selector];
    if (!bubble) {
      bubble = document.createElement("div");
      bubble.className = "dpb-float";
      bubble.innerHTML = '<span class="dpb-float-n"></span><span class="dpb-float-note"></span>';
      rootEl.appendChild(bubble);
      floatMap[a.selector] = bubble;
    }
    var nEl = bubble.querySelector(".dpb-float-n");
    if (nEl) nEl.textContent = String(idx + 1);
    bubble.classList.toggle("dpb-active", idx === activeIdx);
    var noteEl = bubble.querySelector(".dpb-float-note");
    if (noteEl) noteEl.textContent = a.comment || "";
  }
  function positionFloat(a, idx) {
    if (!a.el || !a.el.isConnected) { removeBubble(a.selector); return; }
    var bubble = floatMap[a.selector];
    if (!bubble) return;
    var rect = a.el.getBoundingClientRect();
    var bw = bubble.offsetWidth || 220;
    var top = window.scrollY + rect.top;
    var maxTop = window.scrollY + window.innerHeight - 60;
    bubble.style.top = Math.min(top, maxTop) + "px";
    if (rect.right + 8 + bw <= window.innerWidth) {
      bubble.style.left = (window.scrollX + rect.right + 8) + "px";
    } else if (rect.left - 8 - bw >= 0) {
      bubble.style.left = (window.scrollX + rect.left - bw - 8) + "px";
    } else {
      bubble.style.left = (window.scrollX + Math.max(12, Math.min(rect.left, window.innerWidth - bw - 12))) + "px";
    }
  }
  var repositionTick = false;
  function repositionAll() {
    if (repositionTick) return;
    repositionTick = true;
    window.requestAnimationFrame(function () {
      repositionTick = false;
      anchors.forEach(positionFloat);
    });
  }
  window.addEventListener("scroll", repositionAll, true);
  window.addEventListener("resize", function () { repositionAll(); sizeDrawLayer(); renderDrawStrokes(); });

  // ---- draw layer (artboard-local strokes + free pins) ----
  function sizeDrawLayer() {
    if (!drawLayer) return;
    var w = artboard.offsetWidth || VP_WIDTHS[viewport];
    var h = artboard.offsetHeight || 720;
    drawLayer.setAttribute("width", String(w));
    drawLayer.setAttribute("height", String(h));
    drawLayer.setAttribute("viewBox", "0 0 " + w + " " + h);
  }
  function drawPathD(points) {
    if (!points || !points.length) return "";
    var d = "";
    for (var i = 0; i < points.length; i++) {
      d += (i ? "L" : "M") + Number(points[i][0]).toFixed(1) + " " + Number(points[i][1]).toFixed(1);
    }
    return d + (points.length > 2 ? " Z" : "");
  }
  function renderDrawStrokes() {
    var items = anchors.filter(function (a) { return (a.tag === "draw" && a.points) || (a.tag === "box" && a.rect); });
    var stale = drawLayer.querySelectorAll(".dpb-draw-path, .dpb-draw-badge, .dpb-draw-live, .dpb-box-rect, .dpb-box-badge, .dpb-box-live");
    if (!items.length && !stale.length) return;
    sizeDrawLayer();
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    anchors.forEach(function (a, idx) {
      if (a.tag === "box" && a.rect) {
        var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(a.rect.x));
        rect.setAttribute("y", String(a.rect.y));
        rect.setAttribute("width", String(a.rect.width));
        rect.setAttribute("height", String(a.rect.height));
        rect.setAttribute("rx", "4");
        rect.setAttribute("class", "dpb-box-rect");
        drawLayer.appendChild(rect);
        var bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        bg.setAttribute("x", String(Math.max(0, Number(a.rect.x) - 1)));
        bg.setAttribute("y", String(Math.max(0, Number(a.rect.y) - 22)));
        bg.setAttribute("width", "28");
        bg.setAttribute("height", "18");
        bg.setAttribute("rx", "9");
        var text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", String(Math.max(0, Number(a.rect.x) + 13)));
        text.setAttribute("y", String(Math.max(14, Number(a.rect.y) - 9)));
        text.setAttribute("text-anchor", "middle");
        text.setAttribute("dy", "3.2");
        text.textContent = String(idx + 1);
        var badge = document.createElementNS("http://www.w3.org/2000/svg", "g");
        badge.setAttribute("class", "dpb-box-badge");
        badge.appendChild(bg); badge.appendChild(text);
        drawLayer.appendChild(badge);
        return;
      }
      if (a.tag !== "draw" || !a.points) return;
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", drawPathD(a.points));
      path.setAttribute("class", "dpb-draw-path");
      drawLayer.appendChild(path);
      var p0 = a.points[0];
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "dpb-draw-badge");
      g.setAttribute("transform", "translate(" + Number(p0[0]).toFixed(1) + "," + Math.max(9, Number(p0[1]) - 12).toFixed(1) + ")");
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "9");
      c.setAttribute("class", "dpb-draw-badge-c");
      var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("dy", "3.2");
      t.textContent = String(idx + 1);
      g.appendChild(c); g.appendChild(t);
      drawLayer.appendChild(g);
    });
  }
  function renderFreePins() {
    if (!pinsLayer) return;
    pinsLayer.innerHTML = "";
    anchors.forEach(function (a, idx) {
      if (!a.points || a.tag === "draw") return;
      var p0 = a.points[0];
      var pin = document.createElement("div");
      pin.className = "dpb-free-pin"
        + (resolvedSet[a.selector] ? " dpb-resolved" : "")
        + (idx === activeIdx ? " dpb-active" : "")
        + (a.__fresh ? " dpb-pin-drop" : "");
      pin.textContent = String(idx + 1);
      pin.style.left = p0[0] + "px";
      pin.style.top = p0[1] + "px";
      if (a.__fresh) clearEntranceClass(pin, "dpb-pin-drop");
      pin.addEventListener("click", function (e) {
        e.stopPropagation();
        focusAnchor(idx);
      });
      pinsLayer.appendChild(pin);
    });
  }

  function cancelLiveStroke() {
    livePts = null;
    if (livePathEl && livePathEl.parentNode) livePathEl.parentNode.removeChild(livePathEl);
    livePathEl = null;
  }
  function cancelLiveBox() {
    liveBoxStart = null;
    if (liveBoxEl && liveBoxEl.parentNode) liveBoxEl.parentNode.removeChild(liveBoxEl);
    liveBoxEl = null;
  }
  function clearRuler() {
    rulerPinnedPoint = null;
    if (!drawLayer) return;
    var stale = drawLayer.querySelectorAll(".dpb-ruler-hover, .dpb-ruler-badge, .dpb-ruler-line, .dpb-ruler-point");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
  }
  function artboardElementAt(e) {
    if (!drawLayer) return null;
    var prior = drawLayer.style.pointerEvents;
    drawLayer.style.pointerEvents = "none";
    var el = document.elementFromPoint(e.clientX, e.clientY);
    drawLayer.style.pointerEvents = prior;
    if (!el || !el.closest || !el.closest("#dpb-artboard-inner")) return null;
    return el;
  }
  function rectForElement(el) {
    var r = el.getBoundingClientRect();
    var ar = artboard.getBoundingClientRect();
    return {
      x: Math.round(((r.left - ar.left) / zoom) * 10) / 10,
      y: Math.round(((r.top - ar.top) / zoom) * 10) / 10,
      width: Math.round((r.width / zoom) * 10) / 10,
      height: Math.round((r.height / zoom) * 10) / 10,
    };
  }
  function drawBadge(x, y, text, className) {
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", className || "dpb-ruler-badge");
    var label = String(text || "");
    var w = Math.max(34, label.length * 7 + 12);
    var bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", String(Math.max(0, x)));
    bg.setAttribute("y", String(Math.max(0, y)));
    bg.setAttribute("width", String(w));
    bg.setAttribute("height", "18");
    bg.setAttribute("rx", "9");
    var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", String(Math.max(0, x) + w / 2));
    t.setAttribute("y", String(Math.max(14, y + 11)));
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("dy", "3.2");
    t.textContent = label;
    g.appendChild(bg); g.appendChild(t);
    drawLayer.appendChild(g);
    return g;
  }
  function renderRulerHover(e) {
    var stale = drawLayer.querySelectorAll(".dpb-ruler-hover, .dpb-ruler-badge.is-hover");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    var el = artboardElementAt(e);
    if (!el) return;
    var rect = rectForElement(el);
    if (rect.width <= 0 || rect.height <= 0) return;
    var r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("x", String(rect.x));
    r.setAttribute("y", String(rect.y));
    r.setAttribute("width", String(rect.width));
    r.setAttribute("height", String(rect.height));
    r.setAttribute("rx", "4");
    r.setAttribute("class", "dpb-ruler-hover");
    drawLayer.appendChild(r);
    drawBadge(rect.x + 6, Math.max(0, rect.y - 24), rulerLabel("ruler_size", {
      w: Math.round(rect.width), h: Math.round(rect.height),
    }), "dpb-ruler-badge is-hover");
  }
  function renderRulerLine(a, b) {
    var stale = drawLayer.querySelectorAll(".dpb-ruler-line, .dpb-ruler-point, .dpb-ruler-badge.is-line");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(a[0])); line.setAttribute("y1", String(a[1]));
    line.setAttribute("x2", String(b[0])); line.setAttribute("y2", String(b[1]));
    line.setAttribute("class", "dpb-ruler-line");
    drawLayer.appendChild(line);
    [a, b].forEach(function (p) {
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", String(p[0])); c.setAttribute("cy", String(p[1]));
      c.setAttribute("r", "4"); c.setAttribute("class", "dpb-ruler-point");
      drawLayer.appendChild(c);
    });
    var dx = b[0] - a[0], dy = b[1] - a[1];
    var d = Math.round(Math.sqrt(dx * dx + dy * dy));
    drawBadge((a[0] + b[0]) / 2 + 6, (a[1] + b[1]) / 2 - 24, rulerLabel("ruler_distance", { d: d }), "dpb-ruler-badge is-line");
  }

  drawLayer.addEventListener("pointerdown", function (e) {
    if (tool !== "box" || mode !== "annotate") return;
    e.preventDefault();
    liveBoxStart = toArtboardPoint(e);
    liveBoxEl = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    liveBoxEl.setAttribute("class", "dpb-box-rect dpb-box-live");
    liveBoxEl.setAttribute("rx", "4");
    drawLayer.appendChild(liveBoxEl);
    try { drawLayer.setPointerCapture(e.pointerId); } catch (err) {}
  });
  drawLayer.addEventListener("pointermove", function (e) {
    if (tool === "ruler" && mode === "annotate") renderRulerHover(e);
    if (tool !== "box" || !liveBoxStart || !liveBoxEl) return;
    e.preventDefault();
    var rect = normalRect(liveBoxStart, toArtboardPoint(e));
    liveBoxEl.setAttribute("x", String(rect.x));
    liveBoxEl.setAttribute("y", String(rect.y));
    liveBoxEl.setAttribute("width", String(rect.width));
    liveBoxEl.setAttribute("height", String(rect.height));
  });
  drawLayer.addEventListener("pointerup", function (e) {
    if (tool !== "box" || !liveBoxStart) return;
    e.preventDefault();
    var rect = normalRect(liveBoxStart, toArtboardPoint(e));
    cancelLiveBox();
    addBoxAnchor(rect);
  });
  drawLayer.addEventListener("pointerleave", function () {
    if (tool === "ruler") {
      var stale = drawLayer.querySelectorAll(".dpb-ruler-hover, .dpb-ruler-badge.is-hover");
      for (var i = 0; i < stale.length; i++) stale[i].remove();
    }
  });
  function rulerEventInArtboard(e) {
    var r = artboard.getBoundingClientRect();
    return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
  }
  document.addEventListener("mousemove", function (e) {
    if (tool !== "ruler" || mode !== "annotate" || protoFrame()) return;
    if (!rulerEventInArtboard(e)) return;
    renderRulerHover(e);
  }, true);
  document.addEventListener("pointerup", function (e) {
    if (tool !== "ruler" || mode !== "annotate" || protoFrame()) return;
    if (!rulerEventInArtboard(e)) return;
    e.preventDefault();
    e.stopPropagation();
    var pt = toArtboardPoint(e);
    if (!rulerPinnedPoint) {
      rulerPinnedPoint = pt;
      renderRulerLine(pt, pt);
    } else {
      renderRulerLine(rulerPinnedPoint, pt);
      rulerPinnedPoint = null;
    }
  }, true);
  drawLayer.addEventListener("pointerdown", function (e) {
    if (tool !== "draw" || mode !== "annotate") return;
    e.preventDefault();
    livePts = [toArtboardPoint(e)];
    livePathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    livePathEl.setAttribute("class", "dpb-draw-path dpb-draw-live");
    drawLayer.appendChild(livePathEl);
    try { drawLayer.setPointerCapture(e.pointerId); } catch (err) {}
  });
  drawLayer.addEventListener("pointermove", function (e) {
    if (tool !== "draw" || !livePts) return;
    e.preventDefault();
    livePts.push(toArtboardPoint(e));
    if (livePathEl) livePathEl.setAttribute("d", drawPathD(livePts));
  });
  drawLayer.addEventListener("pointerup", function (e) {
    if (tool !== "draw" || !livePts) return;
    e.preventDefault();
    var pts = livePts;
    cancelLiveStroke();
    addDrawAnchor(pts);
  });
  drawLayer.addEventListener("pointercancel", function () { cancelLiveStroke(); cancelLiveBox(); });

  // free pin: click on the canvas/viewport chrome while select tool is on
  canvas.addEventListener("click", function (e) {
    if (tool !== "select" || mode !== "annotate") return;
    if (e.target.closest && e.target.closest(
      "#dpb-header, #dpb-toolbar, #dpb-inspector, #dpb-reopen-tab, .dpb-modal-scrim, .dpb-toasts, .dpb-coachmark, .dpb-anno-popover"
    )) return;
    if (e.target !== canvas && e.target !== wrap && !wrap.contains(e.target)) return;
    var pt = toArtboardPoint(e);
    addFreePinAnchor(pt);
  });

  // Geometry tools (draw/box/free pin) stage their shape into a draft and
  // open the same in-context popover; the anchor lands on Enter (REC-01).
  function stageDraft(kind, geometry, anchorRect) {
    openDraft({ kind: kind, geometry: geometry, rect: anchorRect });
  }

  function addDrawAnchor(points) {
    if (!points || points.length < 4) return;
    var r = artboard.getBoundingClientRect();
    var p0 = points[0];
    stageDraft("draw", points, {
      x: r.left + p0[0] * zoom,
      y: r.top + p0[1] * zoom,
      w: 24, h: 24,
    });
  }
  function addBoxAnchor(rect) {
    if (!rect || rect.width < 4 || rect.height < 4) return;
    var r = artboard.getBoundingClientRect();
    stageDraft("box", rect, {
      x: r.left + rect.x * zoom,
      y: r.top + rect.y * zoom,
      w: rect.width * zoom, h: rect.height * zoom,
    });
  }
  function addFreePinAnchor(pt) {
    var r = artboard.getBoundingClientRect();
    stageDraft("pin", pt, {
      x: r.left + pt[0] * zoom,
      y: r.top + pt[1] * zoom,
      w: 28, h: 28,
    });
  }

  // ---- in-context draft popover (REC-01: two-phase anchor commit) ----
  // The popover exists only while a draft is unsaved; anchors enter the list
  // exclusively via saveDraftAnchor() with a non-empty comment, so an empty
  // anchor can never reach the ADR-0008 floor (frontend mirror or server).
  var annoPopover = document.getElementById("dpb-anno-popover");
  var annoInput = document.getElementById("dpb-anno-input");
  var annoSel = document.getElementById("dpb-anno-sel");
  var annoN = document.getElementById("dpb-anno-n");
  var annoFloorHint = document.getElementById("dpb-anno-floor-hint");
  var draftState = null;  // {kind, selector, label, el?, geometry?, rect}

  function draftPopoverOpen() { return !!draftState; }

  function positionDraftPopover() {
    if (!draftState || !annoPopover) return;
    var rect = draftState.rect;
    if (!annoPopover.offsetWidth) return;  // hidden
    var pw = annoPopover.offsetWidth || 280;
    var ph = annoPopover.offsetHeight || 140;
    var margin = 8;
    var x, y;
    if (!rect) {
      var cr = canvas.getBoundingClientRect();
      x = cr.left + cr.width / 2 - pw / 2;
      y = cr.top + cr.height / 2 - ph / 2;
    } else {
      // R3: 4-quadrant flip — prefer right of the element, else left, else
      // clamp horizontally; below the element, else above, else clamp.
      if (rect.x + rect.w + margin + pw <= window.innerWidth - margin) {
        x = rect.x + rect.w + margin;
      } else if (rect.x - margin - pw >= margin) {
        x = rect.x - margin - pw;
      } else {
        x = Math.max(margin, Math.min(rect.x, window.innerWidth - pw - margin));
      }
      if (rect.y + rect.h + margin + ph <= window.innerHeight - margin) {
        y = rect.y + rect.h + margin;
      } else if (rect.y - margin - ph >= 0) {
        y = rect.y - margin - ph;
      } else {
        y = Math.max(margin, Math.min(rect.y, window.innerHeight - ph - margin));
      }
    }
    annoPopover.style.left = Math.round(x) + "px";
    annoPopover.style.top = Math.round(y) + "px";
  }

  function openDraft(draft) {
    // A pending draft is replaced (never committed) by the next pick —
    // empty drafts self-destruct instead of piling up ghost anchors.
    cancelDraft(false);
    draftState = draft;
    annoPopover.hidden = false;
    annoPopover.setAttribute("data-theme", root.getAttribute("data-theme") || "light");
    annoSel.textContent = draft.selector || "";
    annoSel.title = draft.selector || "";
    annoN.textContent = String(anchors.length + 1);
    annoFloorHint.textContent = "";
    Array.prototype.forEach.call(document.querySelectorAll("#dpb-anno-tags .dpb-tag"), function (b) {
      b.classList.toggle("is-on", (b.getAttribute("data-tag") || "copy") === activeTag);
    });
    annoInput.value = "";
    positionDraftPopover();
    annoInput.focus();
    announce(tt("popover_aria"));
  }

  function saveDraftAnchor() {
    if (!draftState) return true;
    var text = annoInput.value.trim();
    if (!text) {
      // Empty save attempt: nudge, don't commit (no ghost anchor).
      annoFloorHint.textContent = tt("anchor_placeholder");
      annoInput.classList.remove("is-shaking");
      void annoInput.offsetWidth;
      annoInput.classList.add("is-shaking");
      return false;
    }
    var d = draftState;
    var seq = anchors.length + 1;
    var anchor;
    if (d.kind === "element") {
      anchor = {
        selector: d.selector,
        label: d.label,
        comment: text,
        tag: activeTag,
      };
      // The chip category goes to `tag` for the rail chip; the DOM tag rides
      // along as `dom_tag` so the server's v2 reconnect hint (features.tag)
      // keeps pointing at the real element kind.
      if (d.domTag) anchor.dom_tag = d.domTag;
      if (d.el && d.el.isConnected) {
        anchor.el = d.el;
        d.el.classList.add("dpb-pin-target");
      }
    } else if (d.kind === "draw") {
      drawSeq += 1;
      anchor = {
        selector: "@draw-" + drawSeq,
        label: ttN("draw_label", seq),
        comment: text,
        tag: "draw",
        points: d.geometry,
      };
    } else if (d.kind === "box") {
      boxSeq += 1;
      anchor = {
        selector: "@box-" + boxSeq,
        label: ttN("box_label", seq),
        comment: text,
        tag: "box",
        rect: d.geometry,
      };
    } else {
      freePinSeq += 1;
      anchor = {
        selector: "@pin-" + freePinSeq,
        label: ttN("toast_pin_added", seq),
        comment: text,
        tag: "pin",
        points: [d.geometry],
      };
    }
    pushHistory();  // one snapshot per create+type+Enter (R4 undo granularity)
    anchors.push(markFresh(anchor));
    hideCoachmark(true);  // R9: the first created anchor dismisses the coachmark
    hideDraftPopover();
    draftState = null;
    render();
    // R4: focus returns to the canvas; the pick channel stays on so the next
    // click opens a fresh bubble immediately.
    try { canvas.focus({ preventScroll: true }); } catch (e) { canvas.focus(); }
    return true;
  }

  function cancelDraft(refocus) {
    if (!draftState) return;
    draftState = null;
    hideDraftPopover();
    // Re-echo the anchor list: the bridge highlights the clicked iframe
    // element at click time; a cancelled draft must clear that highlight.
    syncAnchorsToFrame();
    if (refocus) { try { canvas.focus({ preventScroll: true }); } catch (e) { canvas.focus(); } }
  }

  function hideDraftPopover() {
    if (!annoPopover) return;
    annoPopover.hidden = true;
    if (annoInput) {
      annoInput.value = "";
      annoInput.classList.remove("is-shaking");
    }
  }

  if (annoInput) {
    annoInput.addEventListener("keydown", function (e) {
      // R2: an IME's Enter commits composition, never the draft.
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        e.stopPropagation();
        saveDraftAnchor();
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        cancelDraft(true);
      }
      // Ctrl/Cmd+Enter falls through to the global approve channel.
    });
  }
  // DEF-02: the popover is a role=dialog — Tab cycles its own controls
  // (textarea ↔ tag buttons) instead of escaping to background chrome.
  // Esc is handled per-target (input) or by the global keymap (tag buttons),
  // and both paths return focus to the canvas via cancelDraft(true).
  if (annoPopover) {
    annoPopover.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || !draftPopoverOpen()) return;
      var items = [annoInput].concat(
        Array.prototype.slice.call(document.querySelectorAll("#dpb-anno-tags .dpb-tag"))
      ).filter(function (el) { return el && !el.disabled; });
      if (!items.length) { e.preventDefault(); return; }
      var idx = items.indexOf(document.activeElement);
      var dir = e.shiftKey ? -1 : 1;
      e.preventDefault();
      items[(idx + dir + items.length) % items.length].focus();
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("#dpb-anno-tags .dpb-tag"), function (b) {
    b.addEventListener("click", function () {
      activeTag = b.getAttribute("data-tag") || "copy";
      Array.prototype.forEach.call(document.querySelectorAll("#dpb-anno-tags .dpb-tag"), function (x) {
        x.classList.toggle("is-on", x === b);
      });
      annoInput.focus();
    });
  });
  // Panning/zooming invalidates the draft's screen position — drop the draft
  // rather than pinning text to a stale anchor point.
  canvas.addEventListener("wheel", function () { if (draftState) cancelDraft(false); }, { passive: true });
  if (annoPopover) {
    window.addEventListener("resize", function () { if (draftState) positionDraftPopover(); });
  }

  // ---- bridge messages ----
  window.addEventListener("message", function (e) {
    var srcFrame = protoFrame();
    if (!srcFrame || e.source !== srcFrame.contentWindow) return;
    var data = e.data;
    if (!data) return;
    if (data.dpbPinHello) {
      syncPinToFrame();
      syncDrawToFrame();
      syncRulerToFrame();
      syncAnchorsToFrame();
      return;
    }
    if (data.dpbDrawStroke) {
      if (tool !== "draw") return;
      var pts = data.dpbDrawStroke.points;
      if (!Array.isArray(pts) || pts.length < 4) return;
      addDrawAnchor(pts.map(function (p) {
        return [Number(p && p[0]) || 0, Number(p && p[1]) || 0];
      }));
      return;
    }
    if (!pinOn) return;
    if (!data.dpbPinAnchor) return;
    var a = data.dpbPinAnchor;
    var selector = String(a.selector || "");
    var tag = String(a.tag || "").toLowerCase();
    if (!selector) return;
    for (var i = 0; i < anchors.length; i++) {
      if (anchors[i].selector === selector) {
        postToFrame({ dpbPinFlash: { selector: selector } });
        announce(ttN("duplicate_anchor", i + 1));
        return;
      }
    }
    // Cross-origin draft: the bridge reports the element rect in iframe
    // viewport coords; the iframe fills the artboard 1:1, so screen coords
    // are artboardRect.left + x * zoom (artboard rect already carries the
    // wrap's translate+scale transform).
    var r = artboard.getBoundingClientRect();
    var rect = (a.rect && typeof a.rect.x === "number")
      ? {
          x: r.left + Number(a.rect.x) * zoom,
          y: r.top + Number(a.rect.y) * zoom,
          w: Number(a.rect.w || 0) * zoom,
          h: Number(a.rect.h || 0) * zoom,
        }
      : null;
    openDraft({
      kind: "element",
      selector: selector,
      label: labelForTag(tag, selector),
      domTag: tag || "",
      rect: rect,
    });
  });

  /* DPB_REVIEW_INSERT */
  })();
