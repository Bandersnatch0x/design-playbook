"""Single version source for the bundled MCP adapters (T-145).

``.claude-plugin/plugin.json`` is the version of record. Both stdio servers
report that value in ``initialize`` instead of a hard-coded literal, so a
release bump cannot leave the adapters lying about which build is running.
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN_MANIFEST = (
    Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json"
)

# Sentinel for a package copied without its manifest. Deliberately not a
# plausible release number, so it reads as "unknown", never as a version.
_UNKNOWN_VERSION = "0.0.0"


def package_version() -> str:
    """Return the plugin manifest version (``0.0.0`` when unreadable)."""
    try:
        manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _UNKNOWN_VERSION
    version = manifest.get("version") if isinstance(manifest, dict) else None
    return version if isinstance(version, str) and version else _UNKNOWN_VERSION
