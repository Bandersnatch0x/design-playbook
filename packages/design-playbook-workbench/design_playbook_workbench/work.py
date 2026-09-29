"""Bounded Agent work requests: consent, leases, results, cancel (R11).

The workbench never calls a model and never runs a shell. It records a
request the maintainer consented to, mints a credential bound to *that*
request, and accepts results only from a live lease of the current attempt.
Everything else is a typed refusal:

- a claim, heartbeat, or result from a retired capability, a different
  request, another project, or a previous boot is refused;
- a lease is 60 s and a heartbeat 15 s; an expired lease marks the attempt
  ``interrupted`` and its late result is refused instead of accepted;
- cancelling stops accepting new write-backs immediately; the request is
  only ``cancelled`` once the host confirms it stopped;
- a result becomes an ordinary change proposal (R06); ``applied`` never
  means ``verified``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .credentials import remove_private_file, write_private_json
from .errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    STALE_EVIDENCE,
    UNAUTHORIZED,
    WorkbenchError,
)
from .orchestration import OrchestrationService
from .proposals import ProposalService
from .service import Operation, WorkbenchService, payload_digest, utc_now
from .session import WorkbenchSession
from .store import Store, WorkbenchDataDirectory

LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 15
MAX_OPEN_REQUESTS = 20
MAX_PLAN_STEPS = 20
MAX_ALLOWED_ACTIONS = 10
MAX_ARTIFACTS = 200

TARGET_STACKS = frozenset({"static-html", "react-ts"})

#: Actions the maintainer can grant. The workbench enforces exactly these;
#: no instruction inside an asset can add one.
ALLOWED_ACTIONS = frozenset(
    {
        "read-context",
        "propose-source",
        "add-dependency",
        "run-build",
        "run-tests",
        "run-preview",
    }
)

#: States a request can be in (R11). ``proposal-ready`` covers both a
#: submitted result and a result whose proposal was already applied; the
#: read payload distinguishes ``applied`` from ``verified``.
REQUEST_STATES = frozenset(
    {
        "awaiting-consent",
        "waiting-for-agent",
        "running",
        "proposal-ready",
        "failed",
        "cancel-requested",
        "cancelled",
        "interrupted",
        "rejected",
    }
)

ATTEMPT_STATES = frozenset(
    {
        "waiting",
        "running",
        "interrupted",
        "failed",
        "cancelled",
        "result-submitted",
        "rejected",
    }
)

RESULT_FIELDS = frozenset(
    {
        "summary",
        "changes",
        "dependencies",
        "entrypoints",
        "artifacts",
        "runReceipt",
        "notes",
        "targetStack",
    }
)


def _wall_clock() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


class WorkRequestService:
    """Work requests, lease-checked attempts, results, and cancellation."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        proposals: ProposalService,
        orchestration: OrchestrationService,
        session: WorkbenchSession,
        data_dir: WorkbenchDataDirectory,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.proposals = proposals
        self.orchestration = orchestration
        self.session = session
        self.data_dir = data_dir
        self._now = now_fn if now_fn is not None else utc_now

    # -- shared plumbing ------------------------------------------------

    def _moment(self) -> datetime:
        """The current moment from the injected clock (same source as the
        stored timestamps), so lease expiry and records cannot disagree."""
        parsed = _parse_iso(self._now())
        return parsed if parsed is not None else _wall_clock()

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

    def claim_record_path(self, request_id: str) -> Path:
        """The private claim credential for one request (never in a payload)."""
        return self.data_dir.session_dir / f"claim-{request_id}.json"

    def _request_row(self, project_id: str, request_id: str) -> dict:
        row = self.store.work_request(request_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        return row

    def _expired(self, row: dict) -> bool:
        deadline = _parse_iso(row["expires_at"])
        if deadline is None:
            return False
        return self._moment() > deadline

    def _attempt_payload(self, row: dict) -> dict:
        return {
            "attemptId": row["attempt_id"],
            "sequence": int(row["sequence"]),
            "state": row["state"],
            "leaseId": row["lease_id"],
            "leaseExpiresAt": row["lease_expires_at"],
            "progress": json.loads(row["progress_json"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "resultDigest": row["result_digest"],
            "proposalId": row["proposal_id"],
            "capabilityId": row["capability_id"],
            "bootId": row["boot_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _request_payload(self, row: dict) -> dict:
        attempt = self.store.latest_work_attempt(row["request_id"])
        state = row["state"]
        applied = False
        verified = False
        if state == "proposal-ready" and attempt is not None:
            proposal_id = attempt["proposal_id"]
            if proposal_id:
                proposal = self.store.proposal(proposal_id)
                if proposal is not None and proposal["state"] == "applied":
                    state = "applied"
                    applied = True
        return {
            "requestId": row["request_id"],
            "projectId": row["project_id"],
            "title": row["title"],
            "goal": row["goal"],
            "targetStack": row["target_stack"],
            "plan": json.loads(row["plan_json"]),
            "allowedActions": json.loads(row["allowed_actions_json"]),
            "resultSchema": json.loads(row["result_schema_json"]),
            "contextSelectionId": row["context_selection_id"],
            "contextDigest": row["context_digest"],
            "bindingGeneration": int(row["binding_generation"]),
            "state": state,
            "storedState": row["state"],
            "capabilityId": row["capability_id"],
            "handoffCommand": row["handoff_command"],
            "expiresAt": row["expires_at"],
            "counter": int(row["counter"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "attempt": self._attempt_payload(attempt) if attempt else None,
            "applied": applied,
            "verified": verified,
        }

    # -- reads ----------------------------------------------------------

    def list_for_project(self, project_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return {
            "requests": [
                self._request_payload(row)
                for row in self.store.project_work_requests(project_id)
            ]
        }

    def detail(self, project_id: str, request_id: str, *, principal: object = None) -> dict:
        if principal is not None and getattr(principal, "request_id", None) is not None:
            self._require_agent(request_id, principal, scope="read")
        self.service.require_project(project_id, scope="read")
        row = self._request_row(project_id, request_id)
        payload = self._request_payload(row)
        selection = self.store.context_selection(row["context_selection_id"])
        payload["context"] = (
            self.orchestration._context_payload(selection) if selection else None
        )
        payload["attempts"] = [
            self._attempt_payload(item)
            for item in self.store.request_work_attempts(request_id)
        ]
        payload["contextStillConfirmed"] = bool(
            selection is not None
            and selection["state"] == "confirmed"
            and selection["digest"] == payload["contextDigest"]
        )
        return {"request": payload}

    # -- maintainer writes ----------------------------------------------

    def create(
        self,
        project_id: str,
        *,
        title: object,
        goal: object,
        target_stack: object,
        plan: object = None,
        allowed_actions: object = None,
        result_schema: object = None,
        context_selection_id: object,
        expires_in_seconds: object = None,
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(operation, kind="work-request-create", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if not isinstance(title, str) or not title.strip():
            raise WorkbenchError(INVALID_INPUT, detail="title is required")
        if not isinstance(goal, str) or not goal.strip():
            raise WorkbenchError(INVALID_INPUT, detail="goal is required")
        if target_stack not in TARGET_STACKS:
            raise WorkbenchError(
                INVALID_INPUT, detail="target stack must be static-html or react-ts"
            )
        if not isinstance(context_selection_id, str) or not context_selection_id:
            raise WorkbenchError(INVALID_INPUT, detail="a context selection is required")
        selection = self.store.context_selection(context_selection_id)
        if selection is None or selection["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        if selection["state"] != "confirmed":
            # R11: the send scope is confirmed before an Agent ever sees it.
            raise WorkbenchError(
                MISSING_DEPENDENCY, detail="context selection is not confirmed"
            )
        if len(self.store.project_work_requests(project_id)) >= MAX_OPEN_REQUESTS:
            raise WorkbenchError(
                LIMIT_EXCEEDED, detail=f"最多 {MAX_OPEN_REQUESTS} 个任务请求。"
            )
        plan_value = self._parse_plan(plan)
        actions = self._parse_actions(allowed_actions)
        schema = self._parse_result_schema(result_schema)
        ttl = 24 * 3600 if expires_in_seconds in (None, "") else int(expires_in_seconds)
        if ttl <= 0:
            raise WorkbenchError(INVALID_INPUT, detail="expiry must be positive")
        project = self.service.require_project(project_id, scope="read")
        request_id = str(uuid.uuid4())
        now = self._now()
        expires_at = _iso(self._moment() + timedelta(seconds=ttl))

        def apply() -> tuple[dict, int]:
            self.store.insert_work_request(
                request_id=request_id,
                project_id=project_id,
                title=title.strip()[:200],
                goal=goal.strip()[:2000],
                target_stack=target_stack,
                plan=plan_value,
                allowed_actions=actions,
                result_schema=schema,
                context_selection_id=context_selection_id,
                context_digest=selection["digest"],
                binding_generation=int(project["bindingGeneration"]),
                state="awaiting-consent",
                expires_at=expires_at,
                now=now,
            )
            return self._request_payload(self.store.work_request(request_id)), 0

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-create",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _parse_plan(self, raw: object) -> dict:
        plan = raw if isinstance(raw, dict) else {}
        reuse = plan.get("reuse") or []
        adapt = plan.get("adapt") or []
        new = plan.get("new") or []
        for value in (reuse, adapt, new):
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise WorkbenchError(INVALID_INPUT, detail="plan entries must be text")
        if len(reuse) + len(adapt) + len(new) > MAX_PLAN_STEPS:
            raise WorkbenchError(LIMIT_EXCEEDED, detail="plan has too many steps")
        return {"reuse": list(reuse), "adapt": list(adapt), "new": list(new)}

    def _parse_actions(self, raw: object) -> list[str]:
        actions = raw if isinstance(raw, list) else ["propose-source"]
        if not all(isinstance(item, str) for item in actions) or not actions:
            raise WorkbenchError(INVALID_INPUT, detail="allowed actions must be text")
        unknown = set(actions) - ALLOWED_ACTIONS
        if unknown:
            raise WorkbenchError(
                INVALID_INPUT, detail=f"unknown action: {sorted(unknown)[0]}"
            )
        if len(actions) > MAX_ALLOWED_ACTIONS:
            raise WorkbenchError(LIMIT_EXCEEDED, detail="too many allowed actions")
        return list(dict.fromkeys(actions))

    def _parse_result_schema(self, raw: object) -> dict:
        schema = raw if isinstance(raw, dict) else {"required": ["summary"]}
        required = schema.get("required") or ["summary"]
        if not isinstance(required, list) or not all(
            isinstance(item, str) and item for item in required
        ):
            raise WorkbenchError(INVALID_INPUT, detail="result schema is invalid")
        unknown = set(required) - RESULT_FIELDS
        if unknown:
            raise WorkbenchError(
                INVALID_INPUT, detail=f"unknown result field: {sorted(unknown)[0]}"
            )
        return {"required": list(dict.fromkeys(required))}

    def consent(
        self,
        project_id: str,
        request_id: str,
        *,
        digest: object,
        ttl_seconds: int | None = None,
        operation: Operation,
    ) -> dict:
        """Confirm the send scope and mint the request-bound credential."""
        replayed = self.service._replay(
            operation, kind="work-request-consent", entity_id=request_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._request_row(project_id, request_id)
        if row["state"] != "awaiting-consent":
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        if self._expired(row):
            raise WorkbenchError(STALE_EVIDENCE, detail="request already expired")
        if not isinstance(digest, str) or digest != row["context_digest"]:
            raise WorkbenchError(CONFLICT, detail="context digest does not match")
        selection = self.store.context_selection(row["context_selection_id"])
        if (
            selection is None
            or selection["state"] != "confirmed"
            or selection["digest"] != row["context_digest"]
        ):
            raise WorkbenchError(
                CONFLICT, detail="context selection changed; confirm it again"
            )
        token, capability_id = self.session.issue_request_capability(
            project_id=project_id,
            scopes=["read", "write"],
            request_id=request_id,
            ttl_seconds=ttl_seconds,
        )
        project = self.service.require_project(project_id, scope="read")
        command = (
            '/design-playbook:run-handoff project="{}" request="{}"'
        ).format(project["canonicalPath"], request_id)
        now = self._now()

        def apply() -> tuple[dict, int]:
            # The claim credential lives in the private data directory, so
            # the slash entry point reads it from the OS-protected record
            # instead of from a command line or a web payload.
            write_private_json(
                self.claim_record_path(request_id),
                {
                    "requestId": request_id,
                    "projectId": project_id,
                    "capabilityId": capability_id,
                    "token": token,
                    "expiresAt": row["expires_at"],
                    "handoffCommand": command,
                    "createdAt": now,
                },
            )
            counter = self.store.set_work_request_state(
                request_id=request_id,
                state="waiting-for-agent",
                capability_id=capability_id,
                handoff_command=command,
                now=now,
            )
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-consent",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def cancel(
        self, project_id: str, request_id: str, *, operation: Operation
    ) -> dict:
        """Ask for a stop: new write-backs are refused from here on."""
        replayed = self.service._replay(
            operation, kind="work-request-cancel", entity_id=request_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._request_row(project_id, request_id)
        if row["state"] in ("cancelled", "rejected", "applied"):
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.set_work_request_state(
                request_id=request_id, state="cancel-requested", now=now
            )
            attempt = self.store.latest_work_attempt(request_id)
            if attempt is not None and attempt["state"] in ("waiting", "running"):
                self.store.update_work_attempt(
                    attempt_id=attempt["attempt_id"], state="cancelled", now=now
                )
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-cancel",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def confirm_cancelled(
        self, project_id: str, request_id: str, *, operation: Operation
    ) -> dict:
        """Only a host confirmation turns a stop request into ``cancelled``."""
        replayed = self.service._replay(
            operation, kind="work-request-cancel-confirm", entity_id=request_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._request_row(project_id, request_id)
        if row["state"] != "cancel-requested":
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.set_work_request_state(
                request_id=request_id, state="cancelled", now=now
            )
            remove_private_file(self.claim_record_path(request_id))
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-cancel-confirm",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def retry(self, project_id: str, request_id: str, *, operation: Operation) -> dict:
        """A retry is a new attempt with a new capability; the old one dies."""
        replayed = self.service._replay(
            operation, kind="work-request-retry", entity_id=request_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._request_row(project_id, request_id)
        if row["state"] not in ("failed", "interrupted", "running", "waiting-for-agent"):
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        token, capability_id = self.session.issue_request_capability(
            project_id=project_id,
            scopes=["read", "write"],
            request_id=request_id,
        )
        now = self._now()

        def apply() -> tuple[dict, int]:
            write_private_json(
                self.claim_record_path(request_id),
                {
                    "requestId": request_id,
                    "projectId": project_id,
                    "capabilityId": capability_id,
                    "token": token,
                    "expiresAt": row["expires_at"],
                    "handoffCommand": row["handoff_command"],
                    "createdAt": now,
                    "retry": True,
                },
            )
            counter = self.store.set_work_request_state(
                request_id=request_id,
                state="waiting-for-agent",
                capability_id=capability_id,
                handoff_command=row["handoff_command"] or "",
                now=now,
            )
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-retry",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def reject(self, project_id: str, request_id: str, *, operation: Operation) -> dict:
        replayed = self.service._replay(
            operation, kind="work-request-reject", entity_id=request_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._request_row(project_id, request_id)
        if row["state"] != "proposal-ready":
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.set_work_request_state(
                request_id=request_id, state="rejected", now=now
            )
            attempt = self.store.latest_work_attempt(request_id)
            if attempt is not None:
                self.store.update_work_attempt(
                    attempt_id=attempt["attempt_id"], state="rejected", now=now
                )
            remove_private_file(self.claim_record_path(request_id))
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-request-reject",
                entity_id=request_id,
                project_id=project_id,
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- agent writes (request-bound capability) -------------------------

    def _require_agent(
        self, request_id: str, principal: object, *, scope: str = "write"
    ) -> dict:
        row = self.store.work_request(request_id)
        if row is None:
            raise WorkbenchError(INVALID_TARGET)
        permits = getattr(principal, "permits_request", None)
        if permits is None or not permits(request_id):
            raise WorkbenchError(UNAUTHORIZED)
        if not getattr(principal, "permits_project", None) or not principal.permits_project(
            row["project_id"], scope
        ):
            raise WorkbenchError(UNAUTHORIZED)
        if principal.capability_id != row["capability_id"]:
            # A retired capability (an earlier attempt) is not a live one.
            raise WorkbenchError(UNAUTHORIZED, detail="capability was replaced")
        if row["state"] in ("cancel-requested", "cancelled", "rejected"):
            raise WorkbenchError(CONFLICT, detail="request authority was revoked")
        if self._expired(row):
            raise WorkbenchError(STALE_EVIDENCE, detail="request expired")
        if scope == "read":
            if "read-context" not in json.loads(row["allowed_actions_json"]):
                raise WorkbenchError(UNAUTHORIZED)
            attempt = self.store.latest_work_attempt(request_id)
            if attempt is not None and attempt["state"] == "running":
                deadline = _parse_iso(attempt["lease_expires_at"])
                if deadline is None or self._moment() > deadline:
                    raise WorkbenchError(STALE_EVIDENCE, detail="lease expired")
        return row

    def _require_live_lease(
        self,
        row: dict,
        *,
        attempt_id: object,
        lease_id: object,
        sequence: object,
    ) -> dict:
        if row["state"] == "cancel-requested":
            raise WorkbenchError(CONFLICT, detail="cancellation was requested")
        if row["state"] in ("cancelled", "rejected"):
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise WorkbenchError(INVALID_INPUT, detail="attempt id is required")
        attempt = self.store.work_attempt(attempt_id)
        if attempt is None or attempt["request_id"] != row["request_id"]:
            raise WorkbenchError(INVALID_TARGET)
        if not isinstance(lease_id, str) or attempt["lease_id"] != lease_id:
            raise WorkbenchError(CONFLICT, detail="lease does not match")
        if attempt["state"] not in ("running",):
            raise WorkbenchError(CONFLICT, detail=f"attempt is {attempt['state']}")
        if not isinstance(sequence, int) or int(attempt["sequence"]) != int(sequence):
            # Out-of-order or duplicated agent traffic.
            raise WorkbenchError(CONFLICT, detail="attempt sequence does not match")
        if attempt["boot_id"] != self.session.boot_id:
            # A lease never survives a service restart.
            self._interrupt(row, attempt)
            raise WorkbenchError(
                STALE_EVIDENCE, detail="lease belongs to a previous service run"
            )
        deadline = _parse_iso(attempt["lease_expires_at"])
        if deadline is None or self._moment() > deadline:
            self._interrupt(row, attempt)
            raise WorkbenchError(STALE_EVIDENCE, detail="lease expired")
        return attempt

    def _interrupt(self, row: dict, attempt: dict) -> None:
        now = self._now()
        self.store.update_work_attempt(
            attempt_id=attempt["attempt_id"], state="interrupted", now=now
        )
        self.store.set_work_request_state(
            request_id=row["request_id"], state="interrupted", now=now
        )

    def claim(
        self,
        request_id: str,
        *,
        principal: object,
        lease_seconds: object = None,
        operation: Operation,
    ) -> dict:
        row = self._require_agent(request_id, principal)
        replayed = self.service._replay(
            operation, kind="work-claim", entity_id=request_id, project_id=row["project_id"])
        if replayed is not None:
            return replayed
        if row["state"] != "waiting-for-agent":
            raise WorkbenchError(CONFLICT, detail=f"request is {row['state']}")
        if self._expired(row):
            raise WorkbenchError(STALE_EVIDENCE, detail="request already expired")
        lease = LEASE_SECONDS if lease_seconds in (None, "") else int(lease_seconds)
        if lease <= 0 or lease > LEASE_SECONDS:
            raise WorkbenchError(
                INVALID_INPUT, detail=f"lease must be 1..{LEASE_SECONDS} seconds"
            )
        attempt_seq = len(self.store.request_work_attempts(request_id)) + 1
        attempt_id = str(uuid.uuid4())
        lease_id = str(uuid.uuid4())
        now = self._now()
        deadline = _iso(self._moment() + timedelta(seconds=lease))

        def apply() -> tuple[dict, int]:
            self.store.insert_work_attempt(
                attempt_id=attempt_id,
                request_id=request_id,
                sequence=attempt_seq,
                state="running",
                capability_id=row["capability_id"],
                now=now,
            )
            self.store.update_work_attempt(
                attempt_id=attempt_id,
                state="running",
                lease_id=lease_id,
                lease_expires_at=deadline,
                boot_id=self.session.boot_id,
                progress={"phase": "claimed"},
                now=now,
            )
            counter = self.store.set_work_request_state(
                request_id=request_id, state="running", now=now
            )
            payload = self._request_payload(self.store.work_request(request_id))
            payload["lease"] = {
                "attemptId": attempt_id,
                "leaseId": lease_id,
                "sequence": attempt_seq,
                "expiresAt": deadline,
                "heartbeatSeconds": HEARTBEAT_SECONDS,
            }
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-claim",
                entity_id=request_id,
                project_id=row["project_id"],
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def heartbeat(
        self,
        request_id: str,
        *,
        attempt_id: object,
        lease_id: object,
        sequence: object,
        progress: object = None,
        principal: object,
        operation: Operation,
    ) -> dict:
        row = self._require_agent(request_id, principal)
        replayed = self.service._replay(
            operation, kind="work-heartbeat", entity_id=request_id, project_id=row["project_id"])
        if replayed is not None:
            return replayed
        attempt = self._require_live_lease(
            row, attempt_id=attempt_id, lease_id=lease_id, sequence=sequence
        )
        if progress is not None and not isinstance(progress, dict):
            raise WorkbenchError(INVALID_INPUT, detail="progress must be an object")
        lease = LEASE_SECONDS
        now = self._now()
        deadline = _iso(self._moment() + timedelta(seconds=lease))

        def apply() -> tuple[dict, int]:
            self.store.update_work_attempt(
                attempt_id=attempt["attempt_id"],
                state="running",
                lease_id=lease_id,
                lease_expires_at=deadline,
                boot_id=self.session.boot_id,
                progress=progress if isinstance(progress, dict) else None,
                now=now,
            )
            payload = self._request_payload(self.store.work_request(request_id))
            payload["lease"] = {
                "attemptId": attempt["attempt_id"],
                "leaseId": lease_id,
                "sequence": int(attempt["sequence"]),
                "expiresAt": deadline,
                "heartbeatSeconds": HEARTBEAT_SECONDS,
            }
            return payload, int(row["counter"])

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-heartbeat",
                entity_id=request_id,
                project_id=row["project_id"],
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def submit_result(
        self,
        request_id: str,
        *,
        attempt_id: object,
        lease_id: object,
        sequence: object,
        result: object,
        principal: object,
        operation: Operation,
    ) -> dict:
        row = self._require_agent(request_id, principal)
        replayed = self.service._replay(
            operation, kind="work-result", entity_id=request_id, project_id=row["project_id"])
        if replayed is not None:
            return replayed
        attempt = self._require_live_lease(
            row, attempt_id=attempt_id, lease_id=lease_id, sequence=sequence
        )
        if not isinstance(result, dict) or set(result) - RESULT_FIELDS:
            raise WorkbenchError(INVALID_INPUT, detail="unknown result field")
        schema = json.loads(row["result_schema_json"])
        missing = [key for key in schema.get("required", []) if key not in result]
        if missing:
            raise WorkbenchError(
                INVALID_INPUT, detail=f"result is missing: {missing[0]}"
            )
        target = result.get("targetStack") or row["target_stack"]
        if target != row["target_stack"]:
            raise WorkbenchError(
                INVALID_INPUT, detail="result target stack does not match the request"
            )
        changes = result.get("changes", [])
        if not isinstance(changes, list):
            raise WorkbenchError(INVALID_INPUT, detail="changes must be a list")
        artifacts = result.get("artifacts", [])
        if not isinstance(artifacts, list) or len(artifacts) > MAX_ARTIFACTS:
            raise WorkbenchError(INVALID_INPUT, detail="artifacts are invalid")
        dependencies = result.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise WorkbenchError(INVALID_INPUT, detail="dependencies must be a list")
        allowed = json.loads(row["allowed_actions_json"])
        if changes and "propose-source" not in allowed:
            raise WorkbenchError(UNAUTHORIZED, detail="source proposal was not granted")
        if dependencies and "add-dependency" not in allowed:
            raise WorkbenchError(UNAUTHORIZED, detail="dependency change was not granted")
        entrypoints = result.get("entrypoints", {})
        if not isinstance(entrypoints, dict):
            raise WorkbenchError(INVALID_INPUT, detail="entrypoints must be an object")
        digest = payload_digest(result)
        now = self._now()
        submitted = {
            "summary": str(result.get("summary") or "")[:2000],
            "changes": changes,
            "dependencies": dependencies,
            "entrypoints": entrypoints,
            "artifacts": artifacts,
            "runReceipt": result.get("runReceipt"),
            "notes": str(result.get("notes") or "")[:2000],
            "targetStack": target,
        }

        def apply() -> tuple[dict, int]:
            proposal_id: str | None = None
            if changes:
                # The result is a proposal, not a write: R06 owns approval.
                created = self.proposals.create(
                    row["project_id"],
                    changes=changes,
                    summary=f"Agent 结果：{row['title']}（attempt {attempt['sequence']}）",
                    dependency_changes=dependencies,
                    source_request=request_id,
                    operation=Operation(
                        operation_id=f"{operation.operation_id}:proposal",
                        payload={
                            "action": "proposals",
                            "projectId": row["project_id"],
                            "changes": changes,
                            "dependencyChanges": dependencies,
                        },
                    ),
                )["result"]
                proposal_id = created["proposalId"]
            self.store.update_work_attempt(
                attempt_id=attempt["attempt_id"],
                state="result-submitted",
                result=submitted,
                result_digest=digest,
                proposal_id=proposal_id,
                now=now,
            )
            counter = self.store.set_work_request_state(
                request_id=request_id, state="proposal-ready", now=now
            )
            payload = self._request_payload(self.store.work_request(request_id))
            payload["resultDigest"] = digest
            payload["proposalId"] = proposal_id
            payload["verified"] = False
            return payload, counter

        with self.store.transaction():
            result_payload, counter = apply()
            self._record(
                operation,
                kind="work-result",
                entity_id=request_id,
                project_id=row["project_id"],
                result=result_payload,
                counter=counter,
                now=now,
            )
        return {"result": result_payload, "replayed": False, "counter": counter}

    def fail_attempt(
        self,
        request_id: str,
        *,
        attempt_id: object,
        lease_id: object,
        sequence: object,
        reason: object = None,
        principal: object,
        operation: Operation,
    ) -> dict:
        """The Agent reports its own failure: the request stays retryable."""
        row = self._require_agent(request_id, principal)
        replayed = self.service._replay(
            operation, kind="work-fail", entity_id=request_id, project_id=row["project_id"])
        if replayed is not None:
            return replayed
        attempt = self._require_live_lease(
            row, attempt_id=attempt_id, lease_id=lease_id, sequence=sequence
        )
        now = self._now()
        note = reason if isinstance(reason, str) else ""

        def apply() -> tuple[dict, int]:
            self.store.update_work_attempt(
                attempt_id=attempt["attempt_id"],
                state="failed",
                progress={"phase": "failed", "note": note[:500]},
                now=now,
            )
            counter = self.store.set_work_request_state(
                request_id=request_id, state="failed", now=now
            )
            return self._request_payload(self.store.work_request(request_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self._record(
                operation,
                kind="work-fail",
                entity_id=request_id,
                project_id=row["project_id"],
                result=result,
                counter=counter,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}
