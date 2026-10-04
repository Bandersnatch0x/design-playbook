"""Offline Vue 3 host: loopback HTTP and the unchanged DOM bridge, no writes."""
from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE_ROOT))

from design_playbook.mcp.preview.pin_bridge import build_visual_edit_bridge_script  # noqa: E402


class VueHostHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            html = (self.root / "index.html").read_text(encoding="utf-8")
            body = html.replace("<!-- visual-edit-bridge -->",
                                build_visual_edit_bridge_script()).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        elif self.path in ("/app.js", "/vendor/vue.global.prod.js"):
            body = (self.root / self.path[1:]).read_bytes()
            content_type = "text/javascript; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(root: Path, port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), partial(VueHostHandler, root=root.resolve()))


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
            pass  # Normal interactive shutdown; request errors remain visible.


if __name__ == "__main__":
    main()
