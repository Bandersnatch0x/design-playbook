"""Typed component definitions and native page layout trees (R08).

The workbench owns one schema for a component (description, public property
schema and defaults, variants, states, slots, constraints, token/component
dependencies, docs) and one for a native page layout tree. Both are
validated by this module alone: the editor, the publication path, the
instance preview, and the layout checker all call the same parser, so a
definition that the preview can render is exactly the definition that may
be published.

Honesty rules this module enforces rather than documents:

- a native node is one of the declared node types; a screenshot or an
  arbitrary framework source file never gains internal editable layers;
- a definition cannot claim ``runnable-verified`` or ``native-editable``
  without a verification record (publication refuses it, see ``assets``);
- a distilled candidate is a candidate: it is a draft, it names the source
  revision and nodes it came from, and publication stays refused until the
  maintainer completes its public properties and dependencies.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Callable

from .assets import AssetService
from .blobs import BlobStore
from .errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    UNSUPPORTED,
    WorkbenchError,
)
from .reuse import ReuseService
from .service import Operation, WorkbenchService, utc_now
from .store import Store

KIND_COMPONENT = "component"
KIND_PAGE = "page"
KIND_TOKENS = "tokens"

#: Closed property types. A property type is a type, not a hint: the value
#: of a ``number`` property is a number even when a string would parse.
PROP_TYPES = frozenset({"string", "number", "boolean", "enum", "token", "asset"})

NODE_TYPES = frozenset(
    {
        "container",
        "stack",
        "grid",
        "text",
        "image",
        "link",
        "button",
        "instance",
        "slot",
    }
)

CONSTRAINT_KEYS = frozenset(
    {"minWidth", "maxWidth", "minHeight", "maxHeight", "aspectRatio"}
)

#: Geometry keys of a shared node: canvas boards and page layouts alike.
NODE_LAYOUT_KEYS = frozenset({"x", "y", "width", "height", "z"})

MAX_PROPS = 200
MAX_NODES = 500
MAX_VARIANTS = 40
MAX_SLOTS = 40
MAX_STATES = 40

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_DIMENSION = re.compile(r"^-?\d+(?:\.\d+)?(?:px|rem|em|%|vw|vh|ch|pt)?$")

_DOCUMENT_LABELS = {
    KIND_COMPONENT: ("component", "component-definition"),
    KIND_PAGE: ("layout-tree", "page-layout"),
}


_CONSTRAINT_KEYWORDS = frozenset(
    {"auto", "fit-content", "min-content", "max-content", "stretch", "none"}
)


def _constraint_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.strip()
    return bool(_DIMENSION.match(lowered)) or lowered in _CONSTRAINT_KEYWORDS


def _error(kind: str, path: str, **extra: object) -> dict:
    return {"kind": kind, "path": path, **extra}


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", name).strip("-.")
    return cleaned[:80] or "document"


def document_path(kind: str, name: str) -> str:
    """The logical document name of a workbench-owned asset.

    It names the stored document, never a project file: a component
    definition is not written into the project by publishing it.
    """
    suffix = "component.json" if kind == KIND_COMPONENT else "layout.json"
    return f"{_slug(name)}.{suffix}"


def parse_definition(raw: object) -> dict:
    """Parse a component definition into its typed form.

    Raises a typed error for anything that is not a definition document;
    the workbench never stores a definition it cannot first parse.
    """
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WorkbenchError(INVALID_INPUT, detail="definition must be JSON") from None
    if not isinstance(raw, dict):
        raise WorkbenchError(INVALID_INPUT)
    unknown = set(raw) - {
        "name",
        "description",
        "props",
        "variants",
        "states",
        "slots",
        "constraints",
        "dependencies",
        "docs",
        "tree",
        "candidate",
    }
    if unknown:
        raise WorkbenchError(
            UNSUPPORTED, detail=f"unknown definition field: {sorted(unknown)[0]}"
        )
    definition: dict = {
        "name": raw.get("name") or "",
        "description": raw.get("description") or "",
        "docs": raw.get("docs") or "",
        "props": [],
        "variants": [],
        "states": [],
        "slots": [],
        "constraints": {},
        "dependencies": {"tokens": [], "components": []},
        "tree": None,
        "candidate": None,
    }
    props = raw.get("props") or []
    if not isinstance(props, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(props) > MAX_PROPS:
        raise WorkbenchError(LIMIT_EXCEEDED)
    for entry in props:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        prop_type = entry.get("type")
        if prop_type not in PROP_TYPES:
            raise WorkbenchError(
                UNSUPPORTED, detail=f"unknown property type: {prop_type}"
            )
        definition["props"].append(
            {
                "name": entry.get("name"),
                "type": prop_type,
                "default": entry.get("default"),
                "required": bool(entry.get("required")),
                "description": entry.get("description") or "",
                "values": list(entry.get("values") or []),
            }
        )
    variants = raw.get("variants") or []
    if not isinstance(variants, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(variants) > MAX_VARIANTS:
        raise WorkbenchError(LIMIT_EXCEEDED)
    for entry in variants:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        definition["variants"].append(
            {"name": entry.get("name"), "values": list(entry.get("values") or [])}
        )
    states = raw.get("states") or []
    if not isinstance(states, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(states) > MAX_STATES:
        raise WorkbenchError(LIMIT_EXCEEDED)
    definition["states"] = list(states)
    slots = raw.get("slots") or []
    if not isinstance(slots, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(slots) > MAX_SLOTS:
        raise WorkbenchError(LIMIT_EXCEEDED)
    for entry in slots:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        definition["slots"].append(
            {
                "name": entry.get("name"),
                "required": bool(entry.get("required")),
                "description": entry.get("description") or "",
            }
        )
    constraints = raw.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise WorkbenchError(INVALID_INPUT)
    definition["constraints"] = dict(constraints)
    dependencies = raw.get("dependencies") or {}
    if not isinstance(dependencies, dict):
        raise WorkbenchError(INVALID_INPUT)
    for key in ("tokens", "components"):
        values = dependencies.get(key) or []
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise WorkbenchError(INVALID_INPUT)
        definition["dependencies"][key] = list(values)
    tree = raw.get("tree")
    if tree is not None:
        definition["tree"] = parse_layout(tree)
    candidate = raw.get("candidate")
    if candidate is not None:
        if not isinstance(candidate, dict):
            raise WorkbenchError(INVALID_INPUT)
        definition["candidate"] = {
            "fromAssetId": candidate.get("fromAssetId"),
            "fromRevisionId": candidate.get("fromRevisionId"),
            "nodeIds": list(candidate.get("nodeIds") or []),
            "complete": bool(candidate.get("complete")),
        }
    return definition


def parse_layout(raw: object) -> dict:
    """Parse a native page layout tree into ``{nodes: [...]}``."""
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WorkbenchError(INVALID_INPUT, detail="layout must be JSON") from None
    if not isinstance(raw, dict) or set(raw) - {"name", "nodes"}:
        raise WorkbenchError(INVALID_INPUT)
    nodes = raw.get("nodes")
    if not isinstance(nodes, list):
        raise WorkbenchError(INVALID_INPUT)
    if len(nodes) > MAX_NODES:
        raise WorkbenchError(LIMIT_EXCEEDED)
    parsed: list[dict] = []
    for entry in nodes:
        if not isinstance(entry, dict):
            raise WorkbenchError(INVALID_INPUT)
        node_type = entry.get("type")
        if node_type not in NODE_TYPES:
            raise WorkbenchError(UNSUPPORTED, detail=f"unknown node type: {node_type}")
        parsed.append(
            {
                "id": entry.get("id"),
                "type": node_type,
                "children": list(entry.get("children") or []),
                "props": dict(entry.get("props") or {}),
                "layout": dict(entry.get("layout") or {}),
            }
        )
    return {"name": raw.get("name") or "", "nodes": parsed}


def _prop_error(prop: dict) -> str | None:
    name = prop.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        return "invalid-prop-name"
    prop_type = prop["type"]
    default = prop.get("default")
    if prop_type == "enum":
        values = prop.get("values")
        if not values or not all(isinstance(item, str) and item for item in values):
            return "invalid-prop-values"
        if len(set(values)) != len(values):
            return "invalid-prop-values"
        if default is not None and default not in values:
            return "invalid-default"
        return None
    if default is None:
        return None
    if prop_type == "string":
        return None if isinstance(default, str) else "invalid-default"
    if prop_type == "number":
        if isinstance(default, bool) or not isinstance(default, (int, float)):
            return "invalid-default"
        return None
    if prop_type == "boolean":
        return None if isinstance(default, bool) else "invalid-default"
    if prop_type in ("token", "asset"):
        # Both are references: the value is the referenced name or asset ID.
        return None if isinstance(default, str) or default is None else "invalid-default"
    return "invalid-default"  # pragma: no cover - closed type set


def validate_definition(definition: dict, *, dependencies: list[dict] | None = None) -> dict:
    """The one definition validator, shared by edit, preview, and publish."""
    errors: list[dict] = []
    if not isinstance(definition.get("name"), str) or not definition["name"].strip():
        errors.append(_error("missing-name", "name"))
    seen_props: set[str] = set()
    for prop in definition["props"]:
        name = prop.get("name")
        problem = _prop_error(prop)
        if problem is not None:
            errors.append(_error(problem, f"props.{name}", property=name))
            continue
        if name in seen_props:
            errors.append(_error("duplicate-prop", f"props.{name}", property=name))
            continue
        seen_props.add(name)
    seen_variants: set[str] = set()
    for variant in definition["variants"]:
        name = variant.get("name")
        values = variant.get("values")
        path = f"variants.{name}"
        if not isinstance(name, str) or not _NAME.match(name):
            errors.append(_error("invalid-variant", path))
            continue
        if name in seen_variants:
            errors.append(_error("duplicate-variant", path, variant=name))
            continue
        seen_variants.add(name)
        if (
            not values
            or not all(isinstance(item, str) and item for item in values)
            or len(set(values)) != len(values)
        ):
            errors.append(_error("invalid-variant", path, variant=name))
        if name in seen_props:
            # A variant is not a property: the same name would give two
            # contradictory sources for one value.
            errors.append(_error("variant-shadows-prop", path, variant=name))
    seen_states: set[str] = set()
    for state in definition["states"]:
        if not isinstance(state, str) or not state.strip():
            errors.append(_error("invalid-state", "states"))
            continue
        if state in seen_states:
            errors.append(_error("duplicate-state", f"states.{state}"))
            continue
        seen_states.add(state)
    seen_slots: set[str] = set()
    for slot in definition["slots"]:
        name = slot.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            errors.append(_error("invalid-slot", "slots"))
            continue
        if name in seen_slots:
            errors.append(_error("duplicate-slot", f"slots.{name}", slot=name))
            continue
        seen_slots.add(name)
    for key, value in definition["constraints"].items():
        if key not in CONSTRAINT_KEYS:
            errors.append(_error("invalid-constraint", f"constraints.{key}"))
            continue
        if not _constraint_ok(value):
            errors.append(_error("invalid-constraint", f"constraints.{key}"))
    declared = [
        *definition["dependencies"]["tokens"],
        *definition["dependencies"]["components"],
    ]
    if len(declared) != len(set(declared)):
        errors.append(_error("duplicate-dependency", "dependencies"))
    candidate = definition.get("candidate")
    if candidate is not None:
        if not candidate.get("complete"):
            errors.append(
                _error(
                    "incomplete-candidate",
                    "candidate",
                    detail="候选尚未补全公开参数与依赖，不能发布。",
                )
            )
        if not candidate.get("fromAssetId") or not candidate.get("fromRevisionId"):
            errors.append(_error("invalid-candidate", "candidate"))
    return {
        "valid": not errors,
        "errors": errors,
        "propNames": sorted(seen_props),
        "variantNames": sorted(seen_variants),
        "slotNames": sorted(seen_slots),
        "dependencies": dependencies or [],
        "candidate": candidate,
    }


def validate_layout(
    layout: dict,
    *,
    components: dict[str, dict] | None = None,
    instances: dict[str, dict] | None = None,
) -> dict:
    """The one layout validator: ids, containment, node payloads, instances."""
    components = components or {}
    instances = instances or {}
    errors: list[dict] = []
    nodes = layout["nodes"]
    by_id: dict[str, dict] = {}
    for node in nodes:
        node_id = node.get("id")
        path = f"nodes.{node_id}"
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(_error("invalid-node", path))
            continue
        if node_id in by_id:
            errors.append(_error("duplicate-node", path, node=node_id))
            continue
        by_id[node_id] = node
    children_seen: dict[str, str] = {}
    for node in by_id.values():
        node_id = node["id"]
        path = f"nodes.{node_id}"
        for child in node["children"]:
            if not isinstance(child, str) or child not in by_id:
                errors.append(_error("unknown-child", path, node=node_id, child=child))
                continue
            if child == node_id:
                errors.append(_error("node-cycle", path, node=node_id))
                continue
            if child in children_seen:
                errors.append(
                    _error("duplicate-parent", f"nodes.{child}", node=child)
                )
                continue
            children_seen[child] = node_id
        problem = _node_payload_error(node, components, instances)
        if problem is not None:
            errors.append(_error(problem, path, node=node_id))
        layout_problem = _node_layout_error(node)
        if layout_problem is not None:
            errors.append(_error(layout_problem, f"{path}.layout", node=node_id))
    for node in by_id.values():
        if _reaches_itself(node, by_id):
            errors.append(_error("node-cycle", f"nodes.{node['id']}", node=node["id"]))
    return {
        "valid": not errors,
        "errors": errors,
        "nodeIds": sorted(by_id),
        "roots": sorted(
            node_id for node_id in by_id if node_id not in children_seen
        ),
    }


def _node_layout_error(node: dict) -> str | None:
    """Geometry is part of the shared node schema, validated once."""
    geometry = node.get("layout") or {}
    if not isinstance(geometry, dict):
        return "invalid-node-layout"
    for key, value in geometry.items():
        if key not in NODE_LAYOUT_KEYS:
            return "unknown-node-layout-key"
        if key == "z":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return "invalid-node-layout"
            continue
        if isinstance(value, bool):
            return "invalid-node-layout"
        if isinstance(value, (int, float)):
            if key in ("width", "height") and value <= 0:
                return "invalid-node-layout"
            continue
        if isinstance(value, str) and _constraint_ok(value):
            continue
        return "invalid-node-layout"
    return None


def _node_payload_error(
    node: dict,
    components: dict[str, dict],
    instances: dict[str, dict] | None = None,
) -> str | None:
    node_type = node["type"]
    payload = node["props"]
    if node_type == "text":
        return None if isinstance(payload.get("text"), str) else "missing-node-payload"
    if node_type == "image":
        return (
            None
            if isinstance(payload.get("source"), str) and payload["source"]
            else "missing-node-payload"
        )
    if node_type in ("link", "button"):
        if isinstance(payload.get("label"), str) and payload["label"]:
            return None
        return "missing-node-payload"
    if node_type == "slot":
        name = payload.get("name")
        return None if isinstance(name, str) and name else "missing-node-payload"
    if node_type == "instance":
        # Two honest forms: a fixed-revision instance owned by the reuse
        # owner (upgradeable), or an inline parameter set against a
        # published component's declared surface.
        instance_id = payload.get("instanceId")
        if isinstance(instance_id, str) and instance_id:
            if (instances or {}).get(instance_id) is None:
                return "unresolved-instance"
            return None
        asset_id = payload.get("assetId")
        if not isinstance(asset_id, str) or not asset_id:
            return "missing-node-payload"
        entry = components.get(asset_id)
        if entry is None:
            # An instance node names a component that must be resolvable in
            # this project; an unresolved one is a missing dependency.
            return "unresolved-instance"
        if not entry.get("published"):
            return "unpublished-instance"
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return "invalid-instance-params"
        if check_params(entry["definition"], params):
            return "invalid-instance-params"
        return None
    for key in payload:
        if key not in {
            "direction",
            "gap",
            "padding",
            "align",
            "columns",
            "tokenRef",
            "label",
        }:
            return "unknown-node-field"
    return None


def _reaches_itself(node: dict, by_id: dict[str, dict]) -> bool:
    seen: set[str] = set()
    stack = list(node["children"])
    while stack:
        current = stack.pop()
        if current == node["id"]:
            return True
        if current in seen:
            continue
        seen.add(current)
        child = by_id.get(current)
        if child is not None:
            stack.extend(child["children"])
    return False


def check_params(definition: dict, params: dict) -> list[dict]:
    """Validate instance parameters against the public property schema."""
    errors: list[dict] = []
    props = {prop["name"]: prop for prop in definition["props"] if prop.get("name")}
    for name in params:
        if name not in props:
            errors.append(_error("unknown-param", f"params.{name}", property=name))
    for name, prop in props.items():
        value = params.get(name, prop.get("default"))
        if value is None and (prop["required"] or prop.get("default") is None):
            if prop["required"]:
                errors.append(_error("missing-param", f"params.{name}", property=name))
            continue
        if value is None:
            continue
        problem = _param_type_error(prop, value)
        if problem is not None:
            errors.append(
                _error(problem, f"params.{name}", property=name, expected=prop["type"])
            )
    return errors


def _param_type_error(prop: dict, value: object) -> str | None:
    prop_type = prop["type"]
    if prop_type == "string":
        return None if isinstance(value, str) else "invalid-param-value"
    if prop_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "invalid-param-value"
        return None
    if prop_type == "boolean":
        return None if isinstance(value, bool) else "invalid-param-value"
    if prop_type == "enum":
        return None if value in prop.get("values", []) else "invalid-param-value"
    if prop_type in ("token", "asset"):
        return None if isinstance(value, str) and value else "invalid-param-value"
    return "invalid-param-value"  # pragma: no cover - closed type set


def resolve_params(definition: dict, params: dict) -> dict:
    """Defaults first, provided values second: the resolved instance state."""
    resolved: dict = {}
    for prop in definition["props"]:
        name = prop.get("name")
        if not name:
            continue
        if name in params:
            resolved[name] = params[name]
        elif prop.get("default") is not None:
            resolved[name] = prop["default"]
    return resolved


def instance_html(
    definition: dict, params: dict, *, slots: dict | None = None, title: str = ""
) -> str:
    """A sample rendered from the resolved instance state.

    This is a *sample* of the declared public surface: it shows the public
    properties, the declared slots, and the declared states, and it says so.
    It is not a claim that a source component was rendered.
    """
    resolved = resolve_params(definition, params)
    rows = "\n".join(
        f"<tr><th>{prop['name']}</th><td><code>{_text(resolved.get(prop['name']))}</code></td>"
        f"<td>{prop['type']}</td></tr>"
        for prop in definition["props"]
        if prop.get("name") in resolved
    )
    slot_rows = "\n".join(
        f"<li><code>{slot.get('name')}</code>"
        f"{' · 必填' if slot.get('required') else ' · 可选'}"
        f"{' · 已提供' if (slots or {}).get(slot.get('name')) else ''}"
        f"</li>"
        for slot in definition["slots"]
    )
    states = "、".join(definition["states"]) or "未声明"
    variants = "、".join(
        f"{variant.get('name')}({'/'.join(variant.get('values') or [])})"
        for variant in definition["variants"]
    ) or "未声明"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title or definition['name']}</title>
<style>
 body {{ font: 15px/1.5 system-ui, sans-serif; margin: 1.5rem; color: #16181d; }}
 h1 {{ font-size: 1.15rem; }} h2 {{ font-size: 0.95rem; margin-top: 1.2rem; }}
 table {{ border-collapse: collapse; font-size: 0.85rem; }}
 th, td {{ border: 1px solid #d3d7de; padding: 0.2rem 0.5rem; text-align: left; }}
 code {{ background: #f2f4f7; padding: 0 0.25rem; border-radius: 3px; }}
 p.note {{ color: #555b66; font-size: 0.85rem; }}
</style></head><body>
<h1>组件样例：{definition['name']}</h1>
<p class="note">样例由声明的公开属性渲染，不是源码组件运行结果；未执行组件源码。</p>
<h2>当前参数</h2>
<table><tr><th>属性</th><th>值</th><th>类型</th></tr>{rows}</table>
<h2>slots</h2><ul>{slot_rows or '<li>未声明 slot</li>'}</ul>
<h2>变体</h2><p>{variants}</p>
<h2>状态</h2><p>{states}</p>
</body></html>
"""


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "—"
    return str(value)


class ComponentService:
    """Component definitions, native layout trees, and distill candidates."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        assets: AssetService,
        reuse: ReuseService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.assets = assets
        self.reuse = reuse
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- shared plumbing ------------------------------------------------

    def _require_asset(self, project_id: str, asset_id: str, *, kind: str) -> dict:
        row = self.store.asset(asset_id)
        if row is None or row["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        if row["kind"] != kind:
            raise WorkbenchError(
                UNSUPPORTED, detail=f"asset is not a {kind}"
            )
        return row

    def _document_bytes(self, asset_id: str, revision: dict | None = None) -> tuple[bytes, dict]:
        source = revision or self.store.latest_revision(asset_id)
        if source is not None:
            manifest = json.loads(source["manifest_json"])
            if manifest:
                return self.blobs.read(manifest[0]["contentHash"]), {
                    "kind": "revision",
                    "revisionId": source["revision_id"],
                    "revisionNumber": source["revision_number"],
                }
        draft = self.store.draft(asset_id)
        manifest = json.loads(draft["attributes_json"]).get("manifest", [])
        if not manifest:
            raise WorkbenchError(MISSING_DEPENDENCY)
        return self.blobs.read(manifest[0]["contentHash"]), {"kind": "draft"}

    def _component(self, project_id: str, asset_id: str) -> dict:
        self._require_asset(project_id, asset_id, kind=KIND_COMPONENT)
        data, source = self._document_bytes(asset_id)
        definition = parse_definition(data)
        return {
            "assetId": asset_id,
            "definition": definition,
            "validation": self._verdict(project_id, asset_id, definition),
            "source": source,
        }

    def _verdict(self, project_id: str, asset_id: str, definition: dict) -> dict:
        """The definition verdict, including why a dependency is unusable."""
        resolved, dependency_errors = self._dependency_report(
            project_id, asset_id, definition
        )
        verdict = validate_definition(definition, dependencies=resolved)
        verdict["errors"] = [*verdict["errors"], *dependency_errors]
        verdict["valid"] = not verdict["errors"]
        return verdict

    def _dependency_report(
        self, project_id: str, asset_id: str, definition: dict
    ) -> tuple[list[dict], list[dict]]:
        resolved: list[dict] = []
        errors: list[dict] = []
        declared = [
            *(("tokens", item) for item in definition["dependencies"]["tokens"]),
            *(("components", item) for item in definition["dependencies"]["components"]),
        ]
        for declared_kind, dep_asset_id in declared:
            kind = KIND_TOKENS if declared_kind == "tokens" else KIND_COMPONENT
            path = f"dependencies.{declared_kind}.{dep_asset_id}"
            if dep_asset_id == asset_id:
                errors.append(_error("self-dependency", path, dependency=dep_asset_id))
                continue
            row = self.store.asset(dep_asset_id)
            if row is None or row["project_id"] != project_id or row["kind"] != kind:
                errors.append(
                    _error("unresolved-dependency", path, dependency=dep_asset_id)
                )
                continue
            revision = self.store.latest_revision(dep_asset_id)
            if revision is None:
                errors.append(
                    _error("unpublished-dependency", path, dependency=dep_asset_id)
                )
                continue
            resolved.append(
                {"assetId": dep_asset_id, "revisionId": revision["revision_id"]}
            )
        return resolved, errors

    def _resolve_dependencies(
        self, project_id: str, asset_id: str, definition: dict
    ) -> list[dict]:
        resolved, errors = self._dependency_report(project_id, asset_id, definition)
        if errors:
            raise WorkbenchError(
                MISSING_DEPENDENCY,
                detail=json.dumps(errors, ensure_ascii=False),
            )
        return resolved

    def _write_document(
        self,
        *,
        project_id: str,
        asset_id: str,
        kind: str,
        text: str,
        capabilities: list[str],
        locators: list[dict],
        operation: Operation,
        mutation_kind: str,
    ) -> dict:
        record = self.blobs.put(text.encode("utf-8"))
        draft = self.store.draft(asset_id)
        attributes = json.loads(draft["attributes_json"])
        carrier, document = _DOCUMENT_LABELS[kind]
        attributes["manifest"] = [
            {
                "path": document_path(kind, attributes.get("displayName") or draft["name"]),
                "contentHash": record.content_hash,
                "size": record.size,
                "mediaType": "application/json",
                "carrier": carrier,
                "encoding": "utf-8",
            }
        ]
        attributes["carrier"] = carrier
        attributes["document"] = document
        attributes["capabilities"] = list(capabilities)
        attributes["sourceLocators"] = list(locators)
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.update_draft(
                asset_id=asset_id,
                tags=json.loads(draft["tags_json"]),
                attributes=attributes,
                now=now,
            )
            counter = self.store.bump_asset_counter(asset_id=asset_id, now=now)
            payload = self.assets._asset_payload(
                self.store.asset(asset_id), self.store.draft(asset_id), None
            )
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self.assets._record(
                operation=operation,
                kind=mutation_kind,
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def _create_document_asset(
        self,
        *,
        project_id: str,
        kind: str,
        name: str,
        text: str,
        capabilities: list[str],
        locators: list[dict],
        operation: Operation,
        mutation_kind: str,
    ) -> dict:
        replayed = self.service._replay(operation, kind=mutation_kind, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        record = self.blobs.put(text.encode("utf-8"))
        asset_id = str(uuid.uuid4())
        carrier, document = _DOCUMENT_LABELS[kind]
        now = self._now()
        attributes = {
            "manifest": [
                {
                    "path": document_path(kind, name),
                    "contentHash": record.content_hash,
                    "size": record.size,
                    "mediaType": "application/json",
                    "carrier": carrier,
                    "encoding": "utf-8",
                }
            ],
            "carrier": carrier,
            "document": document,
            "capabilities": list(capabilities),
            "sourceLocators": list(locators),
            "roots": [],
            "warnings": [],
            "displayName": name,
        }

        def apply() -> tuple[dict, int]:
            self.store.create_asset(
                asset_id=asset_id,
                project_id=project_id,
                kind=kind,
                name=name,
                tags=[],
                attributes=attributes,
                now=now,
            )
            payload = self.assets._asset_payload(
                self.store.asset(asset_id), self.store.draft(asset_id), None
            )
            return payload, 0

        with self.store.transaction():
            result, counter = apply()
            self.assets._record(
                operation=operation,
                kind=mutation_kind,
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    # -- components -----------------------------------------------------

    def component(self, project_id: str, asset_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        return self._component(project_id, asset_id)

    def create_component(
        self, project_id: str, *, name: str, definition: object, operation: Operation
    ) -> dict:
        if not isinstance(name, str) or not name.strip():
            raise WorkbenchError(INVALID_INPUT)
        parsed = parse_definition(definition)
        parsed["name"] = parsed["name"] or name.strip()
        verdict = validate_definition(parsed)
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        return self._create_document_asset(
            project_id=project_id,
            kind=KIND_COMPONENT,
            name=name.strip()[:120],
            text=json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True),
            capabilities=["reference"],
            locators=[],
            operation=operation,
            mutation_kind="component-create",
        )

    def update_definition(
        self,
        project_id: str,
        asset_id: str,
        *,
        definition: object,
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(operation, kind="component-update", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._require_asset(project_id, asset_id, kind=KIND_COMPONENT)
        parsed = parse_definition(definition)
        verdict = validate_definition(parsed)
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        draft = self.store.draft(asset_id)
        attributes = json.loads(draft["attributes_json"])
        outcome = self._write_document(
            project_id=project_id,
            asset_id=asset_id,
            kind=KIND_COMPONENT,
            text=json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True),
            capabilities=attributes.get("capabilities") or ["reference"],
            locators=attributes.get("sourceLocators") or [],
            operation=operation,
            mutation_kind="component-update",
        )
        outcome["result"]["validation"] = verdict
        return outcome

    def publish(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        """Publish a component only when its definition and deps are complete."""
        replayed = self.service._replay(operation, kind="component-publish", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._require_asset(project_id, asset_id, kind=KIND_COMPONENT)
        data, _ = self._document_bytes(asset_id)
        definition = parse_definition(data)
        dependencies = self._resolve_dependencies(project_id, asset_id, definition)
        verdict = validate_definition(definition, dependencies=dependencies)
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        if self.reuse.would_cycle(
            project_id=project_id, asset_id=asset_id, dependencies=dependencies
        ):
            raise WorkbenchError(MISSING_DEPENDENCY, detail="dependency cycle")
        # The dependency-recording publication path is owned by the reuse
        # module; the derived operation ID keeps the two mutations distinct
        # while this call still answers replays itself.
        outcome = self.reuse.publish_with_dependencies(
            project_id,
            asset_id,
            dependencies=dependencies,
            operation=Operation(
                operation_id=f"{operation.operation_id}:dependencies",
                payload={"action": "publish-with-deps", "assetId": asset_id},
            ),
        )
        result = outcome["result"]
        result["definition"] = definition
        result["validation"] = verdict
        return {"result": result, "replayed": False, "counter": outcome["counter"]}

    def instance_preview(
        self, project_id: str, asset_id: str, *, params: object = None
    ) -> dict:
        """Render the declared public surface with the current parameters."""
        self.service.require_project(project_id, scope="read")
        self._require_asset(project_id, asset_id, kind=KIND_COMPONENT)
        if params is not None and not isinstance(params, dict):
            raise WorkbenchError(INVALID_INPUT)
        data, source = self._document_bytes(asset_id)
        definition = parse_definition(data)
        supplied = dict(params or {})
        errors = check_params(definition, supplied)
        if errors:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(errors, ensure_ascii=False)
            )
        resolved = resolve_params(definition, supplied)
        html = instance_html(
            definition, supplied, title=f"{definition['name']} 实例"
        ).encode("utf-8")
        record = self.blobs.put(html)
        attributes = json.loads(self.store.draft(asset_id)["attributes_json"])
        return {
            "assetId": asset_id,
            "params": resolved,
            "unsetParams": [
                prop["name"]
                for prop in definition["props"]
                if prop.get("default") is None and prop["name"] not in resolved
            ],
            "declared": {
                "variants": [variant.get("name") for variant in definition["variants"]],
                "states": list(definition["states"]),
                "slots": [slot.get("name") for slot in definition["slots"]],
            },
            "capabilities": attributes.get("capabilities", []),
            "limitations": (
                "样例只渲染声明的公开属性；组件源码未执行，截图与任意框架源码不会有内部可编辑图层。"
            ),
            "contentHash": record.content_hash,
            "previewUrl": f"/p/{record.content_hash}/static?type=text/html",
            "source": source,
        }

    # -- pages ----------------------------------------------------------

    def component_index(self, project_id: str) -> dict[str, dict]:
        """Every component in the project with its published state.

        Layout validation resolves instance nodes through this index, so an
        instance of an unpublishable or unpublished component is refused by
        the same rule the component editor knows.
        """
        return self._component_index(project_id)

    def _component_index(self, project_id: str) -> dict[str, dict]:
        """Every component in the project with its published state.

        Layout validation resolves instance nodes through this index, so an
        instance of an unpublishable or unpublished component is refused by
        the same rule the component editor knows.
        """
        index: dict[str, dict] = {}
        for row in self.store.project_assets(project_id):
            if row["kind"] != KIND_COMPONENT:
                continue
            revision = self.store.latest_revision(row["asset_id"])
            try:
                data, _ = self._document_bytes(row["asset_id"])
                definition = parse_definition(data)
            except WorkbenchError:
                # A component whose stored document cannot be parsed cannot
                # be instantiated: an instance node of it stays unresolved.
                continue
            index[row["asset_id"]] = {
                "definition": definition,
                "published": revision is not None,
            }
        return index

    def page_layout(self, project_id: str, asset_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        self._require_asset(project_id, asset_id, kind=KIND_PAGE)
        data, source = self._document_bytes(asset_id)
        layout = parse_layout(data)
        return {
            "assetId": asset_id,
            "layout": layout,
            "validation": validate_layout(layout, components=self._component_index(project_id)),
            "source": source,
        }

    def create_page(
        self, project_id: str, *, name: str, layout: object, operation: Operation
    ) -> dict:
        if not isinstance(name, str) or not name.strip():
            raise WorkbenchError(INVALID_INPUT)
        parsed = parse_layout(layout)
        parsed["name"] = parsed["name"] or name.strip()
        verdict = validate_layout(
            parsed, components=self._component_index(project_id)
        )
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        return self._create_document_asset(
            project_id=project_id,
            kind=KIND_PAGE,
            name=name.strip()[:120],
            text=json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True),
            capabilities=["reference"],
            locators=[],
            operation=operation,
            mutation_kind="page-create",
        )

    def update_layout(
        self,
        project_id: str,
        asset_id: str,
        *,
        layout: object,
        operation: Operation,
    ) -> dict:
        replayed = self.service._replay(operation, kind="page-update", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._require_asset(project_id, asset_id, kind=KIND_PAGE)
        parsed = parse_layout(layout)
        verdict = validate_layout(
            parsed, components=self._component_index(project_id)
        )
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        draft = self.store.draft(asset_id)
        attributes = json.loads(draft["attributes_json"])
        outcome = self._write_document(
            project_id=project_id,
            asset_id=asset_id,
            kind=KIND_PAGE,
            text=json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True),
            capabilities=attributes.get("capabilities") or ["reference"],
            locators=attributes.get("sourceLocators") or [],
            operation=operation,
            mutation_kind="page-update",
        )
        outcome["result"]["validation"] = verdict
        return outcome

    def publish_page(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        replayed = self.service._replay(operation, kind="page-publish", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._require_asset(project_id, asset_id, kind=KIND_PAGE)
        data, _ = self._document_bytes(asset_id)
        layout = parse_layout(data)
        verdict = validate_layout(
            layout, components=self._component_index(project_id)
        )
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        outcome = self.assets.publish_revision(
            project_id,
            asset_id,
            operation=Operation(
                operation_id=f"{operation.operation_id}:revision",
                payload={"action": "publish", "assetId": asset_id},
            ),
        )
        outcome["result"]["validation"] = verdict
        return outcome

    # -- page block to component candidate ------------------------------

    def distill_candidate(
        self,
        project_id: str,
        page_asset_id: str,
        *,
        node_ids: object,
        name: object = None,
        operation: Operation,
    ) -> dict:
        """Turn a page block into a *candidate* component asset.

        The candidate records where it came from and stays a draft: the
        maintainer completes its public properties and dependencies and
        publishes it separately. The source page is never written, and no
        reuse, verification, or approval is claimed.
        """
        replayed = self.service._replay(operation, kind="component-distill", project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        page = self.store.asset(page_asset_id)
        if page is None or page["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        if page["kind"] != KIND_PAGE:
            raise WorkbenchError(UNSUPPORTED, detail="asset is not a page")
        revision = self.store.latest_revision(page_asset_id)
        data, _ = self._document_bytes(page_asset_id)
        layout = parse_layout(data)
        verdict = validate_layout(
            layout, components=self._component_index(project_id)
        )
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        if not isinstance(node_ids, list) or not node_ids:
            raise WorkbenchError(INVALID_INPUT)
        by_id = {node["id"]: node for node in layout["nodes"]}
        selected: set[str] = set()
        stack = list(node_ids)
        while stack:
            current = stack.pop()
            node = by_id.get(current)
            if node is None:
                raise WorkbenchError(INVALID_TARGET)
            if current in selected:
                continue
            selected.add(current)
            stack.extend(node["children"])
        if len(selected) > MAX_NODES:
            raise WorkbenchError(LIMIT_EXCEEDED)
        nodes = [
            json.loads(json.dumps(node))
            for node in layout["nodes"]
            if node["id"] in selected
        ]
        candidate_name = (
            str(name).strip()[:120]
            if isinstance(name, str) and name.strip()
            else f"{page['name']} 区块"
        )
        page_hash = revision["content_hash"] if revision else None
        definition = {
            "name": candidate_name,
            "description": (
                f"来自页面「{page['name']}」的提炼候选；公开参数与依赖需维护者补全。"
            ),
            "props": [],
            "variants": [],
            "states": [],
            "slots": [],
            "constraints": {},
            "dependencies": {"tokens": [], "components": []},
            "docs": "",
            "tree": {"name": candidate_name, "nodes": nodes},
            "candidate": {
                "fromAssetId": page_asset_id,
                "fromRevisionId": revision["revision_id"] if revision else None,
                "nodeIds": sorted(selected),
                "complete": False,
            },
        }
        locators = [
            {
                "kind": "asset-revision",
                "projectId": project_id,
                "assetId": page_asset_id,
                "revisionId": revision["revision_id"] if revision else None,
                "sourceHash": page_hash,
                "run": None,
                "objectType": "revision",
                "objectId": revision["revision_id"] if revision else page_asset_id,
                "nodeIds": sorted(selected),
            }
        ]
        outcome = self._create_document_asset(
            project_id=project_id,
            kind=KIND_COMPONENT,
            name=candidate_name,
            text=json.dumps(definition, ensure_ascii=False, indent=2, sort_keys=True),
            capabilities=["reference"],
            locators=locators,
            operation=operation,
            mutation_kind="component-distill",
        )
        result = outcome["result"]
        result["candidate"] = definition["candidate"]
        result["sourceLocator"] = locators[0]
        result["ownerNote"] = (
            "提炼候选项由页面区块生成，只作为草稿存在；补全公开参数与依赖后另行发布。"
            "源页面未被修改，也不因此声称已复用。"
        )
        return outcome
