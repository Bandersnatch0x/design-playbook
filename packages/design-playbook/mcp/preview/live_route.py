"""Opt-in loopback route observation; no redirects, proxy, or source writes.

The host embeds build_visual_edit_bridge_script() from pin_bridge in its page.
An explicit adjacent assets.json binds local source bytes instead of dynamic HTML.
Without a declaration, response bytes retain the single-artifact binding.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from design_playbook.mcp.preview.integrity import prototype_html_digest
from design_playbook.mcp.preview.visual_batch import VisualBatchError

MAX_ROUTE_BYTES = 2 * 1024 * 1024
MAX_ROUTE_URL = 2000


def validate_live_route_url(value: str) -> str:
    """Accept explicit loopback HTTP(S) URLs, never file paths or credentials."""
    if not isinstance(value, str) or not value or len(value) > MAX_ROUTE_URL or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("live_route_url must be an explicit loopback URL")
    if "#" in value or "\\" in value:
        raise ValueError("live_route_url cannot contain a fragment or backslash")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or parsed.username is not None or parsed.password is not None:
        raise ValueError("live_route_url requires http(s) without credentials")
    if host != "localhost":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("live_route_url host must be loopback")
    port = parsed.port
    if port == 0:
        raise ValueError("live_route_url port must be positive")
    authority = "[" + host + "]" if ":" in host else host
    if port is not None and (parsed.scheme, port) not in (("http", 80), ("https", 443)):
        authority += ":" + str(port)
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", parsed.query, ""))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "live route redirects are not allowed", headers, fp)


def _declared_source_digest(
    prototype: Path, *, source_root: Path | None, asset_map: Path | None,
) -> str | None:
    """Read host-declared files; all paths come from the caller, never HTTP."""
    try:
        sidecar = prototype.resolve().parent / "visual-source.json"
        explicit = source_root is not None or asset_map is not None
        if not explicit and (sidecar.exists() or sidecar.is_symlink()):
            if sidecar.resolve() != sidecar:
                raise ValueError("source declaration cannot be a link")
            context = json.loads(sidecar.read_bytes())
            if (not isinstance(context, dict) or set(context) != {"sourceRoot", "assetMap"}
                    or not all(isinstance(value, str) and value for value in context.values())):
                raise ValueError("source declaration requires sourceRoot and assetMap")
            source_root, asset_map = Path(context["sourceRoot"]), Path(context["assetMap"])
            explicit = True
        if explicit and (source_root is None or asset_map is None):
            raise ValueError("source root and asset map must be declared together")
        root = source_root if explicit else prototype.resolve().parent
        if not root.is_absolute() or not root.is_dir() or root.resolve() != root:
            raise ValueError("source root must be an absolute unlinked directory")
        manifest = root / asset_map if explicit else root / "assets.json"
        if not explicit and not manifest.exists() and not manifest.is_symlink():
            return None
        if manifest.resolve() != manifest or not manifest.is_relative_to(root):
            raise ValueError("asset map must be an unlinked file inside the source root")
        declaration = manifest.read_bytes()
        record = json.loads(declaration)
        names = record.get("assets") if isinstance(record, dict) else None
        if not isinstance(names, list) or not names or any(
            not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(part in ("", ".", "..") for part in name.split("/"))
            for name in names
        ):
            raise ValueError("asset map requires canonical local relative paths")
        if (len({Path(name) for name in names}) != len(names)
                or manifest.relative_to(root) in {Path(name) for name in names}):
            raise ValueError("asset map requires unique source files, not itself")
        digest = hashlib.sha256(declaration)
        for name in sorted(names):
            target = root / name
            if target.resolve() != target or not target.is_relative_to(root) or not target.is_file():
                raise ValueError("asset must be an existing unlinked file inside the source root")
            content = target.read_bytes()
            digest.update(b"\0" + name.encode("utf-8") + b"\0" + str(len(content)).encode() + b"\0" + content)
        return digest.hexdigest()
    except (OSError, ValueError) as exc:
        raise VisualBatchError(f"declared source observation failed: {exc}") from exc


def observe_visual_source(
    prototype: Path, route_url: str = "", *,
    source_root: Path | None = None, asset_map: Path | None = None,
) -> str:
    """Bind declared source bytes + exact URL; still require a healthy HTML route."""
    artifact_hash = prototype_html_digest(prototype.read_bytes())
    if not route_url:
        return artifact_hash
    route_url = validate_live_route_url(route_url)
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(route_url, timeout=3) as response:
            if response.headers.get_content_type() != "text/html":
                raise VisualBatchError("live route must return text/html")
            body = response.read(MAX_ROUTE_BYTES + 1)
    except (OSError, URLError) as exc:
        raise VisualBatchError(f"live route observation failed: {exc}") from exc
    if len(body) > MAX_ROUTE_BYTES:
        raise VisualBatchError("live route exceeds the 2 MiB review limit")
    source_digest = _declared_source_digest(prototype, source_root=source_root, asset_map=asset_map)
    binding = b"declared-source\0" + source_digest.encode() if source_digest is not None else body
    return hashlib.sha256((artifact_hash + "\n" + route_url + "\n").encode() + binding).hexdigest()
