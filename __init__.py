from __future__ import annotations

import shlex
from pathlib import Path

from .models import ModelRegistry
from .snapshots import SnapshotManager
from .store import ObjectStore


HELP = """Commands: help, status, objects, hash <path>, import <path>,
SaveCLI <name>, snapshots, LoadCLI <name>, model status, model verify, chat <message>"""


class MindSERV:
    def __init__(self, root: Path, store: ObjectStore, snapshots: SnapshotManager, models: ModelRegistry, manifest_path: Path):
        self.root = root
        self.store = store
        self.snapshots = snapshots
        self.models = models
        self.manifest_path = manifest_path
        self.cwd = "/"
        self.history: list[str] = []

    def state(self) -> dict:
        return {"cwd": self.cwd, "history": self.history[-100:], "mounted_model": self.models.mounted}

    def execute(self, text: str) -> dict:
        text = text.strip()
        if not text:
            return {"type": "text", "output": ""}
        self.history.append(text)
        try:
            args = shlex.split(text)
        except ValueError as exc:
            return {"type": "error", "output": str(exc)}
        command = args[0].lower()
        try:
            if command == "help":
                output = HELP
            elif command == "status":
                output = "TRON Alpha online. Local-only daemon; VFS, objects, snapshots, and Mind shell active."
            elif command in {"objects", "ls"}:
                items = self.store.list_objects()
                output = "\n".join(f"{x['object_type']:9} {x['id']} {x['name']}" for x in items) or "No objects."
            elif command in {"hash", "import"} and len(args) > 1:
                item = self.store.import_path(Path(args[1]))
                output = f"Imported {item['name']} as {item['id']}"
            elif command == "savecli" and len(args) > 1:
                snap = self.snapshots.save(args[1], self.state())
                output = f"Snapshot {snap['snapshot']} created on {snap['created']}."
            elif command == "snapshots":
                output = "\n".join(f"{x['snapshot']} — {x['created']}" for x in self.snapshots.list()) or "No snapshots."
            elif command == "loadcli" and len(args) > 1:
                snap = self.snapshots.load(args[1])
                self.cwd = snap["state"].get("cwd", "/")
                output = f"Loaded snapshot {snap['snapshot']} (metadata/session state only)."
            elif command == "model" and len(args) > 1:
                manifest = self.models.load_manifest(self.manifest_path)
                if args[1].lower() == "status":
                    output = str(self.models.health(manifest))
                elif args[1].lower() == "verify":
                    output = str(self.models.verify(manifest, self.manifest_path))
                else:
                    output = "Usage: model status|verify"
            elif command == "chat" and len(args) > 1:
                output = self._chat(" ".join(args[1:]))
            else:
                output = self._natural_language(text)
            return {"type": "text", "output": output}
        except Exception as exc:
            return {"type": "error", "output": str(exc)}

    def _chat(self, message: str) -> str:
        manifest = self.models.load_manifest(self.manifest_path)
        return self.models.chat(manifest, [
            {"role": "system", "content": "You are TRON Mind. Never claim to execute commands. Offer safe, concise assistance."},
            {"role": "user", "content": message},
        ])

    def _natural_language(self, text: str) -> str:
        lowered = text.lower()
        if "save" in lowered and ("snapshot" in lowered or "state" in lowered):
            return "Use `SaveCLI <name>` to create a named session snapshot."
        if "list" in lowered and ("file" in lowered or "object" in lowered):
            return self.execute("objects")["output"]
        if "model" in lowered and ("online" in lowered or "status" in lowered):
            return self.execute("model status")["output"]
        try:
            return self._chat(text)
        except RuntimeError:
            return "I recognized natural language, but the local model is offline. Try `help` or start llama.cpp."
