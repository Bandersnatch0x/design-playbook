"""The Console's repair packet and the Python projection must agree, by execution.

``app.js`` re-implements ``repair_packet.derive_repair_packet`` so the operator
can see the packet without a round trip. The only existing lockstep compared the
copy text, and it lived in a module marked ``pytest.mark.browser`` - so the
non-browser suite never ran it, and the comparison skipped the object itself.

The two had drifted: for a present-but-empty ``resumeStage`` or
``recaptureRequirement`` the client rendered a known-empty fact while the server
reported an evidence gap. The client governs, because the client is what the
operator reads, so ``_next_action_field`` now matches it. This test extracts the
packet block from the shipped file and runs it in node against the Python
projection over the same snapshots, comparing the derived objects field by
field.

The block is DOM-free by construction: it ends before ``packetValueText``, which
is where the copy renderer starts reaching for the locale table.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
if str(_PKG_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT / "tests"))

from design_playbook.mcp.run_console.repair_packet import (  # noqa: E402
    derive_repair_packet,
)
from tests.run_console import test_contract as contract_fixtures  # noqa: E402

APP_JS = _PKG_ROOT / "mcp" / "run_console" / "app.js"

_START = '  var PACKET_NOT_PRODUCED = "not-produced";'
_END = "  function packetValueText("


def _packet_block() -> str:
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index(_START)
    end = source.index(_END, start)
    return source[start:end]


def _blocking(**overrides: object) -> dict:
    document = deepcopy(contract_fixtures._valid_snapshot())
    document["evaluation"]["verdict"]["result"] = "Recirculate"
    document["evaluation"]["findings"][0]["result"].update(
        disposition="blocking",
        severity="S3",
        issue="destructive action has no confirmation",
        repair="add a consequence-confirmation dialog",
        owner={
            "kind": "declaration",
            "domainId": "intent.summary",
            "sourceRef": "source.common",
        },
    )
    result = document["nextActions"]["primary"]["result"]
    result.update(
        actionId="action.repair-after-recirculate",
        kind="continue",
        label="Verdict is Recirculate — repair from point-back findings.",
        owner={"actor": "agent", "role": None},
        copyableAgentCommand=None,
        invalidatedEvidence=["L6.3"],
        resumeStage="ui-evaluator",
        recaptureRequirement="Recapture only invalidated evidence.",
    )
    result.update(overrides)
    return document


def _bind_source_set_hash(document: dict) -> None:
    items = document["sources"]["items"]
    retained = [
        {key: item[key] for key in (
            "sourceRef", "authorityKey", "readState",
            "observedHash", "verifiedHash", "freshness",
        )}
        for item in items
    ]
    digest = "sha256:" + hashlib.sha256(
        json.dumps(retained, ensure_ascii=False, separators=(",", ":"),
                   sort_keys=True).encode("utf-8")
    ).hexdigest()
    document["sources"]["sourceSetHash"] = digest
    document["identity"]["snapshot"]["sourceSetHash"] = digest


def _stale_inconsistent() -> dict:
    """Degraded snapshot: a stale intent plus an inconsistent verdict."""
    document = deepcopy(contract_fixtures._valid_snapshot())
    document["identity"]["snapshot"]["buildState"] = "degraded"
    document["sources"]["items"][0].update(
        verifiedHash=contract_fixtures._HASH_2, freshness="changed")
    _bind_source_set_hash(document)
    summary = document["intent"]["summary"]
    summary.update(
        availability="stale",
        reason=contract_fixtures._reason(
            "source-changed-during-build", ["source.common"],
            observed_hashes=[contract_fixtures._HASH_1],
            verified_hashes=[contract_fixtures._HASH_2]),
    )
    summary["source"].update(verifiedSetHash=contract_fixtures._HASH_2)
    verdict = document["evaluation"]["verdict"]
    verdict.update(
        availability="inconsistent",
        result=None,
        reason=contract_fixtures._reason(
            "conflicting-authorities",
            ["source.common", "source.evaluator-report"],
            observed_hashes=[contract_fixtures._HASH_1, contract_fixtures._HASH_3],
            verified_hashes=[contract_fixtures._HASH_1, contract_fixtures._HASH_3],
            conflicts=[{
                "sourceRef": "source.evaluator-report",
                "hash": contract_fixtures._HASH_3,
                "summary": "verdict contradicts the findings ledger",
            }]),
    )
    verdict["source"]["refs"] = ["source.common", "source.evaluator-report"]
    return document


def _unreadable_finding() -> dict:
    """Degraded snapshot: the only finding has an owner-unknown disposition."""
    document = deepcopy(contract_fixtures._valid_snapshot())
    document["identity"]["snapshot"]["buildState"] = "degraded"
    document["evaluation"]["findings"][0].update(
        availability="unknown",
        result=None,
        reason=contract_fixtures._reason("owner-unmapped", ["source.common"]),
    )
    return document

CASES: list[tuple[str, dict]] = [
    ("a snapshot with no blocking finding",
     deepcopy(contract_fixtures._valid_snapshot())),
    ("a fully projected blocking action", _blocking()),
    ("an empty invalidated-evidence set", _blocking(invalidatedEvidence=[])),
    # The divergence this test was written for: the client says known-empty, so
    # the server must not call it an evidence gap.
    ("an empty resume stage", _blocking(resumeStage="")),
    ("an empty recapture requirement", _blocking(recaptureRequirement="")),
    ("a null copyable command", _blocking(copyableAgentCommand=None)),
    # The completed fixture's action omits all three optional fields, so the
    # absent-field path is already covered by the first case.
    ("a stale intent beside an inconsistent verdict", _stale_inconsistent()),
    ("a finding whose disposition is not owner-known", _unreadable_finding()),
]


def _run_client(snapshots: list[dict], tmp_path: Path) -> list[dict]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    script = (
        "(function () {\n"
        + _packet_block()
        + "\nglobalThis.deriveRepairPacket = deriveRepairPacket;\n})();\n"
        + "const cases = " + json.dumps(snapshots) + ";"
        + "\nconsole.log(JSON.stringify(cases.map(deriveRepairPacket)));"
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "repair_packet_mirror.js"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _without_copy_text(packet: dict) -> dict:
    # The copy renderer is the one part that reads the locale table, and the
    # browser lockstep already compares it line by line; this test compares the
    # derived facts.
    return {key: value for key, value in packet.items() if key != "copyText"}


def test_the_client_repair_packet_matches_the_python_projection(tmp_path) -> None:
    client = _run_client([snapshot for _, snapshot in CASES], tmp_path)
    server = [_without_copy_text(derive_repair_packet(snapshot))
              for _, snapshot in CASES]
    mismatches = [
        f"{label}: client={got!r} server={want!r}"
        for (label, _), got, want in zip(CASES, client, server)
        if got != want
    ]
    assert not mismatches, "\n".join(mismatches)
