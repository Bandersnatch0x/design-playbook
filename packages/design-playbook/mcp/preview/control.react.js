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
      var [presenceUsers, setPresenceUsers] = React.useState([]);
      var [presenceStatus, setPresenceStatus] = React.useState("");
      var presence = React.useRef(null);
      var current = React.useRef({}), request = React.useRef(null);
      var sequence = React.useRef(0), draftTimers = React.useRef({});
      var accepted = React.useRef({});
      var [collapsed, setCollapsed] = React.useState({});
      function toggleSection(sec) {
        setCollapsed(function (prev) {
          return Object.assign({}, prev, { [sec]: !prev[sec] });
        });
      }
      var binding = window.DPB_VISUAL_BINDING || { sourceHash: "", routeUrl: "" };
      current.current = { selected: selected, pending: pending, history: history,
        future: future, ready: ready, stale: stale, drafts: drafts };
      var LABELS = {
        sec_typography: { zh: "排版 (Typography)", en: "Typography" },
        sec_colors: { zh: "颜色 (Colors)", en: "Colors" },
        sec_layout: { zh: "布局 (Layout)", en: "Layout" },
        sec_spacing: { zh: "间距 (Spacing)", en: "Spacing" },
        sec_border: { zh: "边框 (Border)", en: "Border" },
        visual_fontFamily: { zh: "字体", en: "Font family" },
        visual_letterSpacing: { zh: "字间距", en: "Letter spacing" },
        visual_display: { zh: "显示", en: "Display" },
        visual_position: { zh: "定位", en: "Position" },
        visual_flexDirection: { zh: "排列方向", en: "Direction" },
        visual_justifyContent: { zh: "主轴对齐", en: "Justify" },
        visual_alignItems: { zh: "交叉轴对齐", en: "Align" },
        visual_borderWidth: { zh: "边框粗细", en: "Border width" },
        visual_borderColor: { zh: "边框颜色", en: "Border color" },
        visual_transform: { zh: "变换", en: "Transform" },
        visual_marginTop: { zh: "上外边距", en: "Margin Top" },
        visual_marginRight: { zh: "右外边距", en: "Margin Right" },
        visual_marginBottom: { zh: "下外边距", en: "Margin Bottom" },
        visual_marginLeft: { zh: "左外边距", en: "Margin Left" },
        visual_paddingTop: { zh: "上内边距", en: "Padding Top" },
        visual_paddingRight: { zh: "右内边距", en: "Padding Right" },
        visual_paddingBottom: { zh: "下内边距", en: "Padding Bottom" },
        visual_paddingLeft: { zh: "左内边距", en: "Padding Left" }
      };
      function t(key) {
        var table = window.DPB_I18N_DUAL;
        var isZh = (locale || "en").indexOf("zh") === 0;
        if (table && table[key]) return table[key][isZh ? "zh" : "en"] || key;
        if (LABELS[key]) return LABELS[key][isZh ? "zh" : "en"] || key;
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
        notifyPresence("user-editing-element", locator, property);
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
          var userId = crypto.randomUUID(), name = "User " + userId.slice(0, 6);
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
          if (!(event.ctrlKey || event.metaKey) || event.altKey || event.isComposing ||
              event.defaultPrevented || mount.offsetParent === null || !mount.contains(event.target)) return;
          var key = event.key.toLowerCase();
          if (key !== "z" && key !== "y") return;
          var state = current.current;
          if (!state.ready || state.stale || !state.selected || request.current) return;
          event.preventDefault();
          replay(key === "y" || event.shiftKey ? "redo" : "undo");
        }
        window.addEventListener("keydown", onHistoryKey);
        return function () { window.removeEventListener("keydown", onHistoryKey); };
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
              notifyPresence("user-editing-element", selection.selector, "");
            }
          }
          var rejected = data.dpbVisualEditRejected;
          if (rejected && request.current && rejected.requestId === request.current.id) {
            if (rejected.code === "visual_target_missing") setStale(true);
            fail(rejected.code); return;
          }
          var change = data.dpbVisualEditChange, operation = request.current;
          if (!change) return;
          if (operation && change.requestId && change.requestId !== operation.id) return;
          notifyPresence("user-committed-edit", change.selector, change.property);
          if (operation && (!change.requestId || change.requestId === operation.id)) {
            clearTimeout(operation.timer); request.current = null; setBusy(false); setDiagnostic("");
          }
          var state = current.current;
          var edit = { kind: LAYOUT.indexOf(change.property) >= 0 ? "layout" : "style",
            viewport: operation ? operation.viewport : (window.DPB_ACTIVE_VIEWPORT || "any"),
            locator: change.selector, property: change.property,
            oldValue: change.oldValue, newValue: change.newValue };
          if (operation && operation.action === "undo") {
            setHistory(state.history.slice(0, -1));
            setFuture(state.future.concat([operation.entry]));
            setPending(state.pending.slice(0, -1));
          } else if (operation && operation.action === "redo") {
            setFuture(state.future.slice(0, -1));
            setHistory(state.history.concat([operation.entry]));
            setPending(state.pending.concat([operation.entry]));
          } else if (change.oldValue !== change.newValue) {
            setPending(state.pending.concat([edit]));
            setHistory(state.history.concat([edit])); setFuture([]);
          }
          if (state.selected && state.selected.selector === change.selector) {
            var valToStore = operation ? operation.value : change.newValue;
            accepted.current = Object.assign({}, accepted.current, { [change.property]: valToStore });
            // A receipt may acknowledge an older keystroke. Never overwrite the
            // newer draft (or another selection) while that request was in flight.
            setDrafts(function (values) {
              if (operation) {
                return values[change.property] === operation.draft
                  ? Object.assign({}, values, { [change.property]: operation.value }) : values;
              }
              return Object.assign({}, values, { [change.property]: valToStore });
            });
          }
          if (operation && (!change.requestId || change.requestId === operation.id)) {
            operation.resolve({ accepted: true, pending: change.oldValue !== change.newValue });
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
      React.useEffect(function () {
        window.DPB_VISUAL_EDIT_BATCH = { schemaVersion: 1, status: stale ? "stale" : "pending",
          sourceHash: binding.sourceHash, routeUrl: binding.routeUrl, edits: pending.slice() };
        var hidden = document.getElementById("dpb-visual-edits-json");
        hidden.value = JSON.stringify(window.DPB_VISUAL_EDIT_BATCH);
        document.getElementById("dpb-visual-count").textContent = String(pending.length);
        document.getElementById("dpb-tab-visual").classList.toggle("is-pending", pending.length > 0);
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
      function replay(action) {
        var state = current.current;
        var entries = action === "undo" ? state.history : state.future;
        var entry = entries[entries.length - 1];
        if (entry) applyStyle(entry.property, action === "undo" ? entry.oldValue : entry.newValue, action, entry);
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
        h("p", { className: "dpb-react-diagnostic", role: "status", "data-stale": stale }, stale ? t("visual_stale") : diagnostic ? t(diagnostic) : ""),
        (function () {
          function handleInput(prop, val) {
            setDrafts(function (old) { return Object.assign({}, old, { [prop]: val }); });
            clearTimeout(draftTimers.current[prop]);
            var sel = selected && selected.selector;
            draftTimers.current[prop] = setTimeout(function () { commit(prop, val, sel); }, 200);
          }
          function handleBlur(prop, val) {
            commit(prop, val, selected && selected.selector);
          }
          function handleKey(prop, val, e) {
            if (e.key === "Enter") { e.preventDefault(); commit(prop, val, selected && selected.selector); }
          }
          function renderField(prop, label, kind, opts, unit) {
            var val = drafts[prop] || "";
            if (kind === "select") {
              return h("label", { className: "dpb-react-field dpb-react-dropdown", key: prop, "data-property": prop },
                h("span", null, label),
                h("select", {
                  value: val, disabled: !selected || !ready || stale,
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
                    value: val, disabled: !selected || !ready || stale,
                    onChange: function (e) { handleInput(prop, e.target.value); },
                    onBlur: function (e) { handleBlur(prop, e.target.value); },
                    onKeyDown: function (e) { handleKey(prop, e.target.value, e); }
                  }),
                  unit ? h("span", { className: "dpb-unit-suffix" }, unit) : null
                )
              );
            }
            if (kind === "color") {
              return h("label", { className: "dpb-react-field dpb-react-color-row", key: prop, "data-property": prop },
                h("span", null, label),
                h("div", { className: "dpb-color-input-wrap" },
                  h("span", { className: "dpb-color-swatch-preview", style: { backgroundColor: val || "transparent" } }),
                  h("input", {
                    value: val, disabled: !selected || !ready || stale,
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
                value: val, disabled: !selected || !ready || stale,
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
                  value: drafts[prop] || "", disabled: !selected || !ready || stale,
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
                    value: drafts[sProp] || "", disabled: !selected || !ready || stale,
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
            return h("section", { className: "dpb-inspector-section" + (isClosed ? " is-collapsed" : " is-open"), key: secId, "data-section": secId },
              h("button", {
                type: "button", className: "dpb-section-header", "aria-expanded": !isClosed,
                onClick: function () { toggleSection(secId); }
              }, h("strong", null, title), h("span", { className: "dpb-section-chevron" }, isClosed ? "▸" : "▾")),
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
        })(), h("p", { className: "dpb-react-help" }, t("visual_help")));
    }
    window.ReactDOM.createRoot(mount).render(h(Editor));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
