#!/usr/bin/env python3
"""Evidence manifest v1 schema tests (T-145).

Two directions, both against the real writer (no hand-built "expected"
sample): a manifest line produced by ``scripts.evidence_manifest.append_entry``
must validate, and malformed variants of that same line must be rejected.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.manifest_schema import (  # noqa: E402
    SCHEMA_PATH,
    manifest_schema,
    validate_manifest_entry,
)
from design_playbook.scripts.evidence_manifest import append_entry  # noqa: E402

REQUEST = {
    "schemaVersion": 1,
    "viewport": {
        "width": 1280,
        "height": 800,
        "devicePixelRatio": 1.0,
        "colorScheme": "light",
    },
    "freeze": {"enabled": True, "waitFonts": True, "networkIdle": False},
}


def _written_entry() -> dict:
    """Write a real manifest line and return the parsed on-disk entry."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "evidence").mkdir()
        (run_dir / "evidence" / "capture.png").write_bytes(b"png-bytes")
        append_entry(
            run_dir,
            criterion="L6.1",
            artifact="capture.png",
            request=REQUEST,
            source="decision-1",
            observed_state="ok",
            result="captured",
            error="",
            method="runtime-observation",
            observation="the button rendered",
            scope="one run",
        )
        line = (run_dir / "evidence" / "manifest.jsonl").read_text(
            encoding="utf-8"
        )
    return json.loads(line)


class ManifestSchemaTest(unittest.TestCase):
    def test_schema_file_is_a_closed_v1_entry(self) -> None:
        schema = manifest_schema()

        assert SCHEMA_PATH.is_file()
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {
            "ts",
            "criterion",
            "artifact",
            "sha256",
            "request",
        }

    def test_writer_output_validates(self) -> None:
        entry = _written_entry()

        assert validate_manifest_entry(entry) == []
        assert entry["request"] == REQUEST

    def test_malformed_entries_are_rejected(self) -> None:
        entry = _written_entry()
        mutations = {
            "missing criterion": lambda e: e.pop("criterion"),
            "bad sha256": lambda e: e.__setitem__("sha256", "ABC"),
            "directory in artifact": lambda e: e.__setitem__(
                "artifact", "nested/capture.png"
            ),
            "unknown top-level key": lambda e: e.__setitem__("extra", 1),
            "unsupported schemaVersion": lambda e: e["request"].__setitem__(
                "schemaVersion", 2
            ),
            "incomplete freeze": lambda e: e["request"].__setitem__(
                "freeze", {"enabled": True}
            ),
            "unknown method": lambda e: e.__setitem__("method", "vibes"),
            "ts without offset": lambda e: e.__setitem__(
                "ts", "2026-11-06T10:00:00"
            ),
        }
        for name, mutate in mutations.items():
            broken = json.loads(json.dumps(entry))
            mutate(broken)
            assert validate_manifest_entry(broken), name


if __name__ == "__main__":
    unittest.main()
