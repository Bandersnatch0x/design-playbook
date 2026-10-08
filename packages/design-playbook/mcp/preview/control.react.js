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
    function getEntryId(item) {
      if (!item) return null;
      if (item._entryId !== undefined) return item._entryId;
      if (Array.isArray(item) && item.length > 0) {
        if (item._entryId !== undefined) return item._entryId;
        if (item[0]._entryId !== undefined) return item[0]._entryId;
        if (item[0]._seq !== undefined) return item[0]._seq;
      }
      if (item._seq !== undefined) return item._seq;
      return null;
    }
    function Editor() {
      var [selected, setSelected] = React.useState(null);
      var [pending, setPending] = React.useState([]);
      var [history, setHistory] = React.useState([]);
      var [future, setFuture] = React.useState([]);
      var [drafts, setDrafts] = React.useState({});
      var [ready, setReady] = React.useState(false);
      var [connecting, setConnecting] = React.useState(true);
      var [stale, setStale] = React.useState(false);
      React.useEffect(function () {
        var loading = document.getElementById("dpb-prototype-loading");
        if (loading) loading.hidden = !connecting;
        document.getElementById("dpb-artboard-inner").setAttribute("aria-busy", String(connecting));
      }, [connecting]);
      var [diagnostic, setDiagnostic] = React.useState("visual_disconnected");
      var [busy, setBusy] = React.useState(false);
      var [webmcp, setWebmcp] = React.useState(false);
      var [locale, setLocale] = React.useState(root.lang);
      var [presenceUsers, setPresenceUsers] = React.useState([]);
      var [presenceStatus, setPresenceStatus] = React.useState("");
      var presence = React.useRef(null);
      var current = React.useRef({}), request = React.useRef(null);
      var sequence = React.useRef(0), draftTimers = React.useRef({});
      var accepted = React.useRef({});
      var pendingRef = React.useRef(pending);
      pendingRef.current = pending;
      var historyRef = React.useRef(history);
      historyRef.current = history;
      var futureRef = React.useRef(future);
      futureRef.current = future;
      var requestPromiseRef = React.useRef(null);
      var isDrainingRef = React.useRef(false);
      var dispatchedDrafts = React.useRef({});
      var unackedRequests = React.useRef({});
      var interruptedValues = React.useRef({});
      var lastAcceptedSeq = React.useRef({});
      var isPublishedRef = React.useRef(true);
      var [collapsed, setCollapsed] = React.useState({ layout: true, spacing: true, border: true });
      var [compact, setCompact] = React.useState(window.innerWidth <= 480);
      // Review readiness is owned by control.review.js, which publishes it. The
      // panel renders a local submit button and mirrors that state instead of
      // re-deriving the floor; the seed covers a publish that landed early.
      var [reviewGate, setReviewGate] = React.useState({ ready: false, label: "" });
      React.useEffect(function () {
        function onGate(event) {
          var detail = (event && event.detail) || {};
          setReviewGate({ ready: !!detail.ready, label: String(detail.label || "") });
        }
        document.addEventListener("dpbReviewReady", onGate);
        var btn = document.getElementById("dpb-btn-approve");
        var label = document.getElementById("dpb-approve-label");
        setReviewGate({
          ready: !!(btn && btn.classList.contains("dpb-approve-ready")),
          label: (label && label.textContent) || "",
        });
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
      current.current = { selected: selected, pending: pending, history: history,
        future: future, ready: ready, stale: stale, drafts: drafts };
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
      function fail(code) {
        setDiagnostic(code);
        if (request.current) {
          clearTimeout(request.current.timer);
          request.current.resolve({ accepted: false, error: code });
          request.current = null;
        }
        requestPromiseRef.current = null;
        setBusy(false);
      }
      function notifyPresence(type, selector, property) {
        var connection = presence.current;
        if (!connection || connection.source.readyState !== EventSource.OPEN) return;
        fetch(connection.url, { method: "POST", credentials: "omit",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ userId: connection.userId, type: type,
            selector: selector, property: property || "" })
        }).then(function (response) {
          if (!response.ok) throw Error("Presence event refused: " + response.status);
        }).catch(function () { setPresenceStatus("unavailable"); });
      }
      function disconnected() {
        setReady(false);
        setConnecting(false);
        // Retain unresolved drafts across disconnect (§3.3)
        if (current.current.pending.length) setStale(true);
        Object.values(draftTimers.current).forEach(clearTimeout);
        draftTimers.current = {};
        var interrupted = Object.values(unackedRequests.current);
        unackedRequests.current = {};
        lastAcceptedSeq.current = {};
        interrupted.forEach(function (operation) {
          var key = operation.locator + ":" + operation.property;
          if (!operation.entry && !Object.prototype.hasOwnProperty.call(interruptedValues.current, key)) {
            interruptedValues.current[key] = operation.oldValue;
          }
          delete dispatchedDrafts.current[operation.property];
        });
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
        fail("visual_disconnected");
      }
      function applyStyle(property, value, action, entry) {
        var state = current.current;
        if (!state.ready || state.stale || !state.selected || request.current) {
          setDiagnostic("visual_unavailable");
          return Promise.resolve({ accepted: false, error: "visual_unavailable" });
        }
        var id = ++sequence.current;
        if (entry) entry._replayId = id;
        // Record what this dispatch sends. Typing already set this in commit(),
        // but the replay paths (undo/redo) did not, so drafts and dispatched
        // values stayed permanently unequal and the editor reported a pending
        // edit forever - which the readiness mirror now reads as "submittable".
        dispatchedDrafts.current[property] = value;
        var locator = entry ? entry[0].locator : state.selected.selector;
        notifyPresence("user-editing-element", locator, property);
        setBusy(true);
        isPublishedRef.current = false;
        var inlineStyle = document.createElement("div").style;
        inlineStyle.cssText = state.selected.inlineStyle || "";
        var unacked = { oldValue: inlineStyle.getPropertyValue(property), id: id, action: action || "edit", entry: entry,
          value: value, draft: state.drafts[property], property: property,
          viewport: entry ? entry[0].viewport : window.DPB_ACTIVE_VIEWPORT || "any",
          locator: locator };
        unackedRequests.current[id] = unacked;
        var p = new Promise(function (resolve) {
          request.current = Object.assign({ resolve: resolve,
            timer: setTimeout(function () {
              if (request.current && request.current.id === id) {
                var req = request.current;
                var prop = req.property;
                if (prop && dispatchedDrafts.current) {
                  delete dispatchedDrafts.current[prop];
                }
                request.current = null;
                requestPromiseRef.current = null;
                setBusy(false);
                setDiagnostic("visual_drain_failed");
                var resFn = req.resolve;
                req.resolve = null;
                if (typeof resFn === "function") {
                  resFn({ accepted: false, error: "timeout" });
                }
              }
            }, 1500) }, unacked);
          post({ type: "set-style", requestId: id, selector: locator, property: property,
            value: value, changes: entry && entry.map(function (item) {
              return { property: item.property, value: action === "undo" ? item.oldValue : item.newValue };
            }), replay: !!entry });
        });
        requestPromiseRef.current = p;
        p.finally(function () {
          if (requestPromiseRef.current === p) requestPromiseRef.current = null;
        });
        return p;
      }
      function commit(property, value, selector) {
        clearTimeout(draftTimers.current[property]);
        delete draftTimers.current[property];
        var state = current.current;
        if (!state.selected || state.selected.selector !== selector) return;
        // Serialize requests, not typing. A newer keystroke replaces this timer.
        if (request.current) {
          draftTimers.current[property] = setTimeout(function () { commit(property, value, selector); }, 200);
          return;
        }
        if (value === accepted.current[property]) return;
        dispatchedDrafts.current[property] = value;
        applyStyle(property, value);
      }
      React.useEffect(function () {
        function close() {
          if (presence.current) presence.current.source.close();
          presence.current = null;
          setPresenceUsers([]); setPresenceStatus("");
        }
        function advertise(event) {
          if (event.source !== frame.contentWindow || !event.data || !event.data.dpbHostPresence ||
              !binding.routeUrl || presence.current || mount.offsetParent === null) return;
          // Host opt-in only. Never accept an endpoint supplied by the child or
          // change iframe sandbox privileges to obtain presence.
          var url = new URL("/_presence", binding.routeUrl), token = event.data.dpbHostPresence.token;
          if (url.protocol !== "http:" || ["127.0.0.1", "localhost", "[::1]"].indexOf(url.hostname) < 0 ||
              typeof token !== "string" || !/^[A-Za-z0-9_-]{32}$/.test(token)) return;
          if (!window.EventSource) { setPresenceStatus("unavailable"); return; }
          var userId = crypto.randomUUID(), name = t("presence_user") + " " + userId.slice(0, 6);
          url.searchParams.set("token", token);
          var postUrl = url.href;
          url.searchParams.set("user", userId); url.searchParams.set("name", name);
          var source = new EventSource(url.href);
          presence.current = { source: source, url: postUrl, userId: userId };
          setPresenceStatus("connecting");
          function update(message) {
            try {
              var data = JSON.parse(message.data);
              if (!Array.isArray(data.users) || data.users.length > 8 || data.users.some(function (user) {
                return !user || typeof user.userId !== "string" || typeof user.name !== "string" ||
                  typeof user.selector !== "string" || typeof user.property !== "string";
              })) throw Error("Invalid host presence");
              setPresenceUsers(data.users); setPresenceStatus("connected");
            } catch (error) {
              source.close(); setPresenceUsers([]); setPresenceStatus("unavailable");
            }
          }
          ["user-join", "user-leave", "user-editing-element", "user-committed-edit"].forEach(function (type) {
            source.addEventListener(type, update);
          });
          source.onerror = function () { setPresenceUsers([]); setPresenceStatus("unavailable"); };
        }
        window.addEventListener("message", advertise);
        frame.addEventListener("load", close);
        window.addEventListener("pagehide", close);
        return function () {
          close(); window.removeEventListener("message", advertise);
          frame.removeEventListener("load", close); window.removeEventListener("pagehide", close);
        };
      }, []);
      React.useEffect(function () {
        var observer = new MutationObserver(function () { setLocale(root.lang); });
        observer.observe(root, { attributes: true, attributeFilter: ["lang"] });
        return function () { observer.disconnect(); };
      }, []);
      React.useEffect(function () {
        function onHistoryKey(event) {
          if (event.key === "Escape") post({ type: "close-color-picker" });
          if (!(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing ||
              event.defaultPrevented || mount.offsetParent === null || !event.target.closest ||
              !event.target.closest("#dpb-react-editor-root, #dpb-canvas, #dpb-artboard-wrap, #dpb-visual-view")) return;
          var key = event.key.toLowerCase();
          if (key !== "z" && key !== "y") return;
          var state = current.current;
          if (!state.ready || state.stale || !state.selected || request.current) return;
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
        var nonce = 0, lastAck = 0, started = Date.now();
        function ping() {
          if (lastAck && Date.now() - lastAck > 2500) disconnected();
          if (!lastAck && Date.now() - started > 2500) setConnecting(false);
          post({ type: "ping", nonce: ++nonce, compact: window.innerWidth <= 480, labels: bridgeLabels() });
        }
        function load() { lastAck = 0; started = Date.now(); disconnected(); setConnecting(true); ping(); }
        function onMessage(event) {
          if (event.source !== frame.contentWindow) return;
          var data = event.data || {};
          if (data.dpbVisualEditReady) {
            var response = data.dpbVisualEditReady;
            if (response.nonce !== nonce) return;
            if (response.routeUrl !== (binding.routeUrl || "about:srcdoc")) {
              setStale(true); setReady(false); fail("visual_stale"); return;
            }
            lastAck = Date.now(); setReady(true); setConnecting(false);
            if (!current.current.stale) setDiagnostic(function (old) { return old === "visual_disconnected" ? "" : old; });
          }
          if (data.dpbVisualEditSelection && lastAck) {
            var selection = data.dpbVisualEditSelection;
            if (selection.requestId) {
              // A mutation snapshot is not a new user selection or draft.
              if (current.current.selected && selection.selector === current.current.selected.selector &&
                  ((request.current && selection.requestId === request.current.id) ||
                    String(selection.requestId).indexOf("gesture-") === 0)) setSelected(selection);
            } else {
              Object.values(draftTimers.current).forEach(clearTimeout);
              setSelected(selection);
              accepted.current = snapshot(selection);
              setDrafts(accepted.current);
              dispatchedDrafts.current = Object.assign({}, accepted.current);
              notifyPresence("user-editing-element", selection.selector, "");
            }
          }
          var rejected = data.dpbVisualEditRejected;
          if (rejected && request.current && rejected.requestId === request.current.id) {
            if (rejected.code === "visual_target_missing") setStale(true);
            fail(rejected.code); return;
          }
          var change = data.dpbVisualEditChange;
          if (!change || !current.current.ready || current.current.stale) return;
          var unacked = unackedRequests.current && unackedRequests.current[change.requestId];
          var operation = (request.current && change.requestId === request.current.id ? request.current : null) || unacked;
          if (!operation && !(typeof change.requestId === "string" && change.requestId.indexOf("gesture-") === 0)) return;
          if (unacked) delete unackedRequests.current[change.requestId];
          if (operation && operation.entry && operation.entry._replayId !== operation.id) return;
          var changes = (change.changes || [change]).map(function (c) {
            var key = change.selector + ":" + c.property;
            if (!Object.prototype.hasOwnProperty.call(interruptedValues.current, key)) return c;
            var recovered = Object.assign({}, c, { oldValue: interruptedValues.current[key] });
            delete interruptedValues.current[key];
            return recovered;
          });
          notifyPresence("user-committed-edit", change.selector, changes.map(function (c) { return c.property; }).join(", "));
          if (operation) {
            clearTimeout(operation.timer);
            if (request.current && request.current.id === change.requestId) {
              request.current = null; requestPromiseRef.current = null; setBusy(false); setDiagnostic("");
            }
          }
          var opSeq = operation ? (operation.id || ++sequence.current) : ++sequence.current;
          var state = current.current;
          var edits = changes.filter(function (c) { return c.oldValue !== c.newValue; }).map(function (c) {
            return { kind: LAYOUT.indexOf(c.property) >= 0 ? "layout" : "style",
              viewport: operation ? operation.viewport : (window.DPB_ACTIVE_VIEWPORT || "any"),
              locator: change.selector, property: c.property, oldValue: c.oldValue, newValue: c.newValue,
              _seq: opSeq,
              _entryId: opSeq };
          });
          if (edits.length) edits._entryId = opSeq;
          if (operation && operation.action === "undo") {
            var targetId = getEntryId(operation.entry);
            var hist = historyRef.current || [];
            var targetIdx = -1;
            for (var i = hist.length - 1; i >= 0; i--) {
              if (getEntryId(hist[i]) === targetId) {
                targetIdx = i;
                break;
              }
            }
            if (targetIdx >= 0) {
              var nextHist = hist.slice(0, targetIdx).concat(hist.slice(targetIdx + 1));
              historyRef.current = nextHist;
              setHistory(nextHist);
              var fut = futureRef.current || [];
              var alreadyInFut = fut.some(function (f) { return getEntryId(f) === targetId; });
              var nextFut = alreadyInFut ? fut : fut.concat([operation.entry]);
              futureRef.current = nextFut;
              setFuture(nextFut);
              var nextPending = (pendingRef.current || []).filter(function (e) {
                return getEntryId(e) !== targetId;
              });
              pendingRef.current = nextPending;
              setPending(nextPending);
              publishBatch(nextPending, current.current.stale);
            }
          } else if (operation && operation.action === "redo") {
            var targetId = getEntryId(operation.entry);
            var fut = futureRef.current || [];
            var targetIdx = -1;
            for (var i = fut.length - 1; i >= 0; i--) {
              if (getEntryId(fut[i]) === targetId) {
                targetIdx = i;
                break;
              }
            }
            if (targetIdx >= 0) {
              var nextFut = fut.slice(0, targetIdx).concat(fut.slice(targetIdx + 1));
              futureRef.current = nextFut;
              setFuture(nextFut);
              var hist = historyRef.current || [];
              var alreadyInHist = hist.some(function (h) { return getEntryId(h) === targetId; });
              var nextHist = alreadyInHist ? hist : hist.concat([operation.entry]);
              nextHist.sort(function (a, b) {
                var aSeq = (a && a[0] && (a[0]._seq || a[0]._entryId)) || 0;
                var bSeq = (b && b[0] && (b[0]._seq || b[0]._entryId)) || 0;
                return aSeq - bSeq;
              });
              historyRef.current = nextHist;
              setHistory(nextHist);
              var curPending = pendingRef.current || [];
              var alreadyInPending = curPending.some(function (e) { return getEntryId(e) === targetId; });
              var nextPending = alreadyInPending ? curPending : curPending.concat(operation.entry);
              nextPending.sort(function (a, b) {
                return ((a._seq || a._entryId) || 0) - ((b._seq || b._entryId) || 0);
              });
              pendingRef.current = nextPending;
              setPending(nextPending);
              publishBatch(nextPending, current.current.stale);
            }
          } else if (edits.length) {
            var nextPending = (pendingRef.current || []).concat(edits);
            nextPending.sort(function (a, b) { return (a._seq || 0) - (b._seq || 0); });
            pendingRef.current = nextPending;
            setPending(pendingRef.current);
            var nextHist = (historyRef.current || []).concat([edits]);
            nextHist.sort(function (a, b) {
              var aSeq = (a && a[0] && a[0]._seq) || 0;
              var bSeq = (b && b[0] && b[0]._seq) || 0;
              return aSeq - bSeq;
            });
            historyRef.current = nextHist;
            setHistory(nextHist);
            var fut = futureRef.current || [];
            var isOlderReceipt = fut.some(function (f) {
              var fSeq = (f && f[0] && (f[0]._seq || f[0]._entryId)) || 0;
              return opSeq < fSeq;
            });
            if (!isOlderReceipt) {
              futureRef.current = [];
              setFuture([]);
            }
            publishBatch(pendingRef.current, current.current.stale);
          }
          if (state.selected && state.selected.selector === change.selector) {
            changes.forEach(function (c) {
              var propKey = change.selector + ":" + c.property;
              var lastSeq = lastAcceptedSeq.current[propKey] || 0;
              if (opSeq >= lastSeq) {
                lastAcceptedSeq.current[propKey] = opSeq;
                accepted.current = syncDraft(accepted.current, c.property, c.newValue);
              }
            });
            // Keep newer inspector keystrokes while acknowledging older requests.
            setDrafts(function (values) {
              changes.forEach(function (c) {
                var propKey = change.selector + ":" + c.property;
                var lastSeq = lastAcceptedSeq.current[propKey] || 0;
                if (opSeq >= lastSeq) {
                  if (!operation || operation.entry || values[c.property] === operation.draft) {
                    values = syncDraft(values, c.property, operation && !operation.entry ? operation.value : c.newValue);
                  }
                }
              });
              return values;
            });
          }
          if (operation && typeof operation.resolve === "function") {
            var resFn = operation.resolve;
            operation.resolve = null;
            resFn({ accepted: true, pending: edits.length > 0 });
          }
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
          if (request.current) clearTimeout(request.current.timer);
        };
      }, []);
      function publishBatch(editsList, isStale) {
        var list = editsList !== undefined ? editsList : (pendingRef.current || []);
        var sorted = (list || []).slice().sort(function (a, b) { return (a._seq || 0) - (b._seq || 0); });
        var cleanEdits = sorted.map(function (e) {
          return { kind: e.kind, viewport: e.viewport, locator: e.locator,
            property: e.property, oldValue: e.oldValue, newValue: e.newValue };
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
        publishBatch(pending, stale);
        var tabEl = document.getElementById("dpb-tab-visual");
        if (tabEl) tabEl.classList.toggle("is-pending", pending.length > 0);
        var countEl = document.getElementById("dpb-visual-count");
        if (countEl) countEl.textContent = String(pending.length);
      }, [pending, stale]);
      React.useEffect(function () {
        // The rail's mirror also depends on work that is in flight (an edit whose
        // acknowledgement has not arrived) and on unsent keystrokes, which do not
        // change the published batch. Tell it whenever those move, so the first
        // edit is submittable immediately instead of only after its receipt.
        document.dispatchEvent(new CustomEvent("dpbVisualEditsChanged"));
      }, [busy, pending, drafts]);
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
            execute: function (input) { return applyStyle(String(input.property || ""), String(input.value || "")); } },
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
          setDiagnostic("visual_tools_unavailable");
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
          publishBatch(pendingRef.current, state.stale);
          return Promise.resolve({ ok: true, batch: window.DPB_VISUAL_EDIT_BATCH });
        }
        isDrainingRef.current = true;
        setBusy(true);

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
            isDrainingRef.current = false;
            setBusy(false);
            resolve({ ok: false, error: "timeout" });
          }, maxWait);

          function finish(ok, err) {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            isDrainingRef.current = false;
            setBusy(false);
            if (!ok) {
              resolve({ ok: false, error: err || "drain_failed" });
              return;
            }
            var batch = publishBatch(pendingRef.current, current.current.stale);
            resolve({ ok: true, batch: batch });
          }

          function step() {
            if (finished) return;
            var curReq = requestPromiseRef.current;
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
              return st.drafts[p] !== undefined && dispatchedDrafts.current[p] !== st.drafts[p];
            });

            if (uncommittedProps.length > 0) {
              var nextProp = uncommittedProps[0];
              var nextVal = st.drafts[nextProp];
              dispatchedDrafts.current[nextProp] = nextVal;
              applyStyle(nextProp, nextVal).then(function (res) {
                if (finished) return;
                if (!res || !res.accepted) {
                  dispatchedDrafts.current[nextProp] = null;
                  finish(false, (res && res.error) || "rejected");
                  return;
                }
                step();
              }).catch(function (err) {
                if (finished) return;
                dispatchedDrafts.current[nextProp] = null;
                finish(false, String(err));
              });
              return;
            }

            if (unackedRequests.current && Object.keys(unackedRequests.current).length > 0) {
              finish(false, "unresolved_edits");
              return;
            }

            finish(true);
          }

          step();
        });
      }

      function hasPendingVisualEdits() {
        var state = current.current;
        if (state.stale || !state.selected) return false;
        if (!isPublishedRef.current) return true;
        if (request.current || requestPromiseRef.current) return true;
        if (unackedRequests.current && Object.keys(unackedRequests.current).length > 0) return true;
        if (Object.keys(draftTimers.current).length > 0) return true;
        return Object.keys(state.drafts).some(function (p) {
          return state.drafts[p] !== undefined && dispatchedDrafts.current[p] !== state.drafts[p];
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
        window.dpbDrainVisualEdits = function () {
          if (drainRef.current) return drainRef.current();
          return Promise.resolve({ ok: true, batch: window.DPB_VISUAL_EDIT_BATCH });
        };
        return function () {
          window.dpbHasPendingVisualEdits = null;
          window.dpbDrainVisualEdits = null;
        };
      }, []);
      function replay(action) {
        var entries = action === "undo" ? (historyRef.current || []) : (futureRef.current || []);
        var entry = entries[entries.length - 1];
        if (entry) applyStyle(entry[0].property, action === "undo" ? entry[0].oldValue : entry[0].newValue, action, entry);
      }
      return h("section", { className: "dpb-react-editor", "aria-label": t("visual_title") },
        h("div", { className: "dpb-react-editor-head" }, h("strong", null, t("visual_title")),
          h("span", { className: "dpb-react-badge" + (webmcp ? " is-on" : "") }, webmcp ? "WebMCP" : t("visual_bridge"))),
        h("div", { className: "dpb-react-route" }, binding.routeUrl || t("visual_artifact")),
        presenceStatus && h("div", { className: "dpb-react-presence", role: "status",
          "aria-live": "polite", "data-state": presenceStatus },
          h("span", null, t("presence_" + presenceStatus)),
          presenceStatus === "connected" && h("ul", null, presenceUsers.map(function (user) {
            return h("li", { key: user.userId, "data-user-id": user.userId }, user.name,
              presence.current && user.userId === presence.current.userId ? " " + t("presence_you") : "",
              user.selector ? " · " + t("presence_editing") + " " + user.selector +
                (user.property ? " · " + user.property : "") : "");
          }))),
        h("div", { className: "dpb-react-selection" }, selected ? selected.selector : t("visual_select")),
        h("div", { className: "dpb-react-actions" },
          h("button", { type: "button", disabled: !ready || stale || busy || !history.length, "aria-label": t("visual_undo"), onClick: function () { replay("undo"); } }, t("visual_undo")),
          h("button", { type: "button", disabled: !ready || stale || busy || !future.length, "aria-label": t("visual_redo"), onClick: function () { replay("redo"); } }, t("visual_redo")),
          h("span", { className: "dpb-react-pending-count" }, t("visual_pending").replace("{n}", pending.length))),
        h("p", { className: "dpb-react-diagnostic", role: "status", "data-stale": stale }, stale ? t("visual_stale") : connecting ? "" : diagnostic ? t(diagnostic) : ""),
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
          function handleKey(prop, val, e) {
            if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); e.stopPropagation(); commit(prop, val, selected && selected.selector); }
          }
          function renderField(prop, label, kind, opts, unit) {
            var val = drafts[prop] || "";
            if (kind === "select") {
              return h("label", { className: "dpb-react-field dpb-react-dropdown", key: prop, "data-property": prop },
                h("span", null, label),
                h("select", {
                  value: val, disabled: fieldDisabled,
                  onChange: function (e) {
                    var v = e.target.value;
                    handleInput(prop, v);
                    commit(prop, v, selected && selected.selector);
                  }
                }, (opts || []).map(function (opt) {
                  var oval = typeof opt === "string" ? opt : opt.value;
                  var olbl = typeof opt === "string" ? (opt || "–") : opt.label;
                  return h("option", { key: oval, value: oval }, olbl);
                }))
              );
            }
            if (kind === "unit") {
              return h("label", { className: "dpb-react-field dpb-react-unit", key: prop, "data-property": prop },
                h("span", null, label),
                h("div", { className: "dpb-unit-input-wrap" },
                  h("input", {
                    value: val, disabled: fieldDisabled,
                    onChange: function (e) { handleInput(prop, e.target.value); },
                    onBlur: function (e) { handleBlur(prop, e.target.value); },
                    onKeyDown: function (e) { handleKey(prop, e.target.value, e); }
                  }),
                  unit && /^-?(?:\d+\.?\d*|\.\d+)$/.test(val) ? h("span", { className: "dpb-unit-suffix" }, unit) : null
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
                  onKeyDown: function (e) { handleKey(prop, e.target.value, e); }
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
                    onKeyDown: function (e) { handleKey(sProp, e.target.value, e); }
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
            var modified = pending.some(function (edit) {
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

          var weightOpts = ["", "normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"];
          var displayOpts = ["", "block", "inline", "inline-block", "flex", "inline-flex", "grid", "inline-grid", "none"];
          var positionOpts = ["", "static", "relative", "absolute", "fixed", "sticky"];
          var flexDirOpts = ["", "row", "column", "row-reverse", "column-reverse"];
          var justifyOpts = ["", "flex-start", "center", "flex-end", "space-between", "space-around", "space-evenly"];
          var alignOpts = ["", "flex-start", "center", "flex-end", "stretch", "baseline"];

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
                  return h("button", { key: action[1], type: "button", "aria-label": action[1], "aria-pressed": action[3],
                    disabled: !ready || stale || busy, onClick: function () { applyStyle(action[2], action[3] ? action[5] : action[4]); } }, action[0]);
                })),
              renderField("font-family", t("visual_fontFamily")),
              renderPair(
                renderField("font-size", t("visual_fontSize"), "unit", null, "px"),
                renderField("font-weight", t("visual_fontWeight"), "text"),
                "pair-font"
              ),
              renderPair(
                renderField("line-height", t("visual_lineHeight"), "unit", null, ""),
                renderField("letter-spacing", t("visual_letterSpacing"), "unit", null, "px"),
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
          // The rail owns the single fixed submission action, so the panel shows
          // the next step instead of rendering a second, competing button.
          h("p", { className: "dpb-react-next", role: "status",
            "data-ready": reviewGate.ready ? "true" : "false" },
            reviewGate.ready ? t("visual_next_ready") : t("visual_next_waiting")),
          h("p", { className: "dpb-react-help" }, t("visual_help"))));
    }
    window.ReactDOM.createRoot(mount).render(h(Editor));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
