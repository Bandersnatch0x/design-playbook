"""Typed design-system tokens, themes, and preview (R07).

One parser and one validator serve editing, rendering, and publication, so
the same rule that stops a broken token set from being published is the
rule the preview and the diff are computed with. Reference resolution is
part of that single implementation: a reference to a missing token, a
reference cycle, and a reference whose target has a different type are all
rejected before anything is written -- and a token *type* is never guessed
from a value's shape alone.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from .assets import AssetService
from .blobs import BlobStore, digest_bytes
from .errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    MISSING_DEPENDENCY,
    UNSUPPORTED,
    WorkbenchError,
)
from .proposals import ProposalService
from .service import Operation, WorkbenchService, utc_now
from .store import Store

#: The closed token categories (R07). A category is a type, not a hint.
CATEGORIES: dict[str, str] = {
    "color": "color",
    "typography": "typography",
    "space": "space",
    "spacing": "space",
    "size": "size",
    "radius": "radius",
    "shadow": "shadow",
}

THEME_KEY = "theme"
REF_KEY = "$ref"

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FUNCTION_COLOR = re.compile(r"^(?:rgb|rgba|hsl|hsla|color-mix)\(.*\)$")
_NAMED_COLORS = frozenset(
    {
        "transparent", "currentcolor", "black", "white", "red", "green", "blue",
        "gray", "grey", "orange", "yellow", "purple", "pink", "brown", "teal",
        "navy", "olive", "lime", "aqua", "cyan", "magenta", "silver", "maroon",
    }
)
_DIMENSION = re.compile(r"^-?\d+(?:\.\d+)?(?:px|rem|em|%|vw|vh|ch|pt|s|ms)?$")


def _classification(category: str) -> str:
    if category in ("space", "spacing"):
        return "space"
    return CATEGORIES.get(category, "")


def parse_document(raw: object) -> dict:
    """Parse a tokens document into ``{category: {name: value}}`` + themes.

    Raises a typed error for anything that is not a tokens document: the
    workbench never edits a file it cannot first parse.
    """
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WorkbenchError(INVALID_INPUT, detail="tokens must be JSON") from None
    if not isinstance(raw, dict):
        raise WorkbenchError(INVALID_INPUT)
    tokens: dict[str, dict] = {}
    themes: dict[str, dict] = {}
    for category, entries in raw.items():
        if category == THEME_KEY:
            if not isinstance(entries, dict):
                raise WorkbenchError(INVALID_INPUT)
            for theme_name, overrides in entries.items():
                if not isinstance(overrides, dict):
                    raise WorkbenchError(INVALID_INPUT)
                themes[str(theme_name)] = parse_document(overrides)["tokens"]
            continue
        if category not in CATEGORIES:
            raise WorkbenchError(
                UNSUPPORTED, detail=f"unknown token category: {category}"
            )
        if not isinstance(entries, dict):
            raise WorkbenchError(INVALID_INPUT)
        bucket = tokens.setdefault(_classification(category), {})
        for name, value in entries.items():
            if not isinstance(name, str) or not name:
                raise WorkbenchError(INVALID_INPUT)
            bucket[str(name)] = value
    return {"tokens": tokens, "themes": themes}


def resolve_references(document: dict) -> tuple[dict, list[dict]]:
    """Resolve every ``$ref`` and report missing, cyclic, or mistyped ones."""
    tokens = document["tokens"]
    errors: list[dict] = []

    def owner_of(name: str) -> str | None:
        if "." in name:
            return name.split(".", 1)[0]
        for category, bucket in tokens.items():
            if name in bucket:
                return category
        return None

    resolved: dict = {}
    for category, bucket in tokens.items():
        resolved[category] = {}
        for name, value in bucket.items():
            resolved[category][name] = _resolve_value(
                category, tokens, value, [], errors, owner_of
            )
    return resolved, errors


def _resolve_value(
    category: str,
    tokens: dict,
    value: object,
    trail: list[str],
    errors: list[dict],
    owner_of: Callable[[str], str | None],
) -> object:
    if isinstance(value, dict) and REF_KEY in value:
        target = value[REF_KEY]
        if not isinstance(target, str) or not target:
            errors.append({"kind": "invalid-reference", "path": ".".join(trail)})
            return None
        if target in trail:
            errors.append({"kind": "reference-cycle", "path": " -> ".join([*trail, target])})
            return None
        target_category = owner_of(target)
        if target_category is None:
            errors.append(
                {"kind": "missing-reference", "path": ".".join(trail), "target": target}
            )
            return None
        if target_category != category:
            # A colour alias must point at a colour: a mismatched reference
            # is a type error, not an implicit conversion.
            errors.append(
                {
                    "kind": "type-mismatch",
                    "path": ".".join(trail),
                    "expected": category,
                    "target": target,
                    "actual": target_category,
                }
            )
            return None
        bare = target.split(".", 1)[1] if "." in target else target
        bucket = tokens.get(target_category)
        if bucket is None or bare not in bucket:
            # A reference into a known category that names no token is a
            # missing reference, never a silent self-alias.
            errors.append(
                {"kind": "missing-reference", "path": ".".join(trail), "target": target}
            )
            return None
        return _resolve_value(
            category, tokens, bucket[bare], [*trail, target], errors, owner_of
        )
    return value


def validate_value(category: str, value: object) -> str | None:
    """Return an error kind when a resolved value does not fit its type."""
    if category == "color":
        if not isinstance(value, str):
            return "type-mismatch"
        lowered = value.strip().lower()
        if (
            _HEX_COLOR.match(lowered)
            or _FUNCTION_COLOR.match(lowered)
            or lowered in _NAMED_COLORS
            or lowered.startswith("var(")
        ):
            return None
        return "invalid-value"
    if category in ("space", "size", "radius"):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return None
        if isinstance(value, str) and _DIMENSION.match(value.strip()):
            return None
        return "invalid-value"
    if category == "shadow":
        if isinstance(value, (str, dict)):
            return None
        return "invalid-value"
    if category == "typography":
        # A typography token is a structured object: any other shape is a
        # type error, not a merely invalid value.
        if isinstance(value, dict):
            return None
        return "type-mismatch"
    return "type-mismatch"


def validate_document(document: dict) -> dict:
    """The one validator: structure, references, and value types."""
    resolved, errors = resolve_references(document)
    for category, bucket in resolved.items():
        for name, value in bucket.items():
            if value is None and any(
                error["path"].endswith(name) for error in errors
            ):
                continue
            problem = validate_value(category, value)
            if problem is not None:
                errors.append(
                    {
                        "kind": problem,
                        "path": f"{category}.{name}",
                        "category": category,
                    }
                )
    for theme_name, overrides in document["themes"].items():
        for category, bucket in overrides.items():
            for name, value in bucket.items():
                problem = validate_value(category, value)
                if problem is not None:
                    errors.append(
                        {
                            "kind": problem,
                            "path": f"theme.{theme_name}.{category}.{name}",
                            "category": category,
                        }
                    )
    return {
        "valid": not errors,
        "errors": errors,
        "resolved": resolved,
        "tokenCount": sum(len(bucket) for bucket in resolved.values()),
        "themes": sorted(document["themes"]),
        "categories": sorted(document["tokens"]),
    }


def diff_documents(before: dict, after: dict) -> dict:
    """A stable, per-token difference between two token sets."""
    before_flat = _flatten(before)
    after_flat = _flatten(after)
    added = sorted(set(after_flat) - set(before_flat))
    removed = sorted(set(before_flat) - set(after_flat))
    changed = sorted(
        key
        for key in set(before_flat) & set(after_flat)
        if before_flat[key] != after_flat[key]
    )
    return {
        "added": [{"path": key, "value": after_flat[key]} for key in added],
        "removed": [{"path": key, "value": before_flat[key]} for key in removed],
        "changed": [
            {
                "path": key,
                "from": before_flat[key],
                "to": after_flat[key],
            }
            for key in changed
        ],
        "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
    }


def _flatten(document: dict) -> dict[str, object]:
    flat: dict[str, object] = {}
    for category, bucket in document.get("tokens", {}).items():
        for name, value in bucket.items():
            flat[f"{category}.{name}"] = value
    for theme_name, overrides in document.get("themes", {}).items():
        for category, bucket in overrides.items():
            for name, value in bucket.items():
                flat[f"theme.{theme_name}.{category}.{name}"] = value
    return flat


def sample_html(document: dict, *, title: str = "Design tokens") -> str:
    """A self-contained sample rendered from the same resolved values."""
    resolved, _ = resolve_references(document)
    colors = resolved.get("color", {})
    spacing = resolved.get("space", {})
    radius = resolved.get("radius", {})
    typography = resolved.get("typography", {})
    shadow = resolved.get("shadow", {})
    swatches = "\n".join(
        f'<li><span class="swatch" style="background:{_css(value)}"></span>'
        f"<code>color.{name}</code><small>{_css(value)}</small></li>"
        for name, value in sorted(colors.items())
    )
    spacing_rows = "\n".join(
        f'<li><span class="bar" style="width:{_css(value)};height:0.5rem;'
        f'background:currentColor"></span><code>space.{name}</code></li>'
        for name, value in sorted(spacing.items())
    )
    radius_rows = "\n".join(
        f'<li><span class="box" style="border-radius:{_css(value)}"></span>'
        f"<code>radius.{name}</code></li>"
        for name, value in sorted(radius.items())
    )
    shadow_rows = "\n".join(
        f'<li><span class="box" style="box-shadow:{_css(value)}"></span>'
        f"<code>shadow.{name}</code></li>"
        for name, value in sorted(shadow.items())
    )
    type_rows = "\n".join(
        f'<p style="font-family:{_css(value.get("fontFamily", "inherit"))};'
        f'font-size:{_css(value.get("fontSize", "1rem"))};'
        f'font-weight:{_css(value.get("fontWeight", "400"))}">'
        f"<code>typography.{name}</code> — 示例文本 Sample</p>"
        for name, value in sorted(typography.items())
        if isinstance(value, dict)
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>
 body {{ font: 16px/1.5 system-ui, sans-serif; margin: 1.5rem; color: #16181d; }}
 h1 {{ font-size: 1.25rem; }} h2 {{ font-size: 1rem; margin-top: 1.5rem; }}
 ul {{ list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 0.6rem; }}
 li {{ display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }}
 .swatch {{ width: 2rem; height: 2rem; border: 1px solid #d3d7de; border-radius: 4px; }}
 .box {{ width: 3rem; height: 2rem; border: 1px solid #d3d7de; display: inline-block; }}
 code {{ background: #f2f4f7; padding: 0 0.25rem; border-radius: 3px; }}
</style></head><body>
<h1>{title}</h1>
<h2>颜色</h2><ul>{swatches}</ul>
<h2>间距</h2><ul>{spacing_rows}</ul>
<h2>圆角</h2><ul>{radius_rows}</ul>
<h2>阴影</h2><ul>{shadow_rows}</ul>
<h2>排版</h2>{type_rows}
</body></html>
"""


def _css(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value}px"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{key}: {_css(item)};" for key, item in sorted(value.items()))
    return "inherit"


class DesignSystemService:
    """Typed design-system revisions, previews, and baseline proposals."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        assets: AssetService,
        proposals: ProposalService,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.assets = assets
        self.proposals = proposals
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- reads ----------------------------------------------------------

    def _tokens_asset(self, project_id: str, asset_id: str) -> dict:
        asset = self.store.asset(asset_id)
        if asset is None or asset["project_id"] != project_id:
            raise WorkbenchError(INVALID_TARGET)
        if asset["kind"] != "tokens":
            raise WorkbenchError(UNSUPPORTED, detail="asset is not a token set")
        return asset

    def _document_bytes(self, asset_id: str, revision: dict | None = None) -> tuple[bytes, dict]:
        """The stored token document plus where it currently comes from."""
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

    def _document_for(self, asset_id: str, revision: dict | None = None) -> dict:
        data, _ = self._document_bytes(asset_id, revision)
        return parse_document(data)

    def document(self, project_id: str, asset_id: str) -> dict:
        """The exact stored text an editor must start from.

        The editor shows the stored document instead of rebuilding one from
        the resolved view, so what the maintainer edits is what was
        published or drafted -- not a lossy round trip.
        """
        self.service.require_project(project_id, scope="read")
        self._tokens_asset(project_id, asset_id)
        data, source = self._document_bytes(asset_id)
        text = data.decode("utf-8")
        return {
            "assetId": asset_id,
            "text": text,
            "themes": sorted(parse_document(text)["themes"]),
            "source": source,
        }

    def validate(self, project_id: str, asset_id: str) -> dict:
        self.service.require_project(project_id, scope="read")
        self._tokens_asset(project_id, asset_id)
        return validate_document(self._document_for(asset_id))

    def preview(self, project_id: str, asset_id: str, *, theme: object = None) -> dict:
        """A sample rendered onto the isolated preview origin."""
        self.service.require_project(project_id, scope="read")
        self._tokens_asset(project_id, asset_id)
        document = self._document_for(asset_id)
        if theme not in (None, ""):
            if not isinstance(theme, str) or theme not in document["themes"]:
                raise WorkbenchError(INVALID_TARGET)
            document = _apply_theme(document, theme)
        html = sample_html(document, title="设计系统样例").encode("utf-8")
        record = self.blobs.put(html)
        return {
            "assetId": asset_id,
            "theme": theme or None,
            "themes": sorted(document["themes"]),
            "contentHash": record.content_hash,
            "previewPath": f"/p/{record.content_hash}/static?type=text/html",
            "bytes": record.size,
            "note": (
                "样例由同一份 token 解析结果渲染，仅用于人工核对；"
                "它不修改任何项目文件，也不改变已发布修订。"
            ),
        }

    def diff(
        self, project_id: str, asset_id: str, *, from_revision: object = None, to_revision: object = None
    ) -> dict:
        self.service.require_project(project_id, scope="read")
        self._tokens_asset(project_id, asset_id)
        revisions = self.store.asset_revisions(asset_id)
        if not revisions:
            raise WorkbenchError(MISSING_DEPENDENCY)
        before = self._pick(revisions, from_revision, 0)
        after = self._pick(revisions, to_revision, len(revisions) - 1)
        return {
            "assetId": asset_id,
            "from": {"revisionId": before["revision_id"], "revisionNumber": before["revision_number"]},
            "to": {"revisionId": after["revision_id"], "revisionNumber": after["revision_number"]},
            **diff_documents(
                self._document_for(asset_id, before), self._document_for(asset_id, after)
            ),
        }

    def _pick(self, revisions: list[dict], requested: object, default_index: int) -> dict:
        if requested in (None, ""):
            return revisions[default_index]
        if not isinstance(requested, str):
            raise WorkbenchError(INVALID_INPUT)
        for row in revisions:
            if row["revision_id"] == requested:
                return row
        raise WorkbenchError(INVALID_TARGET)

    def affected(self, project_id: str, asset_id: str) -> dict:
        """Which published revisions and instances depend on this token set."""
        self.service.require_project(project_id, scope="read")
        self._tokens_asset(project_id, asset_id)
        dependents: list[dict] = []
        for revision in self.store.asset_revisions(asset_id):
            for instance in self.store.revision_instances(revision["revision_id"]):
                dependents.append(
                    {"instanceId": instance["instance_id"], "assetId": instance["asset_id"]}
                )
        components: list[dict] = []
        for other in self.store.project_assets(project_id):
            if other["asset_id"] == asset_id:
                continue
            for revision in self.store.asset_revisions(other["asset_id"]):
                for dependency in self.store.dependencies(revision["revision_id"]):
                    if dependency["depends_on_asset_id"] == asset_id:
                        components.append(
                            {
                                "assetId": other["asset_id"],
                                "name": other["name"],
                                "kind": other["kind"],
                                "revisionId": revision["revision_id"],
                                "revisionNumber": revision["revision_number"],
                            }
                        )
        return {
            "assetId": asset_id,
            "instances": dependents,
            "components": components,
            "note": "发布新版本不会自动升级这些引用；升级需按 WB-04 显式选择。",
        }

    # -- edits ----------------------------------------------------------

    def update_tokens(
        self, project_id: str, asset_id: str, *, document: object, operation: Operation
    ) -> dict:
        """Replace the draft token document after validation."""
        replayed = self.service._replay(operation, kind="design-system-update", entity_id=asset_id, project_id=project_id)
        if replayed is not None:
            return replayed
        self.service.require_project(project_id, scope="write")
        self._tokens_asset(project_id, asset_id)
        parsed = parse_document(document)
        verdict = validate_document(parsed)
        if not verdict["valid"]:
            raise WorkbenchError(INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False))
        data = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        record = self.blobs.put(data)
        draft = self.store.draft(asset_id)
        attributes = json.loads(draft["attributes_json"])
        manifest = [
            {
                "path": attributes.get("manifest", [{}])[0].get("path", "tokens.json"),
                "contentHash": record.content_hash,
                "size": record.size,
                "mediaType": "application/json",
                "carrier": "tokens",
                "encoding": "utf-8",
            }
        ]
        attributes["manifest"] = manifest
        attributes["capabilities"] = ["reference"]
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
            payload["validation"] = verdict
            return payload, counter

        with self.store.transaction():
            result, counter = apply()
            self.assets._record(
                operation=operation,
                kind="design-system-update",
                entity_id=asset_id,
                project_id=project_id,
                result=result,
            )
        return {"result": result, "replayed": False, "counter": counter}

    def publish(self, project_id: str, asset_id: str, *, operation: Operation) -> dict:
        """Publish only after the same validator accepts the document."""
        self.service.require_project(project_id, scope="write")
        self._tokens_asset(project_id, asset_id)
        verdict = validate_document(self._document_for(asset_id))
        if not verdict["valid"]:
            raise WorkbenchError(
                INVALID_INPUT, detail=json.dumps(verdict["errors"], ensure_ascii=False)
            )
        outcome = self.assets.publish_revision(
            project_id, asset_id, operation=operation
        )
        outcome["result"]["validation"] = verdict
        return outcome

    # -- baseline proposal ---------------------------------------------

    def propose_baseline(
        self,
        project_id: str,
        asset_id: str,
        *,
        path: object = None,
        operation: Operation,
    ) -> dict:
        """Hand the published token set to the project's own baseline owner.

        The workbench does not become a second authority for the project
        baseline: this only creates an ordinary R06 change proposal against
        the baseline file, which the maintainer must review and authorize,
        and whose owner remains whatever already owns that file.
        """
        self.service.require_project(project_id, scope="write")
        self._tokens_asset(project_id, asset_id)
        revision = self.store.latest_revision(asset_id)
        if revision is None:
            raise WorkbenchError(MISSING_DEPENDENCY)
        manifest = json.loads(revision["manifest_json"])
        locators = json.loads(revision["source_locators_json"])
        target_path = path
        if target_path in (None, ""):
            target_path = manifest[0]["path"] if manifest else None
            if locators and locators[0].get("path"):
                target_path = locators[0]["path"]
        if not isinstance(target_path, str) or not target_path:
            raise WorkbenchError(MISSING_DEPENDENCY)
        content = self.blobs.read(manifest[0]["contentHash"]).decode("utf-8")
        root = self.service.require_project(project_id, scope="read")["canonicalPath"]
        from pathlib import Path

        candidate = Path(root) / target_path
        base_hash = None
        operation_kind = "create"
        if candidate.is_file():
            operation_kind = "update"
            base_hash = digest_bytes(candidate.read_bytes())
        else:
            raise WorkbenchError(MISSING_DEPENDENCY)
        proposal = self.proposals.create(
            project_id,
            changes=[
                {
                    "path": target_path,
                    "operation": operation_kind,
                    "baseHash": base_hash,
                    "content": content,
                }
            ],
            summary=(
                f"设计系统基线替换：{self.store.asset(asset_id)['name']} "
                f"revision {revision['revision_number']}"
            ),
            operation=operation,
        )
        result = proposal["result"]
        result["baselineOwner"] = (
            f"{target_path} 仍由项目既有 baseline owner 准入；本提案只是普通 R06 变更提案，"
            "需维护者授权后才写入。"
        )
        result["sourceLocator"] = {
            "kind": "asset-revision",
            "projectId": project_id,
            "assetId": asset_id,
            "revisionId": revision["revision_id"],
            "sourceHash": revision["content_hash"],
            "run": None,
            "objectType": "revision",
            "objectId": revision["revision_id"],
        }
        return proposal


def _apply_theme(document: dict, theme_name: str) -> dict:
    overrides = document["themes"].get(theme_name, {})
    merged = {"tokens": {}, "themes": document["themes"]}
    for category, bucket in document["tokens"].items():
        merged["tokens"][category] = dict(bucket)
    for category, bucket in overrides.items():
        merged["tokens"].setdefault(category, {})
        merged["tokens"][category].update(bucket)
    return merged


def new_token_document() -> str:  # pragma: no cover - helper for the UI
    return json.dumps(
        {
            "color": {"brand": "#1f4fd8", "ink": "#16181d"},
            "space": {"gap": "8px"},
            "radius": {"control": "8px"},
        },
        ensure_ascii=False,
        indent=2,
    )
