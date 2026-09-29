"""Archive, recycle bin, and reference-safe deletion (R13).

Lifecycle is discovery state, not destruction: archiving or trashing an
asset changes whether it is surfaced, never the references that point at
it. A published revision's content is immutable and stays readable while
the asset is archived or in the recycle bin.

Permanent deletion is the only destructive path, and it is fail-closed:

- it needs a complete reference scan (instances, dependents, derived/copied
  lineage, cross-project copies, canvas nodes, upgrade records); if any part
  of that scan cannot be built, deletion is refused rather than guessed;
- any live in-registry reference blocks it, so the maintainer must detach
  first; a cross-project copy or an exported backup is out of scope and is
  reported as a surviving boundary rather than chased;
- removing a workbench project deletes only its own stored data, never the
  maintainer's local source repository.
"""
from __future__ import annotations

import json
from typing import Callable

from .assets import AssetService
from .errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    WorkbenchError,
)
from .service import Operation, WorkbenchService, utc_now
from .store import Store

LIFECYCLE_STATES = frozenset({"draft", "published", "archived", "trashed"})


class LifecycleService:
    """Asset archive/trash/restore, reference reports, and hard delete."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        assets: AssetService,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.assets = assets
        self._now = now_fn if now_fn is not None else utc_now

    # -- shared plumbing ------------------------------------------------

    def _record(
        self,
        operation: Operation,
        *,
        kind: str,
        entity_id: str,
        project_id: str,
        result: dict,
        counter: int,
        now: str,
    ) -> None:
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

    def _asset(self, project_id: str, asset_id: str) -> dict:
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        return row

    # -- browse ---------------------------------------------------------

    def browse(self, project_id: str, *, lifecycle: object = None) -> dict:
        """Unified view of assets by lifecycle, plus archived-project flag."""
        self.service.require_project(project_id, scope="read")
        rows = self.store.project_assets(project_id)
        if lifecycle not in (None, "", "all"):
            if lifecycle not in LIFECYCLE_STATES:
                raise WorkbenchError(INVALID_INPUT)
            rows = [row for row in rows if row["lifecycle"] == lifecycle]
        buckets: dict[str, list[dict]] = {state: [] for state in LIFECYCLE_STATES}
        for row in rows:
            buckets.setdefault(row["lifecycle"], []).append(
                {
                    "assetId": row["asset_id"],
                    "name": row["name"],
                    "kind": row["kind"],
                    "lifecycle": row["lifecycle"],
                    "updatedAt": row["updated_at"],
                }
            )
        project = self.store.project(project_id)
        return {
            "projectArchived": bool(project["archived"]),
            "counts": {state: len(items) for state, items in buckets.items()},
            "assets": buckets,
        }

    # -- reference report -----------------------------------------------

    def reference_report(self, project_id: str, asset_id: str) -> dict:
        """The complete impact of touching this asset.

        ``indexComplete`` is False when any part of the scan could not be
        built (for example a canvas document that will not parse); deletion
        is refused in that case rather than proceeding on a partial view.
        """
        self.service.require_project(project_id, scope="read")
        row = self._asset(project_id, asset_id)
        index_complete = True
        instances = [
            {
                "instanceId": item["instance_id"],
                "projectId": item["project_id"],
                "revisionId": item["revision_id"],
            }
            for item in self.store.asset_instances(asset_id)
        ]
        dependents = [
            {
                "assetId": item["asset_id"],
                "name": item["name"],
                "kind": item["kind"],
                "revisionId": item["revision_id"],
                "revisionNumber": item["revision_number"],
                "projectId": item["project_id"],
            }
            for item in self.store.assets_depending_on_asset(asset_id)
        ]
        lineage_children = [
            {
                "assetId": item["child_asset_id"],
                "relation": item["relation"],
                "name": item["name"],
                "kind": item["kind"],
                "projectId": item["project_id"],
            }
            for item in self.store.lineage_children(asset_id)
        ]
        cross_project_copies = [
            {
                "importClosureId": item["import_closure_id"],
                "projectId": item["project_id"],
                "localAssetId": item["local_asset_id"],
                "mode": item["mode"],
            }
            for item in self.store.import_copies_of_source(asset_id)
        ]
        upgrade_records = [
            {
                "recordId": item["record_id"],
                "fromRevisionId": item["from_revision_id"],
                "toRevisionId": item["to_revision_id"],
                "kind": item["kind"],
            }
            for item in self.store.asset_upgrade_records(asset_id)
        ]
        canvas_refs, canvas_ok = self._canvas_references(project_id, asset_id)
        index_complete = index_complete and canvas_ok
        blocking = (
            bool(instances)
            or bool(dependents)
            or bool(lineage_children)
            or bool(canvas_refs)
        )
        return {
            "assetId": asset_id,
            "name": row["name"],
            "kind": row["kind"],
            "lifecycle": row["lifecycle"],
            "instances": instances,
            "dependents": dependents,
            "lineageChildren": lineage_children,
            "canvasReferences": canvas_refs,
            "crossProjectCopies": cross_project_copies,
            "upgradeRecords": upgrade_records,
            "indexComplete": index_complete,
            "deletable": (not blocking) and index_complete,
            "boundaries": [
                "跨项目复制副本属于其他项目，删除本资产不会追删它们。",
                "已导出的备份仍可能包含本资产内容；删除不改变备份。",
                "删除只影响工作台记录，从不改动本地源仓库文件。",
            ],
        }

    def _canvas_references(self, project_id: str, asset_id: str) -> tuple[list[dict], bool]:
        """Canvas nodes that reference this asset, and whether the scan was complete."""
        instance_ids = {
            item["instance_id"] for item in self.store.asset_instances(asset_id)
        }
        refs: list[dict] = []
        complete = True
        for row in self.store.project_canvases(project_id):
            try:
                document = json.loads(row["document_json"])
                boards = document.get("boards") or []
            except (json.JSONDecodeError, TypeError):
                # A canvas whose document will not parse means the scan is
                # incomplete: deletion must fail closed, not skip it.
                complete = False
                continue
            for board in boards:
                for node in board.get("nodes") or []:
                    if node.get("type") != "instance":
                        continue
                    props = node.get("props") or {}
                    if (
                        props.get("assetId") == asset_id
                        or props.get("instanceId") in instance_ids
                    ):
                        refs.append(
                            {
                                "canvasId": row["canvas_id"],
                                "canvasName": row["name"],
                                "boardId": board.get("id"),
                                "nodeId": node.get("id"),
                            }
                        )
        return refs, complete

    # -- archive / trash / restore --------------------------------------

    def _transition(
        self,
        project_id: str,
        asset_id: str,
        *,
        kind: str,
        to_state: str,
        allowed_from: tuple[str, ...],
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(operation, kind=kind, entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._asset(project_id, asset_id)
        if row["lifecycle"] not in allowed_from:
            raise WorkbenchError(
                CONFLICT, detail=f"asset is {row['lifecycle']}, not {allowed_from}"
            )
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.set_asset_lifecycle(
                asset_id=asset_id, lifecycle=to_state, now=now
            )
            result = {
                "assetId": asset_id,
                "lifecycle": to_state,
                "previousLifecycle": row["lifecycle"],
            }
            return result, counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind=kind,
                entity_id=asset_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def archive(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        return self._transition(
            project_id, asset_id, kind="asset-archive", to_state="archived",
            allowed_from=("published", "draft"), operation=operation,
        )

    def unarchive(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        row = self._asset(project_id, asset_id)
        target = "published" if int(row["counter"]) and self.store.latest_revision(asset_id) else "draft"
        return self._transition(
            project_id, asset_id, kind="asset-unarchive", to_state=target,
            allowed_from=("archived",), operation=operation,
        )

    def trash(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        return self._transition(
            project_id, asset_id, kind="asset-trash", to_state="trashed",
            allowed_from=("published", "draft", "archived"), operation=operation,
        )

    def restore(
        self, project_id: str, asset_id: str, *, name: object = None, operation: Operation
    ) -> dict:
        """Restore a trashed asset, keeping its ID; a name clash must be resolved."""
        replayed = self.service._replay(operation, kind="asset-restore", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._asset(project_id, asset_id)
        if row["lifecycle"] != "trashed":
            raise WorkbenchError(CONFLICT, detail="asset is not in the recycle bin")
        target = (
            "published" if self.store.latest_revision(asset_id) is not None else "draft"
        )
        rename_to = row["name"]
        clash = any(
            other["asset_id"] != asset_id
            and other["name"] == row["name"]
            and other["kind"] == row["kind"]
            and other["lifecycle"] != "trashed"
            for other in self.store.project_assets(project_id)
        )
        if clash:
            # Restoring must not silently overwrite or shadow another asset.
            if not isinstance(name, str) or not name.strip():
                raise WorkbenchError(
                    CONFLICT, detail="name conflicts with an active asset; provide a new name"
                )
            rename_to = name.strip()[:120]
            if any(
                other["asset_id"] != asset_id
                and other["name"] == rename_to
                and other["kind"] == row["kind"]
                and other["lifecycle"] != "trashed"
                for other in self.store.project_assets(project_id)
            ):
                raise WorkbenchError(CONFLICT, detail="the new name also conflicts")
        now = self._now()

        def apply() -> tuple[dict, int]:
            if rename_to != row["name"]:
                self.store.rename_asset(asset_id=asset_id, name=rename_to, now=now)
            counter = self.store.set_asset_lifecycle(
                asset_id=asset_id, lifecycle=target, now=now
            )
            return {
                "assetId": asset_id,
                "lifecycle": target,
                "name": rename_to,
                "renamed": rename_to != row["name"],
            }, counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="asset-restore",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- permanent deletion ---------------------------------------------

    def hard_delete(
        self, project_id: str, asset_id: str, *, confirm: object, operation: Operation
    ) -> dict:
        """Permanently delete an asset only when the scan proves it is safe."""
        replayed = self.service._replay(operation, kind="asset-hard-delete", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._asset(project_id, asset_id)
        if confirm is not True:
            # A permanent delete is a second, explicit confirmation.
            raise WorkbenchError(INVALID_INPUT, detail="confirm must be true")
        report = self.reference_report(project_id, asset_id)
        if not report["indexComplete"]:
            raise WorkbenchError(
                CONFLICT, detail="reference index is incomplete; deletion is refused"
            )
        if not report["deletable"]:
            raise WorkbenchError(
                CONFLICT,
                detail=json.dumps(
                    {
                        "instances": len(report["instances"]),
                        "dependents": len(report["dependents"]),
                        "lineageChildren": len(report["lineageChildren"]),
                        "canvasReferences": len(report["canvasReferences"]),
                    },
                    ensure_ascii=False,
                ),
            )
        now = self._now()
        record = {
            "assetId": asset_id,
            "name": row["name"],
            "kind": row["kind"],
            "deletedAt": now,
            "crossProjectCopies": report["crossProjectCopies"],
            "boundaries": report["boundaries"],
        }

        with self.store.transaction():
            self.store.delete_asset(asset_id)
            self._record(
                operation,
                kind="asset-hard-delete",
                entity_id=asset_id,
                project_id=project_id,
                result=record,
                counter=0,
                now=now,
            )
        return {"result": record, "replayed": False, "counter": 0}

    # -- project lifecycle ----------------------------------------------

    def archive_project(
        self, project_id: str, *, archived: bool, operation: Operation
    ) -> dict:
        kind = "project-archive" if archived else "project-unarchive"
        replayed = self.service._replay(operation, kind=kind, entity_id=project_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="read")
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.set_archived(
                project_id=project_id, archived=archived, now=now
            )
            return {"projectId": project_id, "archived": archived}, counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind=kind,
                entity_id=project_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def project_deletion_impact(self, project_id: str) -> dict:
        """What deleting the workbench project data would remove.

        Deleting workbench data never touches the source folder; cross-project
        copies live in other projects and survive.
        """
        self.service.require_project(project_id, scope="read")
        assets = self.store.project_assets(project_id)
        surviving_copies: list[dict] = []
        for asset in assets:
            for copy in self.store.import_copies_of_source(asset["asset_id"]):
                if copy["project_id"] != project_id:
                    surviving_copies.append(
                        {
                            "sourceAssetId": asset["asset_id"],
                            "projectId": copy["project_id"],
                            "localAssetId": copy["local_asset_id"],
                        }
                    )
        return {
            "projectId": project_id,
            "assetCount": len(assets),
            "canvasCount": len(self.store.project_canvases(project_id)),
            "survivingCrossProjectCopies": surviving_copies,
            "boundaries": [
                "删除工作台项目数据只清除本工作台记录，不删除本地源仓库文件。",
                "其他项目中的跨项目复制副本不受影响。",
                "已导出的备份仍包含内容；删除不改变备份。",
            ],
        }


__all__ = ["LIFECYCLE_STATES", "LifecycleService"]
