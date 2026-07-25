from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .mind import MindSERV
from .models import ModelRegistry
from .snapshots import SnapshotManager
from .store import ObjectStore


class TronRuntime:
    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        self.store = ObjectStore(config["data_dir"])
        self.models = ModelRegistry(root)
        self.snapshots = SnapshotManager(config["data_dir"], self.store)
        manifest_path = root / config["model_manifest"]
        self.mind = MindSERV(root, self.store, self.snapshots, self.models, manifest_path)

    def status(self) -> dict:
        return {
            "name": "TRON Alpha",
            "version": "0.1.0",
            "mode": "local-only",
            "objects": len(self.store.list_objects()),
            "snapshots": len(self.snapshots.list()),
        }


def handler_factory(runtime: TronRuntime):
    web_root = runtime.root / "web"

    class Handler(BaseHTTPRequestHandler):
        def _json(self, value: object, status: int = 200) -> None:
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/status":
                self._json(runtime.status())
                return
            if path == "/api/objects":
                self._json(runtime.store.list_objects())
                return
            if path == "/api/snapshots":
                self._json(runtime.snapshots.list())
                return
            requested = "index.html" if path == "/" else path.lstrip("/")
            target = (web_root / requested).resolve()
            if web_root.resolve() not in target.parents and target != web_root.resolve():
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1024 * 1024:
                    self._json({"error": "Request too large"}, 413)
                    return
                data = json.loads(self.rfile.read(length) or b"{}")
                if path == "/api/command":
                    self._json(runtime.mind.execute(str(data.get("command", ""))))
                elif path == "/api/snapshot":
                    self._json(runtime.snapshots.save(str(data.get("name", "")), runtime.mind.state()), 201)
                else:
                    self._json({"error": "Not found"}, 404)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)

        def log_message(self, format: str, *args: object) -> None:
            print(f"[trond] {self.address_string()} {format % args}")

    return Handler


def serve(runtime: TronRuntime, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), handler_factory(runtime))
    print(f"TRON Alpha online at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
