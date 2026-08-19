(function () {
  var bar = document.getElementById("dpb-preview-bar");
  var form = document.getElementById("dpb-decide-form");
  if (!form) return;

  // Follow explicit host theme overrides first, then system preference.
  var colorScheme = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: light)")
    : null;

  function explicitTheme(el) {
    if (!el) return null;
    var dataTheme = el.getAttribute("data-theme");
    if (dataTheme === "light" || dataTheme === "dark") return dataTheme;
    if (el.classList.contains("theme-light")) return "light";
    if (el.classList.contains("theme-dark")) return "dark";
    return null;
  }

  function syncTheme() {
    if (!bar) return;
    var html = document.documentElement;
    var body = document.body;
    var hostTheme = explicitTheme(html) || explicitTheme(body);
    var theme = hostTheme || (colorScheme && colorScheme.matches ? "light" : "dark");
    bar.setAttribute("data-theme", theme);
    if (floatRoot) floatRoot.setAttribute("data-theme", theme);
    var onboardCard = document.getElementById("dpb-onboard");
    if (onboardCard) onboardCard.setAttribute("data-theme", theme);
  }

  syncTheme();
  if (colorScheme) colorScheme.addEventListener("change", syncTheme);
  if (window.MutationObserver) {
    var themeObserver = new MutationObserver(syncTheme);
    var themeObserverOptions = { attributes: true, attributeFilter: ["class", "data-theme"] };
    themeObserver.observe(document.documentElement, themeObserverOptions);
    if (document.body) themeObserver.observe(document.body, themeObserverOptions);
  }

  var I18N = window.DPB_I18N || {};
  var field = form.querySelector('textarea[name="feedback"]');
  var hint = document.getElementById("dpb-feedback-hint");
  var pinBtn = document.getElementById("dpb-pin-toggle");
  var pinLabel = pinBtn ? pinBtn.querySelector(".dpb-pin-label") : null;
  var listEl = document.getElementById("dpb-anchors");
  var hidden = document.getElementById("dpb-anchors-json");
  var openBtn = document.getElementById("dpb-open-drawer");
  var closeBtn = document.getElementById("dpb-close-drawer");
  var pinCountEl = document.getElementById("dpb-pin-count");
  var pillCountEl = document.getElementById("dpb-pill-count");
  var drawerEl = document.getElementById("dpb-drawer");
  var pillReadyEl = document.getElementById("dpb-pill-ready");
  var pillFeedback = document.getElementById("dpb-pill-feedback");
  var anchors = [];
  var pinOn = false;
  var hoverEl = null;
  var floatRoot = null;
  var floatMap = {};  // selector -> bubble element
  var syncingFeedback = false;  // avoid feedback loop between pill input and drawer textarea

  // wayfinder canvas-upgrade 07: draft persistence (per-run localStorage) + anchor undo.
  var historyStack = [];
  var redoStack = [];  // #60: Ctrl/Cmd+Shift+Z redoes the most recent undo
  var DRAFT_KEY = window.DPB_DRAFT_KEY || "";

  function anchorSnapshot() {
    return JSON.stringify(anchors.map(function (a) {
      return { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
    }));
  }

  function pushHistorySnapshot(snapshot) {
    historyStack.push(snapshot);
    if (historyStack.length > 50) historyStack.shift();
    redoStack.length = 0;  // a fresh change invalidates the redo branch
  }

  function pushHistory() {
    pushHistorySnapshot(anchorSnapshot());
  }

  function restoreAnchorsFromData(list) {
    anchors.forEach(function (a) {
      if (a.el) a.el.classList.remove("dpb-pin-target");
    });
    anchors = (list || []).map(function (p) {
      var el = null;
      try { if (p.selector) el = document.querySelector(p.selector); } catch (e) {}
      return { selector: p.selector, label: p.label, comment: p.comment, tag: p.tag, el: el };
    }).filter(function (a) { return a.selector; });
    anchors.forEach(function (a) { if (a.el) a.el.classList.add("dpb-pin-target"); });
  }

  function undo() {
    if (!historyStack.length) return;
    var prev = null;
    try { prev = JSON.parse(historyStack.pop()); } catch (e) { return; }
    redoStack.push(anchorSnapshot());  // #60: keep the undone state redoable
    restoreAnchorsFromData(prev);
    render();
    setReadiness();
    saveDraft();
  }

  function redo() {
    // #60: Ctrl/Cmd+Shift+Z restores the most recent undo. Push the current
    // state straight onto historyStack (NOT pushHistorySnapshot, which would
    // wipe the remaining redo branch).
    if (!redoStack.length) return;
    var next = null;
    try { next = JSON.parse(redoStack.pop()); } catch (e) { return; }
    historyStack.push(anchorSnapshot());
    if (historyStack.length > 50) historyStack.shift();
    restoreAnchorsFromData(next);
    render();
    setReadiness();
    saveDraft();
  }

  function feedbackValue() {
    return (field && field.value || "").trim();
  }

  function setFeedbackValue(value, source) {
    // Single feedback state: pill 1-line input and drawer textarea stay in sync.
    syncingFeedback = true;
    try {
      var next = value == null ? "" : String(value);
      if (field && source !== "field" && field.value !== next) field.value = next;
      if (pillFeedback && source !== "pill" && pillFeedback.value !== next) {
        pillFeedback.value = next;
      }
    } finally {
      syncingFeedback = false;
    }
  }

  function saveDraft() {
    if (!DRAFT_KEY) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        feedback: field ? field.value : "",
        anchors: anchors.map(function (a) {
          return { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
        })
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
    if (typeof data.feedback === "string") setFeedbackValue(data.feedback, null);
    if (Array.isArray(data.anchors)) {
      restoreAnchorsFromData(data.anchors);
      render();
      setReadiness();
    }
  }

  function clearDraft() {
    if (!DRAFT_KEY) return;
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }

  // ---- sandbox iframe channel (#56 pin-state sync, #57 locate/badges) ----
  function protoFrame() {
    return document.querySelector("iframe.dpb-proto-frame");
  }
  function postToFrame(msg) {
    var f = protoFrame();
    if (f && f.contentWindow) {
      try { f.contentWindow.postMessage(msg, "*"); } catch (e) {}
    }
  }
  function syncPinToFrame() {
    // The parent owns pinOn; the bridge inside the opaque-origin iframe only
    // ever learns it through this message (on toggle, on iframe load, and as
    // an answer to the bridge's dpbPinHello resend request).
    postToFrame({ dpbPinState: { on: pinOn } });
  }
  function syncAnchorsToFrame() {
    // #57 scheme A: mirror the anchor list into the iframe as numbered
    // badges so cross-origin annotations stay visible on their elements.
    postToFrame({ dpbPinAnchors: anchors.map(function (a, i) {
      return { selector: a.selector, n: i + 1, comment: a.comment || "" };
    }) });
  }
  var announceEl = document.getElementById("dpb-announce");
  function announce(msg) {
    if (!announceEl) return;
    announceEl.textContent = "";
    window.setTimeout(function () { announceEl.textContent = msg || ""; }, 30);
  }

  function ensureFloatRoot() {
if (floatRoot) return floatRoot;
floatRoot = document.createElement("div");
floatRoot.id = "dpb-float-root";
floatRoot.setAttribute("data-theme", bar.getAttribute("data-theme") || "dark");
document.body.appendChild(floatRoot);
return floatRoot;
  }

  function esc(s) {
return String(s || "").replace(/[&<>"']/g, function (c) {
  return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
});
  }

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

  function labelFor(el) {
var t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
if (t.length > 40) t = t.slice(0, 40) + "…";
if (t) return el.tagName.toLowerCase() + ' "' + t + '"';
if (el.getAttribute("aria-label")) return el.tagName.toLowerCase() + " " + el.getAttribute("aria-label");
if (el.id) return "#" + el.id;
if (el.className && typeof el.className === "string") return el.tagName.toLowerCase() + "." + el.className.trim().split(/\s+/)[0];
return el.tagName.toLowerCase();
  }

  function labelForTag(tag, selector) {
// Cross-origin anchor (el is null): the parent cannot read innerText or
// aria-label from the sandboxed iframe DOM, so derive a readable label from
// the tag + the leaf segment of the cssPath selector the bridge sent.
var parts = String(selector || "").split(/\s*>\s*/);
var leaf = parts.length ? parts[parts.length - 1] : String(selector || "");
if (leaf.charAt(0) === "#") return leaf;
return (tag || "element") + " " + leaf;
  }

  function syncHidden() {
hidden.value = JSON.stringify(anchors.map(function (a) {
  return { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
}));
  }

  function positionFloat(a, idx) {
// ponytail: orphan guard — if target element left the DOM, drop the bubble
if (!a.el || !a.el.isConnected) { removeBubble(a.selector); return; }
var bubble = floatMap[a.selector];
if (!bubble) return;
var rect = a.el.getBoundingClientRect();
var root = ensureFloatRoot();
var nEl = bubble.querySelector(".dpb-float-n");
if (nEl) nEl.textContent = String(idx + 1);
bubble.style.left = (window.scrollX + rect.right + 8) + "px";
var top = window.scrollY + rect.top;
// keep on screen
var maxTop = window.scrollY + window.innerHeight - 60;
bubble.style.top = Math.min(top, maxTop) + "px";
// flip to left if overflows right
if (rect.right + 260 > window.innerWidth) {
  bubble.style.left = (window.scrollX + rect.left - bubble.offsetWidth - 8) + "px";
}
  }

  function ensureBubble(a, idx) {
if (!a.el || !a.el.isConnected) { removeBubble(a.selector); return; }
if (!floatMap[a.selector]) {
  var bubble = document.createElement("div");
  bubble.className = "dpb-float-note";
  bubble.setAttribute("role", "status");
  bubble.innerHTML =
    '<span class="dpb-float-n" aria-hidden="true">' + (idx + 1) + "</span>" +
    '<span class="dpb-float-label">' + esc(a.label) + "</span>" +
    '<span class="dpb-float-comment"></span>';
  ensureFloatRoot().appendChild(bubble);
  floatMap[a.selector] = bubble;
}
var bubble = floatMap[a.selector];
var commentEl = bubble.querySelector(".dpb-float-comment");
commentEl.textContent = a.comment || "";
bubble.style.display = a.comment ? "block" : "none";
if (a.comment) {
  // position after layout
  requestAnimationFrame(function () {
    positionFloat(a, idx);
    bubble.classList.add("is-visible");
  });
} else {
  bubble.classList.remove("is-visible");
}
  }

  function removeBubble(selector) {
var bubble = floatMap[selector];
if (bubble) {
  bubble.remove();
  delete floatMap[selector];
}
  }

  function render() {
listEl.innerHTML = "";
// C1: reconcile float bubbles with the anchor list — undo/redo and removals
// can leave stale selectors in floatMap; drop any bubble without an anchor.
var liveSelectors = {};
anchors.forEach(function (a) { liveSelectors[a.selector] = true; });
Object.keys(floatMap).forEach(function (sel) {
  if (!liveSelectors[sel]) removeBubble(sel);
});
if (!anchors.length) {
  listEl.classList.remove("has-items");
  syncHidden();
  updateCounts();
  return;
}
listEl.classList.add("has-items");
anchors.forEach(function (a, idx) {
  var row = document.createElement("div");
  row.className = "dpb-anchor";
  row.innerHTML =
    '<span class="n">' + (idx + 1) + "</span>" +
    '<div class="meta">' +
      '<button type="button" class="label" data-locate="' + idx + '" title="' + esc(I18N.locate) + '" aria-label="' + esc(I18N.locate_anchor) + ' ' + (idx + 1) + '">' + esc(a.label) + "</button>" +
      '<div class="sel" title="' + esc(a.selector) + '">' + esc(a.selector) + "</div>" +
      '<input type="text" data-i="' + idx + '" aria-label="' + esc(I18N.anchor_num_pre) + (idx + 1) + esc(I18N.anchor_num_post) + '" placeholder="' + esc(I18N.anchor_placeholder) + '" value="' + esc(a.comment) + '" />' +
    "</div>" +
    '<button type="button" class="rm" data-rm="' + idx + '" aria-label="' + esc(I18N.remove_num_pre) + (idx + 1) + '">' + esc(I18N.remove) + '</button>';
  listEl.appendChild(row);
  ensureBubble(a, idx);
});
syncHidden();
updateCounts();
syncAnchorsToFrame();  // #57: keep the in-iframe badges aligned with the list
  }

  function updateCounts() {
var n = anchors.length;
if (pinCountEl) pinCountEl.textContent = (I18N.pin_count_pre || "") + n + (I18N.pin_count_post || "");
if (pillCountEl) {
  pillCountEl.textContent = String(n);
  pillCountEl.classList.toggle("is-on", n > 0);
}
setReadiness();
  }

  // I4: ADR-0008 substantive predicate (mirror of adapter floor) + live readiness.
  // Structural only, no minimum length (ADR-0008: semantic junk is G6's job).
  function isSubstantive() {
var value = feedbackValue();
var anchorsComplete = !anchors.length || anchors.every(function (a) {
  return (a && (a.selector || "").trim() && (a.comment || "").trim());
});
return (value.length > 0 || anchors.length) && anchorsComplete;
  }

  function focusFeedback() {
// Status chip / not-ready paths: prefer visible pill quick input, else drawer textarea.
var pillVisible = !!(pillFeedback && pillFeedback.offsetParent !== null
  && !bar.classList.contains("is-open"));
if (pillVisible) {
  pillFeedback.focus();
  return;
}
if (!bar.classList.contains("is-open")) openDrawer();
setTimeout(function () { if (field) field.focus(); }, 0);
  }

  // Scheme A′: Ctrl/Cmd+Enter always routes confirm through isSubstantive floor.
  function trySubmitPrimary() {
if (isSubstantive()) {
  submitPrimary();
  return;
}
if (field) field.setAttribute("aria-invalid", "true");
if (hint) hint.classList.add("is-on");
focusFeedback();
  }
  var lastReady = null;
  var pillOpenLabel = null;  // I13: original pill-primary label, restored on ready->not-ready flip
  var openPrimary = document.getElementById("dpb-open-primary");
  // #60: pill confirm converged on ONE path — when substantive the pill
  // primary submits directly, exactly like the drawer primary. The old
  // three-state arm mechanism (arm -> 4s window -> submit) was removed so the
  // button behaves identically before and after the readiness flip.
  function setReadiness() {
if (!pillReadyEl) return;
var ready = isSubstantive();
pillReadyEl.classList.toggle("is-ready", ready);
if (ready === lastReady) return;  // P1.6: cache to avoid screen-reader jitter on every input
lastReady = ready;
if (ready) {
  pillReadyEl.textContent = I18N.ready || "";
  if (openPrimary) {
    if (pillOpenLabel === null) pillOpenLabel = openPrimary.textContent;  // I13: capture once
    openPrimary.classList.add('is-direct-confirm');
    openPrimary.removeAttribute('aria-haspopup');  // P1.1: direct confirm, no longer a dialog trigger
    // Mirror the confirm button label so user sees the action will confirm directly
    var drawerPrimary = document.querySelector('.dpb-drawer .dpb-btn-primary');
    if (drawerPrimary && drawerPrimary.textContent && openPrimary.textContent !== drawerPrimary.textContent) {
      openPrimary.textContent = drawerPrimary.textContent;
    }
  }
} else {
  pillReadyEl.textContent = I18N.not_ready || "";
  if (openPrimary) {
    openPrimary.classList.remove('is-direct-confirm');
    openPrimary.setAttribute('aria-haspopup', 'dialog');  // P1.1: restore dialog trigger
    // I13: restore original label so the pill no longer advertises direct confirm
    if (pillOpenLabel !== null && openPrimary.textContent !== pillOpenLabel) {
      openPrimary.textContent = pillOpenLabel;
    }
  }
}
  }

  function clearHover() {
if (hoverEl) {
  hoverEl.classList.remove("dpb-pin-hover");
  hoverEl = null;
}
  }

  function setPin(on) {
pinOn = !!on;
document.body.classList.toggle("dpb-pin-mode", pinOn);
if (pinBtn) {
  pinBtn.classList.toggle("is-on", pinOn);
  pinBtn.setAttribute("aria-pressed", pinOn ? "true" : "false");
}
if (pinLabel) pinLabel.textContent = pinOn ? (I18N.pin_on || "") : (I18N.pin_off || "");
// #58: when the drawer is collapsed while pin stays on, the pill annotate
// button carries the pin indicator and is the one-click path back to the list.
if (openBtn) {
  openBtn.classList.toggle("is-pinning", pinOn);
  openBtn.setAttribute("title", pinOn ? (I18N.pin_on || "") : (I18N.pin_toggle_desc || ""));
}
if (!pinOn) clearHover();
syncPinToFrame();  // #56: bridge switches interception mode instantly
  }

  var lastFocus = null;
  function openDrawer() {
lastFocus = document.activeElement;
// Use non-modal <dialog>.show() (NOT showModal): the drawer must NOT make the
// page inert, because pin-to-annotate requires clicking prototype elements
// behind the drawer. ::backdrop (modal only) is replaced by the .is-open::before
// scrim below. ESC + focus-restore handled manually.
// is-open is the reliable open signal (scrim/pill + CSS display fallback when
// dialog.show is missing or throws — drawer must not depend on dialog[open]).
if (drawerEl && typeof drawerEl.show === "function") {
  try { if (!drawerEl.open) drawerEl.show(); } catch (e) { /* fall through to is-open */ }
}
bar.classList.add("is-open");
setTimeout(function () { if (closeBtn) closeBtn.focus(); }, 0);
  }
  function closeDrawer() {
// #58: collapsing the drawer never turns pin off. Pin has its own explicit
// exits (the drawer's pick toggle, Esc), so anchors survive a collapse and the
// user can keep picking in prototype areas the 380px panel used to cover.
bar.classList.remove("is-open");
hideAbortPopover();  // Scheme A′: dismiss abort popover when drawer closes
if (drawerEl && drawerEl.open && typeof drawerEl.close === "function") drawerEl.close();
if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  // Shared: submit the confirm (drawer primary). Used by pill-primary arm path
  // and trySubmitPrimary (Ctrl+Enter) so confirm always hits the same submitter.
  function submitPrimary() {
var targetBtn = document.querySelector(".dpb-drawer .dpb-btn-primary");
if (targetBtn) form.requestSubmit(targetBtn); else form.requestSubmit();
  }

  // I2: 批注 (annotate) and the not-ready pill primary used to both just open
  // the drawer. Annotate now drops straight into element picking, so the two
  // buttons carry distinct intents (annotate elements vs. review/confirm).
  if (openBtn) openBtn.addEventListener("click", function () {
openDrawer();
setPin(true);
  });
  function handlePillPrimary(e) {
    // #60: single confirm path — identical semantics to the drawer primary.
    // Substantive -> submit confirm in one click; otherwise open the drawer
    // so the user can add the missing feedback. No arm state, no timeout.
    if (isSubstantive()) {
      e.preventDefault();
      submitPrimary();
    } else {
      openDrawer();
    }
  }
  if (openPrimary) openPrimary.addEventListener("click", handlePillPrimary);
  // Scheme A′: pill revise is type=submit — no open-drawer handler.
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (pinBtn) pinBtn.addEventListener("click", function () { setPin(!pinOn); });
  // Status chip focuses the feedback field (pill quick input or drawer textarea).
  if (pillReadyEl) {
pillReadyEl.addEventListener("click", function () { focusFeedback(); });
  }
  // P1.5: click on scrim (outside drawer) closes the drawer. Fires only when pin
  // is OFF (CSS sets scrim pointer-events:none while body.dpb-pin-mode is on, so
  // pin-on clicks reach the page for element selection, not the scrim).
  bar.addEventListener("click", function (e) {
if (bar.classList.contains("is-open") && !pinOn && e.target === bar) closeDrawer();
  });

  // Draft: keep current feedback/anchors in the form and close without a
  // confirm/revise decision (per debate); nothing is submitted or persisted.
  var draftBtn = document.getElementById("dpb-draft");
  if (draftBtn) draftBtn.addEventListener("click", function () { closeDrawer(); });

  // Pill quick feedback: single state with drawer textarea (wide layouts only in CSS).
  if (pillFeedback) {
pillFeedback.addEventListener("input", function () {
  if (syncingFeedback) return;
  setFeedbackValue(pillFeedback.value, "pill");
  if (isSubstantive()) {
    if (field) field.removeAttribute("aria-invalid");
    if (hint) hint.classList.remove("is-on");
  }
  setReadiness();
  saveDraft();
});
pillFeedback.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    trySubmitPrimary();
  }
});
  }

  // I8 / A′: Ctrl/Cmd+Enter submits confirm only when isSubstantive (floor gate).
  if (field) {
field.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    trySubmitPrimary();
  }
});
  }

  // Scheme A′: abort uses an explicit second-confirm popover (not 4s arm).
  var abortBtn = document.getElementById("dpb-abort");
  var abortStatus = document.getElementById("dpb-abort-status");
  var abortPopover = document.getElementById("dpb-abort-popover");
  var abortCancel = document.getElementById("dpb-abort-cancel");
  var abortConfirm = document.getElementById("dpb-abort-confirm");

  function abortPopoverOpen() {
return !!(abortPopover && !abortPopover.hidden);
  }
  function positionAbortPopover() {
// #60: real-measurement placement. The popover is already unhidden when this
// runs, so offsetWidth/offsetHeight give its true size — no hardcoded
// estimates that can push it off-screen when the drawer hugs the corner.
if (!abortPopover || !abortBtn || abortPopover.hidden) return;
var rect = abortBtn.getBoundingClientRect();
var pad = 8;
var popW = abortPopover.offsetWidth || 240;
var popH = abortPopover.offsetHeight || 110;
var left = rect.right + pad;
var top = rect.top;
if (left + popW > window.innerWidth - pad) {
  left = Math.max(pad, rect.left - popW - pad);
}
if (left < pad) left = pad;
if (top + popH > window.innerHeight - pad) {
  top = Math.max(pad, window.innerHeight - popH - pad);
}
if (top < pad) top = pad;
abortPopover.classList.add("is-fixed");
abortPopover.style.setProperty("--dpb-pop-left", left + "px");
abortPopover.style.setProperty("--dpb-pop-top", top + "px");
  }
  function clearAbortPopoverPosition() {
if (!abortPopover) return;
abortPopover.classList.remove("is-fixed");
abortPopover.style.removeProperty("--dpb-pop-left");
abortPopover.style.removeProperty("--dpb-pop-top");
  }
  function showAbortPopover() {
if (!abortPopover) return;
abortPopover.hidden = false;
positionAbortPopover();
if (abortBtn) {
  abortBtn.setAttribute("aria-expanded", "true");
  abortBtn.classList.add("is-armed");
}
if (abortStatus) abortStatus.textContent = I18N.terminate_confirm || "";
setTimeout(function () {
  if (abortConfirm && typeof abortConfirm.focus === "function") abortConfirm.focus();
}, 0);
  }
  function hideAbortPopover(announceCancel) {
var wasOpen = abortPopoverOpen();
if (abortPopover) abortPopover.hidden = true;
clearAbortPopoverPosition();
if (abortBtn) {
  abortBtn.setAttribute("aria-expanded", "false");
  abortBtn.classList.remove("is-armed");
}
if (abortStatus) {
  abortStatus.textContent = (announceCancel && wasOpen)
    ? (I18N.abort_cancelled || "")
    : "";
}
  }
  if (abortBtn) {
abortBtn.addEventListener("click", function (e) {
  e.preventDefault();
  e.stopPropagation();
  if (abortPopoverOpen()) hideAbortPopover();
  else showAbortPopover();
});
  }
  if (abortCancel) {
abortCancel.addEventListener("click", function () { hideAbortPopover(true); });
  }
  // Click elsewhere in the drawer dismisses the abort popover (not the confirm
  // submit control itself).
  if (drawerEl) drawerEl.addEventListener("click", function (e) {
if (!abortPopoverOpen()) return;
if (e.target.closest && e.target.closest(".dpb-abort-wrap")) return;
hideAbortPopover(true);
  });
  window.addEventListener("resize", function () {
if (abortPopoverOpen()) positionAbortPopover();
  });

  // wayfinder canvas-upgrade 07: restore any persisted draft (feedback +
  // anchors) before computing initial readiness, so a refresh keeps the run.
  loadDraft();

  // Initial readiness (may enable direct confirm on pill primary)
  setReadiness();

  // non-modal <dialog>.show() has no native focus trap / ESC. Mirror close +
  // trap Tab inside the drawer when pin is OFF; when pin is ON, Tab must reach
  // the prototype so keyboard users can move focus onto page elements.
  if (drawerEl) drawerEl.addEventListener("close", function () {
bar.classList.remove("is-open");
hideAbortPopover();  // defense-in-depth if dialog closes outside closeDrawer
// #58: like closeDrawer, a native close collapses the drawer without ending
// pin mode — picking state survives until explicitly toggled off.
  });
  function drawerFocusables() {
if (!drawerEl) return [];
var sel = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
var nodes = drawerEl.querySelectorAll(sel);
return Array.prototype.filter.call(nodes, function (el) {
  return !el.hasAttribute("disabled") && el.tabIndex !== -1 &&
    (el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement);
});
  }
  function isTextEditingTarget(target) {
if (!target || !target.closest) return false;
return !!target.closest('input, textarea, [contenteditable]:not([contenteditable="false"])');
  }
  function abortPopoverFocusables() {
if (!abortPopover || abortPopover.hidden) return [];
var sel = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
var nodes = abortPopover.querySelectorAll(sel);
return Array.prototype.filter.call(nodes, function (el) {
  return !el.hasAttribute("disabled") && el.tabIndex !== -1 &&
    (el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement);
});
  }
  document.addEventListener("keydown", function (e) {
if (e.key === "Escape") {
  // #59: Esc dismisses the one-time onboarding card first.
  if (onboardEl && !onboardEl.hidden) {
    e.preventDefault();
    dismissOnboarding();
    return;
  }
  if (abortPopoverOpen()) {
    e.preventDefault();
    hideAbortPopover(true);
    if (abortBtn && typeof abortBtn.focus === "function") abortBtn.focus();
    return;
  }
  if (pinOn) { setPin(false); return; }
  if (bar.classList.contains("is-open")) { e.preventDefault(); closeDrawer(); }
  return;
}
// wayfinder canvas-upgrade 07: Ctrl/Cmd+Z undoes the last anchor change
// (add / remove / committed comment edit). #60: Ctrl/Cmd+Shift+Z redoes it.
if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
  if (isTextEditingTarget(e.target)) return;
  e.preventDefault();
  if (e.shiftKey) { redo(); } else { undo(); }
  return;
}
if (e.key !== "Tab") return;
// When abort popover is open, trap Tab inside the popover (not the whole drawer).
if (abortPopoverOpen()) {
  var popList = abortPopoverFocusables();
  if (!popList.length) return;
  var pFirst = popList[0];
  var pLast = popList[popList.length - 1];
  var pActive = document.activeElement;
  var pOutside = !abortPopover.contains(pActive);
  if (e.shiftKey) {
    if (pOutside || pActive === pFirst) { e.preventDefault(); pLast.focus(); }
  } else {
    if (pOutside || pActive === pLast) { e.preventDefault(); pFirst.focus(); }
  }
  return;
}
if (!bar.classList.contains("is-open") || pinOn) return;  // pinOn: let Tab escape to prototype
var list = drawerFocusables();
if (!list.length) return;
var first = list[0];
var last = list[list.length - 1];
var active = document.activeElement;
var outside = !drawerEl.contains(active);
if (e.shiftKey) {
  if (outside || active === first) { e.preventDefault(); last.focus(); }
} else {
  if (outside || active === last) { e.preventDefault(); first.focus(); }
}
  });

  document.addEventListener("mousemove", function (e) {
if (!pinOn) return;
var el = e.target;
// W1: the onboarding card is control chrome, never a pick target.
if (!el || el.closest("#dpb-preview-bar") || el.closest("#dpb-float-root") || el.closest("#dpb-onboard")) {
  clearHover();
  return;
}
if (el === document.body || el === document.documentElement) {
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
if (!pinOn) return;
var raw = e.target;
// W1: clicks on the onboarding card (e.g. its dismiss button) must pass
// through even while picking — it is chrome, not prototype content.
if (!raw || raw.closest("#dpb-preview-bar") || raw.closest("#dpb-float-root") || raw.closest("#dpb-onboard")) return;
if (raw === document.body || raw === document.documentElement) return;
e.preventDefault();
e.stopPropagation();
// anchor to the hovered element, not the inner node that received the click
var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
var selector = cssPath(el);
if (!selector) return;
// de-dupe by selector; clear stale highlight on any previous element ref
for (var i = 0; i < anchors.length; i++) {
  if (anchors[i].selector === selector) {
    // #60: duplicate pick gets visible feedback (flash + live announcement)
    // instead of silently doing nothing.
    if (anchors[i].el && anchors[i].el !== el) anchors[i].el.classList.remove("dpb-pin-target");
    anchors[i].el = el;
    el.classList.add("dpb-pin-target");
    el.classList.remove("dpb-pin-flash");
    void el.offsetWidth;
    el.classList.add("dpb-pin-flash");
    announce(String(I18N.duplicate_anchor || "").replace("{n}", String(i + 1)));
    render();
    return;
  }
}
pushHistory();
el.classList.add("dpb-pin-target");
anchors.push({
  selector: selector,
  label: labelFor(el),
  comment: "",
  tag: el.tagName.toLowerCase(),
  el: el
});
render();
saveDraft();
// #60: no forced focus grab — picking several elements in a row must not yank
// the keyboard focus back into the drawer input each time.
  }, true);

  // G5 sandbox bridge: accept pin anchors postMessaged from the cross-origin
  // prototype iframe (opaque origin). The iframe cannot read the parent DOM or
  // the hidden decision token; it only sends {selector, tag}. Filter by
  // pinOn so anchors are only recorded while the user is annotating (the
  // bridge gates its own capture on the synced dpbPinState too — defense in
  // depth, #56). el is null cross-origin — the iframe highlights the element
  // itself (dpb-pin-target), and existing el-guarded code already tolerates
  // el === null.
  window.addEventListener("message", function (e) {
// W3: only accept messages from OUR sandboxed prototype iframe. Any other
// window (the prototype's own scripts run in it, but a foreign frame or the
// host page could also postMessage) must not be able to inject anchors.
var srcFrame = protoFrame();
if (!srcFrame || e.source !== srcFrame.contentWindow) return;
var data = e.data;
if (!data) return;
if (data.dpbPinHello) {
  // #56: bridge (re)loaded and asks for the current pin state. W2: resend
  // the badges too — a reload (or a draft restored before the iframe
  // parsed) must not strand the iframe without its numbered annotations.
  syncPinToFrame();
  syncAnchorsToFrame();
  return;
}
if (!pinOn) return;
if (!data.dpbPinAnchor) return;
var a = data.dpbPinAnchor;
var selector = String(a.selector || "");
var tag = String(a.tag || "").toLowerCase();
if (!selector) return;
// de-dupe by selector; no el/classList work (cross-origin)
for (var i = 0; i < anchors.length; i++) {
  if (anchors[i].selector === selector) {
    // #60: duplicate pick — flash the element inside the iframe and announce
    // the existing anchor number instead of failing silently.
    postToFrame({ dpbPinFlash: { selector: selector } });
    announce(String(I18N.duplicate_anchor || "").replace("{n}", String(i + 1)));
    return;
  }
}
pushHistory();
anchors.push({
  selector: selector,
  label: labelForTag(tag, selector),
  comment: "",
  tag: tag,
  el: null
});
render();
saveDraft();
// #60: no forced focus grab after a cross-origin pick either.
  });

  listEl.addEventListener("input", function (e) {
var t = e.target;
if (!t || !t.getAttribute) return;
if (t.getAttribute("data-i") == null) return;
var i = Number(t.getAttribute("data-i"));
anchors[i].comment = t.value;
syncHidden();
ensureBubble(anchors[i], i);
syncAnchorsToFrame();  // #57: badge notes in the iframe follow comment edits
setReadiness();
saveDraft();
  });

  // C4: comment-edit before-snapshots keyed by anchor index (NOT hung on the
  // input DOM node — render() rebuilds rows and would drop node-bound state,
  // making that edit un-undoable).
  var beforeEdits = {};
  listEl.addEventListener("focusin", function (e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    if (t.getAttribute("data-i") == null) return;
    beforeEdits[t.getAttribute("data-i")] = anchorSnapshot();
  });

  // wayfinder canvas-upgrade 07: comment edits enter the undo stack at their
  // commit point (change = blur/Enter), not on every keystroke.
  listEl.addEventListener("change", function (e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    var key = t.getAttribute("data-i");
    if (key == null) return;
    var before = beforeEdits[key];
    if (before != null && before !== anchorSnapshot()) {
      pushHistorySnapshot(before);
    }
    delete beforeEdits[key];
  });

  listEl.addEventListener("click", function (e) {
var t = e.target;
if (!t || !t.getAttribute) return;
var loc = t.getAttribute("data-locate");
if (loc != null) {
  e.preventDefault();
  var a = anchors[Number(loc)];
  if (!a) return;
  if (a.el && a.el.isConnected) {
    a.el.scrollIntoView({ behavior: "smooth", block: "center" });
    a.el.classList.remove("dpb-pin-flash");
    // force reflow so the animation can restart
    void a.el.offsetWidth;
    a.el.classList.add("dpb-pin-flash");
  } else {
    // #57 scheme A: cross-origin anchor (el is null) — ask the bridge to
    // scroll + flash the element inside the sandboxed iframe.
    postToFrame({ dpbPinLocate: { selector: a.selector } });
  }
  return;
}
var rm = t.getAttribute("data-rm");
if (rm == null) return;
var i = Number(rm);
var a = anchors[i];
if (a) {
  if (a.el) a.el.classList.remove("dpb-pin-target");
  removeBubble(a.selector);
}
pushHistory();
anchors.splice(i, 1);
render();
setReadiness();
saveDraft();
  });

  // reposition floats on scroll/resize with requestAnimationFrame throttling
  var ticking = false;
  function repositionAll() {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        anchors.forEach(function (a, idx) { positionFloat(a, idx); });
        ticking = false;
      });
      ticking = true;
    }
  }
  window.addEventListener("scroll", repositionAll, true);
  window.addEventListener("resize", repositionAll);

  // ADR-0008 advisory UX check; Python Preview integrity is authoritative.
  // (non-empty feedback OR >=1 anchor) AND all anchors complete.
  form.addEventListener("submit", function (e) {
syncHidden();
var submitter = e.submitter;
var choice = submitter && submitter.name === "choice" ? submitter.value : "";
if (!choice || choice === "__abort__") { clearDraft(); return; }
if (isSubstantive()) {
  if (field) field.removeAttribute("aria-invalid");
  if (hint) hint.classList.remove("is-on");
  clearDraft();  // real submit: drop the persisted draft
  return;
}
e.preventDefault();
if (!bar.classList.contains("is-open")) openDrawer();
if (field) {
  field.setAttribute("aria-invalid", "true");
  setTimeout(function () { field.focus(); }, 0);
}
if (hint) hint.classList.add("is-on");
// I1: do NOT force pin mode on - that was an intent guess; the user may want
// overall feedback, not element selection.
  });
  if (field) {
field.addEventListener("input", function () {
  if (syncingFeedback) return;
  setFeedbackValue(field.value, "field");
  if (isSubstantive()) {
    field.removeAttribute("aria-invalid");
    if (hint) hint.classList.remove("is-on");
  }
  setReadiness();
  saveDraft();
});
  }

  // ---- #59: one-time onboarding card (pin flow + shortcuts) ----
  var ONBOARD_KEY = "dpb.preview.onboard.v1";
  var onboardEl = document.getElementById("dpb-onboard");
  var onboardCloseBtn = document.getElementById("dpb-onboard-close");
  function showOnboarding() {
if (!onboardEl) return;
var seen = false;
try { seen = !!localStorage.getItem(ONBOARD_KEY); } catch (e) {}
if (seen) return;
onboardEl.hidden = false;
// C3: strictly one-time — mark as read the moment it is shown, not only on
// dismiss. A user who never clicks away still never sees it twice.
try { localStorage.setItem(ONBOARD_KEY, "1"); } catch (e) {}
if (onboardCloseBtn) setTimeout(function () { onboardCloseBtn.focus(); }, 0);
  }
  function dismissOnboarding() {
if (!onboardEl) return;
onboardEl.hidden = true;
try { localStorage.setItem(ONBOARD_KEY, "1"); } catch (e) {}
  }
  if (onboardCloseBtn) onboardCloseBtn.addEventListener("click", dismissOnboarding);
  showOnboarding();

  // ---- #56: keep the sandbox bridge in sync with the parent pin state ----
  // The iframe element is parsed after this inline script, so attach the load
  // resend once the DOM is complete; the bridge's dpbPinHello covers reloads.
  document.addEventListener("DOMContentLoaded", function () {
var f = protoFrame();
if (f) f.addEventListener("load", function () {
  // W2: a (re)loaded iframe lost its bridge state — resend pin mode AND the
  // numbered badges so annotations survive iframe reloads.
  syncPinToFrame();
  syncAnchorsToFrame();
});
syncPinToFrame();
  });
})();
