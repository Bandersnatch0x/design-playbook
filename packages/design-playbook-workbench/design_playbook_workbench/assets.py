"""Read-only asset import, discovery, and immutable revisions (R03, R04).

An import never executes, installs, or fetches anything: it enumerates only
the paths the maintainer selected inside one registered project, reads the
bytes, stores them content-addressed, and then commits the asset draft in
one transaction. Capabilities are *declared from evidence we actually
have* -- a Markdown file is a reference, a static package can be previewed,
TypeScript source is unverified source -- and nothing is ever labelled
``runnable-verified`` or ``native-editable`` merely because of a file
extension. Publishing freezes the draft into an immutable revision.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .blobs import BlobStore, digest_bytes
from .errors import (
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    UNSUPPORTED,
    WorkbenchError,
)
from .paths import assert_contained
from .proposals import relative_parts
from .service import Operation, WorkbenchService, utc_now
from .store import Store

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 200 * 1024 * 1024
MAX_BATCH_FILES = 1000

CAPABILITY_REFERENCE = "reference"
CAPABILITY_STATIC_PREVIEW = "static-preview"
CAPABILITY_SOURCE_UNVERIFIED = "source-unverified"
CAPABILITY_RUNNABLE_VERIFIED = "runnable-verified"
CAPABILITY_NATIVE_EDITABLE = "native-editable"

IMPORTABLE_CAPABILITIES = (
    CAPABILITY_REFERENCE,
    CAPABILITY_STATIC_PREVIEW,
    CAPABILITY_SOURCE_UNVERIFIED,
)

VCS_COMPONENTS = frozenset({".git", ".hg", ".svn", ".bzr", "_darcs"})
DEPENDENCY_DIRS = frozenset(
    {
        "node_modules",
        "vendor",
        "venv",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "coverage",
    }
)
CREDENTIAL_NAMES = frozenset(
    {
        ".env",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        ".aws",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }
)
CREDENTIAL_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks", ".ppk")

TEXT_CARRIERS = frozenset({"markdown", "tokens", "static-package", "react-source"})

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}
TEXT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".ts": "text/typescript",
    ".tsx": "text/typescript",
    ".jsx": "text/javascript",
    ".txt": "text/plain",
    ".yml": "application/yaml",
    ".yaml": "application/yaml",
}

ARCHIVE_SUFFIXES = (".zip", ".tar", ".gz", ".7z", ".rar")

KIND_BY_CARRIER = {
    "markdown": "markdown",
    "tokens": "tokens",
    "static-package": "static-package",
    "react-source": "react-source",
    "image": "image",
    "run-artifact": "run-artifact",
    "binary": "binary",
}


def is_credential_name(name: str) -> bool:
    lowered = name.lower()
    if lowered in CREDENTIAL_NAMES or lowered.startswith(".env"):
        return True
    return lowered.endswith(CREDENTIAL_SUFFIXES)


def is_excluded_directory(name: str) -> bool:
    lowered = name.lower()
    return lowered in VCS_COMPONENTS or lowered in DEPENDENCY_DIRS


@dataclass(frozen=True)
class FileRecord:
    """One imported file: its project-relative path, bytes, and declared facts."""

    relative_path: str
    data: bytes
    size: int
    media_type: str
    carrier: str
    encoding: str
    content_hash: str


@dataclass
class ImportSelection:
    """One maintainer selection: a file or a directory inside the project."""

    relative_path: str
    explicit: bool = True


def classify(relative_path: str, data: bytes) -> tuple[str, str, str, list[str]]:
    """Return ``(carrier, media_type, encoding, capabilities)``.

    The rules are deliberately conservative: a capability is only declared
    when the evidence for it is present in this import.
    """
    suffix = Path(relative_path).suffix.lower()
    name = Path(relative_path).name.lower()
    lowered_path = relative_path.lower()
    if suffix in IMAGE_TYPES:
        return "image", IMAGE_TYPES[suffix], "binary", [CAPABILITY_REFERENCE]
    if suffix in ARCHIVE_SUFFIXES:
        # Archives are a backup format, not a general import: unpacking them
        # is out of scope, so they never become assets.
        raise WorkbenchError(UNSUPPORTED)
    if suffix not in TEXT_TYPES:
        return "binary", "application/octet-stream", "binary", [CAPABILITY_REFERENCE]
    try:
        data.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        # Unreadable as text: it stays a reference-only binary, never a
        # fabricated source or preview capability.
        return "binary", "application/octet-stream", "binary", [CAPABILITY_REFERENCE]
    if suffix in (".md", ".markdown") or name == "design.md":
        return "markdown", "text/markdown", encoding, [CAPABILITY_REFERENCE]
    if suffix == ".json":
        # A token set is recognised by its own name or by a tokens/themes
        # folder; anything else stays a run artifact reference.
        if "token" in lowered_path or "theme" in lowered_path:
            return "tokens", "application/json", encoding, [CAPABILITY_REFERENCE]
        return "run-artifact", "application/json", encoding, [CAPABILITY_REFERENCE]
    if suffix in (".tsx", ".ts", ".jsx"):
        return (
            "react-source",
            TEXT_TYPES[suffix],
            encoding,
            [CAPABILITY_REFERENCE, CAPABILITY_SOURCE_UNVERIFIED],
        )
    if suffix in (".html", ".htm"):
        return (
            "static-package",
            "text/html",
            encoding,
            [CAPABILITY_REFERENCE, CAPABILITY_STATIC_PREVIEW],
        )
    if suffix in (".css", ".js", ".mjs"):
        return "static-package", TEXT_TYPES[suffix], encoding, [CAPABILITY_REFERENCE]
    return "markdown", TEXT_TYPES[suffix], encoding, [CAPABILITY_REFERENCE]


def _media_type_for(relative_path: str) -> str:
    return TEXT_TYPES.get(
        Path(relative_path).suffix.lower(), "application/octet-stream"
    )


def _carrier_kind(records: list[FileRecord]) -> tuple[str, list[str]]:
    carriers = {record.carrier for record in records}
    capabilities: list[str] = []
    if any(record.carrier == "static-package" for record in records):
        capabilities.append(CAPABILITY_REFERENCE)
        if any(record.media_type == "text/html" for record in records):
            capabilities.append(CAPABILITY_STATIC_PREVIEW)
    if "react-source" in carriers:
        capabilities.extend([CAPABILITY_REFERENCE, CAPABILITY_SOURCE_UNVERIFIED])
    if not capabilities:
        capabilities = [CAPABILITY_REFERENCE]
    ordered: list[str] = []
    for capability in IMPORTABLE_CAPABILITIES:
        if capability in capabilities and capability not in ordered:
            ordered.append(capability)
    if len(carriers) == 1:
        carrier = next(iter(carriers))
    else:
        carrier = "static-package" if "static-package" in carriers else sorted(carriers)[0]
    return KIND_BY_CARRIER.get(carrier, "mixed"), ordered


class AssetService:
    """The one owner of asset import, discovery, and revision publication."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- enumeration ----------------------------------------------------

    def _root_of(self, project_id: str) -> Path:
        target = self.service.require_project(project_id, scope="read")
        return Path(target["canonicalPath"])

    def enumerate_selection(
        self, root: Path, selection: ImportSelection
    ) -> tuple[list[tuple[str, Path, bool]], list[str]]:
        """List the readable files under one selection.

        Returns ``(entries, warnings)`` where each entry is
        ``(relative_path, absolute_path, bypassed_exclusion)``. Credential
        files are never included: inside a directory they are skipped with
        a warning, and when named explicitly the whole import is refused.
        Default exclusions (VCS internals, dependency and cache folders)
        apply unless the maintainer's selection itself points inside one.
        """
        parts = relative_parts(selection.relative_path)
        start = root.joinpath(*parts)
        resolved = assert_contained(start, root)
        if not resolved.exists():
            raise WorkbenchError(INVALID_TARGET)
        within_exclusion = any(is_excluded_directory(part) for part in parts)
        entries: list[tuple[str, Path, bool]] = []
        warnings: list[str] = []
        candidates: list[Path] = []
        if resolved.is_file():
            candidates = [resolved]
        elif resolved.is_dir():
            for current, directories, files in os.walk(resolved):
                kept: list[str] = []
                for name in sorted(directories):
                    if is_excluded_directory(name) and not within_exclusion:
                        continue
                    kept.append(name)
                directories[:] = kept
                for name in sorted(files):
                    candidates.append(Path(current) / name)
        else:
            raise WorkbenchError(INVALID_TARGET)

        for candidate in candidates:
            relative = candidate.relative_to(root).as_posix()
            if is_credential_name(candidate.name):
                if resolved.is_file() and selection.explicit:
                    # A credential file named on purpose is refused: keys
                    # must never enter the reusable asset set.
                    raise WorkbenchError(INVALID_TARGET)
                warnings.append(f"跳过了凭证形状的文件：{candidate.name}")
                continue
            excluded = any(
                is_excluded_directory(part) for part in relative.split("/")[:-1]
            )
            if excluded and not within_exclusion:
                continue
            if excluded:
                warnings.append(f"读取了默认排除路径中的文件：{relative}")
            entries.append((relative, candidate, excluded))
        if not entries:
            raise WorkbenchError(INVALID_TARGET)
        if any(entry[2] for entry in entries):
            warnings.append(
                "本次导入包含默认排除项，内容未执行、未安装依赖，但请确认其中没有不该复用的私有材料。"
            )
        return entries, warnings

    # -- import ---------------------------------------------------------

    def import_selection(
        self, project_id: str, *, selections: object, operation: Operation
    ) -> dict:
        replayed = self.service._replay(operation, kind="asset-import", project_id=project_id)
        if replayed is not None:
            return replayed
        root = self._root_of(project_id)
        parsed = self._parse_selections(selections)
        records: list[FileRecord] = []
        warnings: list[str] = []
        seen_paths: set[str] = set()
        total_bytes = 0
        for selection in parsed:
            entries, selection_warnings = self.enumerate_selection(root, selection)
            warnings.extend(selection_warnings)
            for relative, absolute, _ in entries:
                if relative in seen_paths:
                    continue
                seen_paths.add(relative)
                if len(records) + 1 > MAX_BATCH_FILES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                try:
                    size = absolute.stat().st_size
                except OSError:
                    raise WorkbenchError(CORRUPT_CONTENT) from None
                if size > MAX_FILE_BYTES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                total_bytes += size
                if total_bytes > MAX_BATCH_BYTES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                try:
                    data = absolute.read_bytes()
                except OSError:
                    raise WorkbenchError(CORRUPT_CONTENT) from None
                carrier, media_type, encoding, _ = classify(relative, data)
                records.append(
                    FileRecord(
                        relative_path=relative,
                        data=data,
                        size=size,
                        media_type=media_type,
                        carrier=carrier,
                        encoding=encoding,
                        content_hash=digest_bytes(data),
                    )
                )
        if not records:
            raise WorkbenchError(INVALID_TARGET)

        # Blobs first: content must exist before anything references it.
        for record in records:
            self.blobs.put(record.data, expected_hash=record.content_hash)

        kind, capabilities = _carrier_kind(records)
        manifest = [
            {
                "path": record.relative_path,
                "contentHash": record.content_hash,
                "size": record.size,
                "mediaType": record.media_type,
                "carrier": record.carrier,
                "encoding": record.encoding,
            }
            for record in sorted(records, key=lambda item: item.relative_path)
        ]
        name = self._suggested_name(parsed, records)
        source_locators = [
            {
                "kind": "project-file",
                "projectId": project_id,
                "path": record.relative_path,
                "sourceHash": record.content_hash,
                "run": None,
                "objectType": "file",
                "objectId": record.relative_path,
            }
            for record in sorted(records, key=lambda item: item.relative_path)
        ]
        asset_id = str(uuid.uuid4())
        import_id = str(uuid.uuid4())
        now = self._now()
        attributes = {
            "manifest": manifest,
            "carrier": kind,
            "capabilities": capabilities,
            "roots": [selection.relative_path for selection in parsed],
            "warnings": sorted(set(warnings)),
            "dynamicPreviewEnabled": False,
        }

        def apply() -> dict:
            self.store.create_asset(
                asset_id=asset_id,
                project_id=project_id,
                kind=kind,
                name=name,
                tags=[],
                attributes=attributes,
                now=now,
            )
            self.store.create_import(
                import_id=import_id,
                project_id=project_id,
                roots=attributes["roots"],
                status="committed",
                file_count=len(manifest),
                total_bytes=total_bytes,
                warnings=sorted(set(warnings)),
                now=now,
            )
            for record in sorted(records, key=lambda item: item.relative_path):
                self.store.add_import_file(
                    import_id=import_id,
                    relative_path=record.relative_path,
                    content_hash=record.content_hash,
                    size=record.size,
                    media_type=record.media_type,
                    carrier=record.carrier,
                )
            return {
                "importId": import_id,
                "asset": self._asset_payload(
                    self.store.asset(asset_id), self.store.draft(asset_id), None
                ),
                "fileCount": len(manifest),
                "totalBytes": total_bytes,
                "warnings": sorted(set(warnings)),
                "sourceLocators": source_locators,
                "capabilities": capabilities,
            }

        with self.store.transaction():
            result = apply()
            self._record(
                operation=operation,
                kind="asset-import",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": None}

    def _parse_selections(self, raw: object) -> list[ImportSelection]:
        if not isinstance(raw, list) or not raw:
            raise WorkbenchError(INVALID_INPUT)
        selections: list[ImportSelection] = []
        for item in raw:
            if isinstance(item, str):
                selections.append(ImportSelection(relative_path=item))
            elif isinstance(item, dict):
                path = item.get("path")
                relative_parts(path)
                selections.append(
                    ImportSelection(
                        relative_path=str(path).replace("\\", "/"),
                        explicit=bool(item.get("explicit", True)),
                    )
                )
            else:
                raise WorkbenchError(INVALID_INPUT)
        return selections

    def _suggested_name(self, selections: list[ImportSelection], records: list[FileRecord]) -> str:
        if len(selections) == 1:
            first = selections[0].relative_path
            name = Path(first).name or Path(first).parent.name
            if name.lower() in ("", ".", "/"):
                name = "asset"
            return name[:120]
        common = os.path.commonpath([record.relative_path for record in records])
        base = Path(common).name if common else "import"
        return (base or "import")[:120]

    # -- discovery ------------------------------------------------------

    def list_assets(
        self,
        project_id: str,
        *,
        query: object = None,
        kind: object = None,
        capability: object = None,
        lifecycle: object = None,
    ) -> dict:
        self.service.require_project(project_id, scope="read")
        text = query.strip().lower() if isinstance(query, str) else ""
        items: list[dict] = []
        for row in self.store.project_assets(project_id):
            asset_id = row["asset_id"]
            draft = self.store.draft(asset_id)
            attributes = _loads(draft["attributes_json"]) if draft else {}
            capabilities = attributes.get("capabilities", [])
            tags = _loads(draft["tags_json"]) if draft else []
            if kind and row["kind"] != kind:
                continue
            if capability and capability not in capabilities:
                continue
            if lifecycle and row["lifecycle"] != lifecycle:
                continue
            matched_on: str | None = None
            rank = 0
            if text:
                name = row["name"].lower()
                if name.startswith(text):
                    matched_on, rank = "name", 0
                elif text in name:
                    matched_on, rank = "name", 1
                else:
                    hit = next(
                        (tag for tag in tags if text in str(tag).lower()), None
                    )
                    if hit is None:
                        continue
                    matched_on, rank = "tag", 2
            items.append(
                {
                    "assetId": asset_id,
                    "name": row["name"],
                    "kind": row["kind"],
                    "lifecycle": row["lifecycle"],
                    "capabilities": capabilities,
                    "tags": tags,
                    "updatedAt": row["updated_at"],
                    "matchedOn": matched_on,
                    "rank": rank,
                }
            )
        items.sort(
            key=lambda item: (
                item["rank"],
                _time_key(item["updatedAt"]),
                item["assetId"],
            )
        )
        for item in items:
            item.pop("rank", None)
        return {"assets": items}

    def asset_detail(self, project_id: str, asset_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        draft = self.store.draft(asset_id)
        revision = self.store.latest_revision(asset_id)
        payload = self._asset_payload(row, draft, revision)
        payload["revisions"] = [
            {
                "revisionId": item["revision_id"],
                "revisionNumber": item["revision_number"],
                "capabilities": _loads(item["capabilities_json"]),
                "createdAt": item["created_at"],
            }
            for item in self.store.asset_revisions(asset_id)
        ]
        payload["sourceLocators"] = _loads(
            revision["source_locators_json"] if revision else "[]"
        ) or _draft_locators(draft, project_id)
        return {"asset": payload}

    def _asset_payload(self, row: dict, draft: dict | None, revision: dict | None) -> dict:
        attributes = _loads(draft["attributes_json"]) if draft else {}
        return {
            "assetId": row["asset_id"],
            "projectId": row["project_id"],
            "name": row["name"],
            "kind": row["kind"],
            "lifecycle": row["lifecycle"],
            "counter": int(row["counter"]),
            "tags": _loads(draft["tags_json"]) if draft else [],
            "capabilities": attributes.get("capabilities", []),
            "manifest": attributes.get("manifest", []),
            "roots": attributes.get("roots", []),
            "warnings": attributes.get("warnings", []),
            "dynamicPreviewEnabled": bool(attributes.get("dynamicPreviewEnabled")),
            "revisionNumber": int(revision["revision_number"]) if revision else None,
            "revisionId": revision["revision_id"] if revision else None,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    # -- preview --------------------------------------------------------

    def preview_descriptor(
        self, project_id: str, asset_id: str, *, preview_origin: str
    ) -> dict:
        payload = self.asset_detail(project_id, asset_id)["asset"]
        entry = self._preview_entry(payload)
        capabilities = payload["capabilities"]
        static_url = f"{preview_origin}/p/{entry['contentHash']}/static"
        dynamic_url = (
            f"{preview_origin}/p/{entry['contentHash']}/dynamic"
            if payload["dynamicPreviewEnabled"]
            else None
        )
        return {
            "assetId": asset_id,
            "entry": entry["path"],
            "mediaType": entry["mediaType"],
            "previewOrigin": preview_origin,
            "staticUrl": static_url,
            "dynamicUrl": dynamic_url,
            "dynamicAvailable": CAPABILITY_STATIC_PREVIEW in capabilities,
            "sandbox": "allow-scripts" if dynamic_url else "",
            "policy": {
                "scripts": "enabled" if dynamic_url else "disabled",
                "network": "blocked",
                "managementApi": "blocked",
                "sessionCredential": "absent",
            },
            "notes": (
                "静态预览不执行脚本；动态预览需显式启用，且运行在独立回环来源，"
                "不携带会话凭证、不能访问管理 API 或外网。"
            ),
        }

    def _preview_entry(self, payload: dict) -> dict:
        manifest = payload.get("manifest") or []
        for entry in manifest:
            if entry.get("mediaType") == "text/html":
                return entry
        for entry in manifest:
            if str(entry.get("mediaType", "")).startswith("image/"):
                return entry
        for entry in manifest:
            if str(entry.get("mediaType", "")).startswith("text/"):
                return entry
        if not manifest:
            raise WorkbenchError(MISSING_DEPENDENCY)
        return manifest[0]

    def enable_dynamic_preview(
        self, project_id: str, asset_id: str, *, operation: Operation
    ) -> dict:
        replayed = self.service._replay(
            operation, kind="asset-preview-enable", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        draft = self.store.draft(asset_id)
        attributes = _loads(draft["attributes_json"])
        if CAPABILITY_STATIC_PREVIEW not in attributes.get("capabilities", []):
            raise WorkbenchError(MISSING_DEPENDENCY)
        attributes["dynamicPreviewEnabled"] = True
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.update_draft(
                asset_id=asset_id,
                tags=_loads(draft["tags_json"]),
                attributes=attributes,
                now=now,
            )
            counter = self.store.bump_asset_counter(asset_id=asset_id, now=now)
            return (
                self._asset_payload(
                    self.store.asset(asset_id), self.store.draft(asset_id), None
                ),
                counter,
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="asset-preview-enable",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def refresh_draft(
        self, project_id: str, asset_id: str, *, operation: Operation
    ) -> dict:
        """Re-read this asset's recorded sources into its draft, explicitly.

        Content is a snapshot: publishing never re-reads the project behind
        the maintainer's back, and the repository is never the authority for
        what an asset contains. Bringing changed source files in is therefore
        its own explicit step, with the same limits and exclusions as import.
        """
        replayed = self.service._replay(
            operation, kind="asset-refresh-draft", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        root = self._root_of(project_id)
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        draft = self.store.draft(asset_id)
        attributes = _loads(draft["attributes_json"])
        roots = attributes.get("roots") or []
        if not roots:
            raise WorkbenchError(MISSING_DEPENDENCY)
        records: list[FileRecord] = []
        warnings: list[str] = []
        total_bytes = 0
        for raw in roots:
            selection = ImportSelection(
                relative_path=str(raw).replace("\\", "/")
            )
            entries, selection_warnings = self.enumerate_selection(root, selection)
            warnings.extend(selection_warnings)
            for relative, absolute, _ in entries:
                if any(record.relative_path == relative for record in records):
                    continue
                try:
                    size = absolute.stat().st_size
                except OSError:
                    raise WorkbenchError(CORRUPT_CONTENT) from None
                if size > MAX_FILE_BYTES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                total_bytes += size
                if total_bytes > MAX_BATCH_BYTES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                if len(records) + 1 > MAX_BATCH_FILES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
                try:
                    data = absolute.read_bytes()
                except OSError:
                    raise WorkbenchError(CORRUPT_CONTENT) from None
                carrier, media_type, encoding, _ = classify(relative, data)
                records.append(
                    FileRecord(
                        relative_path=relative,
                        data=data,
                        size=size,
                        media_type=media_type,
                        carrier=carrier,
                        encoding=encoding,
                        content_hash=digest_bytes(data),
                    )
                )
        if not records:
            raise WorkbenchError(MISSING_DEPENDENCY)
        for record in records:
            self.blobs.put(record.data, expected_hash=record.content_hash)
        kind, capabilities = _carrier_kind(records)
        manifest = [
            {
                "path": record.relative_path,
                "contentHash": record.content_hash,
                "size": record.size,
                "mediaType": record.media_type,
                "carrier": record.carrier,
                "encoding": record.encoding,
            }
            for record in sorted(records, key=lambda item: item.relative_path)
        ]
        refreshed = dict(attributes)
        refreshed["manifest"] = manifest
        refreshed["carrier"] = kind
        refreshed["capabilities"] = capabilities
        refreshed["warnings"] = sorted(set(warnings))
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.update_draft(
                asset_id=asset_id,
                tags=_loads(draft["tags_json"]),
                attributes=refreshed,
                now=now,
            )
            counter = self.store.bump_asset_counter(asset_id=asset_id, now=now)
            return (
                self._asset_payload(
                    self.store.asset(asset_id), self.store.draft(asset_id), None
                ),
                counter,
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="asset-refresh-draft",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- publish --------------------------------------------------------

    def publish_revision(
        self,
        project_id: str,
        asset_id: str,
        *,
        operation: Operation,
        verified_by: dict | None = None,
    ) -> dict:
        """Publish a revision.

        A capability like ``runnable-verified`` still needs a verification
        record; ``verified_by`` is the owner confirmation bound to the exact
        content hash being published, and nothing else is accepted as proof.
        """
        replayed = self.service._replay(
            operation, kind="asset-publish", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        draft = self.store.draft(asset_id)
        attributes = _loads(draft["attributes_json"])
        manifest = attributes.get("manifest") or []
        if not manifest:
            raise WorkbenchError(MISSING_DEPENDENCY)
        for entry in manifest:
            # Publishing validates content completeness: every declared blob
            # must still be present and readable.
            if not self.blobs.verify(entry["contentHash"]):
                raise WorkbenchError(CORRUPT_CONTENT)
        capabilities = list(attributes.get("capabilities", []))
        verified: list[dict] = []
        if CAPABILITY_RUNNABLE_VERIFIED in capabilities or (
            CAPABILITY_NATIVE_EDITABLE in capabilities
        ):
            # A revision cannot claim a verified capability without a
            # verification record bound to revision, environment, and hash.
            if verified_by is None:
                raise WorkbenchError(MISSING_DEPENDENCY)
            if (
                not isinstance(verified_by, dict)
                or verified_by.get("sourceHash") != manifest[0]["contentHash"]
                or not verified_by.get("confirmationId")
                or not verified_by.get("role")
            ):
                raise WorkbenchError(MISSING_DEPENDENCY)
            verified = [dict(verified_by)]
        revision_number = int(draft["revision_counter"]) + 1
        revision_id = str(uuid.uuid4())
        now = self._now()
        locators = _draft_locators(draft, project_id)

        def apply() -> tuple[dict, int]:
            self.store.insert_revision(
                revision_id=revision_id,
                asset_id=asset_id,
                revision_number=revision_number,
                content_hash=manifest[0]["contentHash"],
                carrier=attributes.get("carrier", row["kind"]),
                capabilities=capabilities,
                dependencies=[],
                source_locators=locators,
                manifest=manifest,
                origin={"kind": "import", "importRoots": attributes.get("roots", [])},
                verified=verified,
                now=now,
            )
            asset = self.store.asset(asset_id)
            return (
                self._asset_payload(asset, self.store.draft(asset_id), self.store.latest_revision(asset_id)),
                int(asset["counter"]),
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="asset-publish",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- mutation plumbing ----------------------------------------------

    def _record(
        self,
        *,
        operation: Operation,
        kind: str,
        entity_id: str,
        project_id: str | None,
        result: dict,
    ) -> None:
        import json as _json_module

        self.store.record_mutation(
            operation_id=operation.operation_id,
            entity_kind=kind,
            entity_id=entity_id,
            payload_digest=operation.digest,
            resulting_counter=None,
            result_json=_json_module.dumps(
                result, separators=(",", ":"), sort_keys=True, ensure_ascii=False
            ),
            project_id=project_id,
            now=self._now(),
        )


def _loads(text: object) -> object:
    import json as _json_module

    if isinstance(text, (list, dict)):
        return text
    if not isinstance(text, str) or not text:
        return []
    try:
        return _json_module.loads(text)
    except _json_module.JSONDecodeError:  # pragma: no cover - stored by us
        return []


def _time_key(value: object) -> tuple[int, ...]:
    """Newest first: negated numeric components of an ISO-8601 timestamp."""
    if not isinstance(value, str):
        return (0,)
    digits = "".join(character if character.isdigit() else " " for character in value).split()
    parts: list[int] = []
    for chunk in digits[:6]:
        try:
            parts.append(-int(chunk))
        except ValueError:  # pragma: no cover - defensive
            parts.append(0)
    while len(parts) < 6:
        parts.append(0)
    return tuple(parts)


def _draft_locators(draft: dict, project_id: str) -> list[dict]:
    if draft is None:
        return []
    attributes = _loads(draft["attributes_json"])
    if "sourceLocators" in attributes:
        # A workbench-owned document (component definition, layout tree)
        # carries typed locators instead of pretending to be a project file;
        # an explicit empty list means "no project source".
        recorded = attributes["sourceLocators"]
        return recorded if isinstance(recorded, list) else []
    locators = []
    for entry in attributes.get("manifest", []):
        locators.append(
            {
                "kind": "project-file",
                "projectId": project_id,
                "path": entry["path"],
                "sourceHash": entry["contentHash"],
                "run": None,
                "objectType": "file",
                "objectId": entry["path"],
            }
        )
    return locators
