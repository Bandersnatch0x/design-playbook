/* Direct preview edits are drafts until the bridge acknowledges a mutation. */
(function () {
  "use strict";
  function boot() {
    if (!window.React || !window.ReactDOM) throw Error("Preview editor runtime missing");
    var React = window.React, h = React.createElement;
    var mount = document.getElementById("dpb-react-editor-root");
    var frame = document.querySelector("iframe.dpb-proto-frame");
    var root = document.getElementById("dpb-root");
    if (!mount) return;
    if (!frame) {
      document.getElementById("dpb-prototype-loading").hidden = true;
      document.getElementById("dpb-artboard-inner").setAttribute("aria-busy", "false");
      return;
    }
    // The only CSS-property -> computed snapshot key mapping in the inspector.
    var FIELDS = [
      ["color", "color"], ["background-color", "backgroundColor"],
      ["font-family", "fontFamily"], ["font-size", "fontSize"],
      ["font-weight", "fontWeight"], ["line-height", "lineHeight"],
      ["letter-spacing", "letterSpacing"], ["display", "display"],
      ["position", "position"], ["flex-direction", "flexDirection"],
      ["justify-content", "justifyContent"], ["align-items", "alignItems"],
      ["gap", "gap"], ["width", "width"], ["height", "height"],
      ["margin", "margin"], ["padding", "padding"],
      ["margin-top", "marginTop"], ["margin-right", "marginRight"],
      ["margin-bottom", "marginBottom"], ["margin-left", "marginLeft"],
      ["padding-top", "paddingTop"], ["padding-right", "paddingRight"],
      ["padding-bottom", "paddingBottom"], ["padding-left", "paddingLeft"],
      ["border-radius", "borderRadius"], ["border-width", "borderWidth"],
      ["border-color", "borderColor"], ["transform", "transform"]
    ];
    var LAYOUT = ["margin", "padding", "width", "height", "gap", "display", "position",
      "flex", "flex-direction", "align-items", "justify-content", "grid-template-columns",
      "margin-top", "margin-right", "margin-bottom", "margin-left",
      "padding-top", "padding-right", "padding-bottom", "padding-left",
      "transform", "left", "top", "right", "bottom"];
    function post(message) {
      frame.contentWindow.postMessage({ dpbVisualEdit: message }, "*");
    }
    function bridgeLabels() {
      var labels = {}, lang = root.lang.indexOf("zh") === 0 ? "zh" : "en";
      Object.keys(window.DPB_I18N_DUAL).forEach(function (key) {
        if (key.indexOf("visual_") === 0) labels[key] = window.DPB_I18N_DUAL[key][lang];
      });
      return labels;
    }
    function syncDraft(values, property, value) {
      var next = Object.assign({}, values, { [property]: value });
      var match = /^(padding|margin)(?:-(top|right|bottom|left))?$/.exec(property);
      if (!match) return next;
      var group = match[1], sides = ["top", "right", "bottom", "left"];
      var style = document.createElement("div").style;
      if (!match[2]) {
        style.setProperty(group, value);
        if (value && !style.getPropertyValue(group)) return next;
        sides.forEach(function (side) { next[group + "-" + side] = style.getPropertyValue(group + "-" + side); });
      } else {
        sides.forEach(function (side) { style.setProperty(group + "-" + side, next[group + "-" + side] || "0px"); });
        next[group] = style.getPropertyValue(group);
      }
      return next;
    }
    // The edit ledger lives in control.edits.js, which the shell ships in its
    // own block ahead of this bundle. A missing module means a wrong script
    // order, so reading it here fails loudly instead of half-working.
    var ledger = window.DPBEdit.ledger;
    // Whether the round still holds unpublished visual work. Pure over a state
    // snapshot so the rule executes in node without a browser; the component
    // assembles the snapshot from its refs. It deliberately does NOT consult a
    // stale flag: a disconnect sets stale whenever work is pending, so treating
    // stale as "nothing pending" made the drain decision blind to an unpublished
    // draft and let the round submit without it. Only an absent selection makes
    // drafts irrelevant.
    function dpbPendingVisualEdits(state) {
      if (!state.selected) return false;
      if (!state.published) return true;
      if (state.request) return true;
      if (state.unacked && Object.keys(state.unacked).length > 0) return true;
      if (Object.keys(state.draftTimers).length > 0) return true;
      return Object.keys(state.drafts).some(function (p) {
        return state.drafts[p] !== undefined && state.dispatched[p] !== state.drafts[p];
      });
    }

    function Editor() {
      var [selected, setSelected] = React.useState(null);
      var [entries, setEntries] = React.useState([]);
      var [future, setFuture] = React.useState([]);
      var [drafts, setDrafts] = React.useState({});
      var [invalid, setInvalid] = React.useState({});
      // The request lifecycle lives in control.edits.js as one store per Editor
      // instance: the request id counter, the request in flight, the requests no
      // receipt has answered, what was dispatched, what was accepted, the accepted
      // sequence per target, the values an interrupted request took with it, and
      // the 1500 ms deadline. It is a ref, not a render-body call: a store built
      // per render would drop the request in flight, the accepted values and the
      // deadline on every keystroke, and the bridge effects below capture the
      // first-render store, so a second store means two disagreeing lifecycles.
      // The status the five scalars render is the store's, so they seed from it.
      // `deps` is what the store must not reach for itself: the transport, the
      // timer, the two DOM-bound normalizers, the publish flag, and `emit` - how a
      // deadline nobody called still reaches React. It is also what makes the
      // lifecycle executable in node.
      var isPublishedRef = React.useRef(true);
      var protocolRef = React.useRef(null);
      if (!protocolRef.current) {
        protocolRef.current = window.DPBEdit.protocol.create({
          send: post,
          setTimer: function (fn, ms) { return setTimeout(fn, ms); },
          clearTimer: function (handle) { clearTimeout(handle); },
          syncDraft: syncDraft,
          canonicalValue: canonicalValue,
          unpublish: function () { isPublishedRef.current = false; },
          emit: function (outcome) { applyOutcome(outcome); },
        });
      }
      var protocol = protocolRef.current;
      var status = protocol.status();
      var [ready, setReady] = React.useState(status.ready);
      var [connecting, setConnecting] = React.useState(status.connecting);
      var [stale, setStale] = React.useState(status.stale);
      React.useEffect(function () {
        var loading = document.getElementById("dpb-prototype-loading");
        if (loading) loading.hidden = !connecting;
        document.getElementById("dpb-artboard-inner").setAttribute("aria-busy", String(connecting));
      }, [connecting]);
      var [diagnostic, setDiagnostic] = React.useState(status.diagnostic);
      var [busy, setBusy] = React.useState(status.busy);
      var [webmcp, setWebmcp] = React.useState(false);
      var [locale, setLocale] = React.useState(root.lang);
      var current = React.useRef({}), draftTimers = React.useRef({});
      var entriesRef = React.useRef(entries);
      entriesRef.current = entries;
      var futureRef = React.useRef(future);
      futureRef.current = future;
      var isDrainingRef = React.useRef(false);
      // The drain timeout outlives the effect that created it, so it needs its
      // own ref: the unmount cleanup must clear it, or an unmount mid-drain
      // leaves a 2s timer that later touches unmounted state.
      var drainTimerRef = React.useRef(null);
      var [collapsed, setCollapsed] = React.useState({ layout: true, spacing: true, border: true });
      var [compact, setCompact] = React.useState(window.innerWidth <= 480);
      // Review readiness is owned by control.review.js, which publishes it. The
      // panel renders a local submit button and mirrors that state instead of
      // re-deriving the floor; the seed covers a publish that landed early.
      var [reviewGate, setReviewGate] = React.useState(false);
      React.useEffect(function () {
        function onGate(event) {
          var detail = (event && event.detail) || {};
          setReviewGate(!!detail.ready);
        }
        document.addEventListener("dpbReviewReady", onGate);
        var btn = document.getElementById("dpb-btn-approve");
        setReviewGate(!!(btn && btn.classList.contains("dpb-approve-ready")));
        return function () { document.removeEventListener("dpbReviewReady", onGate); };
      }, []);
      React.useEffect(function () {
        function resize() { setCompact(window.innerWidth <= 480); }
        window.addEventListener("resize", resize);
        return function () { window.removeEventListener("resize", resize); };
      }, []);
      function toggleSection(sec) {
        setCollapsed(function (prev) {
          return Object.assign({}, prev, { [sec]: !prev[sec] });
        });
      }
      var binding = window.DPB_VISUAL_BINDING || { sourceHash: "", routeUrl: "" };
      current.current = { selected: selected, entries: entries,
        future: future, ready: ready, stale: stale, drafts: drafts };
      // The flat view of the ledger: the edits this round has not published
      // away. Its length is the pending count, not entries.length - one resize
      // receipt is one entry carrying two edits. Derived in the render body so
      // the effects below keep the source state in their dependency arrays.
      var flat = ledger.flatten(entries);
      function t(key) {
        var table = window.DPB_I18N_DUAL;
        var isZh = (locale || "en").indexOf("zh") === 0;
        if (table && table[key]) return table[key][isZh ? "zh" : "en"] || key;
        return key;
      }
      function snapshot(selection) {
        var values = {};
        FIELDS.forEach(function (field) { values[field[0]] = selection.style[field[1]] || ""; });
        return values;
      }
      // Canonical CSS form of a value the parent asked for, computed on a
      // detached declaration: the recorded edit never depends on what the
      // prototype reports back for our own request.
      function canonicalValue(property, value) {
        var probe = document.createElement("div").style;
        probe.setProperty(property, String(value == null ? "" : value));
        return probe.getPropertyValue(property);
      }
      // The one place a protocol outcome becomes React state. A transition that
      // moved nothing hands back no status and no drafts transform, so the
      // setters stay shut: the panel never re-renders for an event that changed
      // no part of the round.
      function applyOutcome(outcome) {
        if (!outcome) return;
        if (outcome.status) {
          setReady(outcome.status.ready);
          setConnecting(outcome.status.connecting);
          setStale(outcome.status.stale);
          setBusy(outcome.status.busy);
          setDiagnostic(outcome.status.diagnostic);
        }
        if (outcome.drafts) setDrafts(outcome.drafts);
      }
      function disconnected() {
        // A round that already holds ledger work goes stale; one that does not
        // keeps whatever staleness it had, exactly as the separate setter did.
        var fields = { ready: false, connecting: false };
        if (current.current.entries.length) fields.stale = true;
        applyOutcome({ status: protocol.patch(fields) });
        // Retain unresolved drafts across disconnect (§3.3)
        Object.values(draftTimers.current).forEach(clearTimeout);
        draftTimers.current = {};
        var interrupted = protocol.interrupt();
        if (interrupted.length) {
          var selection = current.current.selected;
          setDrafts(function (values) {
            var next = Object.assign({}, values);
            interrupted.forEach(function (operation) {
              if (!operation.entry && selection && operation.locator === selection.selector &&
                  values[operation.property] === operation.draft) {
                next = syncDraft(next, operation.property, operation.value);
              }
            });
            return next;
          });
        }
        applyOutcome({ status: protocol.fail("visual_disconnected") });
      }
      function applyStyle(property, value, action, entry, origin) {
        var state = current.current;
        // Only the reads that need the DOM or React state happen here; the
        // dispatch - id, unacked record, deadline, wire, busy - is the store's,
        // and it answers the same `{accepted, error}` promise the inspector, the
        // replay paths and the tool have always awaited.
        var inlineStyle = document.createElement("div").style;
        inlineStyle.cssText = (state.selected && state.selected.inlineStyle) || "";
        return protocol.begin({ property: property, value: value, action: action,
          origin: origin, entry: entry || null,
          // No selection means no target, whatever a replay entry carries: the
          // store refuses an empty locator as the unavailable round it is.
          locator: state.selected ? (entry ? entry[0].locator : state.selected.selector) : null,
          oldValue: inlineStyle.getPropertyValue(property),
          draft: state.drafts[property],
          viewport: entry ? entry[0].viewport : window.DPB_ACTIVE_VIEWPORT || "any" });
      }
      function commit(property, value, selector) {
        clearTimeout(draftTimers.current[property]);
        delete draftTimers.current[property];
        var state = current.current;
        if (!state.selected || state.selected.selector !== selector) return;
        // Serialize requests, not typing. A newer keystroke replaces this timer.
        if (protocol.hasRequest()) {
          draftTimers.current[property] = setTimeout(function () { commit(property, value, selector); }, 200);
          return;
        }
        // A value the engine would drop is flagged here and never dispatched.
        var unsupported = value !== "" && window.CSS && CSS.supports && !CSS.supports(property, String(value));
        setInvalid(function (old) {
          if (!!old[property] === !!unsupported) return old;
          var next = Object.assign({}, old);
          if (unsupported) next[property] = true; else delete next[property];
          return next;
        });
        applyOutcome({ status: protocol.patch({ diagnostic: unsupported ? "visual_invalid_value" :
          protocol.status().diagnostic === "visual_invalid_value" ? "" : protocol.status().diagnostic }) });
        if (unsupported) return;
        if (value === protocol.acceptedValue(property)) return;
        protocol.markDispatched(property, value);
        applyStyle(property, value);
      }
      React.useEffect(function () {
        mount.querySelectorAll("[data-property]").forEach(function (field) {
          var control = field.querySelector("input, select");
          if (!control) return;
          if (invalid[field.getAttribute("data-property")]) control.setAttribute("aria-invalid", "true");
          else control.removeAttribute("aria-invalid");
        });
      }, [invalid, drafts]);
      React.useEffect(function () {
        var observer = new MutationObserver(function () { setLocale(root.lang); });
        observer.observe(root, { attributes: true, attributeFilter: ["lang"] });
        return function () { observer.disconnect(); };
      }, []);
      React.useEffect(function () {
        function onHistoryKey(event) {
          if (event.key === "Escape") post({ type: "close-color-picker" });
          var tgt = event.target;
          if (tgt && tgt.closest && tgt.closest("input, textarea, select, [contenteditable]")) {
            if (!tgt.closest(".dpb-react-field")) return;
          }
          if (!(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing ||
              event.defaultPrevented || mount.offsetParent === null || !event.target.closest ||
              !event.target.closest("#dpb-react-editor-root, #dpb-canvas, #dpb-artboard-wrap, #dpb-visual-view")) return;
          var key = event.key.toLowerCase();
          if (key !== "z" && key !== "y") return;
          var state = current.current;
          if (!state.ready || state.stale || !state.selected || protocol.hasRequest()) return;
          event.preventDefault();
          replay(key === "y" || event.shiftKey ? "redo" : "undo");
        }
        function dismissColor() { post({ type: "close-color-picker" }); }
        window.addEventListener("keydown", onHistoryKey);
        window.addEventListener("pointerdown", dismissColor);
        return function () {
          window.removeEventListener("keydown", onHistoryKey);
          window.removeEventListener("pointerdown", dismissColor);
        };
      }, []);
      React.useEffect(function () {
        post({ type: "localize", labels: bridgeLabels() });
      }, [locale]);
      React.useEffect(function () {
        var nonce = 0, lastAck = 0, started = Date.now(), unanswered = 0;
        function ping() {
          // Count pings the bridge left unanswered instead of comparing wall
          // clock. A background tab throttles this timer, so a single late tick
          // made `Date.now() - lastAck > 2500` read a healthy bridge as dead; it
          // then set the round permanently stale with no reset path. Three
          // unanswered pings is a real disconnect even if one round trip is slow.
          if (lastAck) {
            if (unanswered >= 2) disconnected();
            unanswered += 1;
          }
          if (!lastAck && Date.now() - started > 2500) {
            applyOutcome({ status: protocol.patch({ connecting: false }) });
          }
          post({ type: "ping", nonce: ++nonce, compact: window.innerWidth <= 480, labels: bridgeLabels() });
        }
        function load() {
          lastAck = 0; unanswered = 0; started = Date.now();
          disconnected();
          applyOutcome({ status: protocol.patch({ connecting: true }) });
          ping();
        }
        function onMessage(event) {
          if (event.source !== frame.contentWindow) return;
          var data = event.data || {};
          if (data.dpbVisualEditReady) {
            var response = data.dpbVisualEditReady;
            if (response.nonce !== nonce) return;
            if (response.routeUrl !== (binding.routeUrl || "about:srcdoc")) {
              applyOutcome({ status: protocol.patch({ stale: true, ready: false }) });
              applyOutcome({ status: protocol.fail("visual_stale") });
              return;
            }
            lastAck = Date.now(); unanswered = 0;
            applyOutcome({ status: protocol.patch({ ready: true, connecting: false }) });
            if (!protocol.status().stale && protocol.status().diagnostic === "visual_disconnected") {
              applyOutcome({ status: protocol.patch({ diagnostic: "" }) });
            }
          }
          if (data.dpbVisualEditSelection && lastAck) {
            var selection = data.dpbVisualEditSelection;
            if (selection.requestId) {
              // A mutation snapshot is not a new user selection or draft.
              if (current.current.selected && selection.selector === current.current.selected.selector &&
                  (selection.requestId === protocol.requestId() ||
                    String(selection.requestId).indexOf("gesture-") === 0)) setSelected(selection);
            } else {
              Object.values(draftTimers.current).forEach(clearTimeout);
              setSelected(selection);
              setDrafts(protocol.acceptSelection(snapshot(selection)));
            }
          }
          var rejected = data.dpbVisualEditRejected;
          if (rejected) {
            // The refusal belongs to the store: it is terminal for that request id
            // (the bridge will never confirm it, so a retained entry made every
            // later drain answer unresolved_edits and left only Abort usable), it
            // marks a missing target stale, and it rolls the draft back to what the
            // bridge accepted. `consumed` is the old `return`: the id was this
            // round's request, so no receipt can follow it.
            var refusal = protocol.reduce({ type: "rejected",
              requestId: rejected.requestId, code: rejected.code });
            applyOutcome(refusal);
            if (refusal.consumed) return;
          }
          var change = data.dpbVisualEditChange;
          if (!change) return;
          // The receipt belongs to the store: which request it answers, whether
          // that request still stands, its provenance, the values an interrupt took
          // with it, the accepted sequence per target and the drafts that may stand.
          // A null outcome is its guard ladder - a round that is not ready or has
          // gone stale, an id this store never dispatched and that is not a gesture,
          // or a replay whose receipt has already been spent.
          var receipt = protocol.reduce({ type: "change", requestId: change.requestId,
            selector: change.selector, changes: change.changes,
            selected: (current.current.selected || {}).selector });
          if (!receipt) return;
          var operation = receipt.operation;
          var changes = receipt.changes;
          var source = receipt.source;
          var opSeq = receipt.opSeq;
          applyOutcome(receipt);
          var edits = changes.filter(function (c) { return c.oldValue !== c.newValue; }).map(function (c) {
            return { kind: LAYOUT.indexOf(c.property) >= 0 ? "layout" : "style",
              viewport: operation ? operation.viewport : (window.DPB_ACTIVE_VIEWPORT || "any"),
              locator: change.selector, property: c.property, oldValue: c.oldValue, newValue: c.newValue,
              source: source,
              _seq: opSeq,
              _t: Date.now(),
              _entryId: opSeq };
          });
          if (edits.length) edits._entryId = opSeq;
          if (operation && operation.action === "undo") {
            var undoLists = ledger.undoEntry({ entries: entriesRef.current,
              future: futureRef.current }, operation.entry);
            if (undoLists) {
              entriesRef.current = undoLists.entries;
              setEntries(undoLists.entries);
              futureRef.current = undoLists.future;
              setFuture(undoLists.future);
              publishBatch(ledger.flatten(undoLists.entries), current.current.stale);
            }
          } else if (operation && operation.action === "redo") {
            var redoLists = ledger.redoEntry({ entries: entriesRef.current,
              future: futureRef.current }, operation.entry);
            if (redoLists) {
              futureRef.current = redoLists.future;
              setFuture(redoLists.future);
              entriesRef.current = redoLists.entries;
              setEntries(redoLists.entries);
              publishBatch(ledger.flatten(redoLists.entries), current.current.stale);
            }
          } else if (edits.length === 1 && (function () {
            var list = entriesRef.current || [], last = list[list.length - 1];
            return !!(last && last.length === 1 && !(futureRef.current || []).length && ledger.mergeEdit(last[0], edits[0], edits[0]._t, ledger.MERGE_WINDOW_MS));
          })()) {
            // The coalesce mutates the edit object the last entry already holds,
            // so the merged value reaches the batch through the projection. The
            // shallow copy only hands React a new list to render; keep it.
            var merged = (entriesRef.current || []).slice();
            entriesRef.current = merged;
            setEntries(merged);
            publishBatch(ledger.flatten(merged), current.current.stale);
          } else if (edits.length) {
            var appended = ledger.appendEdits({ entries: entriesRef.current,
              future: futureRef.current }, edits, opSeq);
            entriesRef.current = appended.entries;
            setEntries(appended.entries);
            // null means the redo stack still stands: a receipt that is older
            // than something already in it must not throw that stack away.
            if (appended.future !== null) {
              futureRef.current = appended.future;
              setFuture(appended.future);
            }
            publishBatch(ledger.flatten(entriesRef.current), current.current.stale);
          }
          // The accepted values and the drafts the receipt may stand for are the
          // store's, and `applyOutcome` above already handed the drafts transform
          // to React. Only the promise is settled here, after the ledger has been
          // told, because the drain barrier reads the batch the receipt produced.
          protocol.acknowledge(operation, edits.length > 0);
        }
        window.addEventListener("message", onMessage);
        frame.addEventListener("load", load);
        ping();
        var timer = setInterval(ping, 1000);
        return function () {
          clearInterval(timer);
          window.removeEventListener("message", onMessage);
          frame.removeEventListener("load", load);
          Object.values(draftTimers.current).forEach(clearTimeout);
          protocol.dispose();
          if (drainTimerRef.current) clearTimeout(drainTimerRef.current);
        };
      }, []);
      function publishBatch(editsList, isStale) {
        var list = editsList !== undefined ? editsList : ledger.flatten(entriesRef.current);
        var sorted = (list || []).slice().sort(ledger.bySeq);
        var cleanEdits = sorted.map(function (e) {
          return { kind: e.kind, viewport: e.viewport, locator: e.locator,
            property: e.property, oldValue: e.oldValue, newValue: e.newValue,
            source: e.source };
        });
        var batch = { schemaVersion: 1, status: isStale ? "stale" : "pending",
          sourceHash: binding.sourceHash, routeUrl: binding.routeUrl, edits: cleanEdits };
        window.DPB_VISUAL_EDIT_BATCH = batch;
        var hidden = document.getElementById("dpb-visual-edits-json");
        if (hidden) hidden.value = JSON.stringify(batch);
        var countEl = document.getElementById("dpb-visual-count");
        if (countEl) countEl.textContent = String(cleanEdits.length);
        var tabEl = document.getElementById("dpb-tab-visual");
        if (tabEl) tabEl.classList.toggle("is-pending", cleanEdits.length > 0);
        isPublishedRef.current = true;
        // The rail owns readiness; tell it the published batch changed so it can
        // re-evaluate the floor mirror (an effective edit alone can now satisfy it).
        document.dispatchEvent(new CustomEvent("dpbVisualEditsChanged"));
        return batch;
      }
      React.useEffect(function () {
        publishBatch(flat, stale);
        var tabEl = document.getElementById("dpb-tab-visual");
        if (tabEl) tabEl.classList.toggle("is-pending", flat.length > 0);
        var countEl = document.getElementById("dpb-visual-count");
        if (countEl) countEl.textContent = String(flat.length);
      }, [entries, stale]);
      React.useEffect(function () {
        // The rail's mirror also depends on work that is in flight (an edit whose
        // acknowledgement has not arrived) and on unsent keystrokes, which do not
        // change the published batch. Tell it whenever those move, so the first
        // edit is submittable immediately instead of only after its receipt.
        document.dispatchEvent(new CustomEvent("dpbVisualEditsChanged"));
      }, [busy, entries, drafts]);
      React.useEffect(function () {
        var modelContext = navigator.modelContext;
        if (!modelContext || typeof modelContext.registerTool !== "function") modelContext = document.modelContext;
        if (!modelContext || typeof modelContext.registerTool !== "function") return;
        var tools = [
          { name: "preview_get_selection", description: "Read selected Preview element and computed style",
            inputSchema: { type: "object", properties: {} },
            execute: function () { return current.current.selected || { selected: false }; } },
          { name: "preview_set_style", description: "Request one preview-only CSS edit",
            inputSchema: { type: "object", properties: { property: { type: "string", pattern: "^[A-Za-z-]{1,64}$" }, value: { type: "string" } }, required: ["property", "value"] },
            execute: function (input) { return applyStyle(String(input.property || ""), String(input.value || ""), "edit", null, "agent"); } },
          { name: "preview_get_pending_edits", description: "Read pending Preview edits awaiting coding-agent review",
            inputSchema: { type: "object", properties: {} },
            execute: function () { return window.DPB_VISUAL_EDIT_BATCH; } }
        ];
        var registered = [];
        try {
          tools.forEach(function (tool) {
            tool.annotations = { readOnlyHint: tool.name !== "preview_set_style", consequentialHint: false };
            modelContext.registerTool(tool); registered.push(tool.name);
          });
          setWebmcp(true);
        } catch (error) {
          applyOutcome({ status: protocol.patch({ diagnostic: "visual_tools_unavailable" }) });
        }
        return function () {
          if (typeof modelContext.unregisterTool === "function") registered.forEach(function (name) { modelContext.unregisterTool(name); });
        };
      }, []);
      function drain(timeoutMs) {
        var state = current.current;
        if (!state.ready || state.stale || !state.selected) {
          if (hasPendingVisualEdits()) {
            return Promise.resolve({ ok: false, error: "visual_unavailable" });
          }
          publishBatch(ledger.flatten(entriesRef.current), state.stale);
          return Promise.resolve({ ok: true, batch: window.DPB_VISUAL_EDIT_BATCH });
        }
        isDrainingRef.current = true;
        applyOutcome({ status: protocol.patch({ busy: true }) });

        Object.keys(draftTimers.current).forEach(function (prop) {
          clearTimeout(draftTimers.current[prop]);
          delete draftTimers.current[prop];
        });

        var maxWait = typeof timeoutMs === "number" ? timeoutMs : 2000;

        return new Promise(function (resolve) {
          var finished = false;
          var timer = setTimeout(function () {
            if (finished) return;
            finished = true;
            drainTimerRef.current = null;
            isDrainingRef.current = false;
            applyOutcome({ status: protocol.patch({ busy: false }) });
            resolve({ ok: false, error: "timeout" });
          }, maxWait);
          drainTimerRef.current = timer;

          function finish(ok, err) {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            drainTimerRef.current = null;
            isDrainingRef.current = false;
            applyOutcome({ status: protocol.patch({ busy: false }) });
            if (!ok) {
              resolve({ ok: false, error: err || "drain_failed" });
              return;
            }
            var batch = publishBatch(ledger.flatten(entriesRef.current), current.current.stale);
            resolve({ ok: true, batch: batch });
          }

          function step() {
            if (finished) return;
            var curReq = protocol.pendingRequest();
            if (curReq) {
              curReq.then(function (res) {
                if (finished) return;
                if (!res || !res.accepted) {
                  finish(false, (res && res.error) || "rejected");
                  return;
                }
                step();
              }).catch(function (err) {
                if (finished) return;
                finish(false, String(err));
              });
              return;
            }

            var st = current.current;
            var uncommittedProps = Object.keys(st.drafts).filter(function (p) {
              return st.drafts[p] !== undefined && protocol.dispatchedValues()[p] !== st.drafts[p];
            });

            if (uncommittedProps.length > 0) {
              var nextProp = uncommittedProps[0];
              var nextVal = st.drafts[nextProp];
              protocol.markDispatched(nextProp, nextVal);
              applyStyle(nextProp, nextVal).then(function (res) {
                if (finished) return;
                if (!res || !res.accepted) {
                  protocol.markDispatched(nextProp, null);
                  finish(false, (res && res.error) || "rejected");
                  return;
                }
                step();
              }).catch(function (err) {
                if (finished) return;
                protocol.markDispatched(nextProp, null);
                finish(false, String(err));
              });
              return;
            }

            if (protocol.hasUnacked()) {
              finish(false, "unresolved_edits");
              return;
            }

            finish(true);
          }

          step();
        });
      }

      function hasPendingVisualEdits() {
        // The pending rule is pure and executes in node; this only assembles the
        // snapshot from the component's state and the protocol store's records.
        var state = current.current;
        return dpbPendingVisualEdits({
          selected: state.selected,
          published: isPublishedRef.current,
          request: protocol.pendingRequest(),
          unacked: protocol.unackedTable(),
          draftTimers: draftTimers.current,
          drafts: state.drafts,
          dispatched: protocol.dispatchedValues(),
        });
      }
      var hasPendingRef = React.useRef(hasPendingVisualEdits);
      hasPendingRef.current = hasPendingVisualEdits;

      var drainRef = React.useRef(drain);
      drainRef.current = drain;
      React.useEffect(function () {
        window.dpbHasPendingVisualEdits = function () {
          if (hasPendingRef.current) return hasPendingRef.current();
          return false;
        };
        // Whether the editor can still flush at all. The readiness mirror must
        // not promise a submission while the bridge is offline, but the drain
        // decision must still see the unpublished work so it fails closed
        // instead of dropping it, so the two questions are answered separately.
        window.dpbVisualEditorState = function () {
          var state = current.current;
          return { ready: !!state.ready, stale: !!state.stale };
        };
        window.dpbDrainVisualEdits = function () {
          if (drainRef.current) return drainRef.current();
          return Promise.resolve({ ok: true, batch: window.DPB_VISUAL_EDIT_BATCH });
        };
        return function () {
          window.dpbHasPendingVisualEdits = null;
          window.dpbVisualEditorState = null;
          window.dpbDrainVisualEdits = null;
        };
      }, []);
      function historyLabel(verb, list) {
        var top = list && list[list.length - 1];
        return top && top[0] ? verb + " " + top[0].property : verb;
      }
      function replay(action) {
        var stack = action === "undo" ? (entriesRef.current || []) : (futureRef.current || []);
        var entry = stack[stack.length - 1];
        if (entry) applyStyle(entry[0].property, action === "undo" ? entry[0].oldValue : entry[0].newValue, action, entry);
      }
      return h("section", { className: "dpb-react-editor", "aria-label": t("visual_title") },
        h("div", { className: "dpb-react-editor-head" }, h("strong", null, t("visual_title")),
          h("span", { className: "dpb-react-badge" + (webmcp ? " is-on" : "") }, webmcp ? "WebMCP" : t("visual_bridge"))),
        h("div", { className: "dpb-react-route" }, binding.routeUrl || t("visual_artifact")),
        h("div", { className: "dpb-react-selection" }, selected ? selected.selector : t("visual_select")),
        h("div", { className: "dpb-react-actions" },
          h("button", { type: "button", disabled: !ready || stale || busy || !entries.length, "aria-label": historyLabel(t("visual_undo"), entries), onClick: function () { replay("undo"); } }, t("visual_undo")),
          h("button", { type: "button", disabled: !ready || stale || busy || !future.length, "aria-label": historyLabel(t("visual_redo"), future), onClick: function () { replay("redo"); } }, t("visual_redo")),
          h("span", { className: "dpb-react-pending-count" }, t("visual_pending").replace("{n}", flat.length))),
        h("p", { className: "dpb-react-diagnostic", role: "status", "data-stale": stale }, stale ? t("visual_stale") : connecting ? "" : diagnostic ? t(diagnostic) : ""),
        !connecting && !ready && !stale && diagnostic === "visual_disconnected" && h("button", { type: "button", className: "dpb-react-retry",
          onClick: function () { frame.dispatchEvent(new Event("load")); } }, t("visual_retry")),
        connecting && !stale && h("div", { className: "dpb-loading dpb-editor-loading", role: "status" },
          h("span", null, t("visual_loading")), h("div", { className: "dpb-skeleton", "aria-hidden": true })),
        (function () {
          var fieldDisabled = !selected || !ready || stale || isDrainingRef.current;
          function handleInput(prop, val) {
            if (isDrainingRef.current) return;
            isPublishedRef.current = false;
            setDrafts(function (old) { return syncDraft(old, prop, val); });
            clearTimeout(draftTimers.current[prop]);
            var sel = selected && selected.selector;
            draftTimers.current[prop] = setTimeout(function () { commit(prop, val, sel); }, 200);
          }
          function handleBlur(prop, val) {
            commit(prop, val, selected && selected.selector);
          }
          // Arrow keys step a number: 1, Shift 10, Alt 0.1. Each press goes
          // through the same debounce as typing, so a held key is one commit.
          function stepKey(prop, e, unit) {
            if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return false;
            var m = /^(-?(?:\d+\.?\d*|\.\d+))([a-z%]*)$/i.exec(String(e.target.value).trim());
            if (!m) return false;
            e.preventDefault();
            var step = e.altKey ? 0.1 : e.shiftKey ? 10 : 1;
            var next = Math.round((parseFloat(m[1]) + (e.key === "ArrowUp" ? step : -step)) * 10) / 10;
            handleInput(prop, String(next) + (m[2] || unit || ""));
            return true;
          }
          function handleKey(prop, val, e) {
            if (e.key === "Escape" && invalid[prop]) {
              e.stopPropagation();
              clearTimeout(draftTimers.current[prop]);
              setInvalid(function (old) { var next = Object.assign({}, old); delete next[prop]; return next; });
            // A rejected keystroke returns to what the bridge accepted, which the
            // store now holds.
            setDrafts(function (old) { return syncDraft(old, prop, protocol.acceptedValue(prop) || ""); });
              return;
            }
            if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); e.stopPropagation(); commit(prop, val, selected && selected.selector); }
          }
          // A unit belongs beside the field, not inside it. The number and its
          // unit are split for display and rejoined on commit, so a reviewer
          // never types "px" and never sees it in the box.
          var UNITS = ["px", "em", "rem", "%", "vh", "vw", "pt", "ch", "ex", "fr"];
          function splitUnit(value, fallbackUnit) {
            var raw = String(value == null ? "" : value).trim();
            var match = /^(-?(?:\d+\.?\d*|\.\d+))([a-z%]*)$/i.exec(raw);
            if (!match) return { number: raw, unit: "" };
            var typed = match[2].toLowerCase();
            // A partial unit is still being typed. Stripping "p" out of "70p"
            // moves it into the suffix, so the next keystroke appends to the
            // number again and the unit never accumulates. Show it raw until it
            // is a unit we recognise.
            if (typed && UNITS.indexOf(typed) < 0) return { number: raw, unit: "" };
            return { number: match[1], unit: match[2] || (fallbackUnit || "") };
          }
          function joinUnit(number, unit) {
            var raw = String(number == null ? "" : number).trim();
            if (!/^-?(?:\d+\.?\d*|\.\d+)[a-z%]*$/i.test(raw)) return raw;
            // Already carries a unit: keep it as typed rather than doubling it.
            return /[a-z%]/i.test(raw) ? raw : raw + (unit || "");
          }
          function renderField(prop, label, kind, opts, unit) {
            var val = drafts[prop] || "";
            if (kind === "select") {
              // An enum must not hide a value it does not list, so the element's
              // current value is injected as an option. Switching a field to a
              // dropdown must never silently rewrite the selection.
              var options = (opts || []).map(function (opt) {
                return typeof opt === "string"
                  ? { value: opt, label: opt || "–" }
                  : { value: opt.value, label: opt.label };
              });
              if (val && !options.some(function (opt) { return opt.value === val; })) {
                options = [{ value: val, label: val }].concat(options);
              }
              return h("label", { className: "dpb-react-field dpb-react-dropdown", key: prop, "data-property": prop },
                h("span", null, label),
                h("select", {
                  value: val, disabled: fieldDisabled,
                  onChange: function (e) {
                    var v = e.target.value;
                    handleInput(prop, v);
                    commit(prop, v, selected && selected.selector);
                  }
                }, options.map(function (opt) {
                  return h("option", { key: opt.value, value: opt.value }, opt.label);
                }))
              );
            }
            if (kind === "unit") {
              var parts = splitUnit(val, unit);
              return h("label", { className: "dpb-react-field dpb-react-unit", key: prop, "data-property": prop },
                h("span", null, label),
                h("div", { className: "dpb-unit-input-wrap" },
                  h("input", {
                    value: parts.number, placeholder: "0", disabled: fieldDisabled,
                    // Keystrokes stay raw so the debounce never commits a
                    // half-typed number. A bare 7 would otherwise apply as 7px
                    // and collapse the element mid-typing. The unit is appended
                    // at an explicit commit, Enter or blur.
                    onChange: function (e) { handleInput(prop, e.target.value); },
                    onBlur: function (e) { handleBlur(prop, joinUnit(e.target.value, parts.unit)); },
                    onKeyDown: function (e) { if (!stepKey(prop, e, parts.unit)) handleKey(prop, joinUnit(e.target.value, parts.unit), e); }
                  }),
                  parts.unit ? h("span", { className: "dpb-unit-suffix" }, parts.unit) : null
                )
              );
            }
            if (kind === "color") {
              return h("label", { className: "dpb-react-field dpb-react-color-row", key: prop, "data-property": prop },
                h("span", null, label),
                h("div", { className: "dpb-color-input-wrap" },
                  h("button", { type: "button", className: "dpb-color-swatch-preview", style: { backgroundColor: val || "transparent" },
                    "aria-label": t("visual_color_picker").replace("{label}", label), disabled: fieldDisabled,
                    onClick: function (e) { e.preventDefault(); post({ type: "open-color-picker", selector: selected.selector, property: prop }); } }),
                  h("input", {
                    value: val, disabled: fieldDisabled,
                    onChange: function (e) { handleInput(prop, e.target.value); },
                    onBlur: function (e) { handleBlur(prop, e.target.value); },
                    onKeyDown: function (e) { handleKey(prop, e.target.value, e); }
                  })
                )
              );
            }
            return h("label", { className: "dpb-react-field", key: prop, "data-property": prop },
              h("span", null, label),
              h("input", {
                value: val, disabled: fieldDisabled,
                onChange: function (e) { handleInput(prop, e.target.value); },
                onBlur: function (e) { handleBlur(prop, e.target.value); },
                onKeyDown: function (e) { handleKey(prop, e.target.value, e); }
              })
            );
          }
          function renderPair(c1, c2, key) {
            return h("div", { className: "dpb-react-pair", key: key || Math.random() }, c1, c2);
          }
          function renderQuad(prop, label) {
            var sides = [["T", prop + "-top"], ["R", prop + "-right"], ["B", prop + "-bottom"], ["L", prop + "-left"]];
            return h("div", { className: "dpb-react-quad-row", key: prop, "data-quad": prop },
              h("label", { className: "dpb-react-field", "data-property": prop },
                h("span", null, label),
                h("input", {
                  value: drafts[prop] || "", disabled: fieldDisabled,
                  placeholder: "0px",
                  onChange: function (e) { handleInput(prop, e.target.value); },
                  onBlur: function (e) { handleBlur(prop, e.target.value); },
                  onKeyDown: function (e) { if (!stepKey(prop, e, "px")) handleKey(prop, e.target.value, e); }
                })
              ),
              h("div", { className: "dpb-quad-grid" }, sides.map(function (side) {
                var axis = side[0], sProp = side[1];
                return h("div", { className: "dpb-quad-cell", key: axis, "data-axis": axis, "data-property": sProp },
                  h("em", { className: "dpb-quad-label" }, axis),
                  h("input", {
                    value: drafts[sProp] || "", disabled: fieldDisabled,
                    "aria-label": t("visual_" + sProp.replace(/-([a-z])/g, function (_, c) { return c.toUpperCase(); })),
                    placeholder: "0",
                    onChange: function (e) { handleInput(sProp, e.target.value); },
                    onBlur: function (e) { handleBlur(sProp, e.target.value); },
                    onKeyDown: function (e) { if (!stepKey(sProp, e, "px")) handleKey(sProp, e.target.value, e); }
                  })
                );
              }))
            );
          }
          function renderSection(secId, title, children) {
            var isClosed = !!collapsed[secId];
            var sectionProperties = { colors: /^(color|background-color)$/, typography: /^(font-|line-height|letter-spacing)/,
              layout: /^(display|position|flex|justify|align|gap|width|height|transform)/,
              spacing: /^(padding|margin)/, border: /^border-/ };
            var modified = flat.some(function (edit) {
              return selected && edit.locator === selected.selector && sectionProperties[secId].test(edit.property);
            });
            return h("section", { className: "dpb-inspector-section" + (isClosed ? " is-collapsed" : " is-open"), key: secId, "data-section": secId },
              h("button", {
                type: "button", className: "dpb-section-header", "aria-expanded": !isClosed,
                onClick: function () { toggleSection(secId); }
              }, h("strong", null, title), isClosed && modified && h("span", {
                className: "dpb-section-modified", "aria-label": t("visual_modified") }, "•"),
                h("span", { className: "dpb-section-chevron" }, isClosed ? "▸" : "▾")),
              !isClosed && h("div", { className: "dpb-section-body" }, children)
            );
          }

          // Generic families only: they resolve on every platform, and a value
          // the element already carries is still listed by renderField.
          var fontFamilyOpts = ["", "system-ui", "ui-sans-serif", "ui-serif",
            "ui-monospace", "ui-rounded", "sans-serif", "serif", "monospace"];
          var fontSizeOpts = ["", "12px", "13px", "14px", "15px", "16px", "18px", "20px",
            "22px", "24px", "28px", "32px", "40px", "48px", "64px"];
          var fontWeightOpts = ["", "normal", "bold", "100", "200", "300", "400", "500",
            "600", "700", "800", "900"];
          var lineHeightOpts = ["", "normal", "1", "1.15", "1.25", "1.4", "1.5", "1.6",
            "1.75", "2", "2.5", "3"];
          var letterSpacingOpts = ["", "normal", "-0.03em", "-0.02em", "-0.01em", "0",
            "0.01em", "0.02em", "0.03em", "0.05em", "0.1em"];
          var displayOpts = ["", "block", "inline", "inline-block", "flex", "inline-flex", "grid", "inline-grid", "none"];
          var positionOpts = ["", "static", "relative", "absolute", "fixed", "sticky"];
          var flexDirOpts = ["", "row", "column", "row-reverse", "column-reverse"];
          var justifyOpts = ["", "flex-start", "center", "flex-end", "space-between", "space-around", "space-evenly"];
          var alignOpts = ["", "flex-start", "center", "flex-end", "stretch", "baseline"];

          if (!selected) {
            return h("div", { className: "dpb-react-empty" },
              h("p", null, t("visual_select")),
              h("button", { type: "button", onClick: function () { try { frame.focus(); } catch (_) {} } }, t("visual_pick")));
          }
          return h("div", { className: "dpb-react-fields" },
            renderSection("colors", t("sec_colors"), [
              renderField("color", t("visual_color"), "color"),
              renderField("background-color", t("visual_backgroundColor"), "color")
            ]),
            renderSection("typography", t("sec_typography"), [
              compact && selected && selected.textEditable && h("div", { className: "dpb-compact-text-toolbar", key: "compact-text", role: "toolbar", "aria-label": t("sec_typography") },
                [["B", t("visual_bold"), "font-weight", selected.style.fontWeight >= 600, "bold", "normal"],
                  ["I", t("visual_italic"), "font-style", selected.style.fontStyle === "italic", "italic", "normal"],
                  ["U", t("visual_underline"), "text-decoration", selected.style.textDecoration.indexOf("underline") >= 0, "underline", "none"],
                  ["S", t("visual_strikethrough"), "text-decoration", selected.style.textDecoration.indexOf("line-through") >= 0, "line-through", "none"]].map(function (action) {
                  return h("button", { key: action[1], type: "button", "aria-label": action[1], "aria-pressed": action[3], "data-action": action[4],
                    disabled: !ready || stale || busy, onClick: function () { applyStyle(action[2], action[3] ? action[5] : action[4]); } }, action[0]);
                })),
              renderField("font-family", t("visual_fontFamily"), "select", fontFamilyOpts),
              renderPair(
                renderField("font-size", t("visual_fontSize"), "select", fontSizeOpts),
                renderField("font-weight", t("visual_fontWeight"), "select", fontWeightOpts),
                "pair-font"
              ),
              renderPair(
                renderField("line-height", t("visual_lineHeight"), "select", lineHeightOpts),
                renderField("letter-spacing", t("visual_letterSpacing"), "select", letterSpacingOpts),
                "pair-metrics"
              )
            ]),
            renderSection("layout", t("sec_layout"), [
              renderPair(
                renderField("display", t("visual_display"), "select", displayOpts),
                renderField("position", t("visual_position"), "select", positionOpts),
                "pair-disp-pos"
              ),
              renderField("flex-direction", t("visual_flexDirection"), "select", flexDirOpts),
              renderField("justify-content", t("visual_justifyContent"), "select", justifyOpts),
              renderField("align-items", t("visual_alignItems"), "select", alignOpts),
              renderField("gap", t("visual_gap"), "unit", null, "px"),
              renderPair(
                renderField("width", t("visual_width"), "unit", null, "px"),
                renderField("height", t("visual_height"), "unit", null, "px"),
                "pair-dims"
              )
            ]),
            renderSection("spacing", t("sec_spacing"), [
              renderQuad("padding", t("visual_padding")),
              renderQuad("margin", t("visual_margin"))
            ]),
            renderSection("border", t("sec_border"), [
              renderField("border-radius", t("visual_borderRadius"), "unit", null, "px"),
              renderPair(
                renderField("border-width", t("visual_borderWidth"), "unit", null, "px"),
                renderField("border-color", t("visual_borderColor"), "color"),
                "pair-border"
              )
            ])
          );
        })(), h("div", { className: "dpb-react-submit" },
          // The header owns the decision, so the panel shows the next step rather
          // than a second, competing button.
          h("p", { className: "dpb-react-next", role: "status",
            "data-ready": reviewGate ? "true" : "false" },
            reviewGate ? t("visual_next_ready") : t("visual_next_waiting")),
          h("p", { className: "dpb-react-help" }, t("visual_help"))));
    }
    window.ReactDOM.createRoot(mount).render(h(Editor));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
