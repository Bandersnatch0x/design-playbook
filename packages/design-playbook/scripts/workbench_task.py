#!/usr/bin/env python3
"""Read and report a claimed task through the request-bound Workbench API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts.workbench_claim import ClaimError, request_task  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("read", "heartbeat", "result", "fail"))
    parser.add_argument("--request", required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--operation-id", default=None)
    parser.add_argument("--attempt-id")
    parser.add_argument("--lease-id")
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--stage", help="The stage actually observed by the host.")
    parser.add_argument("--count", type=int, help="The observed completed work count.")
    parser.add_argument("--result", help="Result JSON file, or - to read UTF-8 JSON from stdin.")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    payload: dict = {}
    if args.action != "read":
        if not args.attempt_id or not args.lease_id or args.sequence is None:
            parser.error("reports require --attempt-id, --lease-id and --sequence from the claim")
        payload = {
            "attemptId": args.attempt_id,
            "leaseId": args.lease_id,
            "sequence": args.sequence,
        }
    if args.action == "heartbeat":
        if not args.stage or not args.stage.strip() or args.count is None or args.count < 0:
            parser.error("heartbeat requires a non-empty --stage and a non-negative --count")
        payload["progress"] = {"stage": args.stage, "count": args.count}
    if args.action == "fail":
        if not args.reason or not args.reason.strip():
            parser.error("fail requires a non-empty --reason")
        payload["reason"] = args.reason
    if args.action == "result" and not args.result:
        parser.error("result requires --result <JSON-file> or --result -")
    try:
        if args.action == "result":
            raw = (
                sys.stdin.buffer.read().decode("utf-8")
                if args.result == "-"
                else Path(args.result).read_text(encoding="utf-8")
            )
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ClaimError("the result must be a JSON object")
            payload["result"] = result
        response = request_task(
            request_id=args.request,
            data_dir=args.data_dir,
            verb=None if args.action == "read" else args.action,
            payload=payload,
            operation_id=args.operation_id,
        )
    except (ClaimError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
