"""The register of generated artifacts (ADR-0042, ADR-0048).

Every generated artifact has one canonical source, one generator, and one
drift gate. Written out as separate conventions, they drifted: the adapter
snapshots had a blocking gate and a doctor report, the contract artifacts only
had pytest byte-compares that the release transaction never ran, and a dead
copy (the workbench's ``dpbui-core.js``) sat in the tree with no reader.

This table is the one place that says what is generated, from what, by what,
and which test keeps it honest. ``validate.py`` checks every row; the release
transaction's ``validate`` step runs ``validate.py``, so a new generated
artifact cannot ship without a gate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedArtifact:
    """One generated artifact: its source, maker, outputs, and drift gate."""

    name: str
    #: The canonical owner the artifact is derived from (a path or a group).
    source: str
    #: The script that writes the artifact; ``None`` means no generator runs
    #: (the row is checked only through its gate).
    generator: str | None
    #: Committed paths the generator writes.
    artifacts: tuple[str, ...]
    #: Repo-relative test file that fails when the artifact drifts.
    gate: str


ARTIFACTS: tuple[GeneratedArtifact, ...] = (
    GeneratedArtifact(
        name="codex adapter snapshot",
        source="packages/design-playbook/{skills,commands,.claude-plugin}",
        generator="packages/design-playbook/scripts/generate_adapter.py",
        artifacts=(
            "packages/design-playbook/codex/AGENTS.md",
            "packages/design-playbook/.codex-plugin/plugin.json",
        ),
        gate="tests/test_adapter_drift.py",
    ),
    GeneratedArtifact(
        name="agents marketplace catalog",
        source=(
            "packages/design-playbook/scripts/adapter_matrix.py + "
            "packages/design-playbook/.claude-plugin/plugin.json"
        ),
        generator="packages/design-playbook/scripts/generate_adapter.py",
        artifacts=(".agents/plugins/marketplace.json",),
        gate="tests/test_adapter_generator.py",
    ),
    GeneratedArtifact(
        name="run console snapshot contract",
        source="packages/design-playbook/mcp/run_console/snapshot_v1.schema.json",
        generator="scripts/generate_snapshot_contract.py",
        artifacts=(
            "packages/design-playbook/mcp/run_console/snapshot_contract.js",
        ),
        gate=(
            "packages/design-playbook/tests/run_console/"
            "test_snapshot_contract_generator.py"
        ),
    ),
    GeneratedArtifact(
        name="preview visual contract",
        source="packages/design-playbook/mcp/preview/visual_batch.py",
        generator="scripts/generate_visual_contract.py",
        artifacts=("packages/design-playbook/mcp/preview/visual_contract.js",),
        gate=(
            "packages/design-playbook/tests/preview/"
            "test_visual_contract_generator.py"
        ),
    ),
    GeneratedArtifact(
        name="run console client routes",
        source="packages/design-playbook/mcp/run_console/client_routes.py",
        generator="scripts/generate_run_console_routes.py",
        artifacts=("packages/design-playbook/mcp/run_console/client_routes.js",),
        gate=(
            "packages/design-playbook/tests/run_console/"
            "test_client_routes_generator.py"
        ),
    ),
    GeneratedArtifact(
        name="workbench client routes",
        source=(
            "packages/design-playbook-workbench/design_playbook_workbench/"
            "client_routes.py"
        ),
        generator="scripts/generate_workbench_routes.py",
        artifacts=(
            "packages/design-playbook-workbench/design_playbook_workbench/web/"
            "routes.js",
        ),
        gate="packages/design-playbook-workbench/tests/test_client_routes.py",
    ),
    GeneratedArtifact(
        name="workbench shared UI copies",
        source="packages/design-playbook/mcp/_shared/",
        generator="scripts/sync_ui_shared.py",
        artifacts=(
            "packages/design-playbook-workbench/design_playbook_workbench/web/"
            "tokens.css",
            "packages/design-playbook-workbench/design_playbook_workbench/web/"
            "dpbui.lock.json",
        ),
        gate="tests/test_ui_shared_parity.py",
    ),
)
