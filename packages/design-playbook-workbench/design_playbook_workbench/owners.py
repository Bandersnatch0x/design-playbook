"""Owner facts, freshness, confirmations, and backflow (R12).

The workbench does not decide anything here. It reads a projection document
that an original owner publishes next to its run, rebuilds a typed view of
that owner's facts (criteria, evidence, findings, repair pointers), and
keeps only *references* plus the confirmations a human bound to a content
hash. Three rules are enforced rather than documented:

- a fact is located by run + object type + object id + source hash together,
  so a same-named object in another run is never joined to this one;
- the projection is rebuilt on read and never stored as a second verdict:
  when the referenced source changes, the projection reports ``stale`` (or
  ``unknown`` when it is gone) and the old confirmation stops applying;
- a verified capability can only be published with a confirmation bound to
  the exact content hash, and an Agent credential can never confirm.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable

from .assets import AssetService
from .blobs import digest_bytes
from .blobs import BlobStore
from .components import ComponentService
from .errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    MISSING_DEPENDENCY,
    STALE_EVIDENCE,
    WorkbenchError,
)
from .paths import assert_contained
from .proposals import relative_parts
from .service import Operation, WorkbenchService, payload_digest, utc_now
from .store import Store

#: Where an owner publishes its projection, relative to the project root.
PROJECTION_ROOT = ".design-playbook/runs"

#: Projection document version this adapter understands.
PROJECTION_VERSION = "owner-projection/v1"

#: Semantic roles a human confirmation can carry. An Agent credential never
#: holds one of these; only the maintainer's own session can confirm.
CONFIRMATION_ROLES = frozenset(
    {"owner-verified", "maintainer-accepted", "reproduced"}
)

#: Object types a locator can name.
OBJECT_TYPES = frozenset({"criterion", "evidence", "finding", "run", "repair"})

MAX_CRITERIA = 500
MAX_FINDINGS = 500
MAX_EVIDENCE = 2000


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise WorkbenchError(
            MISSING_DEPENDENCY, detail="owner projection is unreadable"
        ) from None


class OwnerProjectionService:
    """Reads owner facts, tracks freshness, records human confirmations."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        assets: AssetService,
        components: ComponentService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.assets = assets
        self.components = components
        self.blobs = blobs
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

    def _root(self, project_id: str) -> Path:
        return Path(
            self.service.require_project(project_id, scope="read")["canonicalPath"]
        )

    def _projection_path(self, root: Path, run_id: str) -> Path:
        parts = relative_parts(f"{PROJECTION_ROOT}/{run_id}/projection.json")
        assert_contained(root.joinpath(*parts), root)
        return root.joinpath(*parts)

    # -- projections ----------------------------------------------------

    def list_runs(self, project_id: str) -> dict:
        """Every run that published a projection, newest first."""
        self.service.require_project(project_id, scope="read")
        root = self._root(project_id)
        base = root.joinpath(*relative_parts(PROJECTION_ROOT))
        runs: list[dict] = []
        if base.is_dir():
            for entry in sorted(base.iterdir()):
                if not entry.is_dir():
                    continue
                path = entry / "projection.json"
                if not path.is_file():
                    continue
                try:
                    projection = self._parse_projection(
                        _read_json(path), expected_project=project_id
                    )
                except WorkbenchError as error:
                    runs.append(
                        {
                            "runId": entry.name,
                            "state": "unknown",
                            "reason": error.detail or error.code,
                        }
                    )
                    continue
                runs.append(self._summarize(project_id, projection, path))
        return {"runs": runs, "projectionRoot": PROJECTION_ROOT}

    def run(self, project_id: str, run_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        root = self._root(project_id)
        path = self._projection_path(root, run_id)
        if not path.is_file():
            raise WorkbenchError(INVALID_TARGET, detail="unknown run projection")
        projection = self._parse_projection(
            _read_json(path), expected_project=project_id
        )
        return self._detailed(project_id, projection, path)

    def _parse_projection(self, raw: object, *, expected_project: str) -> dict:
        if not isinstance(raw, dict):
            raise WorkbenchError(MISSING_DEPENDENCY, detail="projection must be an object")
        if raw.get("version") != PROJECTION_VERSION:
            raise WorkbenchError(
                MISSING_DEPENDENCY, detail="unknown projection version"
            )
        run_id = raw.get("runId")
        if not isinstance(run_id, str) or not run_id:
            raise WorkbenchError(MISSING_DEPENDENCY, detail="run id is missing")
        owner = raw.get("owner")
        if not isinstance(owner, str) or not owner:
            # No owner means no fact: the workbench does not invent one.
            raise WorkbenchError(MISSING_DEPENDENCY, detail="owner is missing")
        project = raw.get("projectId")
        if project is not None and project != expected_project:
            raise WorkbenchError(
                INVALID_TARGET, detail="projection belongs to another project"
            )
        criteria = raw.get("criteria") or []
        if not isinstance(criteria, list) or len(criteria) > MAX_CRITERIA:
            raise WorkbenchError(MISSING_DEPENDENCY, detail="criteria are invalid")
        findings = raw.get("findings") or []
        if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
            raise WorkbenchError(MISSING_DEPENDENCY, detail="findings are invalid")
        evidence = raw.get("evidence") or []
        if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
            raise WorkbenchError(MISSING_DEPENDENCY, detail="evidence is invalid")
        return {
            "version": PROJECTION_VERSION,
            "runId": run_id,
            "owner": owner,
            "projectId": project,
            "runner": raw.get("runner") or "",
            "generatedAt": raw.get("generatedAt") or "",
            "artifacts": raw.get("artifacts") or [],
            "criteria": criteria,
            "evidence": evidence,
            "findings": findings,
        }

    def _criterion_rows(self, projection: dict) -> list[dict]:
        rows: list[dict] = []
        for item in projection["criteria"]:
            if not isinstance(item, dict):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="criterion is invalid")
            criterion_id = item.get("criterionId")
            verdict = item.get("verdict")
            if not isinstance(criterion_id, str) or not criterion_id:
                raise WorkbenchError(MISSING_DEPENDENCY, detail="criterion id is missing")
            if verdict not in ("pass", "fail", "unknown", "blocked"):
                # The owner's own vocabulary only; no workbench verdict.
                raise WorkbenchError(
                    MISSING_DEPENDENCY, detail=f"criterion {criterion_id} has no verdict"
                )
            evidence_hashes = item.get("evidenceHashes") or []
            if not isinstance(evidence_hashes, list):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="evidence hashes are invalid")
            rows.append(
                {
                    "objectType": "criterion",
                    "objectId": criterion_id,
                    "role": item.get("role") or "",
                    "verdict": verdict,
                    "verdictSource": "owner",
                    "evidenceHashes": evidence_hashes,
                    "sourceHash": item.get("sourceHash"),
                    "confirmedBy": item.get("confirmedBy"),
                }
            )
        return rows

    def _finding_rows(self, projection: dict) -> list[dict]:
        rows: list[dict] = []
        for item in projection["findings"]:
            if not isinstance(item, dict):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="finding is invalid")
            finding_id = item.get("findingId")
            if not isinstance(finding_id, str) or not finding_id:
                raise WorkbenchError(MISSING_DEPENDENCY, detail="finding id is missing")
            pointer = item.get("pointBack") or {}
            if not isinstance(pointer, dict):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="point-back is invalid")
            rows.append(
                {
                    "objectType": "finding",
                    "objectId": finding_id,
                    "severity": item.get("severity") or "info",
                    "summary": item.get("summary") or "",
                    "criterionId": item.get("criterionId"),
                    "pointBack": {
                        "kind": pointer.get("kind") or "unknown",
                        "path": pointer.get("path"),
                        "note": pointer.get("note") or "",
                        "repairOwner": pointer.get("repairOwner") or "",
                    },
                    "sourceHash": item.get("sourceHash"),
                    "role": item.get("role") or "",
                }
            )
        return rows

    def _evidence_rows(self, projection: dict) -> list[dict]:
        rows: list[dict] = []
        for item in projection["evidence"]:
            if not isinstance(item, dict):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="evidence is invalid")
            evidence_id = item.get("evidenceId")
            if not isinstance(evidence_id, str) or not evidence_id:
                raise WorkbenchError(MISSING_DEPENDENCY, detail="evidence id is missing")
            rows.append(
                {
                    "objectType": "evidence",
                    "objectId": evidence_id,
                    "kind": item.get("kind") or "unknown",
                    "hash": item.get("hash"),
                    "mediaType": item.get("mediaType") or "",
                    "criterionId": item.get("criterionId"),
                    "role": item.get("role") or "",
                    "capturedAt": item.get("capturedAt") or "",
                }
            )
        return rows

    def _summarize(self, project_id: str, projection: dict, path: Path) -> dict:
        rows = [
            *self._criterion_rows(projection),
            *self._finding_rows(projection),
            *self._evidence_rows(projection),
        ]
        return {
            "runId": projection["runId"],
            "owner": projection["owner"],
            "runner": projection["runner"],
            "generatedAt": projection["generatedAt"],
            "objectCount": len(rows),
            "criteria": len(projection["criteria"]),
            "findings": len(projection["findings"]),
            "evidence": len(projection["evidence"]),
            "verdictSource": "owner",
            "projectionHash": digest_bytes(path.read_bytes()),
            "state": "fresh",
        }

    def _detailed(self, project_id: str, projection: dict, path: Path) -> dict:
        criteria = self._criterion_rows(projection)
        findings = self._finding_rows(projection)
        evidence = self._evidence_rows(projection)
        return {
            **self._summarize(project_id, projection, path),
            "criteria": [self._with_confirmation(project_id, projection, row) for row in criteria],
            "findings": [self._with_confirmation(project_id, projection, row) for row in findings],
            "evidence": [self._with_confirmation(project_id, projection, row) for row in evidence],
            "note": (
                "以下判据与证据来自原 owner 的投影，工作台不重新裁决；"
                "确认只绑定到当时的对象 hash，源变化后旧确认即失效。"
            ),
        }

    def _with_confirmation(self, project_id: str, projection: dict, row: dict) -> dict:
        confirmation = self.store.find_owner_confirmation(
            project_id=project_id,
            run_id=projection["runId"],
            object_type=row["objectType"],
            object_id=row["objectId"],
            source_hash=str(row.get("sourceHash") or ""),
            roles=tuple(sorted(CONFIRMATION_ROLES)),
        )
        row = dict(row)
        row["confirmation"] = (
            {
                "confirmationId": confirmation["confirmation_id"],
                "role": confirmation["role"],
                "confirmedAt": confirmation["created_at"],
                "confirmedBy": confirmation["confirmed_by"],
            }
            if confirmation is not None
            else None
        )
        return row

    # -- confirmations ---------------------------------------------------

    def list_confirmations(self, project_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return {
            "confirmations": [
                {
                    "confirmationId": row["confirmation_id"],
                    "runId": row["run_id"],
                    "objectType": row["object_type"],
                    "objectId": row["object_id"],
                    "sourceHash": row["source_hash"],
                    "role": row["role"],
                    "note": row["note"],
                    "confirmedBy": row["confirmed_by"],
                    "createdAt": row["created_at"],
                }
                for row in self.store.project_owner_confirmations(project_id)
            ]
        }

    def confirm(
        self,
        project_id: str,
        *,
        run_id: object,
        object_type: object,
        object_id: object,
        source_hash: object,
        role: object,
        note: object = None,
        operation: Operation,
    ) -> dict:
        """Bind a human confirmation to one object hash and semantic role.

        The hash must match what the owner projection currently states, so a
        confirmation never survives a change to the object it was given for.
        """
        replayed = self.service._replay(operation, kind="owner-confirmation", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if not isinstance(run_id, str) or not run_id:
            raise WorkbenchError(INVALID_INPUT, detail="run id is required")
        if object_type not in OBJECT_TYPES:
            raise WorkbenchError(INVALID_INPUT, detail="unknown object type")
        if not isinstance(object_id, str) or not object_id:
            raise WorkbenchError(INVALID_INPUT, detail="object id is required")
        if not isinstance(source_hash, str) or not source_hash:
            # An unhashed object cannot be confirmed: there is nothing to
            # bind the decision to.
            raise WorkbenchError(INVALID_INPUT, detail="source hash is required")
        if role not in CONFIRMATION_ROLES:
            raise WorkbenchError(INVALID_INPUT, detail="unknown confirmation role")
        projection = self._projection_for(project_id, run_id)
        rows = [
            *self._criterion_rows(projection),
            *self._finding_rows(projection),
            *self._evidence_rows(projection),
        ]
        match = next(
            (
                row
                for row in rows
                if row["objectType"] == object_type and row["objectId"] == object_id
            ),
            None,
        )
        if match is None:
            raise WorkbenchError(INVALID_TARGET, detail="unknown owner object")
        current = str(match.get("sourceHash") or "")
        if not current or current != source_hash:
            raise WorkbenchError(
                STALE_EVIDENCE, detail="the object changed since it was shown"
            )
        confirmation_id = str(uuid.uuid4())
        now = self._now()
        project = self.service.require_project(project_id, scope="read")

        def apply() -> tuple[dict, int]:
            self.store.insert_owner_confirmation(
                confirmation_id=confirmation_id,
                project_id=project_id,
                run_id=run_id,
                object_type=object_type,
                object_id=object_id,
                source_hash=source_hash,
                role=role,
                note=str(note or "")[:500],
                confirmed_by=str(project["projectId"]),
                now=now,
            )
            result = {
                "confirmationId": confirmation_id,
                "runId": run_id,
                "objectType": object_type,
                "objectId": object_id,
                "sourceHash": source_hash,
                "role": role,
                "note": str(note or "")[:500],
                "createdAt": now,
                "verdictSource": "owner",
                "noteOverride": False,
            }
            return result, 0

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="owner-confirmation",
                entity_id=confirmation_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _projection_for(self, project_id: str, run_id: str) -> dict:
        root = self._root(project_id)
        path = self._projection_path(root, str(run_id))
        if not path.is_file():
            raise WorkbenchError(INVALID_TARGET, detail="unknown run projection")
        return self._parse_projection(_read_json(path), expected_project=project_id)

    # -- verified publication -------------------------------------------

    def publish_verified(
        self,
        project_id: str,
        asset_id: str,
        *,
        run_id: object,
        object_id: object,
        role: object = "owner-verified",
        operation: Operation,
    ) -> dict:
        """Publish requiring an owner confirmation for the exact content."""
        replayed = self.service._replay(
            operation, kind="owner-verified-publish", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if role not in CONFIRMATION_ROLES:
            raise WorkbenchError(INVALID_INPUT, detail="unknown confirmation role")
        projection = self._projection_for(project_id, str(run_id))
        rows = [
            *self._criterion_rows(projection),
            *self._finding_rows(projection),
            *self._evidence_rows(projection),
        ]
        match = next(
            (
                row
                for row in rows
                if row["objectType"] == "criterion" and row["objectId"] == object_id
            ),
            None,
        )
        if match is None:
            raise WorkbenchError(INVALID_TARGET, detail="unknown criterion")
        return self._publish_with_confirmation(
            project_id,
            asset_id,
            run_id=str(run_id),
            object_id=str(object_id),
            role=str(role),
            criterion=match,
            operation=operation,
        )

    def _publish_with_confirmation(
        self,
        project_id: str,
        asset_id: str,
        *,
        run_id: str,
        object_id: str,
        role: str,
        criterion: dict,
        operation: Operation,
    ) -> dict:
        draft = self.store.draft(asset_id)
        if draft is None or self.store.asset(asset_id) is None:
            raise WorkbenchError(INVALID_TARGET)
        manifest = json.loads(draft["attributes_json"]).get("manifest", [])
        if not manifest:
            raise WorkbenchError(MISSING_DEPENDENCY)
        content_hash = manifest[0]["contentHash"]
        # The owner's CURRENT fact must still verify this exact content: a
        # passing criterion whose source hash is the content being published.
        # A changed verdict or a re-run that moved the hash makes the earlier
        # confirmation stale, so the verified capability is refused rather
        # than published on an out-of-date Pass.
        if criterion.get("verdict") != "pass":
            raise WorkbenchError(
                STALE_EVIDENCE, detail="the owner criterion is no longer passing"
            )
        if str(criterion.get("sourceHash") or "") != content_hash:
            raise WorkbenchError(
                STALE_EVIDENCE,
                detail="the owner criterion no longer matches this content",
            )
        confirmation = self.store.find_owner_confirmation(
            project_id=project_id,
            run_id=run_id,
            object_type="criterion",
            object_id=object_id,
            source_hash=content_hash,
            roles=(role,),
        )
        if confirmation is None:
            # No bound confirmation for this content: the verified
            # capability cannot be published.
            raise WorkbenchError(
                STALE_EVIDENCE,
                detail="no confirmation matches this content hash",
            )
        outcome = self.assets.publish_revision(
            project_id,
            asset_id,
            operation=operation,
            verified_by={
                "confirmationId": confirmation["confirmation_id"],
                "role": confirmation["role"],
                "sourceHash": content_hash,
                "runId": run_id,
                "objectId": object_id,
                "confirmedAt": confirmation["created_at"],
            },
        )
        outcome["result"]["verifiedBy"] = {
            "confirmationId": confirmation["confirmation_id"],
            "role": confirmation["role"],
            "runId": run_id,
            "objectId": object_id,
        }
        return outcome

    # -- backflow --------------------------------------------------------

    def backflow_candidate(
        self,
        project_id: str,
        *,
        run_id: object,
        object_id: object,
        name: object,
        object_type: object = "criterion",
        operation: Operation,
    ) -> dict:
        """Create a *candidate* asset from an owner fact.

        The candidate is a draft with a typed locator back to the run; the
        maintainer completes it and publishes separately. The owner's run is
        not touched, and the candidate never claims the run's verdict.
        """
        replayed = self.service._replay(operation, kind="owner-backflow", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if object_type not in OBJECT_TYPES:
            raise WorkbenchError(INVALID_INPUT, detail="unknown object type")
        if not isinstance(name, str) or not name.strip():
            raise WorkbenchError(INVALID_INPUT, detail="name is required")
        projection = self._projection_for(project_id, str(run_id))
        rows = [
            *self._criterion_rows(projection),
            *self._finding_rows(projection),
            *self._evidence_rows(projection),
        ]
        match = next(
            (
                row
                for row in rows
                if row["objectType"] == object_type and row["objectId"] == object_id
            ),
            None,
        )
        if match is None:
            raise WorkbenchError(INVALID_TARGET, detail="unknown owner object")
        if object_type == "criterion" and match.get("verdict") == "pass":
            # A passing criterion is not a reason to fork a new asset.
            raise WorkbenchError(
                INVALID_INPUT, detail="a passing criterion is not a backflow candidate"
            )
        definition = {
            "name": name.strip()[:120],
            "description": (
                f"来自 {projection['owner']} run {projection['runId']} 的"
                f"{object_type} {object_id} 回流候选；需维护者补全后发布。"
            ),
            "props": [],
            "variants": [],
            "states": [],
            "slots": [],
            "constraints": {},
            "dependencies": {"tokens": [], "components": []},
            "docs": "",
            "tree": None,
            "candidate": None,
        }
        created = self.components.create_component(
            project_id,
            name=definition["name"],
            definition=definition,
            operation=Operation(
                operation_id=f"{operation.operation_id}:component",
                payload={"action": "components", "name": definition["name"]},
            ),
        )["result"]
        locator = {
            "kind": "owner-run",
            "projectId": project_id,
            "runId": projection["runId"],
            "objectType": object_type,
            "objectId": match["objectId"],
            "sourceHash": match.get("sourceHash"),
            "owner": projection["owner"],
            "verdict": match.get("verdict"),
            "role": match.get("role") or "",
        }
        draft = self.store.draft(created["assetId"])
        attributes = json.loads(draft["attributes_json"])
        attributes["sourceLocators"] = [locator]
        attributes["warnings"] = [
            "回流候选：发布前需维护者补全公开面；原 run 的判据不因本候选改变。"
        ]
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.update_draft(
                asset_id=created["assetId"],
                tags=[],
                attributes=attributes,
                now=now,
            )
            counter = self.store.bump_asset_counter(asset_id=created["assetId"], now=now)
            payload = self.assets.asset_detail(project_id, created["assetId"])["asset"]
            payload["sourceLocator"] = locator
            payload["runVerdictUnchanged"] = True
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="owner-backflow",
                entity_id=created["assetId"],
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- helpers shared with other modules ------------------------------

    def locator_digest(self, locator: dict) -> str:
        """A stable digest over the typed locator that identifies one object."""
        if not isinstance(locator, dict):
            raise WorkbenchError(INVALID_INPUT)
        for key in ("runId", "objectType", "objectId", "sourceHash"):
            if not locator.get(key):
                raise WorkbenchError(INVALID_INPUT, detail=f"locator lacks {key}")
        return payload_digest(
            {
                "runId": locator["runId"],
                "objectType": locator["objectType"],
                "objectId": locator["objectId"],
                "sourceHash": locator["sourceHash"],
            }
        )

    def freshness(self, project_id: str, locator: dict) -> dict:
        """Whether the referenced owner fact is still the one that was read."""
        self.service.require_project(project_id, scope="read")
        if not isinstance(locator, dict) or not locator.get("runId"):
            raise WorkbenchError(INVALID_INPUT)
        root = self._root(project_id)
        path = self._projection_path(root, str(locator["runId"]))
        if not path.is_file():
            return {"state": "unknown", "reason": "run projection is gone"}
        projection = self._parse_projection(
            _read_json(path), expected_project=project_id
        )
        rows = [
            *self._criterion_rows(projection),
            *self._finding_rows(projection),
            *self._evidence_rows(projection),
        ]
        match = next(
            (
                row
                for row in rows
                if row["objectType"] == locator.get("objectType")
                and row["objectId"] == locator.get("objectId")
            ),
            None,
        )
        if match is None:
            return {"state": "unknown", "reason": "object is gone from the run"}
        current = str(match.get("sourceHash") or "")
        if not current:
            return {"state": "unknown", "reason": "object has no source hash"}
        if current != locator.get("sourceHash"):
            return {
                "state": "stale",
                "reason": "the object changed since it was referenced",
                "currentSourceHash": current,
            }
        return {"state": "fresh", "currentSourceHash": current}

    def require_fresh(self, project_id: str, locator: dict) -> dict:
        status = self.freshness(project_id, locator)
        if status["state"] != "fresh":
            raise WorkbenchError(
                STALE_EVIDENCE, detail=f"owner fact is {status['state']}"
            )
        return status


__all__ = [
    "CONFIRMATION_ROLES",
    "OBJECT_TYPES",
    "PROJECTION_ROOT",
    "PROJECTION_VERSION",
    "OwnerProjectionService",
]
