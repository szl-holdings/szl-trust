#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real-run tests for the deterministic evidence trajectory compiler."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compile_evidence_trajectory import (  # noqa: E402
    SCHEMA,
    compile_trajectory,
    write_trajectory,
)
from verify_chain import ChainError  # noqa: E402

REAL_RUN = REPO_ROOT / "runs" / "E4-codex-kernel-2026-04-29"


class EvidenceTrajectoryTest(unittest.TestCase):
    def test_real_run_compiles_exact_evidence_topology(self) -> None:
        graph = compile_trajectory(REAL_RUN)

        self.assertEqual(graph["schema"], SCHEMA)
        self.assertEqual(graph["verification"]["steps"], 12)
        self.assertEqual(
            graph["verification"]["final_state_hash"],
            "fe20ecc47445dbd887b5b14ef26ed981",
        )
        self.assertEqual(graph["verification"]["mocked_values"], [False])
        self.assertEqual(
            graph["identity"]["trace_id"], "trace_86725c2a26210b61"
        )
        self.assertEqual(
            graph["identity"]["source_commit"],
            "7eb623f8b870128e615ac6be9880e0265204b454",
        )
        self.assertEqual(graph["metrics"]["edge_counts"]["CITES"], 24)
        self.assertEqual(graph["metrics"]["edge_counts"]["VERIFIES"], 48)
        completeness = graph["metrics"]["structural_completeness"]
        self.assertEqual(completeness["state"], "MEASURED")
        self.assertEqual(completeness["value"], 1.0)
        self.assertEqual(graph["interfaces"]["rest"], "UNAVAILABLE")
        self.assertEqual(graph["interfaces"]["mcp"], "UNAVAILABLE")
        self.assertEqual(graph["authority"]["mutation_authority"], "NONE")

    def test_graph_and_all_projections_are_deterministic_and_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="szl-trajectory-a-") as first_dir:
            with tempfile.TemporaryDirectory(prefix="szl-trajectory-b-") as second_dir:
                first = write_trajectory(REAL_RUN, first_dir)
                second = write_trajectory(REAL_RUN, second_dir)

                for key in first:
                    self.assertEqual(first[key].read_bytes(), second[key].read_bytes())

                graph = json.loads(first["graph"].read_text(encoding="utf-8"))
                receipt = json.loads(first["receipt"].read_text(encoding="utf-8"))
                self.assertEqual(receipt["graph_sha256"], graph["graph_sha256"])
                self.assertEqual(receipt["authority"], "NONE")

                artifacts = receipt["artifacts"]
                self.assertEqual(
                    artifacts["evidence-trajectory.json"],
                    hashlib.sha256(first["graph"].read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    artifacts["evidence-trajectory.md"],
                    hashlib.sha256(first["markdown"].read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    artifacts["agents.md"],
                    hashlib.sha256(first["agents"].read_bytes()).hexdigest(),
                )
                markdown = first["markdown"].read_text(encoding="utf-8")
                agents = first["agents"].read_text(encoding="utf-8")
                self.assertIn(graph["graph_sha256"], markdown)
                self.assertIn(graph["graph_sha256"], agents)
                self.assertIn("No mutation", agents)

    def test_tampered_run_is_rejected_before_graph_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="szl-trajectory-tamper-") as root:
            copied = Path(root) / REAL_RUN.name
            shutil.copytree(REAL_RUN, copied)
            ledger_path = copied / "proof_ledger.jsonl"
            records = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
            ]
            records[0]["state_hash"] = "f" * 32
            ledger_path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ChainError):
                compile_trajectory(copied)

    def test_node_and_edge_identifiers_are_unique(self) -> None:
        graph = compile_trajectory(REAL_RUN)
        node_ids = [node["id"] for node in graph["nodes"]]
        edge_ids = [edge["id"] for edge in graph["edges"]]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        self.assertEqual(len(edge_ids), len(set(edge_ids)))


if __name__ == "__main__":
    unittest.main()
