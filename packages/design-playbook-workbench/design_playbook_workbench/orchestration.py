"""Schemes, fixed snapshots, comparison, and explicit Agent context (R10).

Three rules this module owns:

- a **flow edge** is navigation, not asset lineage: user flows may loop, and
  nothing here writes a derived-from or run/evidence relation;
- a **scheme comparison** works from *fixed* snapshots (a content hash bound
  to the canvas state it was taken from), and comparing never picks a winner
  or grants an approval;
- a **ContextSelection** carries exactly what would be sent -- fixed node
  snapshots, fixed asset revisions, explicitly named files, and the stated
  exclusions -- with a digest that a confirmation is bound to, so any change
  invalidates the old confirmation instead of silently reusing it.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable

from .assets import AssetService, is_credential_name
from .blobs import BlobStore, digest_bytes
from .canvas import CanvasService, instance_count, snapshot_html
from .errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from .paths import assert_contained
from .proposals import relative_parts
from .service import Operation, WorkbenchService, payload_digest, utc_now
from .store import Store

MAX_CONTEXT_NODES = 200
MAX_CONTEXT_REVISIONS = 100
MAX_CONTEXT_FILES = 100
MAX_CONTEXT_BYTES = 128 * 1024 * 1024

COMPARISON_NOTE = (
    "并排比较两份固定快照，只呈现差异；它不选择赢家，也不授予批准或验收结论。"
)


class OrchestrationService:
    """Scheme snapshots, side-by-side comparison, and context selections."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        canvases: CanvasService,
        assets: AssetService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.canvases = canvases
        self.assets = assets
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- shared reads ---------------------------------------------------

    def _canvas(self, project_id: str, canvas_id: str) -> dict:
        return self.canvases._row(project_id, canvas_id)

    def _document(self, row: dict) -> dict:
        return self.canvases._document(row)

    def _board(self, document: dict, board_id: object) -> dict:
        for board in document.get("boards") or []:
            if board["id"] == board_id:
                return board
        raise WorkbenchError(INVALID_TARGET)

    def _send_record(self, operation: Operation, *, kind: str, entity_id: str,
                     project_id: str, result: dict, counter: int, now: str) -> None:
        self.store.record_mutation(
            operation_id=operation.operation_id,
            entity_kind=kind,
            entity_id=entity_id,
            payload_digest=operation.digest,
            resulting_counter=counter,
            result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
            project_id=project_id,
            now=now,
        )

    # -- fixed scheme snapshots -----------------------------------------

    def _snapshot_payload(self, row: dict) -> dict:
        return {
            "snapshotId": row["snapshot_id"],
            "canvasId": row["canvas_id"],
            "boardId": row["board_id"],
            "boardName": row["board_name"],
            "counter": int(row["counter"]),
            "contentHash": row["content_hash"],
            "bytes": int(row["bytes"]),
            "nodeCount": int(row["node_count"]),
            "note": row["note"],
            "createdAt": row["created_at"],
            "frozen": True,
            "previewPath": f"/p/{row['content_hash']}/static?type=text/html",
        }

    def create_snapshot(
        self,
        project_id: str,
        canvas_id: str,
        *,
        board_id: object = None,
        note: object = None,
        operation: Operation,
    ) -> dict:
        """Freeze one board: the hash is bound to this canvas counter."""
        replayed = self.service._replay(operation, kind="scheme-snapshot", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._canvas(project_id, canvas_id)
        document = self._document(row)
        board = self._board(
            document, board_id or (document["boards"][0]["id"] if document["boards"] else None)
        )
        if len(self.store.canvas_scheme_snapshots(canvas_id)) >= 50:
            raise WorkbenchError(
                LIMIT_EXCEEDED, detail="单个画布最多保留 50 份固定快照。"
            )
        html = snapshot_html(
            document, board["id"], title=f"{row['name']} · {board['name']}"
        ).encode("utf-8")
        record = self.blobs.put(html)
        snapshot_id = str(uuid.uuid4())
        now = self._now()
        text = note if isinstance(note, str) else ""

        def apply() -> tuple[dict, int]:
            self.store.insert_scheme_snapshot(
                snapshot_id=snapshot_id,
                canvas_id=canvas_id,
                project_id=project_id,
                board_id=board["id"],
                board_name=board["name"],
                counter=int(row["counter"]),
                content_hash=record.content_hash,
                size=record.size,
                node_count=len(board["nodes"]),
                note=text[:500],
                now=now,
            )
            return self._snapshot_payload(self.store.scheme_snapshot(snapshot_id)), int(
                row["counter"]
            )

        with self.store.transaction():
            result, counter = apply()
            self._send_record(
                operation,
                kind="scheme-snapshot",
                entity_id=snapshot_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def list_snapshots(self, project_id: str, canvas_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        row = self._canvas(project_id, canvas_id)
        return {
            "canvasId": row["canvas_id"],
            "snapshots": [
                self._snapshot_payload(item)
                for item in self.store.canvas_scheme_snapshots(canvas_id)
            ],
        }

    def snapshot(self, project_id: str, canvas_id: str, snapshot_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        row = self._snapshot_row(project_id, canvas_id, snapshot_id)
        return {"snapshot": self._snapshot_payload(row)}

    def _snapshot_row(self, project_id: str, canvas_id: str, snapshot_id: str) -> dict:
        row = self.store.scheme_snapshot(snapshot_id)
        if (
            row is None
            or row["canvas_id"] != canvas_id
            or row["project_id"] != project_id
        ):
            raise WorkbenchError(INVALID_TARGET)
        return row

    def compare(
        self,
        project_id: str,
        canvas_id: str,
        *,
        left: object,
        right: object,
        operation: Operation,
    ) -> dict:
        """Two fixed snapshots side by side, without choosing between them."""
        replayed = self.service._replay(
            operation, kind="scheme-compare", entity_id=f"{left}:{right}", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="read")
        if not isinstance(left, str) or not isinstance(right, str) or left == right:
            raise WorkbenchError(INVALID_INPUT)
        left_row = self._snapshot_row(project_id, canvas_id, left)
        right_row = self._snapshot_row(project_id, canvas_id, right)
        document = self._document(self._canvas(project_id, canvas_id))

        def type_counts(row: dict) -> dict:
            board = self._board(document, row["board_id"])
            counts: dict[str, int] = {}
            for node in board["nodes"]:
                counts[node["type"]] = counts.get(node["type"], 0) + 1
            return counts

        left_counts = type_counts(left_row)
        right_counts = type_counts(right_row)
        node_types = sorted(set(left_counts) | set(right_counts))
        result = {
            "canvasId": canvas_id,
            "left": self._snapshot_payload(left_row),
            "right": self._snapshot_payload(right_row),
            "differences": {
                "nodeCount": {
                    "left": int(left_row["node_count"]),
                    "right": int(right_row["node_count"]),
                },
                "nodeTypes": [
                    {
                        "type": name,
                        "left": left_counts.get(name, 0),
                        "right": right_counts.get(name, 0),
                    }
                    for name in node_types
                ],
                "sameContent": left_row["content_hash"] == right_row["content_hash"],
            },
            "note": COMPARISON_NOTE,
            "winner": None,
            "approval": None,
        }
        now = self._now()
        with self.store.transaction():
            self._send_record(
                operation,
                kind="scheme-compare",
                entity_id=f"{left}:{right}",
                project_id=project_id,
                result=result,
                counter=int(self._canvas(project_id, canvas_id)["counter"]),
                now=now,
            )
        return {"result": result, "replayed": False, "counter": 0}

    # -- explicit Agent context -----------------------------------------

    def _context_payload(self, row: dict) -> dict:
        payload = json.loads(row["payload_json"])
        return {
            **payload,
            "selectionId": row["selection_id"],
            "canvasId": row["canvas_id"],
            "boardId": row["board_id"],
            "canvasCounter": int(row["canvas_counter"]),
            "state": row["state"],
            "digest": row["digest"],
            "confirmed": (
                {"digest": row["confirmed_digest"], "at": row["confirmed_at"]}
                if row["confirmed_digest"]
                else None
            ),
            "staleConfirmation": bool(
                row["confirmed_digest"] and row["confirmed_digest"] != row["digest"]
            ),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def list_contexts(self, project_id: str, canvas_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        row = self._canvas(project_id, canvas_id)
        return {
            "canvasId": row["canvas_id"],
            "selections": [
                self._context_payload(item)
                for item in self.store.canvas_context_selections(canvas_id)
            ],
        }

    def context(self, project_id: str, selection_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return {"selection": self._context_payload(self._context_row(project_id, selection_id))}

    def _context_row(self, project_id: str, selection_id: str) -> dict:
        row = self.store.context_selection(selection_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        return row

    def build_context(
        self,
        project_id: str,
        canvas_id: str,
        *,
        selection_id: object = None,
        board_id: object = None,
        node_ids: object,
        revision_ids: object = None,
        file_paths: object = None,
        operation: Operation,
    ) -> dict:
        """Build or replace a selection: only what is named is ever sent."""
        replayed = self.service._replay(
            operation,
            kind="context-selection",
            entity_id=selection_id if isinstance(selection_id, str) and selection_id else None, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        canvas_row = self._canvas(project_id, canvas_id)
        document = self._document(canvas_row)
        board = self._board(
            document, board_id or (document["boards"][0]["id"] if document["boards"] else None)
        )
        if not isinstance(node_ids, list) or not all(
            isinstance(item, str) and item for item in node_ids
        ):
            raise WorkbenchError(INVALID_INPUT)
        if len(node_ids) > MAX_CONTEXT_NODES:
            raise WorkbenchError(LIMIT_EXCEEDED, detail="选择的节点过多。")
        by_id = {node["id"]: node for node in board["nodes"]}
        unknown = [node_id for node_id in node_ids if node_id not in by_id]
        if unknown:
            raise WorkbenchError(INVALID_TARGET, detail=f"unknown node: {unknown[0]}")
        revisions = self._context_revisions(project_id, board, node_ids, revision_ids)
        files = self._context_files(project_id, file_paths)
        if not node_ids and not revisions and not files:
            raise WorkbenchError(
                INVALID_INPUT, detail="上下文至少要包含一个节点、修订或文件。"
            )
        nodes = [
            {
                "nodeId": node_id,
                "type": by_id[node_id]["type"],
                "props": by_id[node_id]["props"],
                "layout": by_id[node_id]["layout"],
            }
            for node_id in node_ids
        ]
        exclusions = self._exclusions(document, board, node_ids)
        node_bytes = len(
            json.dumps(nodes, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            .encode("utf-8")
        )
        revision_bytes = sum(item["size"] for item in revisions)
        file_bytes = sum(item["size"] for item in files)
        totals = {
            "nodeCount": len(nodes),
            "revisionCount": len(revisions),
            "fileCount": len(files),
            "nodeBytes": node_bytes,
            "revisionBytes": revision_bytes,
            "fileBytes": file_bytes,
            "bytes": node_bytes + revision_bytes + file_bytes,
        }
        if totals["bytes"] > MAX_CONTEXT_BYTES:
            raise WorkbenchError(
                LIMIT_EXCEEDED,
                detail=f"上下文超过 {MAX_CONTEXT_BYTES} 字节上限。",
            )
        content = {
            "nodes": nodes,
            "revisions": revisions,
            "files": files,
            "exclusions": exclusions,
            "totals": totals,
            "boardId": board["id"],
            "canvasCounter": int(canvas_row["counter"]),
        }
        digest = payload_digest(content)
        payload = {**content, "digest": digest}
        now = self._now()
        target_id = selection_id if isinstance(selection_id, str) and selection_id else str(uuid.uuid4())
        previous = self.store.context_selection(target_id)
        if previous is not None and previous["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        if previous is not None and previous["canvas_id"] != canvas_id:
            raise WorkbenchError(INVALID_TARGET)

        def apply() -> tuple[dict, int]:
            if previous is None:
                self.store.insert_context_selection(
                    selection_id=target_id,
                    project_id=project_id,
                    canvas_id=canvas_id,
                    board_id=board["id"],
                    canvas_counter=int(canvas_row["counter"]),
                    payload=payload,
                    digest=digest,
                    now=now,
                )
            else:
                # A changed selection is a draft again: the old confirmation
                # is recorded, never silently carried over.
                self.store.update_context_selection(
                    selection_id=target_id,
                    canvas_counter=int(canvas_row["counter"]),
                    payload=payload,
                    digest=digest,
                    state="draft",
                    now=now,
                )
            return self._context_payload(self.store.context_selection(target_id)), int(
                canvas_row["counter"]
            )

        with self.store.transaction():
            result, counter = apply()
            self._send_record(
                operation,
                kind="context-selection",
                entity_id=target_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _context_revisions(
        self,
        project_id: str,
        board: dict,
        node_ids: list[str],
        revision_ids: object,
    ) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()

        def add(asset_id: str, revision_id: str, reason: str) -> None:
            if revision_id in seen:
                return
            asset = self.store.asset(asset_id)
            revision = self.store.revision(revision_id)
            if asset is None or asset["project_id"] != project_id or revision is None:
                raise WorkbenchError(MISSING_DEPENDENCY, detail="revision is unresolved")
            if revision["asset_id"] != asset_id:
                raise WorkbenchError(INVALID_INPUT)
            manifest = json.loads(revision["manifest_json"])
            size = sum(int(entry.get("size") or 0) for entry in manifest)
            if revision["content_hash"]:
                try:
                    size = max(size, len(self.blobs.read(revision["content_hash"])))
                except WorkbenchError:
                    raise WorkbenchError(MISSING_DEPENDENCY, detail="revision content is missing") from None
            rows.append(
                {
                    "assetId": asset_id,
                    "assetName": asset["name"],
                    "assetKind": asset["kind"],
                    "revisionId": revision_id,
                    "revisionNumber": int(revision["revision_number"]),
                    "contentHash": revision["content_hash"],
                    "manifest": manifest,
                    "size": size,
                    "reason": reason,
                    "fixedRevision": True,
                }
            )
            seen.add(revision_id)

        # An instance node's fixed revision travels with the node.
        for node_id in node_ids:
            node = next((item for item in board["nodes"] if item["id"] == node_id), None)
            if node is None or node["type"] != "instance":
                continue
            instance_id = node["props"].get("instanceId")
            if not isinstance(instance_id, str) or not instance_id:
                continue
            instance = self.store.instance(instance_id)
            if instance is None or instance["project_id"] != project_id:
                raise WorkbenchError(MISSING_DEPENDENCY, detail="instance is unresolved")
            add(instance["asset_id"], instance["revision_id"], "实例节点的固定修订")
        if revision_ids is not None:
            if not isinstance(revision_ids, list) or not all(
                isinstance(item, str) and item for item in revision_ids
            ):
                raise WorkbenchError(INVALID_INPUT)
            if len(revision_ids) > MAX_CONTEXT_REVISIONS:
                raise WorkbenchError(LIMIT_EXCEEDED, detail="显式加入的修订过多。")
            for revision_id in revision_ids:
                revision = self.store.revision(revision_id)
                if revision is None:
                    raise WorkbenchError(
                        INVALID_TARGET, detail=f"unknown revision: {revision_id}"
                    )
                add(revision["asset_id"], revision_id, "显式加入的修订")
        return rows

    def _context_files(self, project_id: str, file_paths: object) -> list[dict]:
        if file_paths in (None, []):
            return []
        if not isinstance(file_paths, list) or not all(
            isinstance(item, str) and item for item in file_paths
        ):
            raise WorkbenchError(INVALID_INPUT)
        if len(file_paths) > MAX_CONTEXT_FILES:
            raise WorkbenchError(LIMIT_EXCEEDED, detail="显式加入的文件过多。")
        root = Path(self.service.require_project(project_id, scope="read")["canonicalPath"])
        files: list[dict] = []
        for relative in file_paths:
            parts = relative_parts(relative)
            if any(is_credential_name(part) for part in parts):
                # Credential-shaped content never enters a context, even when
                # the maintainer names it explicitly.
                raise WorkbenchError(
                    INVALID_INPUT, detail="凭据形状的文件不能加入上下文。"
                )
            assert_contained(root.joinpath(*parts), root)
            target = root.joinpath(*parts)
            if not target.is_file():
                raise WorkbenchError(INVALID_TARGET, detail=f"missing file: {relative}")
            data = target.read_bytes()
            files.append(
                {
                    "path": "/".join(parts),
                    "contentHash": digest_bytes(data),
                    "size": len(data),
                }
            )
        return files

    def _exclusions(self, document: dict, board: dict, node_ids: list[str]) -> list[dict]:
        selected = set(node_ids)
        other_boards = [
            item["id"] for item in document.get("boards") or [] if item["id"] != board["id"]
        ]
        rows = [
            {
                "kind": "unselected-nodes",
                "count": len([node for node in board["nodes"] if node["id"] not in selected]),
                "reason": "未被选择的节点不会进入上下文。",
            },
            {
                "kind": "other-boards",
                "count": len(other_boards),
                "reason": "其他画板不会被隐式发送。",
                "ids": other_boards,
            },
            {
                "kind": "project-files",
                "count": 0,
                "reason": "未显式选择的项目文件不会被扫描或发送。",
            },
            {
                "kind": "run-and-evidence-logs",
                "count": 0,
                "reason": "运行与证据日志由原 owner 持有，不默认发送。",
            },
            {
                "kind": "credentials",
                "count": 0,
                "reason": "凭据无论何时都不进入上下文。",
            },
            {
                "kind": "unselected-revisions",
                "count": 0,
                "reason": "未选择的资产修订不会附带发送。",
            },
        ]
        return rows

    def confirm_context(
        self,
        project_id: str,
        canvas_id: str,
        selection_id: str,
        *,
        digest: object,
        operation: Operation,
    ) -> dict:
        """Bind a confirmation to the current digest; a change invalidates it."""
        replayed = self.service._replay(
            operation, kind="context-confirm", entity_id=selection_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._canvas(project_id, canvas_id)
        row = self._context_row(project_id, selection_id)
        if row["canvas_id"] != canvas_id:
            raise WorkbenchError(INVALID_TARGET)
        if not isinstance(digest, str) or digest != row["digest"]:
            raise WorkbenchError(CONFLICT, detail="上下文内容已变化，请重新确认。")
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.confirm_context_selection(
                selection_id=selection_id, digest=digest, now=now
            )
            return self._context_payload(self.store.context_selection(selection_id)), int(
                row["canvas_counter"]
            )

        with self.store.transaction():
            result, counter = apply()
            self._send_record(
                operation,
                kind="context-confirm",
                entity_id=selection_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}


__all__ = [
    "COMPARISON_NOTE",
    "MAX_CONTEXT_BYTES",
    "OrchestrationService",
    "instance_count",
]
