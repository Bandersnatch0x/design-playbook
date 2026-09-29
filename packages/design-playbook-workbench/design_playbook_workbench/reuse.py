"""Fixed-revision reuse, cross-project import, and controlled upgrades (R04, R05).

An instance always points at one immutable revision: there is no "latest"
indirection anywhere, so publishing a new revision changes nothing that
already exists. Reuse across projects copies a *closed* set of resolvable
revisions plus the minimum provenance locators -- never the whole library,
its logs, or its private paths -- and the imported copy keeps working after
the source project is disconnected. Upgrading is an explicit, atomic
decision over a named set of instances; unselected instances stay exactly
where they were, and every upgrade or rollback is a new record rather than
an erasure of history.
"""
from __future__ import annotations

import json
import uuid
from typing import Callable

from .assets import AssetService
from .blobs import BlobStore
from .errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from .service import Operation, WorkbenchService, utc_now
from .store import Store

MAX_CLOSURE_REVISIONS = 200
RELATIONS = ("derived-from", "copied-from")
MODES = ("reference", "derive", "copy")


def _loads(text: object) -> object:
    if isinstance(text, (list, dict)):
        return text
    if not isinstance(text, str) or not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:  # pragma: no cover - stored by us
        return []


class ReuseService:
    """The one owner of references, lineage, and upgrade propagation."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        assets: AssetService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.assets = assets
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

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
        self.store.record_mutation(
            operation_id=operation.operation_id,
            entity_kind=kind,
            entity_id=entity_id,
            payload_digest=operation.digest,
            resulting_counter=None,
            result_json=json.dumps(
                result, separators=(",", ":"), sort_keys=True, ensure_ascii=False
            ),
            project_id=project_id,
            now=self._now(),
        )

    # -- dependency closure ---------------------------------------------

    def _closure(
        self, *, project_id: str, revision_id: str, seen: set[str] | None = None
    ) -> list[dict]:
        """Resolve one revision's dependency closure, refusing cycles."""
        seen = seen if seen is not None else set()
        if revision_id in seen:
            raise WorkbenchError(MISSING_DEPENDENCY, detail="dependency cycle")
        seen.add(revision_id)
        revision = self.store.revision(revision_id)
        if revision is None:
            raise WorkbenchError(MISSING_DEPENDENCY)
        entries: list[dict] = []
        for dependency in self.store.dependencies(revision_id):
            child_id = dependency["depends_on_revision_id"]
            child = self.store.revision(child_id)
            if child is None:
                raise WorkbenchError(MISSING_DEPENDENCY)
            asset = self.store.asset(child["asset_id"])
            if asset is None or asset["project_id"] != project_id:
                # A dependency must be resolvable inside the consuming
                # project: a dangling cross-project pointer is refused.
                raise WorkbenchError(MISSING_DEPENDENCY)
            entries.extend(
                self._closure(project_id=project_id, revision_id=child_id, seen=seen)
            )
            entries.append(
                {
                    "assetId": child["asset_id"],
                    "revisionId": child_id,
                    "revisionNumber": child["revision_number"],
                }
            )
        if len(seen) > MAX_CLOSURE_REVISIONS:
            raise WorkbenchError(LIMIT_EXCEEDED)
        return entries

    def dependency_closure(
        self, project_id: str, revision_id: str
    ) -> list[dict]:
        return self._closure(project_id=project_id, revision_id=revision_id)

    def would_cycle(
        self, *, project_id: str, asset_id: str, dependencies: list[dict]
    ) -> bool:
        """Public form of the prospective-edge check, for other owners."""
        return self._would_cycle(
            project_id=project_id, asset_id=asset_id, dependencies=dependencies
        )

    def _would_cycle(
        self, *, project_id: str, asset_id: str, dependencies: list[dict]
    ) -> bool:
        """True when the prospective edges close a loop back to this asset.

        The stored graph alone cannot answer this: the edge being added does
        not exist yet, so it is walked explicitly.
        """
        pending = {dependency["revisionId"] for dependency in dependencies}
        seen: set[str] = set()
        stack = list(pending)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            revision = self.store.revision(current)
            if revision is None:
                continue
            if revision["asset_id"] == asset_id:
                return True
            for dependency in self.store.dependencies(current):
                stack.append(dependency["depends_on_revision_id"])
        return False

    # -- publish with a validated closure --------------------------------

    def publish_with_dependencies(
        self,
        project_id: str,
        asset_id: str,
        *,
        dependencies: object,
        operation: Operation,
    ) -> dict:
        """Publish a revision whose declared dependencies must all resolve."""
        replayed = self.service._replay(
            operation, kind="asset-publish-deps", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        parsed = self._parse_dependencies(project_id, dependencies)
        # Completeness, resolvability, and cycles are checked before anything
        # is written -- including the edge this publish is about to add.
        for dependency in parsed:
            self.dependency_closure(project_id, dependency["revisionId"])
        if self._would_cycle(
            project_id=project_id, asset_id=asset_id, dependencies=parsed
        ):
            raise WorkbenchError(MISSING_DEPENDENCY, detail="dependency cycle")
        draft = self.store.draft(asset_id)
        manifest = _loads(draft["attributes_json"]).get("manifest", [])
        for entry in manifest:
            if not self.blobs.verify(entry["contentHash"]):
                raise WorkbenchError(CORRUPT_CONTENT)
        now = self._now()

        def apply() -> tuple[dict, int]:
            revision_number = int(self.store.draft(asset_id)["revision_counter"]) + 1
            revision_id = str(uuid.uuid4())
            attributes = _loads(draft["attributes_json"])
            self.store.insert_revision(
                revision_id=revision_id,
                asset_id=asset_id,
                revision_number=revision_number,
                content_hash=manifest[0]["contentHash"] if manifest else None,
                carrier=attributes.get("carrier", row["kind"]),
                capabilities=attributes.get("capabilities", []),
                dependencies=parsed,
                source_locators=self.assets.asset_detail(project_id, asset_id)[
                    "asset"
                ]["sourceLocators"],
                manifest=manifest,
                origin={"kind": "publish", "withDependencies": True},
                now=now,
            )
            self.store.insert_dependencies(
                revision_id=revision_id, dependencies=parsed, now=now
            )
            refreshed = self.store.asset(asset_id)
            payload = self.assets.asset_detail(project_id, asset_id)["asset"]
            payload["dependencies"] = parsed
            payload["revisionId"] = revision_id
            return payload, int(refreshed["counter"])

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="asset-publish-deps",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _parse_dependencies(self, project_id: str, raw: object) -> list[dict]:
        if raw in (None, []):
            return []
        if not isinstance(raw, list):
            raise WorkbenchError(INVALID_INPUT)
        if len(raw) > MAX_CLOSURE_REVISIONS:
            raise WorkbenchError(LIMIT_EXCEEDED)
        parsed: list[dict] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise WorkbenchError(INVALID_INPUT)
            revision_id = item.get("revisionId")
            if not isinstance(revision_id, str) or not revision_id:
                raise WorkbenchError(INVALID_INPUT)
            if revision_id in seen:
                raise WorkbenchError(INVALID_INPUT)
            revision = self.store.revision(revision_id)
            if revision is None:
                raise WorkbenchError(MISSING_DEPENDENCY)
            asset = self.store.asset(revision["asset_id"])
            if asset is None or asset["project_id"] != project_id:
                raise WorkbenchError(MISSING_DEPENDENCY)
            seen.add(revision_id)
            parsed.append(
                {
                    "assetId": revision["asset_id"],
                    "revisionId": revision_id,
                    "revisionNumber": revision["revision_number"],
                }
            )
        return parsed

    # -- instances -------------------------------------------------------

    def create_instance(
        self,
        project_id: str,
        asset_id: str,
        *,
        revision_id: object = None,
        overrides: object = None,
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(operation, kind="instance-create", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        asset = self.store.asset(asset_id)
        if asset is None:
            raise WorkbenchError(INVALID_TARGET)
        # An instance may reference a revision owned by another project
        # only after that closure was imported; otherwise the revision must
        # belong to the project itself.
        revision = self._resolve_revision(project_id, asset_id, revision_id)
        overrides_map = self._parse_overrides(overrides, revision)
        instance_id = str(uuid.uuid4())
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.insert_instance(
                instance_id=instance_id,
                project_id=project_id,
                asset_id=asset_id,
                revision_id=revision["revision_id"],
                overrides=overrides_map,
                declared_public_params=self._public_params(revision),
                now=now,
            )
            return self._instance_payload(instance_id), 0

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="instance-create",
                entity_id=instance_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _public_params(self, revision: dict) -> list:
        origin = _loads(revision["origin_json"])
        if isinstance(origin, dict):
            params = origin.get("publicParams")
            if isinstance(params, list):
                return params
        return []

    def _parse_overrides(self, raw: object, revision: dict) -> dict:
        if raw in (None, {}):
            return {}
        if not isinstance(raw, dict):
            raise WorkbenchError(INVALID_INPUT)
        declared = {
            str(param.get("name"))
            for param in self._public_params(revision)
            if isinstance(param, dict)
        }
        if declared:
            unknown = set(raw) - declared
            if unknown:
                # An instance cannot override something the revision does
                # not publish as a public parameter.
                raise WorkbenchError(INVALID_INPUT)
        return {str(key): value for key, value in raw.items()}

    def _resolve_revision(
        self, project_id: str, asset_id: str, revision_id: object
    ) -> dict:
        if revision_id in (None, ""):
            revision = self.store.latest_revision(asset_id)
            if revision is None:
                raise WorkbenchError(MISSING_DEPENDENCY)
            return revision
        if not isinstance(revision_id, str):
            raise WorkbenchError(INVALID_INPUT)
        revision = self.store.revision(revision_id)
        if revision is None or revision["asset_id"] != asset_id:
            raise WorkbenchError(INVALID_TARGET)
        asset = self.store.asset(asset_id)
        if asset is not None and asset["project_id"] != project_id:
            closure = self.store.import_closure_by_local_asset(asset_id)
            if closure is None:
                raise WorkbenchError(INVALID_TARGET)
        return revision

    def _instance_payload(self, instance_id: str) -> dict:
        row = self.store.instance(instance_id)
        if row is None:  # pragma: no cover - invariant
            raise WorkbenchError(INVALID_TARGET)
        revision = self.store.revision(row["revision_id"])
        asset = self.store.asset(row["asset_id"])
        return {
            "instanceId": row["instance_id"],
            "projectId": row["project_id"],
            "assetId": row["asset_id"],
            "assetName": asset["name"] if asset else None,
            "revisionId": row["revision_id"],
            "revisionNumber": revision["revision_number"] if revision else None,
            "overrides": _loads(row["overrides_json"]),
            "declaredPublicParams": _loads(row["declared_public_params_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def list_instances(self, project_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return {
            "instances": [
                self._instance_payload(row["instance_id"])
                for row in self.store.project_instances(project_id)
            ]
        }

    # -- lineage: derive and copy ----------------------------------------

    def derive_or_copy(
        self,
        project_id: str,
        asset_id: str,
        *,
        mode: object,
        name: object = None,
        operation: Operation,
    ) -> dict:
        if mode not in MODES:
            raise WorkbenchError(INVALID_INPUT)
        replayed = self.service._replay(operation, kind=f"asset-{mode}", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        source = self.store.asset(asset_id)
        if source is None or source["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        revision = self.store.latest_revision(asset_id)
        if revision is None:
            raise WorkbenchError(MISSING_DEPENDENCY)
        draft = self.store.draft(asset_id)
        attributes = _loads(draft["attributes_json"])
        new_name = (
            f"{source['name']} copy" if name in (None, "") else str(name)
        )[:120]
        now = self._now()
        new_asset_id = str(uuid.uuid4())

        def apply() -> tuple[dict, int]:
            if mode == "reference":
                # A reference reuses the same asset identity: only the
                # instance is new, so no lineage edge is created.
                return self._instance_payload(
                    self._create_instance_row(
                        project_id=project_id,
                        asset_id=asset_id,
                        revision_id=revision["revision_id"],
                        overrides={},
                        now=now,
                    )
                ), 0
            self.store.create_asset(
                asset_id=new_asset_id,
                project_id=project_id,
                kind=source["kind"],
                name=new_name,
                tags=_loads(draft["tags_json"]),
                attributes=attributes,
                now=now,
            )
            for entry in attributes.get("manifest", []):
                if not self.blobs.verify(entry["contentHash"]):
                    raise WorkbenchError(CORRUPT_CONTENT)
            revision_id = str(uuid.uuid4())
            self.store.insert_revision(
                revision_id=revision_id,
                asset_id=new_asset_id,
                revision_number=1,
                content_hash=revision["content_hash"],
                carrier=revision["carrier"],
                capabilities=_loads(revision["capabilities_json"]),
                dependencies=_loads(revision["dependencies_json"]),
                source_locators=_loads(revision["source_locators_json"]),
                manifest=_loads(revision["manifest_json"]),
                # A copy never inherits approvals: verified capabilities
                # start empty on the new asset.
                origin={
                    "kind": mode,
                    "fromAssetId": asset_id,
                    "fromRevisionId": revision["revision_id"],
                },
                now=now,
            )
            if mode == "derive":
                # A derived asset may evolve; a copy is a snapshot that is
                # explicitly not subscribed to upstream changes.
                self.store.add_lineage(
                    child_asset_id=new_asset_id,
                    parent_asset_id=asset_id,
                    parent_revision_id=revision["revision_id"],
                    relation="derived-from",
                    now=now,
                )
            else:
                self.store.add_lineage(
                    child_asset_id=new_asset_id,
                    parent_asset_id=asset_id,
                    parent_revision_id=revision["revision_id"],
                    relation="copied-from",
                    now=now,
                )
            return (
                self.assets.asset_detail(project_id, new_asset_id)["asset"],
                int(self.store.asset(new_asset_id)["counter"]),
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind=f"asset-{mode}",
                entity_id=new_asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _create_instance_row(
        self,
        *,
        project_id: str,
        asset_id: str,
        revision_id: str,
        overrides: dict,
        now: str,
    ) -> str:
        instance_id = str(uuid.uuid4())
        self.store.insert_instance(
            instance_id=instance_id,
            project_id=project_id,
            asset_id=asset_id,
            revision_id=revision_id,
            overrides=overrides,
            declared_public_params=[],
            now=now,
        )
        return instance_id

    # -- cross-project reuse --------------------------------------------

    def reuse_plan(
        self,
        project_id: str,
        *,
        source_asset_id: object,
        source_revision_id: object,
        mode: object,
        target_project_id: object,
    ) -> dict:
        """What a cross-project import would carry, before anything happens."""
        if mode not in MODES:
            raise WorkbenchError(INVALID_INPUT)
        if not isinstance(target_project_id, str) or not target_project_id:
            raise WorkbenchError(INVALID_INPUT)
        self.service.require_project(project_id, scope="read")
        target = self.service.require_project(target_project_id, scope="read")
        source_asset = self.store.asset(str(source_asset_id))
        if source_asset is None or source_asset["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        revision = (
            self.store.revision(str(source_revision_id))
            if source_revision_id
            else self.store.latest_revision(source_asset["asset_id"])
        )
        if revision is None or revision["asset_id"] != source_asset["asset_id"]:
            raise WorkbenchError(INVALID_TARGET)
        closure = self.dependency_closure(project_id, revision["revision_id"])
        manifest = _loads(revision["manifest_json"])
        for entry in manifest:
            if not self.blobs.verify(entry["contentHash"]):
                raise WorkbenchError(CORRUPT_CONTENT)
        return {
            "mode": mode,
            "source": {
                "projectId": project_id,
                "assetId": source_asset["asset_id"],
                "assetName": source_asset["name"],
                "revisionId": revision["revision_id"],
                "revisionNumber": revision["revision_number"],
                "contentHash": revision["content_hash"],
            },
            "target": {
                "projectId": target["projectId"],
                "canonicalPath": target["canonicalPath"],
            },
            "dependencies": closure,
            "manifest": [
                {
                    "path": entry["path"],
                    "contentHash": entry["contentHash"],
                    "size": entry["size"],
                    "mediaType": entry.get("mediaType"),
                }
                for entry in manifest
            ],
            "excluded": [
                "其他画布内容",
                "运行日志与证据",
                "源项目私有路径",
                "未选中的修订",
            ],
            "conflicts": self._reuse_conflicts(target_project_id, revision),
        }

    def _reuse_conflicts(self, target_project_id: str, revision: dict) -> list[dict]:
        conflicts: list[dict] = []
        existing = self.store.import_closure_by_local_asset(
            f"{target_project_id}:{revision['revision_id']}"
        )
        if existing is not None:
            conflicts.append(
                {"kind": "already-imported", "revisionId": revision["revision_id"]}
            )
        return conflicts

    def import_closure(
        self,
        project_id: str,
        *,
        source_asset_id: object,
        source_revision_id: object,
        mode: object,
        target_project_id: object,
        operation: Operation,
    ) -> dict:
        """Import one explicit closure into another project as a resolvable copy."""
        replayed = self.service._replay(operation, kind="closure-import", project_id=target_project_id)
        if replayed is not None:
            return replayed
        plan = self.reuse_plan(
            project_id,
            source_asset_id=source_asset_id,
            source_revision_id=source_revision_id,
            mode=mode,
            target_project_id=target_project_id,
        )
        target_id = plan["target"]["projectId"]
        self.service.require_project(target_id, scope="write")
        revision = self.store.revision(plan["source"]["revisionId"])
        assert revision is not None
        local_asset_id = str(uuid.uuid4())
        local_revision_id = str(uuid.uuid4())
        closure_id = str(uuid.uuid4())
        now = self._now()
        # Only the necessary provenance survives: a locator, not the source
        # project's paths, logs, or private context.
        locators = [
            {
                "kind": "imported-revision",
                "projectId": project_id,
                "assetId": plan["source"]["assetId"],
                "revisionId": plan["source"]["revisionId"],
                "sourceHash": revision["content_hash"],
                "run": None,
                "objectType": "revision",
                "objectId": revision["revision_id"],
            }
        ]

        def apply() -> tuple[dict, int]:
            self.store.create_asset(
                asset_id=local_asset_id,
                project_id=target_id,
                kind=self.store.asset(plan["source"]["assetId"])["kind"],
                name=plan["source"]["assetName"],
                tags=[],
                attributes={
                    "manifest": plan["manifest"],
                    "carrier": revision["carrier"],
                    "capabilities": _loads(revision["capabilities_json"]),
                    "roots": [],
                    "warnings": [],
                    "dynamicPreviewEnabled": False,
                },
                now=now,
            )
            self.store.insert_revision(
                revision_id=local_revision_id,
                asset_id=local_asset_id,
                revision_number=1,
                content_hash=revision["content_hash"],
                carrier=revision["carrier"],
                capabilities=_loads(revision["capabilities_json"]),
                dependencies=[],
                source_locators=locators,
                manifest=plan["manifest"],
                origin={
                    "kind": "imported",
                    "mode": plan["mode"],
                    "sourceProjectId": project_id,
                    "sourceAssetId": plan["source"]["assetId"],
                    "sourceRevisionId": plan["source"]["revisionId"],
                },
                now=now,
            )
            self.store.insert_import_closure(
                import_closure_id=closure_id,
                project_id=target_id,
                source_project_id=project_id,
                source_asset_id=plan["source"]["assetId"],
                source_revision_id=plan["source"]["revisionId"],
                mode=plan["mode"],
                local_asset_id=local_asset_id,
                local_revision_id=local_revision_id,
                locators=locators,
                now=now,
            )
            payload = self.assets.asset_detail(target_id, local_asset_id)["asset"]
            payload["importClosureId"] = closure_id
            payload["mode"] = plan["mode"]
            payload["source"] = plan["source"]
            payload["dependencies"] = plan["dependencies"]
            return payload, 0

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="closure-import",
                entity_id=closure_id,
                project_id=target_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- upgrade and rollback -------------------------------------------

    def upgrade_plan(
        self,
        project_id: str,
        asset_id: str,
        *,
        to_revision_id: object = None,
    ) -> dict:
        """Compare the current revision with a candidate, per instance set."""
        self.service.require_project(project_id, scope="read")
        asset = self.store.asset(asset_id)
        if asset is None or asset["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        target_revision = (
            self.store.revision(str(to_revision_id))
            if to_revision_id
            else self.store.latest_revision(asset_id)
        )
        if target_revision is None or target_revision["asset_id"] != asset_id:
            raise WorkbenchError(INVALID_TARGET)
        instances = self.store.asset_instances(asset_id)
        groups: dict[str, list[dict]] = {}
        for instance in instances:
            groups.setdefault(instance["revision_id"], []).append(instance)
        candidates: list[dict] = []
        for revision_id, members in groups.items():
            if revision_id == target_revision["revision_id"]:
                continue
            current = self.store.revision(revision_id)
            if current is None:
                continue
            conflicts = self._upgrade_conflicts(current, target_revision, members)
            candidates.append(
                {
                    "fromRevisionId": revision_id,
                    "fromRevisionNumber": current["revision_number"],
                    "toRevisionId": target_revision["revision_id"],
                    "toRevisionNumber": target_revision["revision_number"],
                    "instanceIds": [row["instance_id"] for row in members],
                    "instanceCount": len(members),
                    "conflicts": conflicts,
                    "upgradable": not conflicts,
                }
            )
        return {
            "assetId": asset_id,
            "assetName": asset["name"],
            "target": {
                "revisionId": target_revision["revision_id"],
                "revisionNumber": target_revision["revision_number"],
                "capabilities": _loads(target_revision["capabilities_json"]),
            },
            "candidates": candidates,
            "notes": (
                "升级只影响选中的实例，整组原子更新，未选实例保持旧版；"
                "冲突存在时阻止应用。"
            ),
        }

    def _upgrade_conflicts(
        self, current: dict, target: dict, members: list[dict]
    ) -> list[dict]:
        conflicts: list[dict] = []
        if current["carrier"] != target["carrier"]:
            conflicts.append(
                {"kind": "carrier-changed", "from": current["carrier"], "to": target["carrier"]}
            )
        current_caps = set(_loads(current["capabilities_json"]))
        target_caps = set(_loads(target["capabilities_json"]))
        if not current_caps <= target_caps:
            conflicts.append(
                {
                    "kind": "capability-dropped",
                    "dropped": sorted(current_caps - target_caps),
                }
            )
        declared = {
            str(param.get("name"))
            for param in self._public_params(target)
            if isinstance(param, dict)
        }
        for member in members:
            overrides = _loads(member["overrides_json"])
            if not isinstance(overrides, dict) or not overrides:
                continue
            # A target that declares no such parameter cannot honour the
            # instance's override: that is a conflict, not a silent drop.
            if not set(overrides) <= declared:
                conflicts.append(
                    {
                        "kind": "override-unsupported",
                        "instanceId": member["instance_id"],
                        "unknown": sorted(set(overrides) - declared),
                    }
                )
        target_deps = {
            dependency["depends_on_revision_id"]
            for dependency in self.store.dependencies(target["revision_id"])
        }
        for dependency_id in target_deps:
            dependency = self.store.revision(dependency_id)
            if dependency is None:
                conflicts.append({"kind": "missing-dependency", "revisionId": dependency_id})
        return conflicts

    def upgrade_instances(
        self,
        project_id: str,
        asset_id: str,
        *,
        instance_ids: object,
        to_revision_id: object = None,
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(
            operation, kind="instance-upgrade", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if not isinstance(instance_ids, list) or not instance_ids:
            raise WorkbenchError(INVALID_INPUT)
        plan = self.upgrade_plan(project_id, asset_id, to_revision_id=to_revision_id)
        target = self.store.revision(plan["target"]["revisionId"])
        assert target is not None
        selected = set(instance_ids)
        known = {
            instance_id
            for candidate in plan["candidates"]
            for instance_id in candidate["instanceIds"]
        }
        unknown = selected - known
        if unknown:
            raise WorkbenchError(INVALID_TARGET)
        affected = [
            candidate
            for candidate in plan["candidates"]
            if selected & set(candidate["instanceIds"])
        ]
        # The whole selected set is applied atomically: any conflict blocks
        # every change, and unselected instances are never touched.
        blocking = [
            conflict
            for candidate in affected
            for conflict in candidate["conflicts"]
        ]
        if blocking:
            raise WorkbenchError(CONFLICT)
        now = self._now()
        from_revisions = {
            candidate["fromRevisionId"] for candidate in affected
        }

        def apply() -> tuple[dict, int]:
            for instance_id in sorted(selected):
                instance = self.store.instance(instance_id)
                if instance is None:  # pragma: no cover - invariant
                    raise WorkbenchError(INVALID_TARGET)
                overrides = _loads(instance["overrides_json"])
                self.store.set_instance_revision(
                    instance_id=instance_id,
                    revision_id=target["revision_id"],
                    overrides=overrides,
                    now=now,
                )
            record_id = str(uuid.uuid4())
            self.store.insert_upgrade_record(
                record_id=record_id,
                project_id=project_id,
                asset_id=asset_id,
                from_revision_id=sorted(from_revisions)[0],
                to_revision_id=target["revision_id"],
                instance_ids=sorted(selected),
                kind="upgrade",
                now=now,
            )
            return (
                {
                    "recordId": record_id,
                    "assetId": asset_id,
                    "toRevisionId": target["revision_id"],
                    "updatedInstanceIds": sorted(selected),
                    "untouchedInstanceIds": sorted(known - selected),
                    "instances": [
                        self._instance_payload(row["instance_id"])
                        for row in self.store.asset_instances(asset_id)
                    ],
                },
                int(self.store.asset(asset_id)["counter"]),
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="instance-upgrade",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def rollback_instances(
        self,
        project_id: str,
        asset_id: str,
        *,
        instance_ids: object,
        to_revision_id: object,
        operation: Operation,
    ) -> dict:
        """Restore selected instances to an older revision as a new record."""
        replayed = self.service._replay(
            operation, kind="instance-rollback", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if not isinstance(instance_ids, list) or not instance_ids:
            raise WorkbenchError(INVALID_INPUT)
        revision = self.store.revision(str(to_revision_id))
        if revision is None or revision["asset_id"] != asset_id:
            # Unknown target, or content that no longer verifies, must be
            # reported as damage instead of silently becoming "latest".
            raise WorkbenchError(CORRUPT_CONTENT)
        for entry in _loads(revision["manifest_json"]):
            if not self.blobs.verify(entry["contentHash"]):
                raise WorkbenchError(CORRUPT_CONTENT)
        now = self._now()
        selected = [str(item) for item in instance_ids]

        def apply() -> tuple[dict, int]:
            for instance_id in sorted(selected):
                instance = self.store.instance(instance_id)
                if instance is None or instance["project_id"] != project_id:
                    raise WorkbenchError(INVALID_TARGET)
                if instance["asset_id"] != asset_id:
                    raise WorkbenchError(INVALID_TARGET)
                self.store.set_instance_revision(
                    instance_id=instance_id,
                    revision_id=revision["revision_id"],
                    overrides=_loads(instance["overrides_json"]),
                    now=now,
                )
            record_id = str(uuid.uuid4())
            self.store.insert_upgrade_record(
                record_id=record_id,
                project_id=project_id,
                asset_id=asset_id,
                from_revision_id=revision["revision_id"],
                to_revision_id=revision["revision_id"],
                instance_ids=sorted(selected),
                kind="rollback",
                now=now,
            )
            return (
                {
                    "recordId": record_id,
                    "assetId": asset_id,
                    "restoredRevisionId": revision["revision_id"],
                    "restoredInstanceIds": sorted(selected),
                },
                int(self.store.asset(asset_id)["counter"]),
            )

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation=operation,
                kind="instance-rollback",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def asset_history(self, project_id: str, asset_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        asset = self.store.asset(asset_id)
        if asset is None or asset["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        return {
            "assetId": asset_id,
            "lineage": self.store.lineage(asset_id),
            "revisions": [
                {
                    "revisionId": row["revision_id"],
                    "revisionNumber": row["revision_number"],
                    "capabilities": _loads(row["capabilities_json"]),
                    "dependencies": self.store.dependencies(row["revision_id"]),
                    "createdAt": row["created_at"],
                    "instanceCount": len(self.store.revision_instances(row["revision_id"])),
                }
                for row in self.store.asset_revisions(asset_id)
            ],
            "records": [
                {
                    "recordId": row["record_id"],
                    "kind": row["kind"],
                    "toRevisionId": row["to_revision_id"],
                    "instanceIds": _loads(row["instance_ids_json"]),
                    "createdAt": row["created_at"],
                }
                for row in self.store.asset_upgrade_records(asset_id)
            ],
        }
