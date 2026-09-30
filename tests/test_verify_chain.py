#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SZL Holdings — adversarial tests for the offline chain-integrity verifier.
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11 LOCKED (749/14/163)
#
# These tests use ONLY the real published E4 Codex Kernel run as ground truth —
# there are no synthetic fixtures and nothing is spoofed into passing. Each
# adversarial case makes a minimal edit to a COPY of the real artifacts and
# asserts the verifier fails CLOSED (rejects the tampered / malformed run).
#
# Run: python3 -m unittest discover -s tests  (pure stdlib, no external deps)
#
# Signed-off-by: stephenlutar2-hash <270976497+stephenlutar2-hash@users.noreply.github.com>

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_chain  # noqa: E402
from verify_chain import ChainError, verify_run  # noqa: E402

REAL_RUN = REPO_ROOT / "runs" / "E4-codex-kernel-2026-04-29"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


class ChainVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="szl-trust-chain-"))
        self.run = self.tmp / REAL_RUN.name
        shutil.copytree(REAL_RUN, self.run)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- ground truth ----------------------------------------------------
    def test_real_run_passes(self) -> None:
        """The genuine, unmodified E4 run must verify clean."""
        summary = verify_run(self.run)
        self.assertEqual(summary["steps"], 12)
        self.assertEqual(summary["posture_mocked_values"], [False])
        self.assertEqual(summary["final_state_hash"], "fe20ecc47445dbd887b5b14ef26ed981")

    # ---- fail-closed on malformed records --------------------------------
    def test_truncated_json_line_rejected(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        p.write_text(p.read_text(encoding="utf-8") + '{"step":13,"state_hash":"deadbeef"\n',
                     encoding="utf-8")
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("malformed JSON", str(cm.exception))

    def test_blank_line_in_body_rejected(self) -> None:
        p = self.run / "trace.jsonl"
        lines = p.read_text(encoding="utf-8").splitlines()
        lines.insert(3, "")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_empty_file_rejected(self) -> None:
        (self.run / "proof_ledger.jsonl").write_text("", encoding="utf-8")
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_missing_file_rejected(self) -> None:
        (self.run / "trace.jsonl").unlink()
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_top_level_array_rejected(self) -> None:
        (self.run / "proof_ledger.jsonl").write_text("[1,2,3]\n", encoding="utf-8")
        with self.assertRaises(ChainError):
            verify_run(self.run)

    # ---- fail-closed on tampered chain -----------------------------------
    def test_broken_chain_continuity_rejected(self) -> None:
        p = self.run / "trace.jsonl"
        recs = _read_jsonl(p)
        recs[5]["state_prev_hash"] = "0" * 32  # forged link
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("continuity", str(cm.exception))

    def test_state_binding_mismatch_rejected(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        recs = _read_jsonl(p)
        recs[4]["state_hash"] = "f" * 32  # ledger no longer binds to trace
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("state binding", str(cm.exception))

    def test_intermediate_null_hash_pair_rejected(self) -> None:
        """Equal null hashes must not disable the following span's continuity check."""
        ledger_path = self.run / "proof_ledger.jsonl"
        trace_path = self.run / "trace.jsonl"
        ledger = _read_jsonl(ledger_path)
        trace = _read_jsonl(trace_path)
        ledger[4]["state_hash"] = None
        trace[4]["state_next_hash"] = None
        _write_jsonl(ledger_path, ledger)
        _write_jsonl(trace_path, trace)
        with self.assertRaisesRegex(ChainError, "proof_ledger step 5: 'state_hash'"):
            verify_run(self.run)

    def test_state_hash_type_and_format_rejected(self) -> None:
        invalid_hashes = (
            None, 0, 123, False, True, [], {}, "", " ", "g" * 32,
            "a" * 31, "a" * 33, "a" * 64, "A" * 32, "a" * 32 + "\n",
        )
        fields = (
            ("proof_ledger.jsonl", "state_hash"),
            ("trace.jsonl", "state_prev_hash"),
            ("trace.jsonl", "state_next_hash"),
        )
        for filename, field in fields:
            path = self.run / filename
            original = path.read_text(encoding="utf-8")
            for index in (0, 4):
                for value in invalid_hashes:
                    with self.subTest(filename=filename, field=field, index=index, value=value):
                        records = [json.loads(line) for line in original.splitlines()]
                        records[index][field] = value
                        _write_jsonl(path, records)
                        try:
                            with self.assertRaisesRegex(
                                ChainError, f"'{field}' must be a 32-character lowercase hexadecimal string"
                            ):
                                verify_run(self.run)
                        finally:
                            path.write_text(original, encoding="utf-8")

    def test_manifest_state_hash_type_and_format_rejected(self) -> None:
        path = self.run / "run_manifest.json"
        original = path.read_text(encoding="utf-8")
        for value in (None, 0, False, [], {}, "", "g" * 32, "a" * 31, "a" * 64):
            with self.subTest(value=value):
                manifest = json.loads(original)
                manifest["final_state_hash"] = value
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    ChainError,
                    "run_manifest.json: 'final_state_hash' must be a 32-character lowercase hexadecimal string",
                ):
                    verify_run(self.run)

    def test_first_previous_hash_is_not_an_external_anchor(self) -> None:
        path = self.run / "trace.jsonl"
        records = _read_jsonl(path)
        records[0]["state_prev_hash"] = "0" * 32
        _write_jsonl(path, records)
        summary = verify_run(self.run)
        self.assertEqual(summary["steps"], 12)
        self.assertIn("not a proof of authenticity", summary["advisory"])

    def test_manifest_non_object_rejected(self) -> None:
        path = self.run / "run_manifest.json"
        for value in (None, [], False, "", 0):
            with self.subTest(value=value):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ChainError, "run_manifest.json: expected a JSON object"):
                    verify_run(self.run)

    def test_dropped_step_rejected(self) -> None:
        p = self.run / "trace.jsonl"
        recs = _read_jsonl(p)
        del recs[6]  # leaves a gap in the step sequence
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_reordered_steps_rejected(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        recs = _read_jsonl(p)
        recs[2], recs[3] = recs[3], recs[2]
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_step_count_mismatch_rejected(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        recs = _read_jsonl(p)
        recs.pop()  # 11 ledger steps vs 12 trace spans
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("step-count mismatch", str(cm.exception))

    def test_receipt_id_mismatch_rejected(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        recs = _read_jsonl(p)
        recs[0]["receipt_id"] = "rcpt-forged-0001"
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("receipt_id mismatch", str(cm.exception))

    # ---- fail-closed on posture / manifest tampering ---------------------
    def test_non_boolean_posture_rejected(self) -> None:
        p = self.run / "trace.jsonl"
        recs = _read_jsonl(p)
        recs[0]["decision_receipt"]["mocked"] = "false"  # string, not boolean
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("mocked", str(cm.exception))

    def test_missing_posture_field_rejected(self) -> None:
        p = self.run / "trace.jsonl"
        recs = _read_jsonl(p)
        del recs[0]["decision_receipt"]["mocked"]
        _write_jsonl(p, recs)
        with self.assertRaises(ChainError):
            verify_run(self.run)

    def test_manifest_anchor_mismatch_rejected(self) -> None:
        p = self.run / "run_manifest.json"
        manifest = json.loads(p.read_text(encoding="utf-8"))
        manifest["final_state_hash"] = "0" * 32
        p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with self.assertRaises(ChainError) as cm:
            verify_run(self.run)
        self.assertIn("manifest anchor", str(cm.exception))

    def test_decision_receipt_cross_check_rejected(self) -> None:
        p = self.run / "decision_receipt.json"
        dr = json.loads(p.read_text(encoding="utf-8"))
        dr["last_receipt"]["receipt_id"] = "rcpt-forged-9999"
        p.write_text(json.dumps(dr, indent=2), encoding="utf-8")
        with self.assertRaises(ChainError):
            verify_run(self.run)

    # ---- CLI contract ----------------------------------------------------
    def test_cli_exit_zero_on_real_run(self) -> None:
        self.assertEqual(verify_chain.main(["verify_chain.py", str(self.run)]), 0)

    def test_cli_exit_one_on_tampered_run(self) -> None:
        p = self.run / "proof_ledger.jsonl"
        recs = _read_jsonl(p)
        recs[0]["state_hash"] = "f" * 32
        _write_jsonl(p, recs)
        self.assertEqual(verify_chain.main(["verify_chain.py", str(self.run)]), 1)

    def test_cli_exit_one_on_intermediate_null_hash_pair(self) -> None:
        ledger_path = self.run / "proof_ledger.jsonl"
        trace_path = self.run / "trace.jsonl"
        ledger = _read_jsonl(ledger_path)
        trace = _read_jsonl(trace_path)
        ledger[4]["state_hash"] = None
        trace[4]["state_next_hash"] = None
        _write_jsonl(ledger_path, ledger)
        _write_jsonl(trace_path, trace)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = verify_chain.main(["verify_chain.py", str(self.run)])
        self.assertEqual(result, 1)
        self.assertIn("proof_ledger step 5: 'state_hash'", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
