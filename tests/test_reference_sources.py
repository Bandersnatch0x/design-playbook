#!/usr/bin/env python3
"""Public-interface tests for durable reference source ingestion (ADR-0032)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "packages"
    / "design-playbook"
    / "skills"
    / "reference-intake"
    / "scripts"
    / "reference_sources.py"
)

SPEC = importlib.util.spec_from_file_location("reference_sources", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load reference source module: {MODULE_PATH}")
reference_sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference_sources)


PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture-pixels"


class ReferenceSourceTests(unittest.TestCase):
    def test_ephemeral_png_is_copied_and_manifest_forgets_temporary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "host-temp" / "clipboard.png"
            source.parent.mkdir()
            source.write_bytes(PNG_BYTES)
            run_root = root / "project" / ".scratch" / "run-1"

            manifest = reference_sources.ingest_ephemeral_image(
                source,
                run_root,
                run_id="run-1",
                source_id="src-1",
                kind="screenshot",
                captured_at="2026-08-17T10:00:00+08:00",
            )

            digest = hashlib.sha256(PNG_BYTES).hexdigest()
            record = manifest["sources"][0]
            self.assertEqual(record["sha256"], digest)
            self.assertEqual(record["media_type"], "image/png")
            self.assertEqual(record["storage"], "copied")
            self.assertEqual(record["acquired_via"], "attachment")
            self.assertEqual(
                record["locator"], f"reference/assets/clipboard-{digest[:12]}.png"
            )
            preserved = run_root / record["locator"]
            self.assertEqual(preserved.read_bytes(), PNG_BYTES)
            self.assertEqual(
                json.loads(
                    (run_root / "reference" / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                ),
                manifest,
            )
            self.assertNotIn(str(source), json.dumps(manifest))

    def test_provider_neutral_provenance_is_recorded_without_routing_on_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "from-host-tool.png"
            source.write_bytes(PNG_BYTES)

            manifest = reference_sources.ingest_ephemeral_image(
                source,
                root / "run",
                run_id="run",
                source_id="src-1",
                kind="other",
                acquired_via="host-tool",
                provider="figma-mcp",
                captured_at="2026-08-17T10:01:00Z",
            )

            record = manifest["sources"][0]
            self.assertEqual(record["acquired_via"], "host-tool")
            self.assertEqual(record["provider"], "figma-mcp")
            self.assertEqual(record["captured_at"], "2026-08-17T10:01:00Z")

    def test_media_type_is_detected_from_supported_raster_signatures(self) -> None:
        cases = (
            (b"\xff\xd8\xff\xe0jpeg-data", "image/jpeg", ".jpg"),
            (b"RIFF\x0c\x00\x00\x00WEBPwebp-data", "image/webp", ".webp"),
            (b"GIF89agif-data", "image/gif", ".gif"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (content, media_type, suffix) in enumerate(cases, start=1):
                with self.subTest(media_type=media_type):
                    source = root / f"upload-{index}.bin"
                    source.write_bytes(content)
                    run_root = root / f"run-{index}"

                    manifest = reference_sources.ingest_ephemeral_image(
                        source,
                        run_root,
                        run_id=f"run-{index}",
                        source_id=f"src-{index}",
                        kind="other",
                    )

                    record = manifest["sources"][0]
                    self.assertEqual(record["media_type"], media_type)
                    self.assertTrue(record["locator"].endswith(suffix))
                    self.assertEqual((run_root / record["locator"]).read_bytes(), content)

    def test_new_source_is_appended_to_the_complete_existing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run"
            first = root / "first.png"
            second = root / "second.png"
            first.write_bytes(PNG_BYTES + b"-first")
            second.write_bytes(PNG_BYTES + b"-second")
            initial = reference_sources.ingest_ephemeral_image(
                first,
                run_root,
                run_id="run",
                source_id="src-1",
                kind="screenshot",
                captured_at="2026-08-17T10:00:00+08:00",
            )
            initial["extension_field"] = {"preserve": True}
            (run_root / "reference" / "manifest.json").write_text(
                json.dumps(initial), encoding="utf-8"
            )

            manifest = reference_sources.ingest_ephemeral_image(
                second,
                run_root,
                run_id="run",
                source_id="src-2",
                kind="other",
                captured_at="2026-08-17T10:05:00+08:00",
            )

            self.assertEqual([source["id"] for source in manifest["sources"]], ["src-1", "src-2"])
            self.assertEqual(manifest["extension_field"], {"preserve": True})
            self.assertEqual(manifest["captured_at"], "2026-08-17T10:00:00+08:00")

    def test_legacy_v1_source_without_additive_fields_remains_appendable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run"
            reference_dir = run_root / "reference"
            reference_dir.mkdir(parents=True)
            legacy_source = {
                "id": "legacy",
                "kind": "product_analogy",
                "locator": "Existing product analogy",
                "sha256": None,
            }
            (reference_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "design-playbook.reference.manifest/v1",
                        "run_id": "run",
                        "captured_at": "2026-08-17T09:00:00Z",
                        "tool": "reference-intake",
                        "sources": [legacy_source],
                    }
                ),
                encoding="utf-8",
            )
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)

            manifest = reference_sources.ingest_ephemeral_image(
                source,
                run_root,
                run_id="run",
                source_id="new",
                kind="screenshot",
            )

            self.assertEqual(manifest["sources"][0], legacy_source)
            self.assertEqual(manifest["sources"][1]["storage"], "copied")

    def test_duplicate_source_id_is_rejected_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run"
            first = root / "first.png"
            duplicate = root / "duplicate.png"
            first.write_bytes(PNG_BYTES + b"-first")
            duplicate.write_bytes(PNG_BYTES + b"-duplicate")
            reference_sources.ingest_ephemeral_image(
                first,
                run_root,
                run_id="run",
                source_id="src-1",
                kind="screenshot",
            )
            assets = run_root / "reference" / "assets"
            before = sorted(path.name for path in assets.iterdir())

            with self.assertRaisesRegex(ValueError, "duplicate source id"):
                reference_sources.ingest_ephemeral_image(
                    duplicate,
                    run_root,
                    run_id="run",
                    source_id="src-1",
                    kind="screenshot",
                )

            self.assertEqual(sorted(path.name for path in assets.iterdir()), before)
            manifest = json.loads(
                (run_root / "reference" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["sources"]), 1)

    def test_invalid_source_metadata_is_rejected_before_copy(self) -> None:
        cases = (
            ({"kind": "image"}, "kind"),
            ({"kind": "other", "acquired_via": "clipboard"}, "acquired_via"),
            ({"kind": "other", "provider": "  "}, "provider"),
            ({"kind": "other", "provider": "host\nname"}, "provider"),
            ({"kind": "other", "captured_at": ""}, "captured_at"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)
            for index, (overrides, message) in enumerate(cases, start=1):
                with self.subTest(overrides=overrides):
                    run_root = root / f"run-{index}"
                    with self.assertRaisesRegex(ValueError, message):
                        reference_sources.ingest_ephemeral_image(
                            source,
                            run_root,
                            run_id=f"run-{index}",
                            source_id="src-1",
                            **overrides,
                        )
                    self.assertFalse((run_root / "reference").exists())

    def test_provider_cannot_persist_the_ephemeral_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "host-temp" / "clipboard.png"
            source.parent.mkdir()
            source.write_bytes(PNG_BYTES)
            run_root = root / "run"

            with self.assertRaisesRegex(
                reference_sources.ReferenceSourceError, "provider"
            ):
                reference_sources.ingest_ephemeral_image(
                    source,
                    run_root,
                    run_id="run",
                    source_id="src-1",
                    kind="screenshot",
                    provider=str(source),
                )

            self.assertFalse((run_root / "reference").exists())

    def test_invalid_source_files_fail_with_reference_source_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "directory"
            directory.mkdir()
            unsupported = root / "not-an-image.bin"
            unsupported.write_bytes(b"plain text")
            cases = (
                (root / "missing.png", "does not exist"),
                (directory, "regular file"),
                (unsupported, "unsupported image signature"),
            )

            for index, (source, message) in enumerate(cases, start=1):
                with self.subTest(source=source):
                    run_root = root / f"invalid-run-{index}"
                    with self.assertRaisesRegex(
                        reference_sources.ReferenceSourceError, message
                    ):
                        reference_sources.ingest_ephemeral_image(
                            source,
                            run_root,
                            run_id=f"invalid-run-{index}",
                            source_id="src-1",
                            kind="other",
                        )
                    self.assertFalse((run_root / "reference").exists())

    def test_run_and_source_ids_must_be_safe_non_empty_text(self) -> None:
        cases = (
            ("", "src-1", "run_id"),
            ("run-1", "../escape", "source_id"),
            ("run\n1", "src-1", "run_id"),
            ("run-1", "src\x001", "source_id"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)
            for index, (run_id, source_id, message) in enumerate(cases, start=1):
                with self.subTest(run_id=run_id, source_id=source_id):
                    with self.assertRaisesRegex(
                        reference_sources.ReferenceSourceError, message
                    ):
                        reference_sources.ingest_ephemeral_image(
                            source,
                            root / f"run-{index}",
                            run_id=run_id,
                            source_id=source_id,
                            kind="screenshot",
                        )

    def test_existing_manifest_shape_and_storage_are_validated_before_copy(self) -> None:
        valid_source = {
            "id": "existing",
            "kind": "url",
            "locator": "https://example.com/reference",
            "sha256": None,
            "storage": "remote",
        }
        base = {
            "schema": "design-playbook.reference.manifest/v1",
            "run_id": "run",
            "captured_at": "2026-08-17T10:00:00Z",
            "tool": "reference-intake",
            "sources": [valid_source],
        }
        cases = (
            ({**base, "schema": "unknown/v1"}, "schema"),
            ({**base, "run_id": "other-run"}, "run_id"),
            ({**base, "sources": {}}, "sources"),
            (
                {
                    **base,
                    "sources": [
                        {
                            "id": "existing",
                            "kind": "url",
                            "locator": "https://example.com/reference",
                        }
                    ],
                },
                "sha256",
            ),
            (
                {**base, "sources": [valid_source, dict(valid_source)]},
                "duplicate source id",
            ),
            (
                {
                    **base,
                    "sources": [{**valid_source, "storage": "temporary"}],
                },
                "storage",
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)
            for index, (manifest, message) in enumerate(cases, start=1):
                with self.subTest(message=message):
                    run_root = root / f"run-{index}"
                    reference_dir = run_root / "reference"
                    reference_dir.mkdir(parents=True)
                    (reference_dir / "manifest.json").write_text(
                        json.dumps(manifest), encoding="utf-8"
                    )

                    with self.assertRaisesRegex(
                        reference_sources.ReferenceSourceError, message
                    ):
                        reference_sources.ingest_ephemeral_image(
                            source,
                            run_root,
                            run_id="run",
                            source_id="new-source",
                            kind="screenshot",
                        )
                    self.assertFalse((reference_dir / "assets").exists())

    def test_captured_at_must_be_iso8601_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)

            with self.assertRaisesRegex(
                reference_sources.ReferenceSourceError, "captured_at"
            ):
                reference_sources.ingest_ephemeral_image(
                    source,
                    root / "run",
                    run_id="run",
                    source_id="src-1",
                    kind="screenshot",
                    captured_at="not-a-timestamp",
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_destination_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            source.write_bytes(PNG_BYTES)
            run_root = root / "run"
            reference_dir = run_root / "reference"
            reference_dir.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            try:
                os.symlink(outside, reference_dir / "assets", target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink creation unavailable")

            with self.assertRaisesRegex(
                reference_sources.ReferenceSourceError, "escapes run root"
            ):
                reference_sources.ingest_ephemeral_image(
                    source,
                    run_root,
                    run_id="run",
                    source_id="src-1",
                    kind="screenshot",
                )

            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
