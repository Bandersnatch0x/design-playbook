"""Source change proposals and recoverable, authorized application (R06).

A proposal is staged outside every project directory, binds one digest
over the target binding, the file operations, the baseline hashes, and
the resulting hashes, and is applied only after the maintainer confirms
that digest: changing one byte of the proposal invalidates the
authorization. Application re-verifies the binding, the grant, every
path, and every precondition; then it writes each file through a
same-volume temporary file and records progress in a persisted journal,
because a multi-file operating-system write is not atomic. A failure
mid-commit reports ``recovery-required``, blocks further writes to that
project, and leaves recovery as an explicit, hash-checked decision --
never a silent rollback over the maintainer's own edits.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    RECOVERY_REQUIRED,
    WorkbenchError,
)
from .paths import assert_contained
from .service import Operation, WorkbenchService
from .store import Store, WorkbenchDataDirectory

PROPOSAL_TTL_SECONDS = 30 * 60
MAX_CHANGES = 50
MAX_CONTENT_BYTES = 1024 * 1024

FILE_OPERATIONS = frozenset({"create", "update", "delete"})

VCS_COMPONENTS = frozenset({".git", ".hg", ".svn", ".bzr", "_darcs"})
SENSITIVE_NAMES = frozenset(
    {
        ".env",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }
)
SENSITIVE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")

RECEIPT_APPLIED = "applied"
JOURNAL_WRITING = "writing"
JOURNAL_COMMITTED = "committed"
JOURNAL_RECOVERY = "recovery-required"
JOURNAL_ROLLED_BACK = "rolled-back"

STATE_AWAITING = "awaiting-authorization"
STATE_APPLIED = "applied"
STATE_REJECTED = "rejected"
STATE_EXPIRED = "expired"
STATE_RECOVERY = "recovery-required"
STATE_ROLLED_BACK = "rolled-back"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class ChangeSpec:
    """One validated file operation inside a project."""

    path: str
    operation: str
    content: bytes | None
    base_hash: str | None


def relative_parts(raw: object) -> list[str]:
    """Split and validate one project-relative path."""
    if not isinstance(raw, str) or not raw.strip():
        raise WorkbenchError(INVALID_INPUT)
    text = raw.strip().replace("\\", "/")
    if text.startswith("/") or _DRIVE_PATTERN.match(text) or "://" in text:
        raise WorkbenchError(INVALID_TARGET)
    parts = text.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise WorkbenchError(INVALID_TARGET)
        if ":" in part or "\x00" in part:
            raise WorkbenchError(INVALID_TARGET)
    return parts


def _reject_sensitive(parts: list[str]) -> None:
    """Refuse VCS internals and credential-shaped files (R03/R06)."""
    for part in parts[:-1]:
        if part.lower() in VCS_COMPONENTS:
            raise WorkbenchError(INVALID_TARGET)
    name = parts[-1].lower()
    if name in SENSITIVE_NAMES or name.startswith(".env"):
        raise WorkbenchError(INVALID_TARGET)
    if name.endswith(SENSITIVE_SUFFIXES):
        raise WorkbenchError(INVALID_TARGET)


def _atomic_replace(path: Path, data: bytes) -> None:
    """Replace one file through a same-volume temporary file.

    ``os.replace`` is atomic per file on one volume; that is exactly why
    the journal exists -- the set of files is not.
    """
    directory = path.parent
    previous_mode: int | None = None
    if path.exists():
        previous_mode = path.stat().st_mode
    handle = tempfile.NamedTemporaryFile(
        dir=str(directory), prefix=f".{path.name}.wb-", delete=False
    )
    try:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        if previous_mode is not None:
            os.chmod(handle.name, previous_mode)
        os.replace(handle.name, path)
    except BaseException:
        handle.close()
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def _current_hash(path: Path) -> str | None:
    """The file's content hash, ``None`` when it does not exist."""
    try:
        if not path.is_file():
            return None
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _unified_diff(path: str, before: bytes | None, after: bytes | None) -> str:
    def lines(data: bytes | None) -> list[str]:
        if data is None:
            return []
        return data.decode("utf-8", "replace").splitlines(keepends=True)

    return "".join(
        difflib.unified_diff(
            lines(before),
            lines(after),
            fromfile=f"a/{path}" if before is not None else "/dev/null",
            tofile=f"b/{path}" if after is not None else "/dev/null",
        )
    )


class ProposalService:
    """The one owner of proposal staging and project source writes."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        data_dir: WorkbenchDataDirectory,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.data_dir = data_dir
        self._now = now_fn if now_fn is not None else _utc_now
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    # -- helpers --------------------------------------------------------

    def _now_iso(self) -> str:
        return _iso(self._now())

    def _project_lock(self, project_id: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._locks.get(project_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[project_id] = lock
            return lock

    def _staging_dir(self, proposal_id: str) -> Path:
        directory = self.data_dir.staging_dir / proposal_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _resolve(self, root: Path, raw: object) -> tuple[str, Path]:
        """One validated project-relative path resolved inside the project."""
        parts = relative_parts(raw)
        _reject_sensitive(parts)
        relative = "/".join(parts)
        candidate = root.joinpath(*parts)
        # The parent must exist and stay inside the project even when a
        # junction or symlink inside the project points elsewhere.
        assert_contained(candidate.parent, root)
        resolved = assert_contained(candidate, root)
        if resolved.is_dir():
            raise WorkbenchError(INVALID_TARGET)
        return relative, resolved

    def _block_incomplete(self, project_id: str) -> None:
        journal = self.store.incomplete_journal(project_id)
        if journal is None:
            return
        # An unfinished or unrecovered write blocks every new project write
        # until the maintainer resolves it explicitly.
        raise WorkbenchError(RECOVERY_REQUIRED)

    def _record(
        self,
        *,
        operation: Operation,
        kind: str,
        entity_id: str,
        project_id: str | None,
        result: dict,
    ) -> None:
        self.store.record_mutation(
            operation_id=operation.operation_id,
            entity_kind=kind,
            entity_id=entity_id,
            payload_digest=operation.digest,
            resulting_counter=None,
            result_json=_canonical_json(result),
            project_id=project_id,
            now=self._now_iso(),
        )

    # -- proposal creation ---------------------------------------------

    def _parse_changes(self, raw: object) -> list[ChangeSpec]:
        if not isinstance(raw, list) or not raw:
            raise WorkbenchError(INVALID_INPUT)
        if len(raw) > MAX_CHANGES:
            raise WorkbenchError(LIMIT_EXCEEDED)
        specs: list[ChangeSpec] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise WorkbenchError(INVALID_INPUT)
            operation = item.get("operation")
            if operation not in FILE_OPERATIONS:
                raise WorkbenchError(INVALID_INPUT)
            parts = relative_parts(item.get("path"))
            _reject_sensitive(parts)
            path = "/".join(parts)
            if path in seen:
                raise WorkbenchError(INVALID_INPUT)
            seen.add(path)
            base_hash = item.get("baseHash")
            if base_hash is not None and not (
                isinstance(base_hash, str) and base_hash.startswith("sha256:")
            ):
                raise WorkbenchError(INVALID_INPUT)
            content: bytes | None = None
            if operation in ("create", "update"):
                text = item.get("content")
                if not isinstance(text, str):
                    raise WorkbenchError(INVALID_INPUT)
                # surrogateescape keeps the round trip lossless for content
                # that is not valid UTF-8 (reverts restore exact bytes).
                content = text.encode("utf-8", "surrogateescape")
                if len(content) > MAX_CONTENT_BYTES:
                    raise WorkbenchError(LIMIT_EXCEEDED)
            else:
                if item.get("content") not in (None, ""):
                    raise WorkbenchError(INVALID_INPUT)
                if base_hash is None:
                    raise WorkbenchError(INVALID_INPUT)
            if operation in ("update", "delete") and base_hash is None:
                raise WorkbenchError(INVALID_INPUT)
            specs.append(
                ChangeSpec(
                    path=path,
                    operation=operation,
                    content=content,
                    base_hash=base_hash,
                )
            )
        return specs

    def create(
        self,
        project_id: str,
        *,
        changes: object,
        operation: Operation,
        summary: object = None,
        dependency_changes: object = None,
        source_request: object = None,
    ) -> dict:
        replayed = self.service._replay(operation, kind="proposal-create", project_id=project_id)
        if replayed is not None:
            return replayed
        target = self.service.require_project(project_id, scope="write")
        self._block_incomplete(project_id)
        specs = self._parse_changes(changes)
        if summary is not None and not isinstance(summary, str):
            raise WorkbenchError(INVALID_INPUT)
        if dependency_changes is None:
            dependency_changes = []
        if not isinstance(dependency_changes, list):
            raise WorkbenchError(INVALID_INPUT, detail="dependencyChanges must be a list")
        if source_request is not None:
            if not isinstance(source_request, str):
                raise WorkbenchError(INVALID_INPUT, detail="sourceRequest must be a request id")
            request = self.store.work_request(source_request)
            if request is None or request["project_id"] != project_id:
                raise WorkbenchError(INVALID_TARGET, detail="sourceRequest belongs to another project")
        root = Path(target["canonicalPath"])

        entries: list[dict] = []
        for spec in specs:
            relative, resolved = self._resolve(root, spec.path)
            current = _current_hash(resolved)
            if spec.operation == "create":
                if current is not None:
                    # A new file must be new: an existing file is a change
                    # of the maintainer's content, not a creation.
                    raise WorkbenchError(CONFLICT)
                result_hash = sha256_bytes(spec.content or b"")
            else:
                if current is None:
                    raise WorkbenchError(CONFLICT)
                if current != spec.base_hash:
                    raise WorkbenchError(CONFLICT)
                result_hash = (
                    None if spec.operation == "delete" else sha256_bytes(spec.content or b"")
                )
            entries.append(
                {
                    "path": relative,
                    "operation": spec.operation,
                    "baseHash": spec.base_hash if spec.operation != "create" else None,
                    "resultHash": result_hash,
                    "diff": _unified_diff(
                        relative,
                        None if spec.operation == "create" else _read_bytes(resolved),
                        None if spec.operation == "delete" else spec.content,
                    ),
                }
            )

        proposal_id = str(uuid.uuid4())
        staging = self._staging_dir(proposal_id)
        for index, spec in enumerate(specs):
            if spec.operation in ("create", "update"):
                (staging / f"{index:03d}.content").write_bytes(spec.content or b"")
            else:
                (staging / f"{index:03d}.content").write_bytes(b"")
            if spec.operation in ("update", "delete"):
                _, resolved = self._resolve(root, spec.path)
                (staging / f"{index:03d}.backup").write_bytes(_read_bytes(resolved))

        now = self._now()
        expires_at = _iso(now + timedelta(seconds=PROPOSAL_TTL_SECONDS))
        payload = {
            "proposalId": proposal_id,
            "projectId": project_id,
            "state": STATE_AWAITING,
            "summary": summary or "",
            "target": {
                "projectId": project_id,
                "bindingGeneration": target["bindingGeneration"],
                "directoryIdentity": target["directoryIdentity"],
                "canonicalPath": target["canonicalPath"],
            },
            "changes": entries,
            "dependencyChanges": dependency_changes,
            "sourceRequest": source_request,
            "createdAt": _iso(now),
            "expiresAt": expires_at,
            "stagingReference": f"staging/{proposal_id}",
        }
        digest = self._proposal_digest(payload)
        payload["digest"] = digest
        with self.store.transaction():
            self.store.create_proposal(
                proposal_id=proposal_id,
                project_id=project_id,
                binding_generation=target["bindingGeneration"],
                digest=digest,
                payload_json=_canonical_json(payload),
                staging_dir=str(staging),
                expires_at=expires_at,
                now=_iso(now),
            )
            self._record(
                operation=operation,
                kind="proposal-create",
                entity_id=proposal_id,
                project_id=project_id,
                result=payload,
            )
        return {"result": payload, "replayed": False, "counter": None}

    # -- reads ---------------------------------------------------------

    def detail(self, project_id: str, proposal_id: str) -> dict:
        row = self._require_proposal(project_id, proposal_id)
        payload = json.loads(row["payload_json"])
        payload["state"] = self._effective_state(row)
        journal = self.store.journal(proposal_id)
        payload["journalState"] = journal["state"] if journal is not None else None
        return {"proposal": payload}

    def list_for_project(self, project_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        items = []
        for row in self.store.project_proposals(project_id):
            payload = json.loads(row["payload_json"])
            payload["state"] = self._effective_state(row)
            items.append(
                {
                    "proposalId": payload["proposalId"],
                    "digest": payload["digest"],
                    "summary": payload["summary"],
                    "state": payload["state"],
                    "createdAt": payload["createdAt"],
                    "expiresAt": payload["expiresAt"],
                    "changeCount": len(payload["changes"]),
                }
            )
        return {"proposals": items}

    def _effective_state(self, row: dict) -> str:
        journal = self.store.journal(row["proposal_id"])
        if journal is not None and journal["state"] in (
            JOURNAL_WRITING,
            JOURNAL_RECOVERY,
        ):
            # A partial write is the most important thing to show: the
            # proposal is neither applied nor safely discarded.
            return STATE_RECOVERY
        if row["state"] == STATE_AWAITING and _parse_iso(row["expires_at"]) <= self._now():
            return STATE_EXPIRED
        return row["state"]

    @staticmethod
    def _proposal_digest(payload: dict) -> str:
        target = payload["target"]
        source = {
            "projectId": payload["projectId"],
            "bindingGeneration": target["bindingGeneration"],
            "directoryIdentity": target["directoryIdentity"],
            "changes": [
                {key: entry[key] for key in ("path", "operation", "baseHash", "resultHash")}
                for entry in payload["changes"]
            ],
            "dependencyChanges": payload["dependencyChanges"],
        }
        # Existing non-task proposals keep their digest; task provenance is bound.
        if payload.get("sourceRequest") is not None:
            source["sourceRequest"] = payload["sourceRequest"]
        return sha256_bytes(_canonical_json(source).encode("utf-8"))

    def _require_proposal(self, project_id: str, proposal_id: object) -> dict:
        if not isinstance(proposal_id, str) or not proposal_id:
            raise WorkbenchError(INVALID_TARGET)
        row = self.store.proposal(proposal_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        payload = json.loads(row["payload_json"])
        if self._proposal_digest(payload) != row["digest"]:
            raise WorkbenchError(CORRUPT_CONTENT, detail="proposal metadata no longer matches its digest")
        return row

    # -- apply ---------------------------------------------------------

    def _missing_parents(self, root: Path, relative: str) -> list[str]:
        """The ancestor directories of one path that do not exist yet.

        Creating a file in a new folder is part of the same operation, so
        the folders are planned here and removed again on rollback; the
        plan is what makes that reversible.
        """
        parts = relative.split("/")[:-1]
        missing: list[str] = []
        current = root
        for part in parts:
            current = current / part
            if not current.exists():
                missing.append(str(current.relative_to(root)).replace(os.sep, "/"))
        return missing

    def _plan(self, row: dict, target: dict, payload: dict) -> list[dict]:
        """Re-verify every precondition and build the ordered write plan."""
        if int(row["binding_generation"]) != int(target["bindingGeneration"]):
            raise WorkbenchError(CONFLICT)
        if payload["target"]["directoryIdentity"] != target["directoryIdentity"]:
            raise WorkbenchError(CONFLICT)
        root = Path(target["canonicalPath"])
        staging = Path(row["staging_dir"])
        plan: list[dict] = []
        for index, entry in enumerate(payload["changes"]):
            _, resolved = self._resolve(root, entry["path"])
            current = _current_hash(resolved)
            if entry["operation"] == "create":
                if current is not None:
                    raise WorkbenchError(CONFLICT)
            else:
                if current is None or current != entry["baseHash"]:
                    raise WorkbenchError(CONFLICT)
            content_file = staging / f"{index:03d}.content"
            backup_file = staging / f"{index:03d}.backup"
            step = {
                "ordinal": index,
                "path": entry["path"],
                "operation": entry["operation"],
                "baseHash": entry["baseHash"],
                "resultHash": entry["resultHash"],
                "contentFile": str(content_file) if entry["operation"] != "delete" else None,
                "backupFile": str(backup_file) if entry["operation"] != "create" else None,
            }
            if step["contentFile"] is not None:
                if not content_file.is_file():
                    raise WorkbenchError(CORRUPT_CONTENT)
                if sha256_bytes(content_file.read_bytes()) != entry["resultHash"]:
                    raise WorkbenchError(CORRUPT_CONTENT)
            if step["backupFile"] is not None and not backup_file.is_file():
                raise WorkbenchError(CORRUPT_CONTENT)
            plan.append(
                {
                    **step,
                    "createDirs": self._missing_parents(root, entry["path"])
                    if entry["operation"] in ("create", "update")
                    else [],
                }
            )
        return plan

    def _write_steps(
        self,
        *,
        root: Path,
        plan: list[dict],
        journal_id: str,
        done: list[int],
    ) -> list[int]:
        """Write the remaining steps, recording durable progress each time."""
        for step in plan:
            if step["ordinal"] in done:
                continue
            _, resolved = self._resolve(root, step["path"])
            try:
                for directory in step.get("createDirs", []):
                    (root / directory).mkdir(parents=True, exist_ok=True)
                if step["operation"] == "delete":
                    resolved.unlink(missing_ok=True)
                else:
                    _atomic_replace(resolved, Path(step["contentFile"]).read_bytes())
            except OSError as error:
                self._fail_journal(journal_id, done)
                raise WorkbenchError(RECOVERY_REQUIRED, detail=str(error)) from None
            done = [*done, step["ordinal"]]
            self.store.set_journal_state(
                journal_id=journal_id,
                state=JOURNAL_WRITING,
                done_json=_canonical_json(done),
                now=self._now_iso(),
            )
            expected = step["resultHash"]
            if step["operation"] == "delete":
                if _current_hash(resolved) is not None:
                    self._fail_journal(journal_id, done)
                    raise WorkbenchError(RECOVERY_REQUIRED)
            elif _current_hash(resolved) != expected:
                self._fail_journal(journal_id, done)
                raise WorkbenchError(RECOVERY_REQUIRED)
        return done

    def _fail_journal(self, journal_id: str, done: list[int]) -> None:
        self.store.set_journal_state(
            journal_id=journal_id,
            state=JOURNAL_RECOVERY,
            done_json=_canonical_json(done),
            now=self._now_iso(),
        )

    def apply(
        self, project_id: str, proposal_id: str, *, digest: object, operation: Operation
    ) -> dict:
        replayed = self.service._replay(
            operation, kind="proposal-apply", entity_id=proposal_id, project_id=project_id)
        if replayed is not None:
            return replayed
        target = self.service.require_project(project_id, scope="write")
        row = self._require_proposal(project_id, proposal_id)
        if row["state"] != STATE_AWAITING:
            raise WorkbenchError(CONFLICT)
        if _parse_iso(row["expires_at"]) <= self._now():
            self.store.set_proposal_state(
                proposal_id=proposal_id, state=STATE_EXPIRED, now=self._now_iso()
            )
            raise WorkbenchError(CONFLICT)
        if not isinstance(digest, str) or digest != row["digest"]:
            # The authorization binds the reviewed digest: one changed byte
            # and the approval no longer names this proposal.
            raise WorkbenchError(CONFLICT)
        self._block_incomplete(project_id)
        payload = json.loads(row["payload_json"])
        root = Path(target["canonicalPath"])
        with self._project_lock(project_id):
            if self.store.journal(proposal_id) is not None:
                # Every attempt has exactly one journal; a second one would
                # make the recovery decision ambiguous.
                raise WorkbenchError(CONFLICT)
            plan = self._plan(row, target, payload)
            journal_id = self.store.create_journal(
                proposal_id=proposal_id,
                project_id=project_id,
                state=JOURNAL_WRITING,
                plan_json=_canonical_json(plan),
                now=self._now_iso(),
            )
            done = self._write_steps(
                root=root, plan=plan, journal_id=journal_id, done=[]
            )
            receipt = self._receipt(
                proposal_id=proposal_id,
                journal_id=journal_id,
                status=RECEIPT_APPLIED,
                plan=plan,
                mode="apply",
            )
            with self.store.transaction():
                self.store.set_journal_state(
                    journal_id=journal_id,
                    state=JOURNAL_COMMITTED,
                    done_json=_canonical_json(done),
                    now=self._now_iso(),
                )
                self.store.set_proposal_state(
                    proposal_id=proposal_id,
                    state=STATE_APPLIED,
                    now=self._now_iso(),
                    receipt_json=_canonical_json(receipt),
                    applied_at=self._now_iso(),
                )
                self._record(
                    operation=operation,
                    kind="proposal-apply",
                    entity_id=proposal_id,
                    project_id=project_id,
                    result=receipt,
                )
        return {"result": receipt, "replayed": False, "counter": None}

    def _receipt(
        self,
        *,
        proposal_id: str,
        journal_id: str,
        status: str,
        plan: list[dict],
        mode: str,
    ) -> dict:
        return {
            "receiptId": str(uuid.uuid4()),
            "proposalId": proposal_id,
            "transactionId": journal_id,
            "status": status,
            "mode": mode,
            "resultHashes": {
                step["path"]: step["resultHash"] for step in plan
            },
            "files": [step["path"] for step in plan],
            "appliedAt": self._now_iso(),
        }

    # -- recovery ------------------------------------------------------

    def _classify(self, row: dict, target: dict, plan: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        root = Path(target["canonicalPath"])
        applied: list[dict] = []
        pending: list[dict] = []
        external: list[dict] = []
        for step in plan:
            _, resolved = self._resolve(root, step["path"])
            current = _current_hash(resolved)
            for_write = step["resultHash"]
            if step["operation"] == "delete":
                if current is None:
                    applied.append(step)
                elif current == step["baseHash"]:
                    pending.append(step)
                else:
                    external.append(step)
                continue
            if current == for_write:
                applied.append(step)
            elif current == step["baseHash"] or (
                step["operation"] == "create" and current is None
            ):
                pending.append(step)
            else:
                external.append(step)
        return applied, pending, external

    def recover(
        self, project_id: str, proposal_id: str, *, mode: object, operation: Operation
    ) -> dict:
        replayed = self.service._replay(
            operation, kind="proposal-recover", entity_id=proposal_id, project_id=project_id)
        if replayed is not None:
            return replayed
        mode_name = "rollback" if mode in (None, "", "rollback") else mode
        if mode_name not in ("rollback", "finish"):
            raise WorkbenchError(INVALID_INPUT)
        target = self.service.require_project(project_id, scope="write")
        row = self._require_proposal(project_id, proposal_id)
        journal = self.store.journal(proposal_id)
        if journal is None or journal["state"] not in (JOURNAL_WRITING, JOURNAL_RECOVERY):
            raise WorkbenchError(CONFLICT)
        plan = json.loads(journal["plan_json"])
        root = Path(target["canonicalPath"])
        with self._project_lock(project_id):
            applied, pending, external = self._classify(row, target, plan)
            if external:
                # The maintainer changed one of the files after the partial
                # write: recovery is a human decision, so nothing is touched.
                raise WorkbenchError(CONFLICT)
            if mode_name == "rollback":
                for step in reversed(applied):
                    _, resolved = self._resolve(root, step["path"])
                    try:
                        if step["operation"] == "create":
                            resolved.unlink(missing_ok=True)
                        else:
                            _atomic_replace(
                                resolved, Path(step["backupFile"]).read_bytes()
                            )
                    except OSError as error:
                        raise WorkbenchError(RECOVERY_REQUIRED, detail=str(error)) from None
                    restored = _current_hash(resolved)
                    expected = (
                        None if step["operation"] == "create" else step["baseHash"]
                    )
                    if restored != expected:
                        raise WorkbenchError(CORRUPT_CONTENT)
                # Folders this attempt created are removed again, but only
                # while they are still empty: a folder that gained content
                # since (maintainer or other tool) is left alone.
                for step in reversed(plan):
                    for directory in sorted(
                        step.get("createDirs", []), key=len, reverse=True
                    ):
                        try:
                            (root / directory).rmdir()
                        except OSError:
                            pass
                receipt = self._receipt(
                    proposal_id=proposal_id,
                    journal_id=journal["journal_id"],
                    status="rolled-back",
                    plan=plan,
                    mode="rollback",
                )
                with self.store.transaction():
                    self.store.set_journal_state(
                        journal_id=journal["journal_id"],
                        state=JOURNAL_ROLLED_BACK,
                        done_json=_canonical_json([]),
                        now=self._now_iso(),
                    )
                    self.store.set_proposal_state(
                        proposal_id=proposal_id,
                        state=STATE_ROLLED_BACK,
                        now=self._now_iso(),
                        receipt_json=_canonical_json(receipt),
                    )
                    self._record(
                        operation=operation,
                        kind="proposal-recover",
                        entity_id=proposal_id,
                        project_id=project_id,
                        result=receipt,
                    )
                return {"result": receipt, "replayed": False, "counter": None}

            done = self._write_steps(
                root=root,
                plan=pending,
                journal_id=journal["journal_id"],
                done=[step["ordinal"] for step in applied],
            )
            still_applied, still_pending, external = self._classify(row, target, plan)
            if external or still_pending:
                self._fail_journal(journal["journal_id"], done)
                raise WorkbenchError(RECOVERY_REQUIRED)
            receipt = self._receipt(
                proposal_id=proposal_id,
                journal_id=journal["journal_id"],
                status=RECEIPT_APPLIED,
                plan=plan,
                mode="finish",
            )
            with self.store.transaction():
                self.store.set_journal_state(
                    journal_id=journal["journal_id"],
                    state=JOURNAL_COMMITTED,
                    done_json=_canonical_json([step["ordinal"] for step in plan]),
                    now=self._now_iso(),
                )
                self.store.set_proposal_state(
                    proposal_id=proposal_id,
                    state=STATE_APPLIED,
                    now=self._now_iso(),
                    receipt_json=_canonical_json(receipt),
                    applied_at=self._now_iso(),
                )
                self._record(
                    operation=operation,
                    kind="proposal-recover",
                    entity_id=proposal_id,
                    project_id=project_id,
                    result=receipt,
                )
            return {"result": receipt, "replayed": False, "counter": None}

    # -- revert and reject ---------------------------------------------

    def revert(self, project_id: str, proposal_id: str, *, operation: Operation) -> dict:
        """A revert is a new proposal whose preconditions are the current hashes.

        Idempotency is delegated to :meth:`create`: a revert stages a new
        proposal under the caller's operation, so a retry with the same
        operation-id replays that ``proposal-create`` mutation instead of
        staging a duplicate. Reverting does not itself apply the changes, so
        the current-hash preconditions still hold on the retried pass.
        """
        target = self.service.require_project(project_id, scope="write")
        row = self._require_proposal(project_id, proposal_id)
        if row["state"] != STATE_APPLIED:
            raise WorkbenchError(CONFLICT)
        payload = json.loads(row["payload_json"])
        root = Path(target["canonicalPath"])
        staging = Path(row["staging_dir"])
        changes: list[dict] = []
        for index, entry in enumerate(payload["changes"]):
            _, resolved = self._resolve(root, entry["path"])
            current = _current_hash(resolved)
            if entry["operation"] == "create":
                if current != entry["resultHash"]:
                    raise WorkbenchError(CONFLICT)
                changes.append({"path": entry["path"], "operation": "delete",
                                "baseHash": entry["resultHash"]})
                continue
            backup = staging / f"{index:03d}.backup"
            if not backup.is_file():
                raise WorkbenchError(CORRUPT_CONTENT)
            restore = backup.read_bytes()
            if entry["operation"] == "delete":
                if current is not None:
                    raise WorkbenchError(CONFLICT)
                changes.append(
                    {
                        "path": entry["path"],
                        "operation": "create",
                        "content": restore.decode("utf-8", "surrogateescape"),
                    }
                )
            else:
                if current != entry["resultHash"]:
                    raise WorkbenchError(CONFLICT)
                changes.append(
                    {
                        "path": entry["path"],
                        "operation": "update",
                        "baseHash": entry["resultHash"],
                        "content": restore.decode("utf-8", "surrogateescape"),
                    }
                )
        outcome = self.create(
            project_id,
            changes=changes,
            operation=operation,
            summary=f"revert of {proposal_id}",
        )
        return outcome

    def reject(self, project_id: str, proposal_id: str, *, operation: Operation) -> dict:
        replayed = self.service._replay(
            operation, kind="proposal-reject", entity_id=proposal_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self._require_proposal(project_id, proposal_id)
        row = self.store.proposal(proposal_id)
        assert row is not None
        if row["state"] != STATE_AWAITING:
            raise WorkbenchError(CONFLICT)
        result = {"proposalId": proposal_id, "state": STATE_REJECTED}
        with self.store.transaction():
            self.store.set_proposal_state(
                proposal_id=proposal_id, state=STATE_REJECTED, now=self._now_iso()
            )
            self._record(
                operation=operation,
                kind="proposal-reject",
                entity_id=proposal_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": None}


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()
