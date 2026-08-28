  // ---- control.review.js: drawer/review UI half of control.js ----
  // Concatenated at the review insertion marker in control.js by
  // control.py (_load_resources); both fragments share one IIFE scope.

  // ---- annotation list rendering (v9 cards) ----
  function kindChip(a) {
    if (a.tag === "draw") return "draw";
    if (a.tag === "box") return "box";
    if (a.tag === "pin") return "pin";
    if (a.tag === "copy" || a.tag === "layout" || a.tag === "visual") return a.tag;
    if (String(a.selector).charAt(0) === "@") return "note";
    return "element";
  }
  function visibleAnchors() {
    return anchors.map(function (a, i) { return { a: a, i: i }; }).filter(function (x) {
      if (filter === "pending") return !resolvedSet[x.a.selector];
      if (filter === "resolved") return !!resolvedSet[x.a.selector];
      return true;
    });
  }
  function render(persistDraft) {
    listEl.innerHTML = "";
    var liveSelectors = {};
    anchors.forEach(function (a) { liveSelectors[a.selector] = true; });
    Object.keys(floatMap).forEach(function (sel) {
      if (!liveSelectors[sel]) removeBubble(sel);
    });
    listEl.classList.toggle("has-items", anchors.length > 0);
    if (!anchors.length) {
      listEl.innerHTML = '<div class="dpb-anchor-empty">'
        + '<svg viewBox="0 0 16 16" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 2.5v11M2.5 8h11"/><circle cx="8" cy="8" r="5.5"/></svg>'
        + '<div class="dpb-anchor-empty-title">' + esc(tt("drawer_empty_title")) + '</div>'
        + '<p class="dpb-anchor-empty-desc">' + esc(tt("drawer_empty_desc")) + '</p>'
        + '</div>';
      syncHidden();
      updateCounts();
      renderDrawStrokes();
      renderFreePins();
      syncAnchorsToFrame();
      if (persistDraft !== false) scheduleDraft();
      return;
    }
    var entered = [];
    anchors.forEach(function (a, idx) {
      var isFresh = !!a.__fresh;
      var row = document.createElement("div");
      row.className = "dpb-anchor"
        + (idx === activeIdx ? " dpb-active" : "")
        + (resolvedSet[a.selector] ? " dpb-resolved" : "")
        + (isFresh ? " dpb-anchor-enter" : "");
      if (isFresh) entered.push(row);
      if (filter === "resolved" && !resolvedSet[a.selector]) row.style.display = "none";
      if (filter === "pending" && resolvedSet[a.selector]) row.style.display = "none";
      row.innerHTML =
        '<div class="dpb-anchor-meta">'
        + '<span class="dpb-anchor-n">' + (idx + 1) + "</span>"
        + '<span class="dpb-anchor-kind">' + esc(kindChip(a)) + "</span>"
        + '<span class="dpb-anchor-sel" title="' + esc(a.selector) + '">' + esc(a.selector) + "</span>"
        + "</div>"
        + '<div class="dpb-anchor-row">'
        + '<input type="text" data-i="' + idx + '" aria-label="' + esc(tt("anchor_num_pre") + (idx + 1) + tt("anchor_num_post")) + '" placeholder="' + esc(tt("anchor_placeholder")) + '" value="' + esc(a.comment) + '" />'
        + '<button type="button" class="dpb-anchor-rm" data-rm="' + idx + '" aria-label="' + esc(tt("remove_num_pre") + (idx + 1)) + '">' + esc(tt("remove")) + "</button>"
        + "</div>"
        + '<div class="dpb-anchor-foot">'
        + '<button type="button" class="dpb-anchor-resolve" data-rs="' + idx + '">'
        + (resolvedSet[a.selector] ? esc(tt("reopen")) : esc(tt("mark_resolved")))
        + "</button>"
        + '<span class="dpb-anchor-id">#' + (idx + 1) + "</span>"
        + "</div>";
      row.addEventListener("click", function (ev) {
        if (ev.target.closest("input, button")) return;
        focusAnchor(idx);
      });
      listEl.appendChild(row);
      ensureBubble(a, idx);
    });
    syncHidden();
    updateCounts();
    renderDrawStrokes();
    renderFreePins();
    syncAnchorsToFrame();
    entered.forEach(function (el) { clearEntranceClass(el, "dpb-anchor-enter"); });
    anchors.forEach(function (a) { delete a.__fresh; });
    if (persistDraft !== false) scheduleDraft();
  }
  function updateCounts() {
    var n = anchors.length;
    var pending = anchors.filter(function (a) { return !resolvedSet[a.selector]; }).length;
    if (countBadge) countBadge.textContent = String(pending);
    if (reopenBadge) reopenBadge.textContent = String(pending);
    var fa = document.getElementById("dpb-filter-n-all");
    var fp = document.getElementById("dpb-filter-n-pending");
    var fr = document.getElementById("dpb-filter-n-resolved");
    if (fa) fa.textContent = String(n);
    if (fp) fp.textContent = String(pending);
    if (fr) fr.textContent = String(n - pending);
    updateStatus();
  }
  function updateStatus() {
    if (!statusPill) return;
    var ready = isSubstantive();
    statusPill.classList.toggle("dpb-is-ready", ready);
    var pending = anchors.filter(function (a) { return !resolvedSet[a.selector]; }).length;
    statusText.textContent = ready
      ? ttN("status_ready", pending)
      : tt("status_not_ready");
    if (statusApprove) statusApprove.disabled = false;
  }

  // list interactions (delegated)
  listEl.addEventListener("input", function (e) {
    var input = e.target.closest("input[data-i]");
    if (!input) return;
    var idx = parseInt(input.getAttribute("data-i"), 10);
    anchors[idx].comment = input.value;
    var bubble = floatMap[anchors[idx].selector];
    if (bubble) {
      var noteEl = bubble.querySelector(".dpb-float-note");
      if (noteEl) noteEl.textContent = input.value;
    }
    postToFrame({ dpbPinNote: { selector: anchors[idx].selector, comment: input.value } });
    syncHidden();
    updateStatus();
    scheduleDraft();
  });
  // C4: comment-edit before-snapshots keyed by anchor index (NOT hung on the
  // input DOM node - render() rebuilds rows and would drop node-bound state,
  // making that edit un-undoable).
  var beforeEdits = {};
  listEl.addEventListener("focusin", function (e) {
    var t = e.target.closest("input[data-i]");
    if (!t) return;
    beforeEdits[t.getAttribute("data-i")] = anchorSnapshot();
  });
  // comment edits enter the undo stack at their commit point
  // (change = blur/Enter), not on every keystroke.
  listEl.addEventListener("change", function (e) {
    var t = e.target.closest("input[data-i]");
    if (!t) return;
    var key = t.getAttribute("data-i");
    var before = beforeEdits[key];
    if (before != null && before !== anchorSnapshot()) {
      pushHistorySnapshot(before);
    }
    delete beforeEdits[key];
  });
  listEl.addEventListener("click", function (e) {
    var rm = e.target.closest("[data-rm]");
    if (rm) {
      var idx = parseInt(rm.getAttribute("data-rm"), 10);
      pushHistory();
      var removed = anchors.splice(idx, 1)[0];
      if (removed) delete resolvedSet[removed.selector];
      if (activeIdx >= anchors.length) activeIdx = anchors.length - 1;
      render();
      return;
    }
    var rs = e.target.closest("[data-rs]");
    if (rs) {
      var i2 = parseInt(rs.getAttribute("data-rs"), 10);
      var sel = anchors[i2].selector;
      if (resolvedSet[sel]) {
        delete resolvedSet[sel];
        toast(ttN("toast_reopened", i2 + 1));
      } else {
        resolvedSet[sel] = true;
        toast(ttN("toast_resolved", i2 + 1));
      }
      render();
      return;
    }
  });

  // ---- focus / roam (J/K) ----
  function focusAnchor(idx) {
    if (idx < 0 || idx >= anchors.length) return;
    activeIdx = idx;
    var rows = listEl.querySelectorAll(".dpb-anchor");
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove("dpb-active");
    var row = listEl.querySelector('.dpb-anchor input[data-i="' + idx + '"]');
    if (row && row.closest(".dpb-anchor")) {
      row.closest(".dpb-anchor").classList.add("dpb-active");
      try { row.closest(".dpb-anchor").scrollIntoView({ behavior: "smooth", block: "nearest" }); } catch (e) {}
    }
    var a = anchors[idx];
    if (a.el) {
      try { a.el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
    }
    postToFrame({ dpbPinLocate: { selector: a.selector } });
    anchors.forEach(ensureBubble);
    repositionAll();
    renderFreePins();
    syncAnchorsToFrame();
  }
  function roam(dir) {
    if (!anchors.length) return;
    activeIdx = (activeIdx + dir + anchors.length) % anchors.length;
    focusAnchor(activeIdx);
    toast(ttN("toast_focus", activeIdx + 1));
  }
  document.getElementById("dpb-roam-prev").addEventListener("click", function () { roam(-1); });
  document.getElementById("dpb-roam-next").addEventListener("click", function () { roam(1); });

  // ---- filters ----
  function setFilter(f) {
    filter = f;
    ["all", "pending", "resolved"].forEach(function (k) {
      var b = document.getElementById("dpb-filter-" + k);
      if (b) b.setAttribute("aria-pressed", k === f ? "true" : "false");
    });
    render();
  }
  ["all", "pending", "resolved"].forEach(function (k) {
    var b = document.getElementById("dpb-filter-" + k);
    if (b) b.addEventListener("click", function () { setFilter(k); });
  });

  // ---- comment form: tags + add note ----
  Array.prototype.forEach.call(document.querySelectorAll(".dpb-tag"), function (b) {
    b.addEventListener("click", function () {
      activeTag = b.getAttribute("data-tag") || "copy";
      Array.prototype.forEach.call(document.querySelectorAll(".dpb-tag"), function (x) {
        x.classList.toggle("is-on", x === b);
      });
    });
  });
  function submitComment() {
    var val = commentInput.value.trim();
    if (!val) return;
    noteSeq += 1;
    pushHistory();
    anchors.push(markFresh({
      selector: "@note-" + noteSeq,
      label: val.slice(0, 18),
      comment: val,
      tag: activeTag,
    }));
    commentInput.value = "";
    render();
    activeIdx = anchors.length - 1;
    focusAnchor(activeIdx);
    toast(ttN("toast_note_added", anchors.length));
  }
  document.getElementById("dpb-comment-send").addEventListener("click", submitComment);

  // ---- readiness (I4 floor mirror) ----
  function feedbackValue() { return field ? field.value : ""; }
  function isSubstantive() {
    // Mirror of the adapter floor (integrity.evaluate_feedback):
    // when ANY anchor exists, every anchor must carry a non-empty comment
    // (feedback alone cannot compensate); with no anchors, non-empty
    // feedback is substantive. No minimum length (ADR-0008).
    if (anchors.length) {
      return anchors.every(function (a) {
        return String(a.comment || "").trim() !== "";
      });
    }
    return feedbackValue().trim() !== "";
  }
  function setReadiness() { updateStatus(); }
  if (field) field.addEventListener("input", function () { setReadiness(); scheduleDraft(); });

  // ---- drawer collapse ----
  function setDrawer(open, quiet) {
    inspector.classList.toggle("dpb-collapsed", !open);
    reopenTab.hidden = open;
    if (!quiet) toast(tt(open ? "toast_drawer_open" : "toast_drawer_closed"));
  }
  document.getElementById("dpb-drawer-toggle").addEventListener("click", function () { setDrawer(inspector.classList.contains("dpb-collapsed")); });
  document.getElementById("dpb-inspector-close").addEventListener("click", function () { setDrawer(false); });
  reopenTab.addEventListener("click", function () { setDrawer(true); });

  // ---- abort popover (Scheme A′) ----
  var abortBtn = document.getElementById("dpb-abort");
  var abortStatus = document.getElementById("dpb-abort-status");
  var abortPopover = document.getElementById("dpb-abort-popover");
  var abortCancel = document.getElementById("dpb-abort-cancel");
  var abortConfirm = document.getElementById("dpb-abort-confirm");
  function abortPopoverOpen() { return !!(abortPopover && !abortPopover.hidden); }
  function clearAbortPopoverPosition() {
    if (abortPopover) { abortPopover.style.left = ""; abortPopover.style.top = ""; }
  }
  function positionAbortPopover() {
    if (!abortPopover || !abortBtn) return;
    var r = abortBtn.getBoundingClientRect();
    var pw = abortPopover.offsetWidth || 240;
    var left = Math.max(8, Math.min(r.left + r.width / 2 - pw / 2, window.innerWidth - pw - 8));
    abortPopover.style.setProperty("--dpb-pop-left", left + "px");
    abortPopover.style.setProperty("--dpb-pop-top", (r.bottom + 8 + window.scrollY) + "px");
  }
  function showAbortPopover() {
    if (!abortPopover) return;
    abortPopover.hidden = false;
    positionAbortPopover();
    if (abortBtn) {
      abortBtn.setAttribute("aria-expanded", "true");
      abortBtn.classList.add("is-armed");
    }
    setTimeout(function () { if (abortConfirm) abortConfirm.focus(); }, 0);
  }
  function hideAbortPopover(announceCancel) {
    var wasOpen = abortPopoverOpen();
    abortPopover.hidden = true;
    clearAbortPopoverPosition();
    if (abortBtn) {
      abortBtn.setAttribute("aria-expanded", "false");
      abortBtn.classList.remove("is-armed");
    }
    if (abortStatus) {
      abortStatus.textContent = (announceCancel && wasOpen) ? tt("abort_cancelled") : "";
    }
  }
  if (abortBtn) abortBtn.addEventListener("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    if (abortPopoverOpen()) hideAbortPopover();
    else showAbortPopover();
  });
  if (abortCancel) abortCancel.addEventListener("click", function () { hideAbortPopover(true); });
  // Click elsewhere in the shell dismisses the abort popover.
  root.addEventListener("click", function (e) {
    if (!abortPopoverOpen()) return;
    if (e.target.closest && e.target.closest(".dpb-abort-wrap")) return;
    hideAbortPopover(true);
  });
  window.addEventListener("resize", function () { if (abortPopoverOpen()) positionAbortPopover(); });

  // ---- shortcut modal ----
  function toggleModal(show) {
    if (!modal) return;
    modal.hidden = !show;
    if (show) {
      var ok = document.getElementById("dpb-shortcut-ok");
      if (ok) setTimeout(function () { ok.focus(); }, 0);
    }
  }
  document.getElementById("dpb-shortcuts-btn").addEventListener("click", function () { toggleModal(true); });
  document.getElementById("dpb-shortcut-close").addEventListener("click", function () { toggleModal(false); });
  document.getElementById("dpb-shortcut-ok").addEventListener("click", function () { toggleModal(false); });
  modal.addEventListener("click", function (e) { if (e.target === modal) toggleModal(false); });

  // ---- language toggle (L) ----
  function toggleLanguage() {
    langState = langState === "zh" ? "en" : "zh";
    // rebuild the active I18N table from the dual dict
    I18N = {};
    Object.keys(DUAL).forEach(function (k) { I18N[k] = DUAL[k][langState]; });
    applyLanguage();
    render();
    toast(tt("toast_lang"));
  }

  // ---- submit: ADR-0008 advisory floor + skip pass-through ----
  function isSkipChoice(choice) {
    // ADR-0008: i18n.py SKIP_LABELS is the single label source, injected here
    // as the full cross-locale set. Hardcoding the words would silently break
    // the Skip button in any locale added later, while transaction.py kept up.
    var c = String(choice || "").trim().toLowerCase();
    var labels = window.DPB_SKIP_LABELS || [];
    for (var i = 0; i < labels.length; i++) {
      if (c === String(labels[i]).toLowerCase()) return true;
    }
    return false;
  }
  function setHintGate(on) {
    if (!hint) return;
    hint.classList.toggle("is-on", !!on);
  }
  function submitPrimary() {
    var targetBtn = document.getElementById("dpb-btn-approve");
    if (targetBtn) form.requestSubmit(targetBtn); else form.requestSubmit();
  }
  form.addEventListener("submit", function (e) {
    syncCriteriaHidden();
    var submitter = e.submitter;
    var choice = submitter && submitter.name === "choice" ? submitter.value : "";
    if (!choice || choice === "__abort__") { clearDraft(); return; }
    if (isSkipChoice(choice)) {
      if (field) field.removeAttribute("aria-invalid");
      setHintGate(false);
      clearDraft();
      return;
    }
    if (isSubstantive()) {
      if (field) field.removeAttribute("aria-invalid");
      setHintGate(false);
      // Anchor comments are folded into the feedback block by the Python
      // adapter (_format_feedback) at collect time (ADR-0013).
      clearDraft();
      return;
    }
    e.preventDefault();
    if (field) {
      field.setAttribute("aria-invalid", "true");
      field.classList.remove("is-shaking");
      void field.offsetWidth;
      field.classList.add("is-shaking");
      setTimeout(function () { field.focus(); }, 0);
    }
    setHintGate(true);
    announce(tt("gate_hint"));
    setDrawer(true, true);
  });
  if (statusApprove) statusApprove.addEventListener("click", function () {
    if (isSubstantive()) submitPrimary();
    else {
      setDrawer(true, true);
      if (field) {
        field.setAttribute("aria-invalid", "true");
        field.classList.remove("is-shaking");
        void field.offsetWidth;
        field.classList.add("is-shaking");
        setTimeout(function () { field.focus(); }, 0);
      }
      setHintGate(true);
      announce(tt("gate_hint"));
    }
  });
  var draftBtn = document.getElementById("dpb-draft");
  if (draftBtn) draftBtn.addEventListener("click", function () {
    saveDraft();
    setDrawer(false);
  });

  // ---- keyboard map (v9) ----
  function isTextEditingTarget(el) {
    if (!el) return false;
    return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
  }
  document.addEventListener("keydown", function (e) {
    var activeEl = document.activeElement;
    // Ctrl/Cmd+Enter is the global approve channel - it must fire even while
    // a textarea/input has focus (v9 keymap).
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      submitPrimary();
      return;
    }
    if (isTextEditingTarget(activeEl)) {
      if (e.key === "Enter" && !e.shiftKey && activeEl === commentInput) {
        e.preventDefault();
        submitComment();
      }
      return;
    }
    if (e.code === "Space" && !isSpaceDown) {
      e.preventDefault();
      isSpaceDown = true;
      if (!isPanning) canvas.style.cursor = "grab";
      return;
    }
    var k = e.key.toLowerCase();
    if (e.key === "?" || (e.shiftKey && e.key === "/")) {
      e.preventDefault(); toggleModal(true); return;
    }
    if (e.key === "Escape") {
      if (modal && !modal.hidden) { e.preventDefault(); toggleModal(false); return; }
      if (abortPopoverOpen()) { e.preventDefault(); hideAbortPopover(true); if (abortBtn) abortBtn.focus(); return; }
      if (tool === "draw" || tool === "box" || tool === "ruler" || tool === "hand") { setTool("select"); return; }
      // v9: Esc is the skip channel when no overlay/tool is active
      var skipBtn = document.getElementById("dpb-btn-skip");
      if (skipBtn) form.requestSubmit(skipBtn);
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault(); submitPrimary(); return;
    }
    if ((e.ctrlKey || e.metaKey) && k === "z") {
      if (isTextEditingTarget(activeEl)) return;
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
      return;
    }
    if (e.shiftKey && (e.key === "Delete" || e.key === "Backspace")) {
      e.preventDefault();
      if (abortPopoverOpen()) hideAbortPopover();
      else showAbortPopover();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === "l") { e.preventDefault(); toggleLanguage(); return; }
    if (k === "h") { e.preventDefault(); setTool(tool === "hand" ? "select" : "hand"); return; }
    if (k === "j") { e.preventDefault(); roam(1); return; }
    if (k === "k") { e.preventDefault(); roam(-1); return; }
    if (k === "v") { e.preventDefault(); setMode("preview"); setTool("select", true); return; }
    if (k === "d") { e.preventDefault(); setTool(tool === "draw" ? "select" : "draw"); return; }
    if (k === "b") { e.preventDefault(); setTool(tool === "box" ? "select" : "box"); return; }
    if (k === "r") { e.preventDefault(); setTool(tool === "ruler" ? "select" : "ruler"); return; }
    if (k === "p") { e.preventDefault(); setTool("select"); setMode("annotate"); return; }
    if (e.key === "=" || e.key === "+") { e.preventDefault(); handleZoom(0.1); return; }
    if (e.key === "-" || e.key === "_") { e.preventDefault(); handleZoom(-0.1); return; }
    if (e.key === "0") { e.preventDefault(); fitCanvas(); return; }
    if (e.key === "[" || e.key === "]") {
      e.preventDefault();
      setDrawer(inspector.classList.contains("dpb-collapsed"));
      return;
    }
  });
  document.addEventListener("keyup", function (e) {
    if (e.code === "Space") {
      isSpaceDown = false;
      if (!isPanning) canvas.style.cursor = tool === "hand" ? "grab" : ((tool === "draw" || tool === "box" || tool === "ruler") ? "crosshair" : "default");
    }
  });

  // ---- onboarding (first-use, versioned and best-effort persisted) ----
  var ONBOARDING_KEY = "dpb.onboarding.v1";
  var onboardingModal = document.getElementById("dpb-onboarding-modal");
  var onboardingClose = document.getElementById("dpb-onboarding-close");
  var onboardingDismiss = document.getElementById("dpb-onboarding-dismiss");
  function onboardingWasSeen() {
    try { return localStorage.getItem(ONBOARDING_KEY) === "1"; }
    catch (e) { return false; }
  }
  function rememberOnboarding() {
    try { localStorage.setItem(ONBOARDING_KEY, "1"); }
    catch (e) { /* private mode/quota: onboarding remains best-effort */ }
  }
  function toggleOnboarding(show) {
    if (!onboardingModal) return;
    onboardingModal.hidden = !show;
    onboardingModal.setAttribute("aria-hidden", show ? "false" : "true");
    if (!show) rememberOnboarding();
    if (show && onboardingClose) setTimeout(function () { onboardingClose.focus(); }, 0);
  }
  if (onboardingClose) onboardingClose.addEventListener("click", function () { toggleOnboarding(false); });
  if (onboardingDismiss) onboardingDismiss.addEventListener("click", function () { toggleOnboarding(false); });
  if (onboardingModal) onboardingModal.addEventListener("click", function (e) {
    if (e.target === onboardingModal) toggleOnboarding(false);
  });

  // ---- init ----
  setViewport("desktop", true);
  setMode("annotate", true);
  setTool("select", true);
  syncCriteriaHidden();
  loadDraft();
  render(false);
  setReadiness();
  fitCanvas();
  syncPinToFrame();
  syncDrawToFrame();
  syncRulerToFrame();
  syncAnchorsToFrame();
  if (!onboardingWasSeen()) setTimeout(function () { toggleOnboarding(true); }, 0);
