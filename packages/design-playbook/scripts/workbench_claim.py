#!/usr/bin/env python3
"""Claim one workbench task with the credential the maintainer's host holds.

R11: the slash side claims a request through the same typed Workbench API the
browser uses, using the OS-protected credential record the service wrote for
that request. The credential is read from the local record, never passed on a
command line, and the claim returns a lease the host then heartbeats.

This is an argument and transport layer. The service owns the state machine,
the lease, and every acceptance rule; this module decides nothing about what
a task may do.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPTS_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts.project_target import (  # noqa: E402
    ServiceUnavailable,
    _workbench_data_dir,
    read_session_record,
)

CAPABILITY_HEADER = "X-Workbench-Capability"
CLAIM_TIMEOUT_SECONDS = 15


class ClaimError(Exception):
    """Operator-visible failure with the reason the service gave."""


def claim_record_path(data_dir: Path | str, request_id: str) -> Path:
    """The private per-request credential the service minted at consent."""
    return Path(data_dir) / "session" / f"claim-{request_id}.json"


def read_claim_record(data_dir: Path | str, request_id: str) -> dict:
    path = claim_record_path(data_dir, request_id)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise ClaimError(
            f"no claim record for {request_id}: the maintainer must confirm the "
            "send scope first"
        ) from None
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        raise ClaimError("the claim record is not readable") from None
    for field in ("token", "projectId", "requestId"):
        if not isinstance(record, dict) or not record.get(field):
            raise ClaimError(f"the claim record is missing {field}")
    return record


def request_task(
    *,
    request_id: str,
    data_dir: Path | str | None = None,
    verb: str | None = None,
    payload: dict | None = None,
    operation_id: str | None = None,
    opener=urllib.request.urlopen,
) -> dict:
    """Read or report one task using only its protected claim credential."""
    if verb not in (None, "claim", "heartbeat", "result", "fail"):
        raise ClaimError("unsupported agent task verb")
    root = Path(data_dir) if data_dir is not None else _workbench_data_dir()
    record = read_claim_record(root, request_id)
    if record["requestId"] != request_id:
        raise ClaimError("the claim record belongs to a different request")
    try:
        session_record = read_session_record(root)
    except ServiceUnavailable as error:
        raise ClaimError(str(error)) from None
    authority = session_record["authority"]
    project_url = f"{authority}/api/v1/projects/{record['projectId']}"
    data = None
    if verb is not None:
        fields = payload or {}
        body = {
            **fields,
            "operation": {
                "operationId": operation_id or f"{verb}-{uuid.uuid4()}",
                "payload": {"action": verb, "requestId": request_id, **fields},
            },
        }
        data = json.dumps(body).encode("utf-8")
        url = f"{project_url}/actions/requests/{request_id}/{verb}"
    else:
        url = f"{project_url}/requests/{request_id}"
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if verb else "GET",
        headers={
            "Content-Type": "application/json",
            CAPABILITY_HEADER: record["token"],
        },
    )
    try:
        with opener(request, timeout=CLAIM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ClaimError(f"the service refused the {verb or 'request read'}: {detail}") from None
    except (urllib.error.URLError, OSError) as error:
        raise ClaimError(f"the workbench service is not reachable: {error}") from None


def claim_request(
    *,
    request_id: str,
    data_dir: Path | str | None = None,
    lease_seconds: int | None = None,
    operation_id: str | None = None,
    opener=urllib.request.urlopen,
) -> dict:
    """Claim one request and return the service's lease payload."""
    return request_task(
        request_id=request_id,
        data_dir=data_dir,
        verb="claim",
        payload={"leaseSeconds": lease_seconds} if lease_seconds is not None else {},
        operation_id=operation_id,
        opener=opener,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Claim one workbench task with its OS-protected credential."
    )
    parser.add_argument("--request", required=True, help="The request id to claim.")
    parser.add_argument("--data-dir", default=None, help="The workbench data directory.")
    parser.add_argument("--lease-seconds", type=int, default=None)
    parser.add_argument("--operation-id", default=None)
    args = parser.parse_args(argv)
    try:
        payload = claim_request(
            request_id=args.request,
            data_dir=args.data_dir,
            lease_seconds=args.lease_seconds,
            operation_id=args.operation_id,
        )
    except ClaimError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
