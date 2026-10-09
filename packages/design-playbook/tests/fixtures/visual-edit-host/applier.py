"""HOST-ONLY candidate review/apply CLI; never imported by plugin runtime.

The coding agent supplies candidate styles.css or a directory of existing text files. This host does not
pretend DOM selectors automatically map to source or that it invokes a model.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from host import ASSET_MANIFEST, source_files, source_hash, source_path as _source_path

from design_playbook.mcp.preview.live_route import observe_visual_source, validate_live_route_url
from design_playbook.mcp.preview.visual_batch import normalize_visual_batch
from design_playbook.mcp.preview.visual_handoff import build_agent_handoff


def user_identity(value):
    """Local display identity for conflict diagnostics; not authentication."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 64
            or not all(c.isascii() and (c.isalnum() or c in "_-") for c in value)):
        raise ValueError("user identity must be 1-64 letters, digits, underscores or hyphens")
    return value


def _candidate_files(candidate: Path) -> dict[str, bytes]:
    if not candidate.is_dir():
        return {"styles.css": candidate.read_bytes()}
    contents = {}
    for path in sorted(candidate.rglob("*")):
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("candidate must not contain links")
        if path.is_file():
            contents[path.relative_to(candidate).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            raise ValueError("candidate must contain only regular text files")
    if not contents:
        raise ValueError("candidate directory is empty")
    return contents


def _file_diff(name: str, before: bytes, after: bytes) -> str:
    lines = difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        fromfile="a/" + name, tofile="b/" + name,
    )
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                   for line in lines)


def review(root: Path, handoff_path: Path, candidate_path: Path, route: str) -> tuple[dict, dict[str, bytes]]:
    """Read the persisted plugin handoff, not a test-created substitute."""
    route = validate_live_route_url(route)
    root = root.resolve()
    assets = source_files(root)
    asset_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()}
    record = json.loads(handoff_path.read_text(encoding="utf-8"))
    current = observe_visual_source(root / "index.html", route)
    batch = normalize_visual_batch(record["visual_edits"], source_hash=current, route_url=route)
    handoff = record["visual_handoff"]
    if handoff != build_agent_handoff(batch, current_source_hash=current, route_url=route):
        raise ValueError("handoff does not match the pending batch")
    candidate = _candidate_files(candidate_path.resolve())
    if ASSET_MANIFEST in candidate or not candidate.keys() <= assets.keys():
        raise ValueError("candidate must select only host-declared assets, not the asset manifest")
    before = {name: assets[name] for name in candidate}
    files = {name: {"beforeHash": hashlib.sha256(before[name]).hexdigest(),
                    "afterHash": hashlib.sha256(content).hexdigest()}
             for name, content in candidate.items()}
    diff = "".join(_file_diff(name, before[name], content) for name, content in candidate.items())
    if not diff:
        raise ValueError("agent candidate has no source changes")
    binding = json.dumps({"sourceHash": current, "routeUrl": route, "files": files,
                          "batchHash": handoff["batchHash"], "diff": diff,
                          "assetHashes": asset_hashes}, sort_keys=True)
    return {
        "owner": "host-applier", "pluginWritesSource": False,
        "sourceHash": current, "hostSourceHash": source_hash(root),
        "stylesHash": hashlib.sha256((root / "styles.css").read_bytes()).hexdigest(),
        "files": files, "assetHashes": asset_hashes,
        "batchHash": handoff["batchHash"], "routeUrl": route,
        "edits": handoff["edits"], "diff": diff,
        "confirmation": "APPLY " + hashlib.sha256(binding.encode("utf-8")).hexdigest(),
    }, candidate


def _stage(target: Path, content: bytes) -> Path:
    """Stage bytes beside the target without changing any source file."""
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as pending:
        staged = Path(pending.name)
        try:
            pending.write(content)
            pending.flush()
            os.fsync(pending.fileno())
        except OSError:
            pending.close()
            staged.unlink()
            raise
    return staged


def _atomic_replace(target: Path, content: bytes) -> None:
    staged = _stage(target, content)
    try:
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)


class HostWriteError(ValueError):
    def __init__(self, phase: str, error: Exception | str, committed: list[str],
                 rollback_errors: dict[str, str]):
        super().__init__(f"{phase} failed: {error}; rolledBack={not rollback_errors}")
        self.details = {"outcome": "failed", "phase": phase, "reason": str(error),
                        "writeApplied": bool(committed), "committedFiles": committed,
                        "rollbackAttempted": bool(committed),
                        "rolledBack": not rollback_errors, "rollbackErrors": rollback_errors}


def _restore(root: Path, before: dict[str, bytes], names: list[str]) -> dict[str, str]:
    errors = {}
    for name in names:
        try:
            _atomic_replace(root / name, before[name])
        except OSError as exc:
            # Try every restoration even when an earlier file cannot be restored.
            errors[name] = str(exc)
    return errors


INTERRUPT_POINTS = ("after-staging", "after-first-commit")


class FixtureInterrupted(BaseException):
    """A controlled fixture abort, NOT an OS kill or a generic signal handler."""
    def __init__(self, point: str):
        super().__init__("fixture-abort:" + point)
        self.point = point


def _commit(root: Path, content: dict[str, bytes], before: dict[str, bytes],
            interrupt_at: str | None = None) -> None:
    staged = {}
    committed = []
    phase = "stage"
    try:
        for name, data in content.items():
            staged[name] = _stage(root / name, data)
        if interrupt_at == "after-staging":
            raise FixtureInterrupted(interrupt_at)
        phase = "commit"
        for name, pending in staged.items():
            os.replace(pending, root / name)
            committed.append(name)
            if interrupt_at == "after-first-commit" and len(committed) == 1:
                raise FixtureInterrupted(interrupt_at)
    except (OSError, FixtureInterrupted) as exc:
        errors = _restore(root, before, committed)
        error = HostWriteError("interruption" if isinstance(exc, FixtureInterrupted) else phase,
                               str(exc), committed, errors)
        if isinstance(exc, FixtureInterrupted):
            error.details.update({"faultPoint": exc.point,
                                  "recoveryScope": "controlled-fixture-abort-only"})
        raise error from exc
    finally:
        for pending in staged.values():
            pending.unlink(missing_ok=True)


class PostWriteObservationError(HostWriteError):
    def __init__(self, observation_error: Exception, names: list[str], errors: dict[str, str]):
        super().__init__("observation", observation_error, names, errors)
        rollback_error = "; ".join(errors.values())
        outcome = f"rollback failed: {rollback_error}" if errors else "rollback succeeded"
        replaced = "styles.css was replaced" if names == ["styles.css"] else ", ".join(names) + " were replaced"
        self.args = (f"post-write observation failed; {replaced}; "
                     f"{outcome}; observation error: {observation_error}",)
        self.details.update({"observationFailed": True, "observationError": str(observation_error)})
        if errors:
            self.details["rollbackError"] = rollback_error


@contextmanager
def _source_lock(root: Path, identity: str, edits: list[dict]):
    """Serialize cooperative appliers; never infer that an old lock is safe to steal."""
    lock = root.parent / ("." + root.name + ".applier.lock")
    marker = json.dumps({"owner": "host-applier", "pid": os.getpid(),
                         "nonce": uuid.uuid4().hex, "sourceRoot": str(root),
                         "userId": identity, "selectors": sorted({e["locator"] for e in edits}),
                         "pendingEdits": edits}).encode("utf-8")
    if len(marker) > 262144:
        raise ValueError("applier ownership marker exceeds 256 KiB")
    staged = _stage(lock, marker)
    try:
        # Publish a complete owner atomically, without replacing another owner.
        os.link(staged, lock)
    except FileExistsError as exc:
        error = HostWriteError("lock", "applier-lock-exists", [], {})
        error.args = ("applier-lock-exists; active or stale locks require explicit inspection and removal",)
        error.details["lockPath"] = str(lock)
        error.details["requestedBy"] = identity
        try:
            if lock.is_symlink() or lock.stat().st_size > 262144:
                raise ValueError("lock owner marker is linked or oversized")
            owner = json.loads(lock.read_bytes())
            if not isinstance(owner, dict):
                raise ValueError("lock owner marker is not an object")
            error.details["lockOwner"] = owner
            pending = owner.get("pendingEdits", [])
            if not isinstance(pending, list) or any(not isinstance(e, dict) or
                    any(not isinstance(e.get(key), str) for key in ("locator", "property", "oldValue", "newValue"))
                    for e in pending):
                raise ValueError("lock pending edits are not a list of objects")
            requested = {(e["locator"], e["property"]) for e in edits}
            error.details["conflicts"] = [e for e in pending
                                          if (e.get("locator"), e.get("property")) in requested]
            error.args = (f"applier-lock-exists; held by {owner.get('userId', owner.get('owner'))} "
                          f"(pid={owner.get('pid')}); pending edits: {json.dumps(pending)}; "
                          "active or stale locks require explicit inspection and removal",)
        except (OSError, ValueError) as owner_error:
            # An incomplete, corrupt or unreadable owner marker still holds the lock.
            error.details["lockOwnerError"] = str(owner_error)
        raise error from exc
    finally:
        staged.unlink()
    try:
        yield
    finally:
        # Never remove a replacement lock belonging to a different owner.
        if lock.read_bytes() != marker:
            raise ValueError("applier lock owner changed; lock retained; inspect source state")
        lock.unlink()


def apply(root: Path, handoff: Path, candidate: Path, route: str, *,
          interrupt_at: str | None = None, user_id: str | None = None) -> dict:
    if interrupt_at is not None and interrupt_at not in INTERRUPT_POINTS:
        raise ValueError("unknown fixture interruption point")
    root = root.resolve()
    identity = user_identity(user_id if user_id is not None else f"user-{os.getpid()}")
    record = json.loads(handoff.read_text(encoding="utf-8"))
    batch = record["visual_edits"]
    # Metadata is the requested edit, not source-mapping or approval authority.
    # The existing review inside the lock still validates the actual source.
    normalized = normalize_visual_batch(batch, source_hash=batch["sourceHash"], route_url=route)
    edits = [{key: edit[key] for key in ("locator", "property", "oldValue", "newValue")}
             for edit in normalized["edits"]]
    try:
        with _source_lock(root, identity, edits):
            return _apply_locked(root, handoff, candidate, route, interrupt_at)
    except HostWriteError as exc:
        if exc.details["phase"] == "interruption":
            # Reached only after our context manager released its own marker.
            exc.details["lockDisposition"] = "owned-lock-released"
        raise


def _apply_locked(root: Path, handoff: Path, candidate: Path, route: str,
                  interrupt_at: str | None = None) -> dict:
    proposal, content = review(root, handoff, candidate, route)
    print(proposal["diff"], end="", flush=True)
    print("Type exactly: " + proposal["confirmation"], flush=True)
    if sys.stdin.readline().strip() != proposal["confirmation"]:
        raise PermissionError("explicit hash-bound host confirmation required; source unchanged")
    # Re-read after the review/typing delay. Changed source or a swapped candidate
    # cannot ride an earlier approval (including changes in raw newline bytes).
    refreshed, latest_content = review(root, handoff, candidate, route)
    if refreshed != proposal or latest_content != content:
        raise PermissionError("review changed while awaiting confirmation; review again")
    root = root.resolve()
    before = {name: _source_path(root, name).read_bytes() for name in content}
    _commit(root, content, before, interrupt_at)
    try:
        after_source_hash = observe_visual_source(root / "index.html", route)
        after_host_hash = source_hash(root)
        after_styles_hash = hashlib.sha256((root / "styles.css").read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        errors = _restore(root, before, list(before))
        raise PostWriteObservationError(exc, list(before), errors) from exc
    return {"owner": "host-applier", "pluginWritesSource": False,
            "outcome": "applied", "files": proposal["files"],
            "beforeSourceHash": proposal["sourceHash"],
            "afterSourceHash": after_source_hash,
            "beforeHostSourceHash": proposal["hostSourceHash"],
            "afterHostSourceHash": after_host_hash,
            "beforeStylesHash": proposal["stylesHash"],
            "afterStylesHash": after_styles_hash}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("review", "apply"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--route-url", required=True)
    parser.add_argument("--user-id", help="local display identity for conflict diagnostics; not authentication")
    parser.add_argument("--interrupt-at", choices=INTERRUPT_POINTS,
                        help="controlled HOST fixture abort; no OS/process crash guarantee")
    args = parser.parse_args()
    if args.interrupt_at and args.action != "apply":
        parser.error("--interrupt-at is only valid for apply")
    try:
        if args.action == "review":
            result, _ = review(args.root, args.handoff, args.candidate, args.route_url)
        else:
            result = apply(args.root, args.handoff, args.candidate, args.route_url,
                           interrupt_at=args.interrupt_at, user_id=args.user_id)
    except (OSError, ValueError, KeyError) as exc:
        error = {"owner": "host-applier", "pluginWritesSource": False,
                 "status": "error", "error": str(exc)}
        if isinstance(exc, HostWriteError):
            error.update(exc.details)
        print("REFUSED: " + json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
