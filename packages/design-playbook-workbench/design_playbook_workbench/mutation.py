"""The one workbench mutation gate (R04, R06, T-086).

Every write in the workbench is one of two shapes: it changes an existing row,
or it creates one. Both need the same six steps in the same order - replay, load
the row, compare the expected counter, open the transaction, apply, record the
result. Written out at each call site those steps drift, and the drift is silent
because each one looks locally correct.

So they live here, behind two methods. A caller supplies what to load and what to
apply. It never decides whether a request is a replay, never compares counters
itself, and never writes the ledger.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from .errors import CONFLICT, INVALID_INPUT, INVALID_TARGET, WorkbenchError
from .store import Store


@dataclass(frozen=True)
class Operation:
    """MutationEnvelope: unique ID, expected counter, confirmed payload."""

    operation_id: str
    payload: dict
    expected_counter: int | None = None

    @property
    def digest(self) -> str:
        return payload_digest(self.payload)


def payload_digest(payload: dict) -> str:
    """Stable digest of the confirmed payload (reason strings are stable)."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_operation(raw: object) -> Operation:
    """Parse one mutation envelope from a request body."""
    if not isinstance(raw, dict):
        raise WorkbenchError(INVALID_INPUT)
    operation_id = raw.get("operationId")
    if not isinstance(operation_id, str) or not _looks_like_token(operation_id):
        raise WorkbenchError(INVALID_INPUT)
    expected = raw.get("expectedCounter", None)
    if expected is not None and (
        isinstance(expected, bool) or not isinstance(expected, int) or expected < 0
    ):
        raise WorkbenchError(INVALID_INPUT)
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise WorkbenchError(INVALID_INPUT)
    return Operation(operation_id=operation_id, payload=payload, expected_counter=expected)


def _looks_like_token(value: str) -> bool:
    return 8 <= len(value) <= 128 and all(
        character.isalnum() or character in "-_." for character in value
    )


class MutationGate:
    """Replay, load, counter check, transaction, apply, record."""

    def __init__(self, store: Store, now: Callable[[], str]) -> None:
        self.store = store
        self._now = now

    def replay(
        self, operation: Operation, *, kind: str, entity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict | None:
        """The replay gate: the recorded result, or a conflict, or ``None``.

        A recorded mutation only replays when the operation id, the payload
        digest, the entity kind and -- for an operation that targets an
        existing entity -- the entity id all match. Reusing an operation id
        against a different target, kind, or payload is a conflict, never a
        replay of some other entity's success.
        """
        recorded = self.store.mutation(operation.operation_id)
        if recorded is None:
            return None
        if (
            recorded["payload_digest"] != operation.digest
            or recorded["entity_kind"] != kind
            or (entity_id is not None and recorded["entity_id"] != entity_id)
            or (project_id is not None and recorded["project_id"] != project_id)
        ):
            raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
        return {
            "result": json.loads(recorded["result_json"]),
            "counter": recorded["resulting_counter"],
            "replayed": True,
        }

    def existing(
        self,
        operation: Operation,
        *,
        kind: str,
        entity_id: str,
        project_id: str | None,
        load_row: Callable[[], dict | None],
        apply: Callable[[], tuple[dict, int]],
        authorize: Callable[[], None] | None = None,
        require_counter: bool = True,
        validate: Callable[[dict], None] | None = None,
    ) -> dict:
        """One write against a row that already exists.

        ``load_row`` is called inside the transaction and its ``counter`` is
        what the caller's ``expected_counter`` is checked against; a caller
        never reads the counter itself. A missing row is a bad target, not a
        server fault. ``apply`` returns ``(result, resulting_counter)``.

        ``authorize`` runs only for a fresh request, after the replay check:
        a retry of a write that already succeeded must get its recorded result
        even if the project has since been disconnected or its grant revoked.

        ``validate`` runs after the row loads and before the counter is
        compared, so a document whose own rules are broken reports that
        reason instead of a stale-counter one. Two call sites state that
        ordering as a rule; putting it in the gate's sequence is what keeps
        them from having to re-derive it.

        ``require_counter`` exists for the rows that have no optimistic-
        concurrency contract yet -- work requests, proposals, schemes and
        owner backflow. They are recorded with a counter but never compare
        one, and this round is not allowed to add that enforcement (T-127).
        Passing ``False`` keeps the gap exactly where it is; it does not close
        it. Every such call site names that ticket, so the gap stays greppable
        instead of being invisible.
        """
        replayed = self.replay(
            operation, kind=kind, entity_id=entity_id, project_id=project_id
        )
        if replayed is not None:
            return replayed
        if authorize is not None:
            authorize()
        with self.store.transaction():
            # Re-check inside the transaction: two concurrent requests with
            # the same counter can otherwise both pass the pre-check.
            if self.store.mutation(operation.operation_id) is not None:
                raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            row = load_row()
            if row is None:
                raise WorkbenchError(INVALID_TARGET)
            if validate is not None:
                validate(row)
            if require_counter:
                if operation.expected_counter is None:
                    raise WorkbenchError(
                        INVALID_INPUT, operation_id=operation.operation_id
                    )
                if operation.expected_counter != int(row["counter"]):
                    raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            result, new_counter = apply()
            self.record(
                operation, kind=kind, entity_id=entity_id, result=result,
                counter=new_counter, project_id=project_id,
            )
        return {"result": result, "counter": new_counter, "replayed": False}

    def record(
        self, operation: Operation, *, kind: str, entity_id: str, result: dict,
        counter: int | None, project_id: str | None = None,
    ) -> None:
        """Write the ledger row for one applied mutation.

        Exposed for the two writes that cannot run their work inside the
        transaction - sealing a backup and restoring one write whole archives -
        but still need the ledger write to be one implementation.
        """
        with self.store.transaction():
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind=kind,
                entity_id=entity_id,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, separators=(",", ":"), sort_keys=True),
                project_id=project_id,
                now=self._now(),
            )

    def create(
        self,
        operation: Operation,
        *,
        kind: str,
        entity_of: Callable[[dict], str],
        project_of: Callable[[dict], str | None],
        apply: Callable[[], dict],
        authorize: Callable[[], None] | None = None,
        counter: int | None = None,
        project_id: str | None = None,
    ) -> dict:
        """One write that creates its row; there is no counter to be stale against.

        ``entity_of`` and ``project_of`` name the new row after ``apply`` has
        produced it, so the ledger records the id the write actually made.
        ``authorize`` runs after the replay check, for the same reason as
        ``existing``. ``counter`` is what the ledger reports as the resulting
        counter; a create has no prior row to advance, so callers that report
        ``0`` pass it and callers that report nothing leave it ``None``.

        ``project_id`` is the target a caller already knows before the row
        exists, and it binds the replay the same way ``existing`` binds it: an
        operation id reused against another project is a conflict, never that
        project's success. It has to agree with what ``project_of`` records;
        a caller whose ledger row deliberately names no project leaves both
        out.
        """
        replayed = self.replay(operation, kind=kind, project_id=project_id)
        if replayed is not None:
            return replayed
        if authorize is not None:
            authorize()
        with self.store.transaction():
            if self.store.mutation(operation.operation_id) is not None:
                raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            result = apply()
            self.record(
                operation, kind=kind, entity_id=entity_of(result),
                result=result, counter=counter, project_id=project_of(result),
            )
        return {"result": result, "counter": counter, "replayed": False}
