"""The client-visible workbench route vocabulary.

``web/app.js`` builds every API URL it calls. Written out as inline template
literals, a route rename passes every Python test and fails only in the
browser. This module is the one owner of the paths; ``scripts/
generate_workbench_routes.py`` derives ``web/routes.js`` from it, and the
drift gate turns a regenerate-then-edit red.

Constants only: no imports, safe for the generator to load by path.
"""
from __future__ import annotations

API = "/api/v1"
STATUS = API + "/status"
RESOLVE = API + "/resolve"
PROJECTS = API + "/projects"
PROBE = API + "/projects/probe"
BACKUP = API + "/backup"
SESSION = API + "/session"

#: ``(js_name, template)`` for the path builders. ``{name}`` placeholders are
#: URL-encoded by the generated function; callers append query strings.
BUILDERS: tuple[tuple[str, str], ...] = (
    ("project", API + "/projects/{project}"),
    ("projectAction", API + "/projects/{project}/actions/{action}"),
    ("assets", API + "/projects/{project}/assets"),
    ("asset", API + "/projects/{project}/assets/{asset}"),
    ("assetAction", API + "/projects/{project}/actions/assets/{asset}/{verb}"),
    ("assetPreview", API + "/projects/{project}/assets/{asset}/preview"),
    ("assetDocument", API + "/projects/{project}/assets/{asset}/document/{view}"),
    ("assetTokens", API + "/projects/{project}/assets/{asset}/tokens/{view}"),
    ("assetReferences", API + "/projects/{project}/assets/{asset}/references"),
    ("proposals", API + "/projects/{project}/proposals"),
    ("proposal", API + "/projects/{project}/proposals/{proposal}"),
    (
        "proposalAction",
        API + "/projects/{project}/actions/proposals/{proposal}/{verb}",
    ),
    ("instances", API + "/projects/{project}/instances"),
    ("canvases", API + "/projects/{project}/canvases"),
    ("canvas", API + "/projects/{project}/canvases/{canvas}"),
    (
        "canvasAction",
        API + "/projects/{project}/actions/canvases/{canvas}/{verb}",
    ),
    ("requests", API + "/projects/{project}/requests"),
    (
        "requestAction",
        API + "/projects/{project}/actions/requests/{request}/{verb}",
    ),
    ("backupPath", API + "/backup?path={path}"),
)
