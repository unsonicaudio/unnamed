import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tron.models import ManifestError, ModelRegistry
from tron.snapshots import SnapshotManager
from tron.store import ObjectStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ObjectStore(self.root / "data")

    def tearDown(self):
        self.temp.cleanup()

    def test_import_file_is_content_addressed(self):
        path = self.root / "hello.txt"
        path.write_text("hello", encoding="utf-8")
        item = self.store.import_file(path)
        expected = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(item["payload_hash"], expected)
        self.assertTrue((self.store.objects / expected).exists())

    def test_directory_hash_is_deterministic(self):
        folder = self.root / "folder"
        folder.mkdir()
        (folder / "a.txt").write_text("A", encoding="utf-8")
        self.assertEqual(self.store.import_directory(folder)["root_hash"], self.store.import_directory(folder)["root_hash"])

    def test_snapshot_rejects_path_traversal(self):
        snapshots = SnapshotManager(self.root / "data", self.store)
        with self.assertRaises(ValueError):
            snapshots.save("../escape", {})


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = ModelRegistry(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data):
        path = self.root / "model.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def valid(self):
        return {
            "vobj_version": "0.1", "object_type": "language_model", "id": "model:test",
            "name": "Test", "runtime": {"endpoint": "http://127.0.0.1:8090/v1"},
            "weights": {"file": "missing.gguf", "sha256": "REPLACE_ME"},
            "permissions": {"network": False},
        }

    def test_rejects_missing_fields(self):
        with self.assertRaises(ManifestError):
            self.registry.load_manifest(self.write({"name": "bad"}))

    def test_rejects_remote_endpoint(self):
        data = self.valid()
        data["runtime"]["endpoint"] = "https://example.com/v1"
        with self.assertRaises(ManifestError):
            self.registry.load_manifest(self.write(data))

    def test_missing_weights_do_not_verify(self):
        path = self.write(self.valid())
        manifest = self.registry.load_manifest(path)
        self.assertFalse(self.registry.verify(manifest, path)["ok"])


if __name__ == "__main__":
    unittest.main()
