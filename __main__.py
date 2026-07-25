from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path


class ManifestError(ValueError):
    pass


REQUIRED = {"vobj_version", "object_type", "id", "name", "runtime", "weights", "permissions"}


class ModelRegistry:
    def __init__(self, root: Path):
        self.root = root
        self.mounted: str | None = None

    def load_manifest(self, path: Path) -> dict:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED - manifest.keys()
        if missing:
            raise ManifestError(f"Missing fields: {', '.join(sorted(missing))}")
        if manifest["object_type"] != "language_model":
            raise ManifestError("object_type must be language_model")
        endpoint = manifest["runtime"].get("endpoint", "")
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ManifestError("Alpha only permits loopback model endpoints")
        return manifest

    def verify(self, manifest: dict, manifest_path: Path) -> dict:
        filename = manifest["weights"].get("file")
        expected = manifest["weights"].get("sha256", "")
        if not filename:
            return {"ok": False, "reason": "No weights file configured"}
        path = (manifest_path.parent / filename).resolve()
        if not path.exists():
            return {"ok": False, "reason": "Weights not installed", "path": str(path)}
        if expected.startswith("REPLACE_") or len(expected) != 64:
            return {"ok": False, "reason": "Expected SHA-256 not configured", "path": str(path)}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"ok": digest == expected, "actual": digest, "expected": expected, "path": str(path)}

    def health(self, manifest: dict) -> dict:
        url = manifest["runtime"]["endpoint"].rstrip("/") + "/models"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return {"online": response.status == 200}
        except (urllib.error.URLError, TimeoutError):
            return {"online": False}

    def chat(self, manifest: dict, messages: list[dict]) -> str:
        endpoint = manifest["runtime"]["endpoint"].rstrip("/") + "/chat/completions"
        payload = json.dumps({
            "model": manifest["runtime"].get("model_name", manifest["id"]),
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": manifest.get("limits", {}).get("max_output_tokens", 512),
        }).encode()
        request = urllib.request.Request(
            endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=manifest.get("limits", {}).get("timeout_seconds", 90)) as response:
                data = json.loads(response.read())
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Local model unavailable: {exc}") from exc
