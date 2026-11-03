"""Client-visible Run Console routes and typed-action names (RCV1-009, ADR-0044).

The Console client and the HTTP server both have to know these paths, action
names, and payload schema version. Written out in both languages, a rename
passes every Python test and fails only in the browser. ``client_routes.js``
is generated from this module, so the client reads the same facts and the
drift gate turns a regenerate-then-edit red.

This module holds constants only: it imports nothing, opens nothing, and is
safe for the generator to load by path.
"""
from __future__ import annotations

#: Every client-visible payload is versioned by this one number.
SCHEMA_VERSION = 1

SNAPSHOT_ROUTE = "/api/v1/snapshot"
SOURCES_PREFIX = "/api/v1/sources/"

ACTION_REFRESH = "refresh"
REFRESH_ROUTE = "/api/v1/actions/refresh"

ACTION_EXPORT_PREVIEW = "diagnostic-export-preview"
EXPORT_PREVIEW_ROUTE = "/api/v1/actions/diagnostic-export/preview"
ACTION_EXPORT_WRITE = "diagnostic-export-write"
EXPORT_WRITE_ROUTE = "/api/v1/actions/diagnostic-export/write"
