"""Session isolation for the Preview suite.

The preview round ledger defaults to the user-level
``~/.design-playbook/preview-ledger`` (see ``ledger.ledger_root``). Left alone,
every suite run appends dozens of round files to the developer's home directory,
so the machine accumulates state the tests never asked for and the suite stops
being hermetic.

Point the ledger at a per-session temporary directory instead.
``DESIGN_PLAYBOOK_PREVIEW_LEDGER_DIR`` is the documented override, and host
applier subprocesses (``applier.py``) inherit the environment, so the isolation
reaches them too. An explicit developer override is still respected.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from design_playbook.mcp.preview.ledger import LEDGER_ENV_VAR

if not os.environ.get(LEDGER_ENV_VAR):
    os.environ[LEDGER_ENV_VAR] = str(
        Path(tempfile.mkdtemp(prefix="dpb-preview-ledger-")).resolve()
    )


_INSPECTOR_SECTIONS = {
    prop: section
    for section, properties in {
        "colors": "color background-color",
        "typography": "font-family font-size font-weight line-height letter-spacing",
        "layout": "display position flex-direction justify-content align-items gap width height transform",
        "spacing": "margin padding margin-top margin-right margin-bottom margin-left padding-top padding-right padding-bottom padding-left",
        "border": "border-radius border-width border-color",
    }.items()
    for prop in properties.split()
}


def expand_inspector_section(page, property_name: str) -> None:
    """Open a property's inspector section without toggling an already-open one."""
    section = _INSPECTOR_SECTIONS[property_name]
    header = page.locator(
        f'.dpb-inspector-section[data-section="{section}"] .dpb-section-header'
    )
    if header.get_attribute("aria-expanded") == "false":
        header.click()
