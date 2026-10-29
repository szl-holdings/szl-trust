import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_source_manifest import load_manifest, main, validate_manifest  # noqa: E402


class SourceManifestTests(unittest.TestCase):
    def run_cli(self, content):
        with tempfile.TemporaryDirectory(prefix="szl-source-manifest-") as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(content, encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main([str(path)])
        return code, stdout.getvalue(), stderr.getvalue()

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

    def test_duplicate_members_are_rejected_at_every_depth(self):
        for content in (
            '{"schema":"wrong","schema":"szl.source-binding/v1","records":[]}',
            '{"status":"SOURCE_UNBOUND","status":"OPERATIONAL"}',
            '{"github":{"commit":"short","commit":"' + "a" * 40 + '"}}',
            '{"proof":{"receipt":false,"receipt":true}}',
            '{"extension":[{"name":"old","name":"new"}]}',
        ):
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, "duplicate JSON member"):
                    load_manifest(content)
                code, stdout, stderr = self.run_cli(content)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("duplicate JSON member", stderr)

    def test_non_finite_json_is_rejected_before_schema_validation(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(value=value):
                content = ('{"schema":"szl.source-binding/v1","records":[],"extension":'
                           + value + '}')
                code, stdout, stderr = self.run_cli(content)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("finite", stderr)

    def test_finite_json_numbers_remain_supported(self):
        self.assertEqual(load_manifest('{"number":1.25e2}'), {"number": 125.0})

    def test_invalid_status_types_return_errors(self):
        for value in ([], {}, None, True, 1):
            with self.subTest(value=value):
                errors = validate_manifest({
                    "schema": "szl.source-binding/v1",
                    "records": [{"id": "invalid", "status": value}],
                })
                self.assertTrue(any(".status must be" in error for error in errors))

    def test_invalid_identity_types_return_errors(self):
        for value in ([], {}, None, True, 1):
            with self.subTest(value=value):
                errors = validate_manifest({
                    "schema": "szl.source-binding/v1",
                    "records": [{"id": "invalid", "status": "SOURCE_UNBOUND",
                                 "domain": {"url": "https://example.invalid", "identity": value}}],
                })
                self.assertTrue(any("domain.identity is invalid" in error for error in errors))

    def test_schema_success_does_not_claim_admission(self):
        example = Path(__file__).resolve().parents[1] / "docs" / "source-manifest.example.json"
        code, stdout, stderr = self.run_cli(example.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout.startswith("DECLARED:"))
        self.assertIn("authorization remain UNKNOWN", stdout)
        self.assertNotIn("ALLOW", stdout)


if __name__ == "__main__":
    unittest.main()
