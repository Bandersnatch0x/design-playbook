"""Offline host app: serves real source and the plugin bridge; never writes source."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from presence import PRESENCE_PATH, Presence

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
    def __init__(self, *args, root: Path, presence: Presence, **kwargs):
        self.root = root
        self.presence = presence
        super().__init__(*args, **kwargs)

    def log_request(self, code="-", size="-"):
        # Presence capability lives in the SSE URL; never put it in access logs.
        self.log_message("%s %s %s %s", self.command, urlsplit(self.path).path, code, size)

    def _presence_access(self, *, token=True):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(403, "presence requires the loopback host")
            return False
        origin = self.headers.get("Origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                parsed.port  # Reject malformed external port syntax at the boundary.
            except ValueError:
                self.send_error(403, "invalid presence origin")
                return False
            if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                    or parsed.path or parsed.query or parsed.fragment or parsed.username):
                self.send_error(403, "presence requires a loopback origin")
                return False
        query = parse_qs(urlsplit(self.path).query)
        if token and not secrets.compare_digest(query.get("token", [""])[0].encode(), self.presence.token.encode()):
            self.send_error(403, "presence capability required")
            return False
        return True

    def _presence_headers(self, status, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if self.headers.get("Origin"):
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):  # noqa: N802
        if urlsplit(self.path).path != PRESENCE_PATH:
            self.send_error(404)
            return
        if not self._presence_access(token=False):
            return
        self._presence_headers(204, "text/plain")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if urlsplit(self.path).path != PRESENCE_PATH:
            self.send_error(404)
            return
        if not self._presence_access():
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("presence requires bounded JSON")
            self.connection.settimeout(3)
            self.presence.edit(json.loads(self.rfile.read(size)))
        except (OSError, ValueError) as exc:
            self.send_error(400, str(exc))
            return
        self._presence_headers(204, "text/plain")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _presence_stream(self):
        if not self._presence_access():
            return
        query = parse_qs(urlsplit(self.path).query)
        identity = query.get("user", [""])[0]
        try:
            cursor = self.presence.join(identity, query.get("name", [""])[0])
        except ValueError as exc:
            self.send_error(409, str(exc))
            return
        try:
            self.connection.settimeout(3)
            self._presence_headers(200, "text/event-stream; charset=utf-8")
            self.end_headers()
            while True:
                events = self.presence.after(cursor)
                for cursor, data in events:
                    self.wfile.write(data)
                if not events:
                    self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
        except (OSError, ValueError) as exc:
            self.log_error("presence stream closed for %s: %s", identity, exc)
        finally:
            self.presence.leave(identity)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path == PRESENCE_PATH:
            self._presence_stream()
            return
        if self.path == "/":
            # Artifact-only callers still bind response bytes. Keep the marker
            # for that legacy path; declared-map callers hash local files directly.
            marker = f'<meta name="host-source-hash" content="{source_hash(self.root)}">'
            html = (self.root / "index.html").read_text(encoding="utf-8")
            # Advertise only from this opt-in HOST, in response to the existing
            # parent ping. The sandbox stays allow-scripts (opaque child origin).
            presence_bridge = """<script>window.addEventListener('message', function(event) {
              if (event.source !== window.parent || !event.data || !event.data.dpbVisualEdit ||
                  event.data.dpbVisualEdit.type !== 'ping') return;
              window.parent.postMessage({dpbHostPresence: {token: TOKEN}}, '*');
            });</script>""".replace("TOKEN", json.dumps(self.presence.token))
            body = html.replace("<!-- visual-edit-bridge -->",
                                marker + presence_bridge + build_visual_edit_bridge_script()).encode("utf-8")
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
    return ThreadingHTTPServer(("127.0.0.1", port),
                               partial(HostHandler, root=root.resolve(), presence=Presence()))


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
