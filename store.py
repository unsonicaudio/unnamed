from __future__ import annotations

import json
from pathlib import Path


DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8765,
    "data_dir": "data",
    "model_manifest": "models/qwen3-4b/model.vobj.json",
}


def load_config(root: Path) -> dict:
    path = root / "tron.config.json"
    config = dict(DEFAULTS)
    if path.exists():
        config.update(json.loads(path.read_text(encoding="utf-8")))
    config["root"] = root
    config["data_dir"] = (root / config["data_dir"]).resolve()
    return config
