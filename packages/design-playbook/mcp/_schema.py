"""Tiny JSON-Schema subset validator (T-145).

The bundled MCP adapters ship zero third-party runtime dependencies, so the
manifest contract cannot lean on ``jsonschema``. This evaluates the closed
subset the shipped schema files use — ``type`` / ``const`` / ``enum`` /
``required`` / ``properties`` / ``additionalProperties`` / ``items`` /
``minItems`` / ``minLength`` / ``pattern`` / ``minimum`` / ``$ref`` — and
returns readable violation strings instead of raising.

Supported schema files are ours: an unsupported keyword is a bug in the
schema, not a validation result, so it is ignored rather than guessed at.
"""
from __future__ import annotations

import re
from typing import Any, Iterator

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
}


def _is_type(value: object, expected: str) -> bool:
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in (int, float)
    return isinstance(value, _JSON_TYPES[expected])


def _same_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _resolve(reference: str, root: dict[str, Any]) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local $ref is supported: {reference}")
    node: Any = root
    for segment in reference[2:].split("/"):
        node = node[segment]
    return node


def _walk(
    value: object, schema: dict[str, Any], root: dict[str, Any], path: str
) -> Iterator[str]:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        yield from _walk(value, _resolve(reference, root), root, path)

    expected = schema.get("type")
    if isinstance(expected, str) and not _is_type(value, expected):
        yield f"{path}: expected {expected}"
        return
    if "const" in schema and not _same_json_value(value, schema["const"]):
        yield f"{path}: expected const {schema['const']!r}"
    if "enum" in schema and not any(
        _same_json_value(value, candidate) for candidate in schema["enum"]
    ):
        yield f"{path}: expected one of {schema['enum']!r}"

    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                yield f"{path}: missing required {key!r}"
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties")
        if additional is False:
            for key in value:
                if key not in properties:
                    yield f"{path}: unexpected property {key!r}"
        elif isinstance(additional, dict):
            for key, item in value.items():
                if key not in properties:
                    yield from _walk(item, additional, root, f"{path}.{key}")
        for key, child in properties.items():
            if key in value:
                yield from _walk(value[key], child, root, f"{path}.{key}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            yield f"{path}: expected at least {schema['minItems']} items"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                yield from _walk(item, item_schema, root, f"{path}[{index}]")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            yield f"{path}: shorter than {schema['minLength']} characters"
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            yield f"{path}: does not match {pattern!r}"

    if type(value) in (int, float):
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            yield f"{path}: below minimum {minimum}"


def violations(instance: object, schema: dict[str, Any]) -> list[str]:
    """Return every violation of ``schema`` by ``instance`` (empty = valid)."""
    return list(_walk(instance, schema, schema, "$"))
