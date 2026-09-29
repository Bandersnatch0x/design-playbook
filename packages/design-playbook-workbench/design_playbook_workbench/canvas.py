"""Personal multi-board canvas: transactional commands and undo (R09).

One implementation owns the canvas document, the command set, the patch
format that makes a transaction reversible, and the validation that runs
before anything is stored. The canvas never edits a component, a revision
or project source: instance nodes reference a fixed-revision instance row
owned by the reuse module, so upgrade and rollback stay WB-04 operations.

Two boundaries this module enforces rather than documents:

- a canvas holds at most ``MAX_INSTANCES`` instance nodes, and an
  operation that would exceed the limit is rejected as a whole;
- only the last ``UNDO_HISTORY_LIMIT`` saved edits stay undoable, a new
  edit clears the redo branch, and undo/redo can never touch a published
  asset, revision, or repository write.
"""
from __future__ import annotations

import json
import uuid
from typing import Callable

from .blobs import BlobStore
from .components import (
    MAX_NODES,
    ComponentService,
    check_params,
    parse_layout,
    validate_layout,
)
from .errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from .reuse import ReuseService
from .service import Operation, WorkbenchService, utc_now
from .store import Store

MAX_INSTANCES = 200
UNDO_HISTORY_LIMIT = 100
MAX_BOARDS = 50
MAX_FLOW_EDGES = 100
MAX_SCHEME_RULES = 20
FLOW_EDGE_KINDS = frozenset({"navigation", "user-flow", "interaction", "back"})
MAX_COMMANDS_PER_BATCH = 20

#: Closed command fields: an unknown field is a typed refusal, so a
#: client cannot smuggle local-only state into the stored transaction.
COMMAND_FIELDS: dict[str, frozenset] = {
    "board-add": frozenset({"kind", "boardId", "name", "width", "height", "background"}),
    "board-rename": frozenset({"kind", "boardId", "name"}),
    "board-resize": frozenset({"kind", "boardId", "width", "height"}),
    "board-delete": frozenset({"kind", "boardId"}),
    "node-add": frozenset({"kind", "boardId", "node", "parentId"}),
    "node-props": frozenset({"kind", "boardId", "nodeId", "props"}),
    "instance-params": frozenset({"kind", "boardId", "nodeId", "params"}),
    "node-move": frozenset({"kind", "boardId", "nodeIds", "dx", "dy"}),
    "node-resize": frozenset({"kind", "boardId", "nodeId", "layout"}),
    "node-reorder": frozenset({"kind", "boardId", "nodeId", "action"}),
    "node-duplicate": frozenset({"kind", "boardId", "nodeIds", "newIds"}),
    "node-delete": frozenset({"kind", "boardId", "nodeIds"}),
    "node-group": frozenset({"kind", "boardId", "nodeIds", "name", "groupId"}),
    "node-align": frozenset({"kind", "boardId", "nodeIds", "mode"}),
    "board-scheme": frozenset({"kind", "boardId", "scheme"}),
    "scheme-derive": frozenset({"kind", "boardId", "newBoardId", "name", "snapshotId"}),
    "flow-edge-add": frozenset({"kind", "boardId", "edge"}),
    "flow-edge-update": frozenset({"kind", "boardId", "edgeId", "edge"}),
    "flow-edge-delete": frozenset({"kind", "boardId", "edgeId"}),
}

ALIGN_MODES = frozenset(
    {
        "left",
        "hcenter",
        "right",
        "top",
        "vcenter",
        "bottom",
        "hdistribute",
        "vdistribute",
    }
)

REORDER_ACTIONS = frozenset({"front", "back", "forward", "backward"})

NODE_TYPES_WITH_CHILDREN = frozenset({"container", "stack", "grid"})

_DEFAULT_SIZE = {
    "text": (160, 32),
    "link": (140, 32),
    "button": (140, 40),
    "image": (240, 160),
    "instance": (200, 80),
    "slot": (200, 120),
    "container": (400, 300),
    "stack": (400, 300),
    "grid": (400, 300),
}


def _error(kind: str, path: str, **extra: object) -> dict:
    return {"kind": kind, "path": path, **extra}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# -- document shape ------------------------------------------------------


def parse_canvas(raw: object) -> dict:
    """Parse a canvas document into ``{name, boards: [...]}``."""
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WorkbenchError(INVALID_INPUT, detail="canvas must be JSON") from None
    if not isinstance(raw, dict) or set(raw) - {"name", "boards"}:
        raise WorkbenchError(INVALID_INPUT)
    boards = raw.get("boards")
    if not isinstance(boards, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(boards) > MAX_BOARDS:
        raise WorkbenchError(LIMIT_EXCEEDED)
    parsed: list[dict] = []
    for entry in boards:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        unknown = set(entry) - {
            "id",
            "name",
            "width",
            "height",
            "background",
            "nodes",
            "flowEdges",
            "scheme",
        }
        if unknown:
            raise WorkbenchError(
                INVALID_INPUT, detail=f"unknown board field: {sorted(unknown)[0]}"
            )
        layout = parse_layout({"name": entry.get("name") or "", "nodes": entry.get("nodes")})
        parsed.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name") or "",
                "width": entry.get("width"),
                "height": entry.get("height"),
                "background": entry.get("background") or "",
                "nodes": layout["nodes"],
                "flowEdges": _parse_flow_edges(entry.get("flowEdges")),
                "scheme": _parse_scheme(entry.get("scheme")),
            }
        )
    return {"name": raw.get("name") or "", "boards": parsed}


def _parse_scheme(raw: object) -> dict | None:
    """A scheme's declared constraints: viewport, rules, regions, intent."""
    if raw in (None, {}):
        return None
    if not isinstance(raw, dict) or set(raw) - {
        "viewport",
        "rules",
        "replaceableRegions",
        "acceptance",
        "derivedFrom",
    }:
        raise WorkbenchError(INVALID_INPUT)
    viewport = raw.get("viewport") or {}
    if not isinstance(viewport, dict) or set(viewport) - {"width", "height", "device"}:
        raise WorkbenchError(INVALID_INPUT)
    rules = raw.get("rules") or []
    if not isinstance(rules, list) or not all(isinstance(item, str) for item in rules):
        raise WorkbenchError(INVALID_INPUT)
    regions = raw.get("replaceableRegions") or []
    if not isinstance(regions, list) or not all(
        isinstance(item, str) and item for item in regions
    ):
        raise WorkbenchError(INVALID_INPUT)
    derived = raw.get("derivedFrom")
    if derived is not None:
        if not isinstance(derived, dict) or set(derived) - {"boardId", "snapshotId"}:
            raise WorkbenchError(INVALID_INPUT)
        derived = {
            "boardId": derived.get("boardId"),
            "snapshotId": derived.get("snapshotId"),
        }
    return {
        "viewport": {
            "width": viewport.get("width"),
            "height": viewport.get("height"),
            "device": viewport.get("device") or "",
        },
        "rules": list(rules),
        "replaceableRegions": list(regions),
        "acceptance": raw.get("acceptance") or "",
        "derivedFrom": derived,
    }


def _parse_flow_edges(raw: object) -> list[dict]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise WorkbenchError(INVALID_INPUT)
    edges: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) - {"id", "from", "to", "kind", "label"}:
            raise WorkbenchError(INVALID_INPUT)
        edges.append(
            {
                "id": entry.get("id"),
                "from": entry.get("from"),
                "to": entry.get("to"),
                "kind": entry.get("kind") or "navigation",
                "label": entry.get("label") or "",
            }
        )
    return edges


def validate_canvas(
    document: dict,
    *,
    components: dict[str, dict] | None = None,
    instances: dict[str, dict] | None = None,
) -> dict:
    """The one canvas validator: boards, shared node schema, instance cap."""
    components = components or {}
    instances = instances or {}
    errors: list[dict] = []
    if not isinstance(document.get("name"), str) or not document["name"].strip():
        errors.append(_error("missing-name", "name"))
    boards = document.get("boards") or []
    if not boards:
        errors.append(_error("missing-board", "boards"))
    seen_boards: set[str] = set()
    seen_board_names: set[str] = set()
    instance_count = 0
    node_count = 0
    for board in boards:
        board_id = board.get("id")
        path = f"boards.{board_id}"
        if not isinstance(board_id, str) or not board_id:
            errors.append(_error("invalid-board", path))
            continue
        for key in ("width", "height"):
            value = board.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                errors.append(
                    _error("invalid-board-size", f"{path}.{key}", board=board_id)
                )
        if board_id in seen_boards:
            errors.append(_error("duplicate-board", path, board=board_id))
            continue
        seen_boards.add(board_id)
        name = board.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(_error("invalid-board", f"{path}.name", board=board_id))
        elif name in seen_board_names:
            errors.append(_error("duplicate-board-name", path, board=board_id))
        else:
            seen_board_names.add(name)
        layout_verdict = validate_layout(
            {"name": board.get("name") or "", "nodes": board.get("nodes") or []},
            components=components,
            instances=instances,
        )
        for error in layout_verdict["errors"]:
            errors.append({**error, "path": f"boards.{board_id}.{error['path']}"})
        node_count += len(board.get("nodes") or [])
        instance_count += sum(
            1 for node in board.get("nodes") or [] if node.get("type") == "instance"
        )
        errors.extend(_scheme_errors(board, document))
        errors.extend(_flow_edge_errors(board, document))
    if instance_count > MAX_INSTANCES:
        errors.append(
            _error(
                "instance-limit",
                "boards",
                limit=MAX_INSTANCES,
                count=instance_count,
            )
        )
    return {
        "valid": not errors,
        "errors": errors,
        "boardIds": sorted(seen_boards),
        "nodeCount": node_count,
        "instanceCount": instance_count,
        "instanceLimit": MAX_INSTANCES,
        "undoLimit": UNDO_HISTORY_LIMIT,
    }


def _scheme_errors(board: dict, document: dict) -> list[dict]:
    """Scheme constraints are validated per board, including the derived link."""
    scheme = board.get("scheme")
    if scheme is None:
        return []
    board_id = board.get("id")
    path = f"boards.{board_id}.scheme"
    errors: list[dict] = []
    for key in ("width", "height"):
        value = scheme["viewport"].get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(_error("invalid-viewport", f"{path}.viewport.{key}", board=board_id))
    if len(scheme["rules"]) > MAX_SCHEME_RULES:
        errors.append(_error("limit-exceeded", f"{path}.rules", board=board_id))
    elif not all(len(rule) <= 200 for rule in scheme["rules"]):
        errors.append(_error("invalid-rule", f"{path}.rules", board=board_id))
    if len(scheme["acceptance"]) > 500:
        errors.append(_error("invalid-acceptance", f"{path}.acceptance", board=board_id))
    node_ids = {node.get("id") for node in board.get("nodes") or []}
    for region in scheme["replaceableRegions"]:
        if region not in node_ids:
            errors.append(
                _error(
                    "unknown-region",
                    f"{path}.replaceableRegions.{region}",
                    board=board_id,
                    node=region,
                )
            )
    derived = scheme.get("derivedFrom")
    if derived is not None:
        target = derived.get("boardId")
        if not isinstance(target, str) or not target:
            errors.append(_error("invalid-derived-from", f"{path}.derivedFrom", board=board_id))
        elif target == board_id:
            errors.append(_error("self-derived", f"{path}.derivedFrom", board=board_id))
        elif not any(item.get("id") == target for item in document.get("boards") or []):
            errors.append(_error("unknown-board", f"{path}.derivedFrom", board=target))
    return errors


def _flow_edge_errors(board: dict, document: dict) -> list[dict]:
    """Flow edges are typed navigation, not asset lineage.

    An endpoint is an interaction point (a node in this board) or another
    board: user flows may legitimately loop, so nothing here rejects a
    cycle -- unlike the dependency DAG, which the reuse owner validates.
    """
    board_id = board.get("id")
    node_ids = {node.get("id") for node in board.get("nodes") or []}
    board_ids = {item.get("id") for item in document.get("boards") or []}
    seen: set[str] = set()
    errors: list[dict] = []
    for edge in board.get("flowEdges") or []:
        path = f"boards.{board_id}.flowEdges.{edge.get('id')}"
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            errors.append(_error("invalid-flow-edge", path, board=board_id))
            continue
        if edge_id in seen:
            errors.append(_error("duplicate-flow-edge", path, board=board_id))
            continue
        seen.add(edge_id)
        if edge.get("kind") not in FLOW_EDGE_KINDS:
            errors.append(_error("invalid-flow-kind", f"{path}.kind", board=board_id))
        for key in ("from", "to"):
            endpoint = edge.get(key)
            if not isinstance(endpoint, str) or not endpoint:
                errors.append(_error("invalid-flow-edge", f"{path}.{key}", board=board_id))
            elif endpoint not in node_ids and endpoint not in board_ids:
                errors.append(
                    _error("unknown-flow-endpoint", f"{path}.{key}", board=board_id)
                )
    return errors


# -- commands ------------------------------------------------------------


def _board(document: dict, board_id: object) -> dict:
    for board in document.get("boards") or []:
        if board["id"] == board_id:
            return board
    raise WorkbenchError(INVALID_TARGET)


def _node(board: dict, node_id: object) -> dict:
    for node in board["nodes"]:
        if node["id"] == node_id:
            return node
    raise WorkbenchError(INVALID_TARGET)


def instance_count(document: dict) -> int:
    return sum(
        1
        for board in document.get("boards") or []
        for node in board["nodes"]
        if node.get("type") == "instance"
    )


def default_layout(node_type: str, index: int = 0) -> dict:
    width, height = _DEFAULT_SIZE.get(node_type, (160, 32))
    return {
        "x": 24 + (index % 5) * 24,
        "y": 24 + (index % 5) * 24,
        "width": width,
        "height": height,
        "z": index,
    }


def apply_command(
    document: dict,
    command: object,
    *,
    components: dict[str, dict] | None = None,
    instances: dict[str, dict] | None = None,
) -> tuple[dict, dict, dict, str, list[str]]:
    """Apply one command for real; return the new document and its patch.

    Returns ``(document, before_patch, after_patch, label, target_ids)``.
    The patches are what makes undo and redo exact: only the affected
    boards and nodes are recorded, so a 200-instance canvas does not store
    a full copy of itself for every edit.
    """
    components = components or {}
    instances = instances or {}
    if not isinstance(command, dict):
        raise WorkbenchError(INVALID_INPUT)
    kind = command.get("kind")
    if not isinstance(kind, str) or not kind:
        raise WorkbenchError(INVALID_INPUT)
    allowed = COMMAND_FIELDS.get(kind)
    if allowed is None:
        raise WorkbenchError(INVALID_INPUT, detail=f"unknown canvas command: {kind}")
    extra = set(command) - allowed
    if extra:
        raise WorkbenchError(
            INVALID_INPUT, detail=f"unknown command field: {sorted(extra)[0]}"
        )
    original = json.loads(json.dumps(document))
    working = json.loads(json.dumps(document))
    # Which boards and nodes the patches must cover: the diff is derived from
    # before/after states, so no snapshot can be taken too late.
    touched_boards: set[str] = set()
    touched_nodes: dict[str, set[str]] = {}
    targets: list[str] = []
    if kind == "board-add":
        board = _board_add(working, command)
        targets = [board["id"]]
        touched_boards.add(board["id"])
        label = f"新建画板 {board['name']}"
    elif kind in ("board-rename", "board-resize"):
        board = _board(working, command.get("boardId"))
        touched_boards.add(board["id"])
        if kind == "board-rename":
            name = command.get("name")
            if not isinstance(name, str) or not name.strip():
                raise WorkbenchError(INVALID_INPUT)
            board["name"] = name.strip()[:120]
            label = f"重命名画板 {board['name']}"
        else:
            board["width"] = _positive_number(command.get("width"), "width")
            board["height"] = _positive_number(command.get("height"), "height")
            label = f"调整画板尺寸 {board['name']}"
        targets = [board["id"]]
    elif kind == "board-delete":
        board = _board(working, command.get("boardId"))
        if len(working["boards"]) <= 1:
            raise WorkbenchError(INVALID_INPUT, detail="the last board cannot be deleted")
        touched_boards.add(board["id"])
        working["boards"] = [item for item in working["boards"] if item["id"] != board["id"]]
        targets = [board["id"]]
        label = f"删除画板 {board['name']}"
    elif kind == "node-add":
        board = _board(working, command.get("boardId"))
        parent_id = command.get("parentId") or None
        parent_snapshot = (
            json.loads(json.dumps(_node(board, parent_id))) if parent_id else None
        )
        node = _node_add(board, command)
        if node["type"] == "instance":
            _check_instance_params(node, components)
        targets = [node["id"]]
        touched_nodes.setdefault(board["id"], set()).add(node["id"])
        if parent_snapshot is not None:
            # The parent's child list is part of the transaction too.
            touched_nodes.setdefault(board["id"], set()).add(parent_id)
        label = f"添加 {node['type']} 节点"
    elif kind == "node-props":
        board = _board(working, command.get("boardId"))
        node = _node(board, command.get("nodeId"))
        props = command.get("props")
        if not isinstance(props, dict):
            raise WorkbenchError(INVALID_INPUT)
        node["props"] = {**node["props"], **props}
        if node["type"] == "instance":
            _check_instance_params(node, components)
        touched_nodes.setdefault(board["id"], set()).add(node["id"])
        targets = [node["id"]]
        label = f"修改 {node['type']} 属性"
    elif kind == "instance-params":
        board = _board(working, command.get("boardId"))
        node = _node(board, command.get("nodeId"))
        if node["type"] != "instance":
            raise WorkbenchError(INVALID_INPUT)
        params = command.get("params")
        if not isinstance(params, dict):
            raise WorkbenchError(INVALID_INPUT)
        node["props"] = {**node["props"], "params": params}
        _check_instance_params(node, components)
        touched_nodes.setdefault(board["id"], set()).add(node["id"])
        targets = [node["id"]]
        label = "修改实例参数"
    elif kind == "node-move":
        board = _board(working, command.get("boardId"))
        node_ids = _node_ids(command.get("nodeIds"))
        dx = _number(command.get("dx"), "dx")
        dy = _number(command.get("dy"), "dy")
        for node_id in node_ids:
            node = _node(board, node_id)
            geometry = node["layout"]
            geometry["x"] = round(_number(geometry.get("x"), "x") + dx, 3)
            geometry["y"] = round(_number(geometry.get("y"), "y") + dy, 3)
            touched_nodes.setdefault(board["id"], set()).add(node_id)
        targets = list(node_ids)
        label = f"移动 {len(node_ids)} 个节点"
    elif kind == "node-resize":
        board = _board(working, command.get("boardId"))
        node = _node(board, command.get("nodeId"))
        geometry = command.get("layout")
        if not isinstance(geometry, dict) or set(geometry) - {"x", "y", "width", "height"}:
            raise WorkbenchError(INVALID_INPUT)
        for key, value in geometry.items():
            node["layout"][key] = (
                _positive_number(value, key) if key in ("width", "height") else _number(value, key)
            )
        touched_nodes.setdefault(board["id"], set()).add(node["id"])
        targets = [node["id"]]
        label = "缩放节点"
    elif kind == "node-reorder":
        board = _board(working, command.get("boardId"))
        action = command.get("action")
        if action not in REORDER_ACTIONS:
            raise WorkbenchError(INVALID_INPUT)
        node = _node(board, command.get("nodeId"))
        _reorder(board, node, action)
        touched_nodes.setdefault(board["id"], set()).update(
            other["id"] for other in board["nodes"]
        )
        targets = [node["id"]]
        label = "调整图层顺序"
    elif kind == "node-duplicate":
        board = _board(working, command.get("boardId"))
        node_ids = _node_ids(command.get("nodeIds"))
        requested = _optional_ids(command.get("newIds"), len(node_ids), "newIds")
        created: list[dict] = []
        for index, node_id in enumerate(node_ids):
            source = _node(board, node_id)
            clone = json.loads(json.dumps(source))
            clone["id"] = requested[index] if requested else _new_id("n")
            if any(item["id"] == clone["id"] for item in board["nodes"]):
                raise WorkbenchError(INVALID_INPUT, detail="duplicate node id")
            clone["layout"]["x"] = _number(clone["layout"].get("x"), "x") + 16
            clone["layout"]["y"] = _number(clone["layout"].get("y"), "y") + 16
            clone["layout"]["z"] = _max_z(board) + 1  # int: layers are indices
            clone["children"] = []
            board["nodes"].append(clone)
            created.append(clone)
        touched_nodes.setdefault(board["id"], set()).update(
            clone["id"] for clone in created
        )
        targets = [node["id"] for node in created]
        label = f"复制 {len(created)} 个节点"
    elif kind == "node-delete":
        board = _board(working, command.get("boardId"))
        node_ids = _node_ids(command.get("nodeIds"))
        parents = {
            parent_id
            for node_id in node_ids
            for parent_id in _parents_of(board, node_id)
        }
        for node_id in node_ids:
            _node(board, node_id)
            touched_nodes.setdefault(board["id"], set()).add(node_id)
        board["nodes"] = [node for node in board["nodes"] if node["id"] not in set(node_ids)]
        for node in board["nodes"]:
            if not set(node["children"]) & set(node_ids):
                continue
            touched_nodes.setdefault(board["id"], set()).add(node["id"])
            node["children"] = [
                child for child in node["children"] if child not in set(node_ids)
            ]
        targets = list(node_ids)
        label = f"删除 {len(node_ids)} 个节点（含 {len(parents)} 个父节点引用）"
    elif kind == "node-group":
        board = _board(working, command.get("boardId"))
        node_ids = _node_ids(command.get("nodeIds"))
        if len(node_ids) < 2:
            raise WorkbenchError(INVALID_INPUT)
        group_id = command.get("groupId")
        if group_id is not None and (not isinstance(group_id, str) or not group_id):
            raise WorkbenchError(INVALID_INPUT)
        if isinstance(group_id, str) and any(
            item["id"] == group_id for item in board["nodes"]
        ):
            raise WorkbenchError(INVALID_INPUT, detail="duplicate node id")
        group = _group(board, node_ids, command.get("name"), group_id=group_id)
        touched_nodes.setdefault(board["id"], set()).update(
            node["id"] for node in board["nodes"]
        )
        touched_nodes[board["id"]].add(group["id"])
        targets = [group["id"], *node_ids]
        label = f"成组 {len(node_ids)} 个节点"
    elif kind == "node-align":
        board = _board(working, command.get("boardId"))
        node_ids = _node_ids(command.get("nodeIds"))
        mode = command.get("mode")
        if mode not in ALIGN_MODES:
            raise WorkbenchError(INVALID_INPUT)
        if len(node_ids) < 2:
            raise WorkbenchError(INVALID_INPUT)
        nodes = [_node(board, node_id) for node_id in node_ids]
        _align(nodes, mode)
        touched_nodes.setdefault(board["id"], set()).update(node_ids)
        targets = list(node_ids)
        label = f"对齐 {len(node_ids)} 个节点"
    elif kind == "board-scheme":
        board = _board(working, command.get("boardId"))
        touched_boards.add(board["id"])
        scheme = command.get("scheme")
        board["scheme"] = (
            None if scheme in (None, {}) else _parse_scheme(scheme)
        )
        if board["scheme"] is not None:
            board["scheme"]["viewport"]["width"] = int(
                _positive_number(board["scheme"]["viewport"]["width"], "viewport width")
            )
            board["scheme"]["viewport"]["height"] = int(
                _positive_number(board["scheme"]["viewport"]["height"], "viewport height")
            )
        targets = [board["id"]]
        label = f"设置方案约束 {board['name']}"
    elif kind == "scheme-derive":
        source = _board(working, command.get("boardId"))
        name = command.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WorkbenchError(INVALID_INPUT)
        if len(working["boards"]) >= MAX_BOARDS:
            raise WorkbenchError(LIMIT_EXCEEDED, detail=f"最多 {MAX_BOARDS} 个画板。")
        new_board_id = command.get("newBoardId") or _new_id("b")
        if not isinstance(new_board_id, str) or not new_board_id:
            raise WorkbenchError(INVALID_INPUT)
        if any(item["id"] == new_board_id for item in working["boards"]):
            raise WorkbenchError(INVALID_INPUT, detail="board id already exists")
        derived = _derive_board(
            source,
            board_id=new_board_id,
            name=name.strip()[:120],
            snapshot_id=command.get("snapshotId"),
        )
        working["boards"].append(derived)
        touched_boards.add(new_board_id)
        targets = [new_board_id]
        label = f"派生方案 {derived['name']}"
    elif kind == "flow-edge-add":
        board = _board(working, command.get("boardId"))
        touched_boards.add(board["id"])
        edge = _flow_edge_add(board, command.get("edge"))
        targets = [edge["id"]]
        label = f"新增流程边 {edge['id']}"
    elif kind in ("flow-edge-update", "flow-edge-delete"):
        board = _board(working, command.get("boardId"))
        touched_boards.add(board["id"])
        edge_id = command.get("edgeId")
        edge = next(
            (item for item in board["flowEdges"] if item["id"] == edge_id), None
        )
        if edge is None:
            raise WorkbenchError(INVALID_TARGET)
        if kind == "flow-edge-delete":
            board["flowEdges"] = [
                item for item in board["flowEdges"] if item["id"] != edge_id
            ]
        else:
            patch = command.get("edge")
            if not isinstance(patch, dict) or set(patch) - {"from", "to", "kind", "label"}:
                raise WorkbenchError(INVALID_INPUT)
            edge.update({key: value for key, value in patch.items()})
            if edge.get("kind") not in FLOW_EDGE_KINDS:
                raise WorkbenchError(INVALID_INPUT, detail="unknown flow edge kind")
        targets = [edge_id]
        label = (
            f"删除流程边 {edge_id}"
            if kind == "flow-edge-delete"
            else f"修改流程边 {edge_id}"
        )
    else:
        raise WorkbenchError(
            INVALID_INPUT, detail=f"unknown canvas command: {kind}"
        )
    if instance_count(working) > MAX_INSTANCES:
        raise WorkbenchError(
            LIMIT_EXCEEDED,
            detail=(
                f"画布最多 {MAX_INSTANCES} 个实例；本次操作会使实例数达到 "
                f"{instance_count(working)}。"
            ),
        )
    for board in working["boards"]:
        if len(board["nodes"]) > MAX_NODES:
            raise WorkbenchError(
                LIMIT_EXCEEDED, detail=f"单画板最多 {MAX_NODES} 个节点。"
            )
    before, after = _diff_patches(original, working, touched_boards, touched_nodes)
    return working, before, after, label, targets


def _empty_patch() -> dict:
    return {"boards": [], "nodes": []}


def _board_patch_fields(source: dict, target: dict) -> dict:
    """Only the board fields that actually changed, merged on apply."""
    changed: dict = {}
    for key in ("name", "width", "height", "background"):
        if source.get(key) != target.get(key):
            changed[key] = target.get(key)
    if source.get("flowEdges") != target.get("flowEdges"):
        changed["flowEdges"] = target.get("flowEdges") or []
    if source.get("scheme") != target.get("scheme"):
        changed["scheme"] = target.get("scheme")
    return changed


def _find_board(document: dict, board_id: str) -> dict | None:
    return next(
        (board for board in document.get("boards") or [] if board["id"] == board_id),
        None,
    )


def _find_node(board: dict | None, node_id: str) -> dict | None:
    if board is None:
        return None
    return next(
        (node for node in board["nodes"] if node["id"] == node_id), None
    )


def _diff_patches(
    original: dict,
    working: dict,
    board_ids: set[str],
    node_ids: dict[str, set[str]],
) -> tuple[dict, dict]:
    """The smallest reversible patch pair for the touched ids."""
    before = _empty_patch()
    after = _empty_patch()
    for board_id in sorted(board_ids):
        source = _find_board(original, board_id)
        target = _find_board(working, board_id)
        if source is None and target is None:
            continue
        if source is None or target is None:
            # A created or deleted board carries its nodes with it.
            before["boards"].append(
                {"boardId": board_id, "board": None if source is None else source}
            )
            after["boards"].append(
                {"boardId": board_id, "board": None if target is None else target}
            )
            continue
        changed_before = _board_patch_fields(target, source)
        changed_after = _board_patch_fields(source, target)
        if changed_before or changed_after:
            before["boards"].append({"boardId": board_id, "board": changed_before})
            after["boards"].append({"boardId": board_id, "board": changed_after})
    for board_id, ids in sorted(node_ids.items()):
        source_board = _find_board(original, board_id)
        target_board = _find_board(working, board_id)
        source_index = {
            node["id"]: index for index, node in enumerate((source_board or {}).get("nodes", []))
        }
        target_index = {
            node["id"]: index for index, node in enumerate((target_board or {}).get("nodes", []))
        }
        for node_id in sorted(ids):
            source = _find_node(source_board, node_id)
            target = _find_node(target_board, node_id)
            if source is None and target is None:
                continue
            if source is not None and target is not None and source == target:
                continue
            before["nodes"].append(
                {
                    "boardId": board_id,
                    "node": source,
                    "nodeId": node_id,
                    "index": source_index.get(node_id, target_index.get(node_id, 0)),
                }
            )
            after["nodes"].append(
                {
                    "boardId": board_id,
                    "node": target,
                    "nodeId": node_id,
                    "index": target_index.get(node_id, source_index.get(node_id, 0)),
                }
            )
    return before, after


def _board_add(document: dict, command: dict) -> dict:
    name = command.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WorkbenchError(INVALID_INPUT)
    if len(document["boards"]) >= MAX_BOARDS:
        raise WorkbenchError(LIMIT_EXCEEDED, detail=f"最多 {MAX_BOARDS} 个画板。")
    board = {
        "id": command.get("boardId") or _new_id("b"),
        "name": name.strip()[:120],
        "width": _positive_number(command.get("width", 1200), "width"),
        "height": _positive_number(command.get("height", 800), "height"),
        "background": command.get("background") or "",
        "nodes": [],
        "flowEdges": [],
    }
    if any(item["id"] == board["id"] for item in document["boards"]):
        raise WorkbenchError(INVALID_INPUT, detail="board id already exists")
    document["boards"].append(board)
    return board


def _node_add(board: dict, command: dict) -> dict:
    raw = command.get("node")
    if not isinstance(raw, dict):
        raise WorkbenchError(INVALID_INPUT)
    parsed = parse_layout({"name": "", "nodes": [raw]})["nodes"][0]
    node = {
        "id": parsed["id"] or _new_id("n"),
        "type": parsed["type"],
        "children": [],
        "props": parsed["props"],
        "layout": parsed["layout"] or default_layout(parsed["type"], len(board["nodes"])),
    }
    if any(item["id"] == node["id"] for item in board["nodes"]):
        raise WorkbenchError(INVALID_INPUT, detail="node id already exists")
    # A stored node always carries full geometry: a partial layout would
    # only move the failure to the next edit.
    defaults = default_layout(node["type"], len(board["nodes"]))
    for key, value in defaults.items():
        node["layout"].setdefault(key, value)
    # z is a layer index: an integer, never a float from a numeric helper.
    node["layout"]["z"] = int(_number(node["layout"]["z"], "z"))
    parent_id = command.get("parentId")
    if parent_id:
        parent = _node(board, parent_id)
        if parent["type"] not in NODE_TYPES_WITH_CHILDREN:
            raise WorkbenchError(INVALID_INPUT, detail="parent cannot contain children")
        parent["children"].append(node["id"])
    board["nodes"].append(node)
    return node


def _derive_board(
    source: dict, *, board_id: str, name: str, snapshot_id: object
) -> dict:
    """Copy a board as a derived scheme with fresh ids.

    Node ids are remapped (containment and flow endpoints included), so the
    derived scheme is its own document rather than a hidden alias of the
    original. The lineage is recorded in the scheme metadata, and a fixed
    snapshot may be named as the comparison baseline.
    """
    mapping = {node["id"]: _new_id("n") for node in source["nodes"]}
    nodes: list[dict] = []
    for node in source["nodes"]:
        clone = json.loads(json.dumps(node))
        clone["id"] = mapping[node["id"]]
        clone["children"] = [mapping[child] for child in node["children"] if child in mapping]
        nodes.append(clone)
    edges: list[dict] = []
    for edge in source["flowEdges"]:
        clone = json.loads(json.dumps(edge))
        clone["id"] = _new_id("f")
        for key in ("from", "to"):
            if clone.get(key) in mapping:
                clone[key] = mapping[clone[key]]
        edges.append(clone)
    scheme = source.get("scheme")
    derived_scheme = (
        json.loads(json.dumps(scheme))
        if scheme is not None
        else {
            "viewport": {"width": source["width"], "height": source["height"], "device": ""},
            "rules": [],
            "replaceableRegions": [],
            "acceptance": "",
            "derivedFrom": None,
        }
    )
    derived_scheme["replaceableRegions"] = [
        mapping[region]
        for region in (scheme or {}).get("replaceableRegions", [])
        if region in mapping
    ]
    derived_scheme["derivedFrom"] = {
        "boardId": source["id"],
        "snapshotId": snapshot_id if isinstance(snapshot_id, str) else None,
    }
    return {
        "id": board_id,
        "name": name,
        "width": source["width"],
        "height": source["height"],
        "background": source["background"],
        "nodes": nodes,
        "flowEdges": edges,
        "scheme": derived_scheme,
    }


def _flow_edge_add(board: dict, raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) - {"id", "from", "to", "kind", "label"}:
        raise WorkbenchError(INVALID_INPUT)
    if len(board["flowEdges"]) >= MAX_FLOW_EDGES:
        raise WorkbenchError(
            LIMIT_EXCEEDED, detail=f"单画板最多 {MAX_FLOW_EDGES} 条流程边。"
        )
    edge = {
        "id": raw.get("id") or _new_id("f"),
        "from": raw.get("from"),
        "to": raw.get("to"),
        "kind": raw.get("kind") or "navigation",
        "label": raw.get("label") or "",
    }
    if not isinstance(edge["id"], str) or not edge["id"]:
        raise WorkbenchError(INVALID_INPUT)
    if any(item["id"] == edge["id"] for item in board["flowEdges"]):
        raise WorkbenchError(INVALID_INPUT, detail="flow edge id already exists")
    if edge["kind"] not in FLOW_EDGE_KINDS:
        raise WorkbenchError(INVALID_INPUT, detail="unknown flow edge kind")
    for key in ("from", "to"):
        if not isinstance(edge[key], str) or not edge[key]:
            raise WorkbenchError(INVALID_INPUT, detail=f"flow edge {key} is required")
    board["flowEdges"].append(edge)
    return edge


def _check_instance_params(node: dict, components: dict[str, dict]) -> None:
    asset_id = node["props"].get("assetId")
    if not isinstance(asset_id, str) or not asset_id:
        # A fixed-revision instance carries its revisions in the instance
        # row, so there is nothing to check against a component schema.
        return
    entry = components.get(asset_id)
    if entry is None:
        raise WorkbenchError(MISSING_DEPENDENCY, detail="instance component is unresolved")
    params = node["props"].get("params") or {}
    problems = check_params(entry["definition"], params)
    if problems:
        raise WorkbenchError(
            INVALID_INPUT, detail=json.dumps(problems, ensure_ascii=False)
        )


def _group(
    board: dict, node_ids: list[str], name: object, *, group_id: object = None
) -> dict:
    nodes = [_node(board, node_id) for node_id in node_ids]
    xs = [_number(node["layout"].get("x"), "x") for node in nodes]
    ys = [_number(node["layout"].get("y"), "y") for node in nodes]
    rights = [x + _number(node["layout"].get("width"), "width") for x, node in zip(xs, nodes)]
    bottoms = [y + _number(node["layout"].get("height"), "height") for y, node in zip(ys, nodes)]
    group = {
        "id": group_id or _new_id("n"),
        "type": "container",
        "children": list(node_ids),
        "props": {"label": str(name).strip()[:120] if isinstance(name, str) and name.strip() else "分组"},
        "layout": {
            "x": min(xs),
            "y": min(ys),
            "width": max(rights) - min(xs),
            "height": max(bottoms) - min(ys),
            "z": int(min(_number(node["layout"].get("z", 0), "z") for node in nodes)),
        },
    }
    selected = set(node_ids)
    for node in board["nodes"]:
        if node["id"] in selected:
            continue
        if selected & set(node["children"]):
            node["children"] = [
                child for child in node["children"] if child not in selected
            ]
    board["nodes"].append(group)
    return group


def _align(nodes: list[dict], mode: str) -> None:
    xs = [_number(node["layout"].get("x"), "x") for node in nodes]
    ys = [_number(node["layout"].get("y"), "y") for node in nodes]
    widths = [_number(node["layout"].get("width"), "width") for node in nodes]
    heights = [_number(node["layout"].get("height"), "height") for node in nodes]
    left, right = min(xs), max(x + width for x, width in zip(xs, widths))
    top, bottom = min(ys), max(y + height for y, height in zip(ys, heights))
    if mode == "left":
        for node in nodes:
            node["layout"]["x"] = left
    elif mode == "right":
        for node, width in zip(nodes, widths):
            node["layout"]["x"] = right - width
    elif mode == "hcenter":
        center = (left + right) / 2
        for node, width in zip(nodes, widths):
            node["layout"]["x"] = round(center - width / 2, 3)
    elif mode == "top":
        for node in nodes:
            node["layout"]["y"] = top
    elif mode == "bottom":
        for node, height in zip(nodes, heights):
            node["layout"]["y"] = bottom - height
    elif mode == "vcenter":
        center = (top + bottom) / 2
        for node, height in zip(nodes, heights):
            node["layout"]["y"] = round(center - height / 2, 3)
    elif mode == "hdistribute":
        _distribute(nodes, axis="x", size="width")
    else:
        _distribute(nodes, axis="y", size="height")


def _distribute(nodes: list[dict], *, axis: str, size: str) -> None:
    ordered = sorted(nodes, key=lambda node: _number(node["layout"].get(axis), axis))
    spanned = sum(_number(node["layout"].get(size), size) for node in ordered)
    start = _number(ordered[0]["layout"].get(axis), axis)
    end = _number(ordered[-1]["layout"].get(axis), axis) + _number(
        ordered[-1]["layout"].get(size), size
    )
    gaps = len(ordered) - 1
    if gaps <= 0:
        return
    step = (end - start - spanned) / gaps
    cursor = start
    for node in ordered:
        node["layout"][axis] = round(cursor, 3)
        cursor += _number(node["layout"].get(size), size) + step


def _reorder(board: dict, node: dict, action: str) -> None:
    ordered = sorted(board["nodes"], key=lambda item: _number(item["layout"].get("z", 0), "z"))
    index = ordered.index(node)
    if action == "front":
        ordered.remove(node)
        ordered.append(node)
    elif action == "back":
        ordered.remove(node)
        ordered.insert(0, node)
    elif action == "forward" and index < len(ordered) - 1:
        ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]
    elif action == "backward" and index > 0:
        ordered[index], ordered[index - 1] = ordered[index - 1], ordered[index]
    # z stays a small contiguous integer so the layer order is legible in
    # the document and stable across undo.
    for position, item in enumerate(ordered):
        item["layout"]["z"] = position


def _max_z(board: dict) -> int:
    return max(
        (int(_number(node["layout"].get("z", 0), "z")) for node in board["nodes"]),
        default=-1,
    )


def _parents_of(board: dict, node_id: str) -> list[str]:
    return [
        node["id"] for node in board["nodes"] if node_id in (node["children"] or [])
    ]


def apply_patch(document: dict, patch: object) -> dict:
    """Return a new document with ``patch`` applied (undo or redo)."""
    if not isinstance(patch, dict) or set(patch) - {"boards", "nodes"}:
        raise WorkbenchError(INVALID_INPUT)
    working = json.loads(json.dumps(document))
    boards = working.get("boards") or []
    for entry in patch.get("boards") or []:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        board_id = entry.get("boardId")
        board = entry.get("board")
        existing = next((item for item in boards if item["id"] == board_id), None)
        if board is None:
            working["boards"] = [item for item in boards if item["id"] != board_id]
            boards = working["boards"]
            continue
        if existing is None:
            boards.append(json.loads(json.dumps(board)))
        else:
            # Merged, not replaced: a rename or resize patch carries only
            # the board fields it changed, never the nodes.
            existing.update(json.loads(json.dumps(board)))
    for entry in patch.get("nodes") or []:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        board = next(
            (item for item in working["boards"] if item["id"] == entry.get("boardId")),
            None,
        )
        if board is None:
            raise WorkbenchError(INVALID_TARGET)
        node = entry.get("node")
        node_id = entry.get("nodeId") or (node or {}).get("id")
        existing = next(
            (item for item in board["nodes"] if item["id"] == node_id), None
        )
        if node is None:
            board["nodes"] = [item for item in board["nodes"] if item["id"] != node_id]
            for item in board["nodes"]:
                if node_id in (item["children"] or []):
                    item["children"] = [
                        child for child in item["children"] if child != node_id
                    ]
            continue
        if existing is None:
            position = entry.get("index")
            if isinstance(position, int) and 0 <= position <= len(board["nodes"]):
                board["nodes"].insert(position, json.loads(json.dumps(node)))
            else:
                board["nodes"].append(json.loads(json.dumps(node)))
        else:
            existing.clear()
            existing.update(json.loads(json.dumps(node)))
    return working


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkbenchError(INVALID_INPUT, detail=f"{label} must be a number")
    return float(value)


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise WorkbenchError(INVALID_INPUT, detail=f"{label} must be positive")
    return number


def _optional_ids(raw: object, expected: int, label: str) -> list[str] | None:
    """Client-supplied ids for nodes a command creates, when given."""
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != expected:
        raise WorkbenchError(INVALID_INPUT, detail=f"{label} must match nodeIds")
    if not all(isinstance(item, str) and item for item in raw):
        raise WorkbenchError(INVALID_INPUT, detail=f"{label} must be ids")
    if len(set(raw)) != len(raw):
        raise WorkbenchError(INVALID_INPUT, detail=f"{label} must be unique")
    return list(raw)


def _node_ids(raw: object) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise WorkbenchError(INVALID_INPUT)
    if not all(isinstance(item, str) and item for item in raw):
        raise WorkbenchError(INVALID_INPUT)
    return list(dict.fromkeys(raw))


# -- static board snapshot ----------------------------------------------


def snapshot_html(document: dict, board_id: str, *, title: str = "") -> str:
    """A static render of one board: layout only, nothing executed."""
    board = _board(document, board_id)
    boxes = []
    for node in sorted(board["nodes"], key=lambda item: _number(item["layout"].get("z", 0), "z")):
        geometry = node["layout"]
        x = _number(geometry.get("x", 0), "x")
        y = _number(geometry.get("y", 0), "y")
        width = geometry.get("width", 160)
        height = geometry.get("height", 32)
        label = _node_label(node)
        boxes.append(
            f'<div class="node {node["type"]}" style="left:{x}px;top:{y}px;'
            f'width:{width}px;height:{height}px;z-index:{int(_number(geometry.get("z", 0), "z"))}">'
            f'<span class="kind">{node["type"]}</span><span class="label">{label}</span></div>'
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title or board['name']}</title>
<style>
 body {{ font: 14px/1.4 system-ui, sans-serif; margin: 0; background: #eceef2; color: #16181d; }}
 .board {{ position: relative; margin: 16px; width: {board['width']}px; height: {board['height']}px;
   background: {board['background'] or '#ffffff'}; border: 1px solid #d3d7de; overflow: hidden; }}
 .node {{ position: absolute; box-sizing: border-box; border: 1px dashed #9aa3b2;
   border-radius: 6px; padding: 2px 4px; overflow: hidden; background: #f7f9fc; }}
 .node.text {{ border-style: solid; background: #ffffff; }}
 .node.instance {{ border-style: solid; border-color: #1f4fd8; background: #eef3ff; }}
 .kind {{ font-size: 10px; color: #6b7280; display: block; }}
 .label {{ font-size: 12px; }}
 h1 {{ font-size: 14px; margin: 16px 16px 0; }}
 p.note {{ margin: 0 16px; color: #555b66; font-size: 12px; }}
</style></head><body>
<h1>{board['name']} · {board['width']}×{board['height']}</h1>
<p class="note">静态布局快照：渲染画板几何与节点类型，不执行任何脚本，也不渲染组件源码内部结构。</p>
<div class="board">{''.join(boxes)}</div>
</body></html>
"""


def _node_label(node: dict) -> str:
    props = node["props"]
    if node["type"] == "text":
        return str(props.get("text", ""))[:60]
    if node["type"] in ("link", "button"):
        return str(props.get("label", ""))[:60]
    if node["type"] == "image":
        return str(props.get("source", ""))[:60]
    if node["type"] == "instance":
        count = len(props.get("params") or {})
        return f"实例 {str(props.get('instanceId') or props.get('assetId'))[:12]}… · 参数 {count}"
    if node["type"] == "slot":
        return f"slot {props.get('name', '')}"
    return str(props.get("label", node["type"]))[:60]


class CanvasService:
    """Canvas documents, transactional commands, and undo history."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        components: ComponentService,
        reuse: ReuseService | None = None,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.components = components
        self.reuse = reuse
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- helpers --------------------------------------------------------

    def _row(self, project_id: str, canvas_id: str) -> dict:
        row = self.store.canvas(canvas_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        return row

    def _document(self, row: dict) -> dict:
        return parse_canvas(row["document_json"])

    def _indexes(self, project_id: str) -> tuple[dict, dict]:
        components = self.components.component_index(project_id)
        instances = {
            row["instance_id"]: {
                "assetId": row["asset_id"],
                "revisionId": row["revision_id"],
            }
            for row in self.store.project_instances(project_id)
        }
        return components, instances

    def _verdict(self, project_id: str, document: dict) -> dict:
        components, instances = self._indexes(project_id)
        return validate_canvas(document, components=components, instances=instances)

    def _require_valid(self, project_id: str, document: dict) -> dict:
        verdict = self._verdict(project_id, document)
        if not verdict["valid"]:
            if any(error["kind"] == "instance-limit" for error in verdict["errors"]):
                # Capacity is its own answer, not a generic invalid input.
                raise WorkbenchError(
                    LIMIT_EXCEEDED,
                    detail=json.dumps(
                        [
                            error
                            for error in verdict["errors"]
                            if error["kind"] == "instance-limit"
                        ],
                        ensure_ascii=False,
                    ),
                )
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        return verdict

    def _check_counter(self, row: dict, operation: Operation) -> int:
        """R04: an explicit expected counter is required, never last-write-wins."""
        if operation.expected_counter is None:
            raise WorkbenchError(
                INVALID_INPUT, detail="canvas writes require an expected counter"
            )
        if int(operation.expected_counter) != int(row["counter"]):
            raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
        return int(row["counter"])

    def _history_summary(self, canvas_id: str) -> dict:
        rows = self.store.canvas_transactions(canvas_id)
        return {
            "applied": [row["sequence"] for row in rows if not row["undone"]],
            "undone": [row["sequence"] for row in rows if row["undone"]],
            "labels": [
                json.loads(row["transaction_json"])["label"] for row in rows
            ],
            "limit": UNDO_HISTORY_LIMIT,
            "canUndo": any(not row["undone"] for row in rows),
            "canRedo": any(row["undone"] for row in rows),
        }

    def _payload(self, project_id: str, row: dict) -> dict:
        document = self._document(row)
        return {
            "canvas": {
                "canvasId": row["canvas_id"],
                "projectId": row["project_id"],
                "name": row["name"],
                "counter": int(row["counter"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            },
            "document": document,
            "validation": self._verdict(project_id, document),
            "history": self._history_summary(row["canvas_id"]),
        }

    # -- reads ----------------------------------------------------------

    def list_for_project(self, project_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return {
            "canvases": [
                {
                    "canvasId": row["canvas_id"],
                    "name": row["name"],
                    "counter": int(row["counter"]),
                    "updatedAt": row["updated_at"],
                    "boardCount": len(
                        (json.loads(row["document_json"]).get("boards") or [])
                    ),
                }
                for row in self.store.project_canvases(project_id)
            ]
        }

    def detail(self, project_id: str, canvas_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return self._payload(project_id, self._row(project_id, canvas_id))

    def snapshot(
        self, project_id: str, canvas_id: str, *, board_id: object = None
    ) -> dict:
        self.service.require_project(project_id, scope="read")
        row = self._row(project_id, canvas_id)
        document = self._document(row)
        target = board_id or (document["boards"][0]["id"] if document["boards"] else None)
        if not isinstance(target, str) or not target:
            raise WorkbenchError(MISSING_DEPENDENCY)
        board = _board(document, target)
        html = snapshot_html(document, target, title=f"{row['name']} · {board['name']}")
        record = self.blobs.put(html.encode("utf-8"))
        return {
            "canvasId": canvas_id,
            "boardId": target,
            "boardName": board["name"],
            "contentHash": record.content_hash,
            "bytes": record.size,
            "previewPath": f"/p/{record.content_hash}/static?type=text/html",
            "note": (
                "静态布局快照：几何与节点类型，不执行脚本，也不渲染组件内部结构。"
            ),
        }

    # -- writes ---------------------------------------------------------

    def create(
        self, project_id: str, *, name: str, document: object, operation: Operation
    ) -> dict:
        replayed = self.service._replay(operation, kind="canvas-create", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        parsed = parse_canvas(document)
        # The name may arrive either as the request field or inside the
        # document; reject only when neither supplies one.
        document_name = parsed.get("name")
        resolved = (name.strip() if isinstance(name, str) else "") or (
            document_name.strip() if isinstance(document_name, str) else ""
        )
        if not resolved:
            raise WorkbenchError(
                INVALID_INPUT, detail="a canvas name is required"
            )
        parsed["name"] = resolved
        self._require_valid(project_id, parsed)
        canvas_id = str(uuid.uuid4())
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.create_canvas(
                canvas_id=canvas_id,
                project_id=project_id,
                name=resolved[:120],
                document=parsed,
                now=now,
            )
            return self._payload(project_id, self._row(project_id, canvas_id)), 0

        with self.store.transaction():
            result, counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind="canvas-create",
                entity_id=canvas_id,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                project_id=project_id,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def run_commands(
        self, project_id: str, canvas_id: str, *, commands: object, operation: Operation
    ) -> dict:
        """Apply 1..20 commands atomically: one transaction per command."""
        replayed = self.service._replay(
            operation, kind="canvas-commands", entity_id=canvas_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        if not isinstance(commands, list) or not commands:
            raise WorkbenchError(INVALID_INPUT)
        if len(commands) > MAX_COMMANDS_PER_BATCH:
            raise WorkbenchError(
                LIMIT_EXCEEDED,
                detail=f"单次最多 {MAX_COMMANDS_PER_BATCH} 条画布命令。",
            )
        row = self._row(project_id, canvas_id)
        self._check_counter(row, operation)
        components, instances = self._indexes(project_id)
        document = self._document(row)
        transactions: list[dict] = []
        for command in commands:
            document, before, after, label, targets = apply_command(
                document, command, components=components, instances=instances
            )
            transactions.append(
                {
                    "transactionId": str(uuid.uuid4()),
                    "kind": command.get("kind"),
                    "label": label,
                    "targetIds": targets,
                    "before": before,
                    "after": after,
                    "at": self._now(),
                }
            )
        self._require_valid(project_id, document)
        now = self._now()
        recorded: list[dict] = []

        def apply() -> tuple[dict, int]:
            # A new edit clears the redo branch (R09), then each command is
            # one history row, trimmed to the persisted undo limit.
            self.store.clear_canvas_redo(canvas_id)
            for transaction in transactions:
                sequence = self.store.append_canvas_transaction(
                    canvas_id=canvas_id, transaction=transaction, now=now
                )
                recorded.append({"sequence": sequence, "label": transaction["label"]})
            counter = self.store.save_canvas(
                canvas_id=canvas_id,
                document=document,
                bump=len(transactions),
                now=now,
            )
            self.store.trim_canvas_transactions(
                canvas_id=canvas_id, keep=UNDO_HISTORY_LIMIT
            )
            payload = self._payload(project_id, self._row(project_id, canvas_id))
            payload["transactions"] = recorded
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind="canvas-commands",
                entity_id=canvas_id,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                project_id=project_id,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def undo(self, project_id: str, canvas_id: str, *, operation: Operation) -> dict:
        return self._step(project_id, canvas_id, operation=operation, reverse=False)

    def redo(self, project_id: str, canvas_id: str, *, operation: Operation) -> dict:
        return self._step(project_id, canvas_id, operation=operation, reverse=True)

    def _step(
        self, project_id: str, canvas_id: str, *, operation: Operation, reverse: bool
    ) -> dict:
        kind = "canvas-redo" if reverse else "canvas-undo"
        replayed = self.service._replay(operation, kind=kind, entity_id=canvas_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._row(project_id, canvas_id)
        self._check_counter(row, operation)
        rows = self.store.canvas_transactions(canvas_id)
        candidates = [item for item in rows if bool(item["undone"]) == reverse]
        if not candidates:
            raise WorkbenchError(
                MISSING_DEPENDENCY,
                detail="没有可撤销的编辑" if not reverse else "没有可重做的编辑",
            )
        # Undo walks backwards from the newest edit; redo walks forwards
        # from the oldest undone one.
        picked = candidates[-1] if not reverse else candidates[0]
        transaction = json.loads(picked["transaction_json"])
        patch = transaction["before"] if not reverse else transaction["after"]
        document = apply_patch(self._document(row), patch)
        self._require_valid(project_id, document)
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.save_canvas(
                canvas_id=canvas_id, document=document, now=now
            )
            self.store.set_canvas_transaction_undone(
                canvas_id=canvas_id,
                sequence=picked["sequence"],
                undone=not reverse,
            )
            payload = self._payload(project_id, self._row(project_id, canvas_id))
            payload["stepped"] = {
                "sequence": picked["sequence"],
                "label": transaction["label"],
                "direction": "redo" if reverse else "undo",
            }
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind=kind,
                entity_id=canvas_id,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                project_id=project_id,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def rename(
        self, project_id: str, canvas_id: str, *, name: object, operation: Operation
    ) -> dict:
        replayed = self.service._replay(
            operation, kind="canvas-rename", entity_id=canvas_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        row = self._row(project_id, canvas_id)
        self._check_counter(row, operation)
        if not isinstance(name, str) or not name.strip():
            raise WorkbenchError(INVALID_INPUT)
        document = self._document(row)
        document["name"] = name.strip()[:120]
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.save_canvas(
                canvas_id=canvas_id,
                document=document,
                name=document["name"],
                now=now,
            )
            return self._payload(project_id, self._row(project_id, canvas_id)), counter

        with self.store.transaction():
            result, counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind="canvas-rename",
                entity_id=canvas_id,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                project_id=project_id,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def fork(
        self,
        project_id: str,
        canvas_id: str,
        *,
        name: object = None,
        document: object = None,
        operation: Operation,
    ) -> dict:
        """Save a conflicting draft as a new canvas instead of overwriting.

        A stale counter is a conflict, not a reason to last-write-wins: the
        maintainer's window keeps its own edits and stores them under a new
        canvas, leaving the other writer's state untouched.
        """
        replayed = self.service._replay(operation, kind="canvas-fork", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        source = self._row(project_id, canvas_id)
        branched = (
            parse_canvas(document)
            if document is not None
            else self._document(source)
        )
        default_name = f"{source['name']} 分支"
        branched["name"] = (
            str(name).strip()[:120] if isinstance(name, str) and name.strip() else default_name[:120]
        )
        self._require_valid(project_id, branched)
        canvas_id_new = str(uuid.uuid4())
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.create_canvas(
                canvas_id=canvas_id_new,
                project_id=project_id,
                name=branched["name"],
                document=branched,
                now=now,
            )
            payload = self._payload(project_id, self._row(project_id, canvas_id_new))
            payload["forkedFrom"] = canvas_id
            return payload, 0

        with self.store.transaction():
            result, counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind="canvas-fork",
                entity_id=canvas_id_new,
                payload_digest=operation.digest,
                resulting_counter=counter,
                result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
                project_id=project_id,
                now=now,
            )
        return {"result": result, "replayed": False, "counter": counter}
