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
})(window);
