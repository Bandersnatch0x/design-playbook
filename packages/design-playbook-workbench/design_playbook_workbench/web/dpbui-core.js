(function (global) {
  "use strict";

  // ---- preference stores: theme + locale (ADR-0048 Stage P) ----
  // Each global preference gets one store with a single write point. Both live
  // here, and the server inlines this file in its own script block ahead of
  // each shell's own bundle, so no shell can grow a private copy of either
  // store. resolveTheme (host preference, stored choice, system fallback) and
  // the locale table swap are pure, so node can run them without a browser.
  var DPBUI = (global.DPBUI = global.DPBUI || {});

  DPBUI.theme = (function () {
    var STORAGE_KEY = "dpb.preview.theme";
    var ICONS = {
      light: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.2 10.6A5.6 5.6 0 0 1 5.4 2.8 6.1 6.1 0 1 0 13.2 10.6Z"/></svg>',
      dark: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="3.1"/><path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1"/></svg>',
    };

    function pick(value) {
      return value === "light" || value === "dark" ? value : null;
    }

    function resolveTheme(explicit, stored, prefersDark) {
      return pick(explicit) || pick(stored) || (prefersDark ? "dark" : "light");
    }

    function explicitTheme(el) {
      if (!el) return null;
      var v = el.getAttribute("data-theme");
      if (v === "light" || v === "dark") return v;
      if (el.classList.contains("theme-light")) return "light";
      if (el.classList.contains("theme-dark")) return "dark";
      return null;
    }

    function storedTheme() {
      try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
    }

    function applyTheme(theme, persist) {
      var rootEl = document.getElementById("dpb-root");
      if (!rootEl) return;
      rootEl.setAttribute("data-theme", theme);
      var floatEl = document.getElementById("dpb-float-root");
      if (floatEl) floatEl.setAttribute("data-theme", theme);
      var toastsEl = document.getElementById("dpb-toasts");
      if (toastsEl) toastsEl.setAttribute("data-theme", theme);
      var icon = document.getElementById("dpb-theme-icon");
      if (icon) icon.innerHTML = ICONS[theme === "dark" ? "dark" : "light"];
      if (persist) {
        try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
      }
    }

    function syncTheme() {
      var scheme = window.matchMedia
        ? window.matchMedia("(prefers-color-scheme: dark)")
        : null;
      applyTheme(resolveTheme(
        explicitTheme(document.documentElement) || explicitTheme(document.body),
        storedTheme(),
        !!(scheme && scheme.matches)
      ), false);
    }

    function current() {
      var el = document.getElementById("dpb-root");
      return (el && el.getAttribute("data-theme")) || "light";
    }

    return {
      STORAGE_KEY: STORAGE_KEY,
      resolveTheme: resolveTheme,
      applyTheme: applyTheme,
      syncTheme: syncTheme,
      current: current,
    };
  })();

  // ---- i18n: active table + dual dict (v9 L toggle) ----
  // One write point: setLang swaps the active table. A shell's thin tt/ttN
  // wrappers and the review file's toggle all read through it.
  DPBUI.i18n = (function () {
    var DUAL = window.DPB_I18N_DUAL || {};
    var I18N = window.DPB_I18N || {};
    var lang = "en";

    function initialLang(rootEl) {
      lang = rootEl.getAttribute("lang").indexOf("zh") === 0 ? "zh" : "en";
    }

    function setLang(next) {
      lang = next === "zh" ? "zh" : "en";
      // rebuild the active I18N table from the dual dict
      I18N = {};
      Object.keys(DUAL).forEach(function (k) { I18N[k] = DUAL[k][lang]; });
    }

    function tt(key) { return I18N[key] || (DUAL[key] && DUAL[key][lang]) || key; }
    function ttN(key, n) { return String(tt(key)).replace("{n}", String(n)); }

    return {
      initialLang: initialLang,
      setLang: setLang,
      getLang: function () { return lang; },
      tt: tt,
      ttN: ttN,
    };
  })();

  // ---- pure geometry helpers shared by the shells and the bridge ----
  // Both capture surfaces (the parent shell and the sandboxed bridge) build
  // the same anchors, so the selector, stroke and badge math lives here once.
  // The stop-node ids differ per surface and arrive as a parameter; the
  // environment difference (no localStorage inside the iframe) is a store
  // concern and stays out of these pure functions.
  DPBUI.pure = (function () {
    function cssPath(el, stopIds) {
      if (!el || el.nodeType !== 1) return "";
      if (el.id) return "#" + CSS.escape(el.id);
      var stops = stopIds || [];
      var parts = [];
      var cur = el;
      var depth = 0;
      while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {
        if (stops.indexOf(cur.id) >= 0) break;
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

    function drawPathD(points) {
      if (!points || !points.length) return "";
      var d = "";
      for (var i = 0; i < points.length; i++) {
        d += (i ? "L" : "M") + Number(points[i][0]).toFixed(1) + " " + Number(points[i][1]).toFixed(1);
      }
      return d + (points.length > 2 ? " Z" : "");
    }

    function buildDrawBadge(svg, cls, x, y, label) {
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", cls);
      g.setAttribute("transform", "translate(" + Number(x).toFixed(1) + "," + Math.max(9, Number(y) - 12).toFixed(1) + ")");
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "9");
      c.setAttribute("class", "dpb-draw-badge-c");
      var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("dy", "3.2");
      t.textContent = String(label);
      g.appendChild(c); g.appendChild(t);
      svg.appendChild(g);
      return g;
    }

    function resolveThemeFrom(setAttr, prefersDark) {
      if (setAttr === "light" || setAttr === "dark") return setAttr;
      return prefersDark ? "dark" : "light";
    }

    return {
      cssPath: cssPath,
      drawPathD: drawPathD,
      buildDrawBadge: buildDrawBadge,
      resolveThemeFrom: resolveThemeFrom,
    };
  })();
})(window);
