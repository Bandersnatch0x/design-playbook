#!/usr/bin/env python3
"""One-way sync for the shared UI layer (ADR-0048, 2026-10-13 amendment).

``packages/design-playbook/mcp/_shared/`` holds the canonical, editable
copies of the shared UI layer. The workbench ships byte copies flat in
its ``web/`` directory because its package data does not recurse. This
script is the only way to make those copies: it writes each one and then
the sha256 lock that sits beside them, so the root parity test, the
workbench's own startup check and the packaging test all compare against
one record. Run it after editing anything in ``mcp/_shared/``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = ROOT / "packages" / "design-playbook" / "mcp" / "_shared"
TARGET_DIR = (
    ROOT / "packages" / "design-playbook-workbench"
    / "design_playbook_workbench" / "web"
)
LOCK_NAME = "dpbui.lock.json"

#: Files the workbench ships as flat byte copies of their canonical file.
#: A name here is the file's name in both directories; add a row when the
#: workbench starts carrying another shared file, then rerun this script.
COPIES = ("tokens.css",)


def main() -> int:
    files: dict[str, str] = {}
    for name in COPIES:
        canonical = CANONICAL_DIR / name
        if not canonical.is_file():
            print(f"missing canonical file: {canonical}")
            return 1
        raw = canonical.read_bytes()
        (TARGET_DIR / name).write_bytes(raw)
        files[name] = hashlib.sha256(raw).hexdigest()
    lock = TARGET_DIR / LOCK_NAME
    lock.write_text(
        json.dumps({"schemaVersion": 1, "files": files}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        # Fixed LF so the committed bytes are identical on every platform
        # (.gitattributes enforces the same for the copies themselves).
        newline="\n",
    )
    print(f"synced {len(files)} file(s); wrote {lock.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
