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
  var anchors = [];
  var pinOn = false;
  var hoverEl = null;
  var floatRoot = null;
  var floatMap = {};  // selector -> bubble element

  // wayfinder canvas-upgrade 07: draft persistence (per-run localStorage) + anchor undo.
  var historyStack = [];
  var DRAFT_KEY = window.DPB_DRAFT_KEY || "";

  function pushHistory() {
    historyStack.push(JSON.stringify(anchors.map(function (a) {
      return { selector: a.selector, label: a.label, comment: a.comment, tag: a.tag };
    })));
    if (historyStack.length > 50) historyStack.shift();
  }

  function restoreAnchorsFromData(list) {
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
    restoreAnchorsFromData(prev);
    render();
    setReadiness();
    saveDraft();
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
    if (field && typeof data.feedback === "string") field.value = data.feedback;
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
  if (cur.id === "dpb-preview-bar" || cur.id === "dpb-preview-spacer" || cur.id === "dpb-float-root") break;
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
var value = (field && field.value || "").trim();
var anchorsComplete = !anchors.length || anchors.every(function (a) {
  return (a && (a.selector || "").trim() && (a.comment || "").trim());
});
return (value.length > 0 || anchors.length) && anchorsComplete;
  }
  var lastReady = null;
  var pillOpenLabel = null;  // I13: original pill-primary label, restored on ready->not-ready flip
  var openPrimary = document.getElementById("dpb-open-primary");
  // Pill direct-confirm 二级保护: first click arms, second submits (mirrors abort arm).
  var CONFIRM_ARM_MS = 4000;
  var pillConfirmArmed = false;
  var pillConfirmTimer = null;
  var pillConfirmReadyLabel = null;  // label while ready (pre-arm)
  var pillArmStatus = document.getElementById("dpb-pill-arm-status");
  function resetPillConfirmArmed(announceCancel) {
if (pillConfirmTimer) { clearTimeout(pillConfirmTimer); pillConfirmTimer = null; }
var wasArmed = pillConfirmArmed;
if (openPrimary && pillConfirmArmed) {
  pillConfirmArmed = false;
  openPrimary.classList.remove("is-armed");
  if (pillConfirmReadyLabel !== null) openPrimary.textContent = pillConfirmReadyLabel;
}
if (pillArmStatus) {
  pillArmStatus.textContent = (announceCancel && wasArmed)
    ? (I18N.confirm_cancelled || "")
    : "";
}
  }
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
    pillConfirmReadyLabel = openPrimary.textContent;  // snapshot for arm restore
  }
} else {
  resetPillConfirmArmed();  // readiness flip undoes any pending arm
  pillReadyEl.textContent = I18N.not_ready || "";
  if (openPrimary) {
    openPrimary.classList.remove('is-direct-confirm');
    openPrimary.setAttribute('aria-haspopup', 'dialog');  // P1.1: restore dialog trigger
    // I13: restore original label so the pill no longer advertises direct confirm
    if (pillOpenLabel !== null && openPrimary.textContent !== pillOpenLabel) {
      openPrimary.textContent = pillOpenLabel;
    }
  }
  pillConfirmReadyLabel = null;
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
if (!pinOn) clearHover();
  }

  var lastFocus = null;
  function openDrawer() {
lastFocus = document.activeElement;
resetPillConfirmArmed();  // drawer open: pill is hidden; drop any pending confirm arm
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
bar.classList.remove("is-open");
resetAbortArmed();  // I18: clear abort arming when drawer closes (no stale armed state on reopen)
resetPillConfirmArmed();  // pill reappears disarmed
if (pinOn) setPin(false);
if (drawerEl && drawerEl.open && typeof drawerEl.close === "function") drawerEl.close();
if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  // I2: 批注 (annotate) and the not-ready pill primary used to both just open
  // the drawer. Annotate now drops straight into element picking, so the two
  // buttons carry distinct intents (annotate elements vs. review/confirm).
  if (openBtn) openBtn.addEventListener("click", function () {
openDrawer();
setPin(true);
  });
  // Shared: submit the confirm (drawer primary). Used by pill-primary direct
  // confirm (handlePillPrimary) and Ctrl+Enter (I8) to avoid divergent targets.
  function submitPrimary() {
var targetBtn = document.querySelector(".dpb-drawer .dpb-btn-primary");
if (targetBtn) form.requestSubmit(targetBtn); else form.requestSubmit();
  }
  function handlePillPrimary(e) {
    if (isSubstantive()) {
      // 二级保护: ready pill primary is arm → confirm (not one-click submit).
      // Accidental click on a resting "确认通过" must not kill the review session.
      e.preventDefault();
      if (!pillConfirmArmed) {
        pillConfirmArmed = true;
        if (pillConfirmReadyLabel === null) pillConfirmReadyLabel = openPrimary.textContent;
        openPrimary.classList.add("is-armed");
        openPrimary.textContent = I18N.confirm_confirm || "";
        if (pillArmStatus) pillArmStatus.textContent = I18N.confirm_confirm || "";
        pillConfirmTimer = setTimeout(function () { resetPillConfirmArmed(true); }, CONFIRM_ARM_MS);
        return;
      }
      resetPillConfirmArmed();
      submitPrimary();
    } else {
      resetPillConfirmArmed();
      openDrawer();
    }
  }
  if (openPrimary) openPrimary.addEventListener("click", handlePillPrimary);
  var pillReviseBtns = bar.querySelectorAll('[data-pill-revise]');
  for (var ri = 0; ri < pillReviseBtns.length; ri++) {
    pillReviseBtns[ri].addEventListener("click", function () {
      resetPillConfirmArmed();
      openDrawer();
      setTimeout(function () { if (field) field.focus(); }, 0);
    });
  }
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (pinBtn) pinBtn.addEventListener("click", function () { setPin(!pinOn); });
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

  // I8: Ctrl/Cmd+Enter in the feedback textarea submits the confirm (primary) action
  if (field) {
field.addEventListener("keydown", function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    submitPrimary();
  }
});
  }

  // I18: abort requires a second click within the confirm window (prevents accidental
  // session kill). First click arms the button for ABORT_ARM_MS; second click submits __abort__.
  // Armed state is announced to screen readers via the #dpb-abort-status alert
  // region (the visible textContent swap alone is not reliably announced).
  // 4000ms: at 2000ms a hesitant user's second click landed AFTER expiry and
  // just re-armed, so the button felt dead no matter how often it was clicked.
  var ABORT_ARM_MS = 4000;
  var abortBtn = document.getElementById("dpb-abort");
  var abortStatus = document.getElementById("dpb-abort-status");
  var abortArmed = false;
  var abortTimer = null;
  var abortLabel = "";
  // announceCancel: when true (4s timeout), write "cancelled" to the sr-only
  // status so screen readers hear the arm expire; other paths clear silently.
  function resetAbortArmed(announceCancel) {
if (abortTimer) { clearTimeout(abortTimer); abortTimer = null; }
var wasArmed = abortArmed;
if (abortBtn && abortArmed) {
  abortArmed = false;
  abortBtn.textContent = abortLabel;
  abortBtn.classList.remove("is-armed");
}
if (abortStatus) {
  abortStatus.textContent = (announceCancel && wasArmed)
    ? (I18N.abort_cancelled || "")
    : "";
}
  }
  if (abortBtn) {
abortLabel = abortBtn.textContent;
abortBtn.addEventListener("click", function (e) {
  if (!abortArmed) {
    e.preventDefault();
    abortArmed = true;
    abortBtn.textContent = I18N.terminate_confirm || "";
    abortBtn.classList.add("is-armed");
    if (abortStatus) abortStatus.textContent = I18N.terminate_confirm || "";
    abortTimer = setTimeout(function () { resetAbortArmed(true); }, ABORT_ARM_MS);
  }  // else: let the submit proceed (choice=__abort__)
});
  }
  // MEDIUM: clicking elsewhere in the drawer cancels abort arming (not just
  // ESC / 4s timeout); the abort button's own click is excluded via closest.
  if (drawerEl) drawerEl.addEventListener("click", function (e) {
if (abortArmed && abortBtn && !e.target.closest("#dpb-abort")) {
  resetAbortArmed();
}
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
resetAbortArmed();  // I18: defense-in-depth - clear arming if a future path closes the dialog directly
if (pinOn) setPin(false);
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
  document.addEventListener("keydown", function (e) {
if (e.key === "Escape") {
  if (pinOn) { setPin(false); return; }
  if (bar.classList.contains("is-open")) { e.preventDefault(); closeDrawer(); }
  return;
}
// wayfinder canvas-upgrade 07: Ctrl/Cmd+Z undoes the last anchor change
// (add / remove / committed comment edit).
if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
  if (!e.shiftKey) { e.preventDefault(); undo(); }
  return;
}
if (e.key !== "Tab") return;
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
if (!el || el.closest("#dpb-preview-bar") || el.closest("#dpb-preview-spacer") || el.closest("#dpb-float-root")) {
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
if (!raw || raw.closest("#dpb-preview-bar") || raw.closest("#dpb-preview-spacer") || raw.closest("#dpb-float-root")) return;
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
    if (anchors[i].el && anchors[i].el !== el) anchors[i].el.classList.remove("dpb-pin-target");
    anchors[i].el = el;
    el.classList.add("dpb-pin-target");
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
// focus newest comment input
setTimeout(function () {
  var inputs = listEl.querySelectorAll("input[data-i]");
  if (inputs.length) inputs[inputs.length - 1].focus();
}, 0);
  }, true);

  // G5 sandbox bridge: accept pin anchors postMessaged from the cross-origin
  // prototype iframe (opaque origin). The iframe cannot read the parent DOM or
  // the hidden decision token; it only sends {selector, tag}. Filter by
  // pinOn so the always-on bridge only records while the user is annotating
  // (no pin-state sync needed). el is null cross-origin — the iframe highlights
  // the element itself (dpb-pin-target), and existing el-guarded code
  // (positionFloat/ensureBubble/locate) already tolerates el === null.
  window.addEventListener("message", function (e) {
if (!pinOn) return;
var data = e.data;
if (!data || !data.dpbPinAnchor) return;
var a = data.dpbPinAnchor;
var selector = String(a.selector || "");
var tag = String(a.tag || "").toLowerCase();
if (!selector) return;
// de-dupe by selector; no el/classList work (cross-origin)
for (var i = 0; i < anchors.length; i++) {
  if (anchors[i].selector === selector) return;
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
setTimeout(function () {
  var inputs = listEl.querySelectorAll("input[data-i]");
  if (inputs.length) inputs[inputs.length - 1].focus();
}, 0);
  });

  listEl.addEventListener("input", function (e) {
var t = e.target;
if (!t || !t.getAttribute) return;
if (t.getAttribute("data-i") == null) return;
var i = Number(t.getAttribute("data-i"));
anchors[i].comment = t.value;
syncHidden();
ensureBubble(anchors[i], i);
setReadiness();
saveDraft();
  });

  // wayfinder canvas-upgrade 07: comment edits enter the undo stack at their
  // commit point (change = blur/Enter), not on every keystroke.
  listEl.addEventListener("change", function (e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    if (t.getAttribute("data-i") == null) return;
    pushHistory();
  });

  listEl.addEventListener("click", function (e) {
var t = e.target;
if (!t || !t.getAttribute) return;
var loc = t.getAttribute("data-locate");
if (loc != null) {
  e.preventDefault();
  var a = anchors[Number(loc)];
  if (a && a.el && a.el.isConnected) {
    a.el.scrollIntoView({ behavior: "smooth", block: "center" });
    a.el.classList.remove("dpb-pin-flash");
    // force reflow so the animation can restart
    void a.el.offsetWidth;
    a.el.classList.add("dpb-pin-flash");
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

  // ADR-0008: confirm requires substantive feedback too -
  // (non-empty feedback OR >=1 anchor) AND all anchors complete.
  // Frontend mirrors adapter _check_feedback_floor via isSubstantive().
  var reviseLabels = {__DPB_REVISE_LABELS__};
  form.addEventListener("submit", function (e) {
syncHidden();
var submitter = e.submitter;
var choice = submitter && submitter.name === "choice" ? submitter.value : "";
if (!choice || choice === "__abort__") { clearDraft(); return; }
var isRevise = !!reviseLabels[choice] || /修改|revise|change/i.test(choice);
// For revise actions (e.g. "需要修改"), allow even without substantive feedback (the point is to request changes).
// Only enforce floor for actual confirm actions.
if (isRevise || isSubstantive()) {
  if (field) field.removeAttribute("aria-invalid");
  if (hint) hint.classList.remove("is-on");
  clearDraft();  // real submit: drop the persisted draft
  return;
}
e.preventDefault();
if (field) { field.setAttribute("aria-invalid", "true"); field.focus(); }
if (hint) hint.classList.add("is-on");
if (!bar.classList.contains("is-open")) openDrawer();
// I1: do NOT force pin mode on - that was an intent guess; the user may want
// overall feedback, not element selection.
  });
  if (field) {
field.addEventListener("input", function () {
  if (isSubstantive()) {
    field.removeAttribute("aria-invalid");
    if (hint) hint.classList.remove("is-on");
  }
  setReadiness();
  saveDraft();
});
  }
})();
