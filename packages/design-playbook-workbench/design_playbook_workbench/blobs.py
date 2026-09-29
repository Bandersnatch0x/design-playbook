"""Content-addressed blob storage for imported carriers (R03, R14).

Bytes are the authority: a blob is written and hash-verified *before* any
directory transaction references it, so a failed import can leave an
unreferenced blob (reported, never silently deleted) but never a record
pointing at content that is missing. Content is addressed by SHA-256 and
stored under a two-level fan-out directory; writing the same bytes twice
is the same blob.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CORRUPT_CONTENT, WorkbenchError

HASH_PREFIX = "sha256:"
MAX_BLOB_BYTES = 20 * 1024 * 1024


def digest_bytes(data: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def _hex(hash_value: str) -> str:
    if not isinstance(hash_value, str) or not hash_value.startswith(HASH_PREFIX):
        raise WorkbenchError(CORRUPT_CONTENT)
    body = hash_value[len(HASH_PREFIX) :]
    if len(body) != 64 or any(character not in "0123456789abcdef" for character in body):
        raise WorkbenchError(CORRUPT_CONTENT)
    return body


@dataclass(frozen=True)
class BlobRecord:
    content_hash: str
    size: int


class BlobStore:
    """The one writer/reader of immutable content."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, content_hash: str) -> Path:
        body = _hex(content_hash)
        return self.root / body[:2] / body[2:]

    def exists(self, content_hash: str) -> bool:
        try:
            return self.path_for(content_hash).is_file()
        except WorkbenchError:
            return False

    def put(self, data: bytes, *, expected_hash: str | None = None) -> BlobRecord:
        """Write bytes atomically and verify the resulting hash."""
        if not isinstance(data, bytes):  # pragma: no cover - defensive
            raise WorkbenchError(CORRUPT_CONTENT)
        if len(data) > MAX_BLOB_BYTES:
            raise WorkbenchError("limit-exceeded")
        content_hash = digest_bytes(data)
        if expected_hash is not None and expected_hash != content_hash:
            raise WorkbenchError(CORRUPT_CONTENT)
        target = self.path_for(content_hash)
        if target.is_file():
            if self.read(content_hash) != data:
                raise WorkbenchError(CORRUPT_CONTENT)
            return BlobRecord(content_hash=content_hash, size=len(data))
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            dir=str(target.parent), prefix=".blob-", delete=False
        )
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            os.replace(handle.name, target)
        except BaseException:
            handle.close()
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise
        return BlobRecord(content_hash=content_hash, size=len(data))

    def read(self, content_hash: str) -> bytes:
        target = self.path_for(content_hash)
        try:
            data = target.read_bytes()
        except OSError:
            raise WorkbenchError(CORRUPT_CONTENT) from None
        if digest_bytes(data) != content_hash:
            # Content that does not match its address is corruption, never
            # something to serve or to repair silently.
            raise WorkbenchError(CORRUPT_CONTENT)
        return data

    def verify(self, content_hash: str) -> bool:
        try:
            self.read(content_hash)
        except WorkbenchError:
            return False
        return True

    def iter_hashes(self):
        for directory in sorted(self.root.iterdir()) if self.root.is_dir() else []:
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                if entry.is_file() and not entry.name.startswith(".blob-"):
                    yield HASH_PREFIX + directory.name + entry.name

    def unreferenced(self, referenced: set[str]) -> list[str]:
        """Blobs nothing points at: reported for explicit maintenance only."""
        return sorted(
            content_hash
            for content_hash in self.iter_hashes()
            if content_hash not in referenced
        )
