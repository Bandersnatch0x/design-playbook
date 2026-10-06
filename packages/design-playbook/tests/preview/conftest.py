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
