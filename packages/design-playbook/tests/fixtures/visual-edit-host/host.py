"""Offline host app: serves real source and the plugin bridge; never writes source."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE_ROOT))

from design_playbook.mcp.preview.pin_bridge import build_visual_edit_bridge_script  # noqa: E402


DEFAULT_ASSETS = ("index.html", "styles.css")
ASSET_MANIFEST = "assets.json"


def source_path(root: Path, name: str) -> Path:
    target = root / name
    if target.resolve() != target or not target.is_relative_to(root) or not target.is_file():
        raise ValueError("host asset must be an existing file inside the host root without links")
    return target


def source_files(root: Path) -> dict[str, bytes]:
    """Only HOST-declared local assets, plus the declaration bytes themselves."""
    root = root.resolve()
    manifest = root / ASSET_MANIFEST
    files = {}
    names = DEFAULT_ASSETS
    if manifest.exists() or manifest.is_symlink():
        files[ASSET_MANIFEST] = source_path(root, ASSET_MANIFEST).read_bytes()
        record = json.loads(files[ASSET_MANIFEST])
        if not isinstance(record, dict) or set(record) != {"assets"}:
            raise ValueError("host asset manifest must contain only an assets list")
        names = record["assets"]
        if not isinstance(names, list) or not names or any(
            not isinstance(name, str) or not name or "\\" in name or ":" in name
            or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))
            for name in names
        ):
            raise ValueError("host asset manifest requires canonical local relative paths")
        paths = {Path(name) for name in names}
        if (len(paths) != len(names) or Path(ASSET_MANIFEST) in paths
                or not set(DEFAULT_ASSETS).issubset(names)):
            raise ValueError("host asset manifest requires unique assets including index.html and styles.css")
    for name in sorted(names):
        files[name] = source_path(root, name).read_bytes()
    return files


def source_hash(root: Path) -> str:
    """Bind every declared dependency and the exact manifest, without discovery."""
    digest = hashlib.sha256()
    for name, data in source_files(root).items():
        digest.update(name.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


class HostHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            # Artifact-only callers still bind response bytes. Keep the marker
            # for that legacy path; declared-map callers hash local files directly.
            marker = f'<meta name="host-source-hash" content="{source_hash(self.root)}">'
            html = (self.root / "index.html").read_text(encoding="utf-8")
            body = html.replace("<!-- visual-edit-bridge -->",
                                marker + build_visual_edit_bridge_script()).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        elif self.path == "/styles.css":
            body = (self.root / "styles.css").read_bytes()
            content_type = "text/css; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except ConnectionError as exc:
            # Preview may replace its iframe while a response is in flight.
            self.log_error("client disconnected during response: %s", exc)


def create_server(root: Path, port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), partial(HostHandler, root=root.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    with create_server(args.root, args.port) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass  # Interactive host shutdown, not a swallowed request failure.


if __name__ == "__main__":
    main()
