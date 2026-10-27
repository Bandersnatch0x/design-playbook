// Generated from design_playbook/mcp/preview/visual_batch.py by
// scripts/generate_visual_contract.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.visualContract = {
    SCHEMA_VERSION: 1,
    STATUS_PENDING: "pending",
    STATUS_STALE: "stale",
    CHANGE_KINDS: ["style", "layout", "content", "responsive", "structure"],
    CSS_KINDS: ["style", "layout", "responsive"],
    VIEWPORTS: ["desktop", "tablet", "mobile", "any"],
    EDIT_SOURCES: ["shell", "frame", "agent", "unknown"],
    SHELL_SOURCE: "shell",
    FRAME_SOURCE: "frame",
    CONTENT_PROPERTIES: ["text", "placeholder", "aria-label"],
    ANY_VIEWPORT: "any",
    MAX_EDITS: 200,
    MAX_SELECTOR: 512,
    MAX_VALUE: 2000,
  };
})(window);
