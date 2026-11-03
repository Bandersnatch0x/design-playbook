// Generated from mcp/run_console/client_routes.py by
// scripts/generate_run_console_routes.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.runConsoleRoutes = {
    SCHEMA_VERSION: 1,
    SNAPSHOT: "/api/v1/snapshot",
    SOURCES_PREFIX: "/api/v1/sources/",
    REFRESH: { path: "/api/v1/actions/refresh", action: "refresh", schemaVersion: 1 },
    EXPORT_PREVIEW: { path: "/api/v1/actions/diagnostic-export/preview", action: "diagnostic-export-preview", schemaVersion: 1 },
    EXPORT_WRITE: { path: "/api/v1/actions/diagnostic-export/write", action: "diagnostic-export-write", schemaVersion: 1 },
  };
})(window);
