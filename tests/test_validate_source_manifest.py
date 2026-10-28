import json
import unittest
from pathlib import Path

from validate_source_manifest import validate_manifest


class SourceManifestTests(unittest.TestCase):
    def test_example_is_valid(self):
        manifest_path = Path(__file__).resolve().parent / "source_manifest.example.json"
        if not manifest_path.exists():
            manifest_path = Path(__file__).resolve().parents[1] / "docs" / "source-manifest.example.json"
        with manifest_path.open(encoding="utf-8") as handle:
            self.assertEqual(validate_manifest(json.load(handle)), [])

    def test_source_bound_requires_full_sha(self):
        record = {
            "schema": "szl.source-binding/v1",
            "records": [{
                "id": "bad", "kind": "repository", "name": "bad",
                "status": "OPERATIONAL", "observed_at": "now",
                "github": {"repo": "szl-holdings/bad", "commit": "short"}
            }]
        }
        errors = validate_manifest(record)
        self.assertTrue(any("full 40-char SHA" in error for error in errors))

    def test_proved_requires_kernel_receipt(self):
        record = {
            "schema": "szl.source-binding/v1",
            "records": [{
                "id": "proof", "kind": "theorem", "name": "F1",
                "status": "PROVED", "observed_at": "now",
                "github": {"repo": "szl-holdings/lutar-lean", "commit": "a" * 40}
            }]
        }
        errors = validate_manifest(record)
        self.assertTrue(any("proof is required" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
