"""The one owner for freezing an asset draft into a revision (R04, R07).

Publishing is one concept with several entry points: a plain asset publish, a
publish that declares dependency edges, a component or page publish whose
document must validate first, a tokens publish, and an owner-verified publish.
Written out at each entry point, the revision row, its closure checks, its
ledger row and its response drift apart -- and the drift is silent, because
each copy looks locally correct. One copy even allowed a revision with no
content, and another skipped the verified-capability rule.

So the freeze lives here, behind one method. A caller says which publication
this is (``kind``, its replay identity), what must hold before the freeze
(``prepare``), and -- only for a client-declared edge set -- the raw edges.
It never writes the revision row, never writes the ledger, and never assembles
the response after the fact: the recorded result is the response.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .blobs import BlobStore
from .errors import (
    CORRUPT_CONTENT,
    INVALID_INPUT,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from .service import Operation, WorkbenchService, utc_now
from .store import Store

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .assets import AssetService

MAX_CLOSURE_REVISIONS = 200

#: Capabilities that mean "someone verified this content". A revision cannot
#: claim one without a record bound to its exact content hash, environment,
#: and role -- on every publication path, not just the plain asset one.
VERIFIED_CAPABILITIES = frozenset({"runnable-verified", "native-editable"})


@dataclass(frozen=True)
class PublicationPlan:
    """What one publication's own rules add before the freeze.

    ``dependencies`` are the edges this revision declares; ``response`` holds
    the fields only that publication kind can compute (a validation verdict,
    a parsed definition). Both are merged into the recorded result, so a retry
    gets the first call's answer rather than a recomputation against newer
    state. ``verified_by`` is the owner record a verified capability needs.
    """

    dependencies: list[dict] = field(default_factory=list)
    response: dict = field(default_factory=dict)
    verified_by: dict | None = None


class PublicationService:
    """One revision-row construction, one closure check, one ledger row."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        blobs: BlobStore,
        assets: AssetService,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.blobs = blobs
        self._assets = assets
        self._now = now_fn if now_fn is not None else utc_now

    def publish(
        self,
        project_id: str,
        asset_id: str,
        *,
        operation: Operation,
        kind: str,
        prepare: Callable[[], PublicationPlan] | None = None,
        dependencies: object = None,
    ) -> dict:
        """Freeze the asset's current draft as its next revision.

        ``prepare`` runs after a replay has been answered and inside the
        transaction, before the counter comparison: an entry point's own
        document rules belong there, so a retry is never refused by state that
        moved after the write it is retrying. ``dependencies`` is the
        client-declared, still-unresolved edge list; a prepared plan supplies
        edges that are already resolved. Exactly one of the two is used.
        """
        held: dict = {}

        def validate(row: dict) -> None:
            plan = prepare() if prepare is not None else PublicationPlan()
            # One parser for both channels: a prepared edge set is already
            # resolved, a client-declared one is not, and both end in the
            # same recorded shape.
            raw = plan.dependencies if prepare is not None else dependencies
            declared = self._parse_dependencies(project_id, raw)
            # Completeness and cycles are checked before anything is written,
            # including the edge this publish is about to add.
            for edge in declared:
                self.closure(project_id, edge["revisionId"])
            if self.would_cycle(
                project_id=project_id, asset_id=asset_id, dependencies=declared
            ):
                raise WorkbenchError(MISSING_DEPENDENCY, detail="dependency cycle")
            held["plan"] = PublicationPlan(
                dependencies=declared,
                response=plan.response,
                verified_by=plan.verified_by,
            )

        def apply() -> tuple[dict, int]:
            plan = held["plan"]
            asset = self.store.asset(asset_id)
            draft = self.store.draft(asset_id)
            attributes = _loads(draft["attributes_json"]) if draft else {}
            manifest = attributes.get("manifest") or []
            if not manifest:
                # A publish freezes content. An asset with no manifest has
                # none to freeze, whichever entry point asked.
                raise WorkbenchError(MISSING_DEPENDENCY)
            for entry in manifest:
                # Publishing validates content completeness: every declared
                # blob must still be present and readable.
                if not self.blobs.verify(entry["contentHash"]):
                    raise WorkbenchError(CORRUPT_CONTENT)
            capabilities = list(attributes.get("capabilities", []))
            verified: list[dict] = []
            verified_by = plan.verified_by
            if VERIFIED_CAPABILITIES.intersection(capabilities):
                # A revision cannot claim a verified capability without a
                # verification record bound to revision, environment, and
                # hash.
                if not _is_bound_record(verified_by, manifest[0]["contentHash"]):
                    raise WorkbenchError(MISSING_DEPENDENCY)
                verified = [dict(verified_by)]
            revision_id = str(uuid.uuid4())
            now = self._now()
            self.store.insert_revision(
                revision_id=revision_id,
                asset_id=asset_id,
                revision_number=int(draft["revision_counter"]) + 1,
                content_hash=manifest[0]["contentHash"],
                carrier=attributes.get("carrier", asset["kind"]),
                capabilities=capabilities,
                dependencies=plan.dependencies,
                source_locators=self._assets.draft_locators(draft, project_id),
                manifest=manifest,
                origin={"kind": "publish"},
                verified=verified,
                now=now,
            )
            if plan.dependencies:
                self.store.insert_dependencies(
                    revision_id=revision_id, dependencies=plan.dependencies, now=now
                )
            refreshed = self.store.asset(asset_id)
            payload = self._assets.asset_payload(
                refreshed, draft, self.store.latest_revision(asset_id)
            )
            payload["dependencies"] = plan.dependencies
            payload.update(plan.response)
            if verified_by is not None:
                # The recorded result is the response: a retry gets this dict
                # back verbatim, so the verification record has to be part of
                # it rather than added to the caller's copy afterwards.
                payload["verifiedBy"] = {
                    key: verified_by[key]
                    for key in (
                        "confirmationId",
                        "role",
                        "runId",
                        "objectId",
                        "environment",
                    )
                }
            return payload, int(refreshed["counter"])

        return self.service.mutations.existing(
            operation,
            kind=kind,
            entity_id=asset_id,
            project_id=project_id,
            authorize=lambda: self.service.require_project(project_id, scope="write"),
            load_row=lambda: self._assets.owned_asset(project_id, asset_id),
            validate=validate,
            apply=apply,
        )

    # -- dependency closure ---------------------------------------------

    def closure(self, project_id: str, revision_id: str) -> list[dict]:
        """Resolve one revision's dependency closure, refusing cycles."""
        return self._closure(project_id=project_id, revision_id=revision_id)

    def _closure(
        self, *, project_id: str, revision_id: str, seen: set[str] | None = None
    ) -> list[dict]:
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

    def would_cycle(
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

    # -- declared edges ---------------------------------------------------

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


def _is_bound_record(verified_by: object, content_hash: str) -> bool:
    """True when a verification record names this content and where it ran."""
    return (
        isinstance(verified_by, dict)
        and verified_by.get("sourceHash") == content_hash
        and bool(verified_by.get("confirmationId"))
        and bool(verified_by.get("role"))
        # R03: a verification record names the environment it ran in. A hash
        # alone cannot tell a later reader where the check happened.
        and bool(verified_by.get("environment"))
    )


def _loads(text: object) -> object:
    if isinstance(text, (list, dict)):
        return text
    if not isinstance(text, str) or not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:  # pragma: no cover - stored by us
        return {}
