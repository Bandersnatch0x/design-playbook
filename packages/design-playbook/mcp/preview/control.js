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

  function updateThemeIcon(theme) {
    var icon = document.getElementById("dpb-theme-icon");
    if (icon) icon.textContent = theme === "dark" ? "☀" : "☾";
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
  var langState = (document.documentElement.getAttribute("lang") || "zh").indexOf("zh") === 0 ? "zh" : "en";
  var I18N = window.DPB_I18N || {};
  function tt(key) { return I18N[key] || (DUAL[key] && DUAL[key][langState]) || key; }
  function ttN(key, n) { return String(tt(key)).replace("{n}", String(n)); }

  function applyLanguage() {
    var dict = DUAL;
    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var key = el.getAttribute("data-i18n");
      var entry = dict[key];
      if (entry && entry[langState]) {
        el.style.opacity = "0";
        (function (node, text) {
          setTimeout(function () { node.textContent = text; node.style.opacity = "1"; }, 80);
        })(el, entry[langState]);
      }
    }
    var ci = document.getElementById("dpb-comment-input");
    if (ci) ci.placeholder = tt("comment_placeholder");
    var fb = document.getElementById("dpb-feedback");
    if (fb) fb.placeholder = tt("field_placeholder");
    syncCriteriaHidden();
    updateStatus();
  }

  // ---- element refs ----
  var bar = root;  // #dpb-root owns the shell
  var form = document.getElementById("dpb-decide-form");
  var hidden = document.getElementById("dpb-anchors-json");
  var listEl = document.getElementById("dpb-anchors");
  var field = document.getElementById("dpb-feedback");
  var hint = document.getElementById("dpb-feedback-hint");
  var commentInput = document.getElementById("dpb-comment-input");
  var statusPill = document.getElementById("dpb-status-pill");
  var statusText = document.getElementById("dpb-status-text");
  var statusApprove = document.getElementById("dpb-status-approve");
  var countBadge = document.getElementById("dpb-count-badge");
  var reopenBadge = document.getElementById("dpb-reopen-badge");
  var canvas = document.getElementById("dpb-canvas");
  var wrap = document.getElementById("dpb-artboard-wrap");
  var artboard = document.getElementById("dpb-artboard");
  var artboardInner = document.getElementById("dpb-artboard-inner");
  var drawLayer = document.getElementById("dpb-draw-layer");
  var pinsLayer = document.getElementById("dpb-pins-layer");
  var inspector = document.getElementById("dpb-inspector");
  var reopenTab = document.getElementById("dpb-reopen-tab");
  var zoomIndicator = document.getElementById("dpb-zoom-indicator");
  var announceEl = document.getElementById("dpb-announce");
  var modal = document.getElementById("dpb-shortcut-modal");
  var pinBtn = document.getElementById("dpb-pin-toggle");
  var drawBtn = document.getElementById("dpb-draw-toggle");
  var handBtn = document.getElementById("dpb-hand-toggle");
  var modePreviewBtn = document.getElementById("dpb-mode-preview");
  var modeAnnotateBtn = document.getElementById("dpb-mode-annotate");
  var criteriaHidden = document.getElementById("dpb-criteria-json");
  var criteriaPanel = document.getElementById("dpb-spec-panel");
  var criteriaToggle = document.getElementById("dpb-criteria-toggle");
  var criteriaCount = document.getElementById("dpb-criteria-count");
  var criteriaChecks = document.querySelectorAll(".dpb-criterion-check");
  var themeToggle = document.getElementById("dpb-theme-toggle");

  // ---- state ----
  var anchors = [];
  var historyStack = [];
  var redoStack = [];
  var DRAFT_KEY = window.DPB_DRAFT_KEY || "";
  var drawSeq = 0, noteSeq = 0, freePinSeq = 0;
  var activeIdx = -1;
  var resolvedSet = {};          // selector -> true (local resolve state)
  var filter = "all";
  var activeTag = "copy";
  var tool = "select";           // 'select' | 'draw' | 'hand'
  var mode = "annotate";         // 'preview' | 'annotate'
  var viewport = "desktop";
  var zoom = 1, panX = 0, panY = 0;
  var isPanning = false, isSpaceDown = false, panStartX = 0, panStartY = 0;
  var livePts = null, livePathEl = null;

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
  function syncCriteriaHidden() {
    var items = criteriaSnapshot();
    if (criteriaHidden) criteriaHidden.value = JSON.stringify(items);
    if (criteriaCount) {
      var checked = items.filter(function (item) { return item.checked; }).length;
      criteriaCount.textContent = criteriaCountLabel(checked, items.length);
    }
    if (criteriaToggle) criteriaToggle.hidden = items.length === 0;
  }
  function setSpecPanel(open) {
    if (!criteriaPanel) return;
    criteriaPanel.classList.toggle("dpb-collapsed", !open);
    root.classList.toggle("dpb-spec-collapsed", !open);
    if (criteriaToggle) criteriaToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  for (var ci = 0; ci < criteriaChecks.length; ci++) {
    criteriaChecks[ci].addEventListener("change", syncCriteriaHidden);
  }
  if (criteriaToggle) {
    criteriaToggle.addEventListener("click", function () {
      setSpecPanel(criteriaPanel.classList.contains("dpb-collapsed"));
    });
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
      canvas.style.cursor = tool === "hand" ? "grab" : (tool === "draw" ? "crosshair" : "default");
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
    tool = t;
    if (t === "draw" && mode === "preview") setMode("annotate", true);
    pinBtn.setAttribute("aria-pressed", t === "select" ? "true" : "false");
    drawBtn.setAttribute("aria-pressed", t === "draw" ? "true" : "false");
    handBtn.setAttribute("aria-pressed", t === "hand" ? "true" : "false");
    document.body.classList.toggle("dpb-tool-draw", t === "draw");
    document.body.classList.toggle("dpb-tool-select", t === "select");
    canvas.style.cursor = t === "hand" ? "grab" : (t === "draw" ? "crosshair" : "default");
    if (!quiet) {
      if (t === "draw") toast(tt("tool_draw"));
      else if (t === "hand") toast(tt("tool_hand"));
    }
    syncPinToFrame();
  }
  pinBtn.addEventListener("click", function () { setTool("select"); });
  drawBtn.addEventListener("click", function () { setTool(tool === "draw" ? "select" : "draw"); });
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
  function syncAnchorsToFrame() {
    // #57 scheme A: mirror the anchor list into the iframe as numbered
    // badges; draw anchors carry stroke points for in-frame rendering.
    postToFrame({ dpbPinAnchors: anchors.map(function (a, i) {
      var o = { selector: a.selector, n: i + 1, comment: a.comment || "" };
      if (a.tag) o.tag = a.tag;
      if (a.points) o.points = a.points;
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
    el.classList.add("dpb-pin-target");
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
    pushHistory();
    anchors.push({
      selector: selector,
      label: labelFor(el),
      comment: "",
      tag: el.tagName.toLowerCase(),
      el: el,
    });
    render();
  }, true);

  // ---- anchor pipeline (kept from the pre-v9 control, points-aware) ----
  function anchorSnapshot() {
    return JSON.stringify(anchors.map(function (a) {
      var o = { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
      if (a.points) o.points = a.points;
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
      if (p.points) a.points = p.points;
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
      if (a.points) o.points = a.points;
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
    var items = anchors.filter(function (a) { return a.tag === "draw" && a.points; });
    if (!items.length && !drawLayer.firstChild) return;
    sizeDrawLayer();
    var stale = drawLayer.querySelectorAll(".dpb-draw-path, .dpb-draw-badge, .dpb-draw-live");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    anchors.forEach(function (a, idx) {
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
      pin.className = "dpb-free-pin" + (resolvedSet[a.selector] ? " dpb-resolved" : "");
      pin.textContent = String(idx + 1);
      pin.style.left = p0[0] + "px";
      pin.style.top = p0[1] + "px";
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
  drawLayer.addEventListener("pointercancel", cancelLiveStroke);

  // free pin: click on the canvas/viewport chrome while select tool is on
  canvas.addEventListener("click", function (e) {
    if (tool !== "select" || mode !== "annotate") return;
    if (e.target.closest && e.target.closest(
      "#dpb-header, #dpb-toolbar, #dpb-inspector, .dpb-status-pill, #dpb-reopen-tab, .dpb-modal-scrim, .dpb-toasts"
    )) return;
    if (e.target !== canvas && e.target !== wrap && !wrap.contains(e.target)) return;
    var pt = toArtboardPoint(e);
    addFreePinAnchor(pt);
  });

  function addDrawAnchor(points) {
    if (!points || points.length < 4) return;
    drawSeq += 1;
    pushHistory();
    anchors.push({
      selector: "@draw-" + drawSeq,
      label: ttN("draw_label", anchors.length + 1),
      comment: "",
      tag: "draw",
      points: points,
    });
    render();
    toast(ttN("toast_loop_done", anchors.length));
    if (commentInput) commentInput.focus();
  }
  function addFreePinAnchor(pt) {
    freePinSeq += 1;
    pushHistory();
    anchors.push({
      selector: "@pin-" + freePinSeq,
      label: ttN("toast_pin_added", anchors.length + 1),
      comment: "",
      tag: "pin",
      points: [pt],
    });
    render();
    toast(ttN("toast_pin_added", anchors.length));
    if (commentInput) commentInput.focus();
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
    pushHistory();
    anchors.push({
      selector: selector,
      label: labelForTag(tag, selector),
      comment: "",
      tag: tag,
    });
    render();
  });

  /* DPB_REVIEW_INSERT */
  })();
