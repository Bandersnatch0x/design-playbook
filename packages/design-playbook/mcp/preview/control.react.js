/* Direct preview edits are drafts until the bridge acknowledges a mutation. */
(function () {
  "use strict";
  function boot() {
    if (!window.React || !window.ReactDOM) throw Error("Preview editor runtime missing");
    var React = window.React, h = React.createElement;
    var mount = document.getElementById("dpb-react-editor-root");
    var frame = document.querySelector("iframe.dpb-proto-frame");
    var root = document.getElementById("dpb-root");
    if (!mount || !frame) return;
    // The only CSS-property -> computed snapshot key mapping in the inspector.
    var FIELDS = [
      ["color", "color"], ["background-color", "backgroundColor"],
      ["font-size", "fontSize"], ["font-weight", "fontWeight"],
      ["line-height", "lineHeight"], ["margin", "margin"],
      ["padding", "padding"], ["width", "width"], ["height", "height"],
      ["gap", "gap"], ["border-radius", "borderRadius"]
    ];
    var LAYOUT = ["margin", "padding", "width", "height", "gap", "display", "position",
      "flex", "flex-direction", "align-items", "justify-content", "grid-template-columns"];
    function post(message) {
      frame.contentWindow.postMessage({ dpbVisualEdit: message }, "*");
    }
    function Editor() {
      var [selected, setSelected] = React.useState(null);
      var [pending, setPending] = React.useState([]);
      var [history, setHistory] = React.useState([]);
      var [future, setFuture] = React.useState([]);
      var [drafts, setDrafts] = React.useState({});
      var [ready, setReady] = React.useState(false);
      var [stale, setStale] = React.useState(false);
      var [diagnostic, setDiagnostic] = React.useState("visual_disconnected");
      var [busy, setBusy] = React.useState(false);
      var [webmcp, setWebmcp] = React.useState(false);
      var [locale, setLocale] = React.useState(root.lang);
      var current = React.useRef({}), request = React.useRef(null);
      var sequence = React.useRef(0), draftTimers = React.useRef({});
      var accepted = React.useRef({});
      var binding = window.DPB_VISUAL_BINDING || { sourceHash: "", routeUrl: "" };
      current.current = { selected: selected, pending: pending, history: history,
        future: future, ready: ready, stale: stale, drafts: drafts };
      function t(key) {
        var table = window.DPB_I18N_DUAL;
        return table[key][locale.indexOf("zh") === 0 ? "zh" : "en"];
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
        setBusy(false);
      }
      function disconnected() {
        setReady(false);
        setSelected(null);
        setDrafts({});
        if (current.current.pending.length) setStale(true);
        Object.values(draftTimers.current).forEach(clearTimeout);
        fail("visual_disconnected");
      }
      function applyStyle(property, value, action, entry) {
        var state = current.current;
        if (!state.ready || state.stale || !state.selected || request.current) {
          setDiagnostic("visual_unavailable");
          return Promise.resolve({ accepted: false, error: "visual_unavailable" });
        }
        var id = ++sequence.current;
        var locator = entry ? entry.locator : state.selected.selector;
        setBusy(true);
        return new Promise(function (resolve) {
          request.current = { id: id, action: action || "edit", entry: entry, resolve: resolve,
            value: value, draft: state.drafts[property],
            viewport: entry ? entry.viewport : window.DPB_ACTIVE_VIEWPORT || "any",
            timer: setTimeout(disconnected, 1500) };
          post({ type: "set-style", requestId: id, selector: locator, property: property,
            value: value, replay: !!entry });
        });
      }
      function commit(property, value, selector) {
        clearTimeout(draftTimers.current[property]);
        var state = current.current;
        if (!state.selected || state.selected.selector !== selector) return;
        // Serialize requests, not typing. A newer keystroke replaces this timer.
        if (request.current) {
          draftTimers.current[property] = setTimeout(function () { commit(property, value, selector); }, 200);
          return;
        }
        if (value === accepted.current[property]) return;
        applyStyle(property, value);
      }
      React.useEffect(function () {
        var observer = new MutationObserver(function () { setLocale(root.lang); });
        observer.observe(root, { attributes: true, attributeFilter: ["lang"] });
        return function () { observer.disconnect(); };
      }, []);
      React.useEffect(function () {
        var nonce = 0, lastAck = 0;
        function ping() {
          if (lastAck && Date.now() - lastAck > 2500) disconnected();
          post({ type: "ping", nonce: ++nonce });
        }
        function load() { lastAck = 0; disconnected(); ping(); }
        function onMessage(event) {
          if (event.source !== frame.contentWindow) return;
          var data = event.data || {};
          if (data.dpbVisualEditReady) {
            var response = data.dpbVisualEditReady;
            if (response.nonce !== nonce) return;
            if (response.routeUrl !== (binding.routeUrl || "about:srcdoc")) {
              setStale(true); setReady(false); fail("visual_stale"); return;
            }
            lastAck = Date.now(); setReady(true);
            if (!current.current.stale) setDiagnostic(function (old) { return old === "visual_disconnected" ? "" : old; });
          }
          if (data.dpbVisualEditSelection && lastAck) {
            var selection = data.dpbVisualEditSelection;
            if (selection.requestId) {
              // A mutation snapshot is not a new user selection or draft.
              if (request.current && selection.requestId === request.current.id &&
                  current.current.selected && selection.selector === current.current.selected.selector) setSelected(selection);
            } else {
              Object.values(draftTimers.current).forEach(clearTimeout);
              setSelected(selection);
              accepted.current = snapshot(selection);
              setDrafts(accepted.current);
            }
          }
          var rejected = data.dpbVisualEditRejected;
          if (rejected && request.current && rejected.requestId === request.current.id) {
            if (rejected.code === "visual_target_missing") setStale(true);
            fail(rejected.code); return;
          }
          var change = data.dpbVisualEditChange, operation = request.current;
          if (!change || !operation || change.requestId !== operation.id) return;
          clearTimeout(operation.timer); request.current = null; setBusy(false); setDiagnostic("");
          var state = current.current;
          var edit = { kind: LAYOUT.indexOf(change.property) >= 0 ? "layout" : "style",
            viewport: operation.viewport, locator: change.selector, property: change.property,
            oldValue: change.oldValue, newValue: change.newValue };
          if (operation.action === "undo") {
            setHistory(state.history.slice(0, -1));
            setFuture(state.future.concat([operation.entry]));
            setPending(state.pending.slice(0, -1));
          } else if (operation.action === "redo") {
            setFuture(state.future.slice(0, -1));
            setHistory(state.history.concat([operation.entry]));
            setPending(state.pending.concat([operation.entry]));
          } else if (change.oldValue !== change.newValue) {
            setPending(state.pending.concat([edit]));
            setHistory(state.history.concat([edit])); setFuture([]);
          }
          if (state.selected && state.selected.selector === change.selector) {
            accepted.current = Object.assign({}, accepted.current, { [change.property]: operation.value });
            // A receipt may acknowledge an older keystroke. Never overwrite the
            // newer draft (or another selection) while that request was in flight.
            setDrafts(function (values) {
              return values[change.property] === operation.draft
                ? Object.assign({}, values, { [change.property]: operation.value }) : values;
            });
          }
          operation.resolve({ accepted: true, pending: change.oldValue !== change.newValue });
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
      React.useEffect(function () {
        window.DPB_VISUAL_EDIT_BATCH = { schemaVersion: 1, status: stale ? "stale" : "pending",
          sourceHash: binding.sourceHash, routeUrl: binding.routeUrl, edits: pending.slice() };
        var hidden = document.getElementById("dpb-visual-edits-json");
        hidden.value = JSON.stringify(window.DPB_VISUAL_EDIT_BATCH);
        document.getElementById("dpb-visual-count").textContent = String(pending.length);
      }, [pending, stale]);
      React.useEffect(function () {
        var modelContext = navigator.modelContext;
        if (!modelContext || typeof modelContext.registerTool !== "function") modelContext = document.modelContext;
        if (!modelContext || typeof modelContext.registerTool !== "function") return;
        var tools = [
          { name: "preview_get_selection", description: "Read selected Preview element and computed style",
            inputSchema: { type: "object", properties: {} },
            execute: function () { return current.current.selected || { selected: false }; } },
          { name: "preview_set_style", description: "Request one preview-only CSS edit",
            inputSchema: { type: "object", properties: { property: { type: "string" }, value: { type: "string" } }, required: ["property", "value"] },
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
      function replay(action) {
        var entries = action === "undo" ? history : future;
        var entry = entries[entries.length - 1];
        if (entry) applyStyle(entry.property, action === "undo" ? entry.oldValue : entry.newValue, action, entry);
      }
      return h("section", { className: "dpb-react-editor", "aria-label": t("visual_title") },
        h("div", { className: "dpb-react-editor-head" }, h("strong", null, t("visual_title")),
          h("span", { className: "dpb-react-badge" }, webmcp ? "WebMCP" : t("visual_bridge"))),
        h("div", { className: "dpb-react-route" }, binding.routeUrl || t("visual_artifact")),
        h("div", { className: "dpb-react-selection" }, selected ? selected.selector : t("visual_select")),
        h("div", { className: "dpb-react-actions" },
          h("button", { type: "button", disabled: !ready || stale || busy || !history.length, onClick: function () { replay("undo"); } }, t("visual_undo")),
          h("button", { type: "button", disabled: !ready || stale || busy || !future.length, onClick: function () { replay("redo"); } }, t("visual_redo")),
          h("span", { className: "dpb-react-pending-count" }, t("visual_pending").replace("{n}", pending.length))),
        h("p", { className: "dpb-react-diagnostic", role: "status" }, stale ? t("visual_stale") : diagnostic ? t(diagnostic) : ""),
        h("div", { className: "dpb-react-fields" }, FIELDS.map(function (field) {
          var property = field[0];
          return h("label", { className: "dpb-react-field", key: property, "data-property": property },
            h("span", null, t("visual_" + field[1])), h("input", {
              value: drafts[property] || "", disabled: !selected || !ready || stale,
              onChange: function (event) {
                var value = event.target.value;
                setDrafts(function (old) { return Object.assign({}, old, { [property]: value }); });
                clearTimeout(draftTimers.current[property]);
                var selector = selected.selector;
                draftTimers.current[property] = setTimeout(function () { commit(property, value, selector); }, 200);
              },
              onBlur: function (event) { commit(property, event.target.value, selected && selected.selector); },
              onKeyDown: function (event) { if (event.key === "Enter") { event.preventDefault(); commit(property, event.target.value, selected && selected.selector); } }
            }));
        })), h("p", { className: "dpb-react-help" }, t("visual_help")));
    }
    window.ReactDOM.createRoot(mount).render(h(Editor));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
