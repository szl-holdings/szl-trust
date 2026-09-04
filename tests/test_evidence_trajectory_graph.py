from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from evidence_trajectory_graph import (  # noqa: E402
    RECEIPT_SCHEMA,
    SCHEMA,
    GraphError,
    build_graph,
    build_receipt,
    render_agents_md,
    render_markdown,
    write_outputs,
)

REAL_RUN = ROOT / "runs" / "E4-codex-kernel-2026-04-29"


def test_real_run_compiles_to_one_verified_evidence_trajectory_graph() -> None:
    graph = build_graph(REAL_RUN)

    assert graph["schema"] == SCHEMA
    assert graph["run"] == "E4-codex-kernel-2026-04-29"
    assert graph["summary"]["steps"] == 12
    assert graph["summary"]["citation_edges"] == 24
    assert graph["summary"]["validator_edges"] == 48
    assert graph["summary"]["mocked_values"] == [False]
    assert graph["summary"]["final_state_hash"] == "fe20ecc47445dbd887b5b14ef26ed981"
    assert graph["source_identity"]["repo_commit"] == "7eb623f8b870128e615ac6be9880e0265204b454"
    assert graph["trace_identity"]["trace_id"] == "trace_86725c2a26210b61"
    assert len(graph["graph_sha256"]) == 64


def test_structural_completeness_is_measured_but_never_promoted_to_correctness() -> None:
    graph = build_graph(REAL_RUN)
    completeness = graph["structural_completeness"]

    assert completeness["numerator"] == completeness["denominator"]
    assert completeness["score"] == 1.0
    assert completeness["evidence_label"] == "MEASURED"
    assert "does not prove correctness" in completeness["claim_boundary"]
    assert graph["authority_boundary"]["graph_grants_authority"] is False
    assert graph["authority_boundary"]["recorded_execution_is_not_future_authority"] is True


def test_graph_preserves_citation_validator_receipt_and_state_relationships() -> None:
    graph = build_graph(REAL_RUN)
    kinds = {node["kind"] for node in graph["nodes"]}
    edge_kinds = {edge["kind"] for edge in graph["edges"]}

    assert {
        "RUN_MANIFEST",
        "STATE",
        "ACTION",
        "EVIDENCE_SOURCE",
        "VALIDATOR",
        "RECEIPT",
    } <= kinds
    assert {"INPUT_STATE", "CITES", "VERIFIES", "PRODUCES", "COMMITS", "ANCHORS"} <= edge_kinds
    assert sum(node["kind"] == "ACTION" for node in graph["nodes"]) == 12
    assert sum(node["kind"] == "RECEIPT" for node in graph["nodes"]) == 12


def test_same_verified_run_is_byte_deterministic() -> None:
    first = build_graph(REAL_RUN)
    second = build_graph(REAL_RUN)

    assert first == second
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second,
        sort_keys=True,
        ensure_ascii=False,
    )


def test_human_and_agent_projections_share_the_same_graph_identity() -> None:
    graph = build_graph(REAL_RUN)
    markdown = render_markdown(graph)
    agents = render_agents_md(graph)
    receipt = build_receipt(graph, markdown, agents)

    assert graph["graph_sha256"] in markdown
    assert graph["graph_sha256"] in agents
    assert "Structural completeness does **not** prove correctness" in markdown
    assert "Graph discovery grants **no authority**" in agents
    assert "REST: `UNAVAILABLE`" in agents
    assert "MCP: `UNAVAILABLE`" in agents
    assert receipt.schema == RECEIPT_SCHEMA
    assert receipt.graph_sha256 == graph["graph_sha256"]
    assert len(receipt.markdown_sha256) == 64
    assert len(receipt.agents_md_sha256) == 64


def test_outputs_are_four_projections_bound_by_receipt(tmp_path: Path) -> None:
    paths = write_outputs(REAL_RUN, tmp_path / "graph")

    assert len(paths) == 4
    output = tmp_path / "graph"
    graph = json.loads((output / "evidence-trajectory.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (output / "evidence-trajectory.receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["graph_sha256"] == graph["graph_sha256"]
    assert (output / "evidence-trajectory.md").exists()
    assert (output / "agents.md").exists()


def test_existing_chain_verifier_blocks_graph_generation_after_tamper(tmp_path: Path) -> None:
    tampered = tmp_path / "run"
    shutil.copytree(REAL_RUN, tampered)
    trace_path = tampered / "trace.jsonl"
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["state_next_hash"] = "0" * 32
    trace_path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(GraphError, match="existing trust-chain verification failed"):
        build_graph(tampered)
