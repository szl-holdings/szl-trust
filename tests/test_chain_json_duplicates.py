"""Reject ambiguous JSON in copies of the published E4 run artifacts."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_chain


class DuplicateChainJsonTests(unittest.TestCase):
    def assert_duplicate_rejected(self, filename, old, new):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            shutil.copytree(ROOT / "runs/E4-codex-kernel-2026-04-29", run)
            path = run / filename
            if filename.endswith(".jsonl"):
                rows = path.read_text(encoding="utf-8").splitlines()
                text = json.dumps(json.loads(rows[0]), separators=(",", ":"))
                self.assertIn(old, text)
                rows[0] = text.replace(old, new, 1)
                path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            else:
                text = json.dumps(json.loads(path.read_text(encoding="utf-8")), separators=(",", ":"))
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
            with self.assertRaisesRegex(verify_chain.ChainError, "duplicate JSON member"):
                verify_chain.verify_run(run)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = verify_chain.main(["verify_chain.py", str(run)])
            self.assertEqual(result, 1)
            self.assertNotIn("OK ", stdout.getvalue())
            self.assertIn("duplicate JSON member", stderr.getvalue())

    def test_ledger_conflicting_step(self):
        self.assert_duplicate_rejected("proof_ledger.jsonl", '"step":1', '"step":999,"step":1')

    def test_ledger_identical_step(self):
        self.assert_duplicate_rejected("proof_ledger.jsonl", '"step":1', '"step":1,"step":1')

    def test_ledger_escaped_equivalent_name(self):
        self.assert_duplicate_rejected("proof_ledger.jsonl", '"step":1', '"st\\u0065p":999,"step":1')

    def test_trace_nested_posture(self):
        self.assert_duplicate_rejected("trace.jsonl", '"mocked":false', '"mocked":true,"mocked":false')

    def test_manifest_conflicting_anchor(self):
        self.assert_duplicate_rejected("run_manifest.json", '"final_state_hash":', '"final_state_hash":"' + '0' * 32 + '","final_state_hash":')

    def test_final_receipt_conflicting_object(self):
        self.assert_duplicate_rejected("decision_receipt.json", '"last_receipt":', '"last_receipt":null,"last_receipt":')

    def test_final_receipt_nested_posture(self):
        self.assert_duplicate_rejected("decision_receipt.json", '"mocked":false', '"mocked":true,"mocked":false')


if __name__ == "__main__":
    unittest.main()
