#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile a verified SZL trust run into one evidence + trajectory graph.

The graph is the shared truth object for human review, agent consumption, and
future REST/MCP projections. This module does not create authority and does not
claim correctness. It first runs the existing cross-artifact chain verifier, then
normalizes state, action, evidence, validator, receipt, and manifest relationships
into a deterministic graph with an explicit structural-completeness measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from verify_chain import ChainError, verify_run

SCHEMA: Final = "szl.evidence-trajectory/v1"
RECEIPT_SCHEMA: Final = "szl.evidence-trajectory-receipt/v1"
NODE_KINDS: Final = frozenset(
    {
        "RUN_MANIFEST",
        "STATE",
        "ACTION",
        "EVIDENCE_SOURCE",
        "VALIDATOR",
        "RECEIPT",
    }
)
EDGE_KINDS: Final = frozenset(
    {
        "INPUT_STATE",
        "CITES",
        "VERIFIES",
        "PRODUCES",
        "COMMITS",
        "ANCHORS",
    }
)
EVIDENCE_LABELS: Final = frozenset(
    {"PROVED", "MEASURED", "REPORTED", "MODELED", "CONJECTURE", "UNKNOWN", "UNAVAILABLE"}
)


class GraphError(ValueError):
    """Raised when a verified run still cannot produce an unambiguous graph."""


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    evidence_label: str
    trace_id: str
    span_id: str | None
    payload: dict[str, Any]
    payload_sha256: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str
    step: int | None


@dataclass(frozen=True)
class GraphReceipt:
    schema: str
    run: str
    graph_sha256: str
    markdown_sha256: str
    agents_md_sha256: str
    node_count: int
    edge_count: int
    structural_completeness_numerator: int
    structural_completeness_denominator: int

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, indent=2) + "\n"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode()
    else:
        raw = _canonical(value)
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GraphError(f"required artifact missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphError(f"{path.name}: malformed JSON ({exc.msg})") from exc
    if not isinstance(value, dict):
        raise GraphError(f"{path.name}: root must be an object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise GraphError(f"required artifact missing: {path.name}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GraphError(f"{path.name}:{number}: malformed JSON ({exc.msg})") from exc
        if not isinstance(value, dict):
            raise GraphError(f"{path.name}:{number}: row must be an object")
        rows.append(value)
    if not rows:
        raise GraphError(f"{path.name}: no records")
    return rows


def _span_id(trace_id: str, step: int) -> str:
    return _digest(f"{trace_id}:step:{step}")[:16]


def _node_id(kind: str, identity: str) -> str:
    return f"{kind.lower()}:{_digest(f'{kind}:{identity}')[:24]}"


def _node(
    *,
    kind: str,
    identity: str,
    evidence_label: str,
    trace_id: str,
    span_id: str | None,
    payload: dict[str, Any],
) -> Node:
    if kind not in NODE_KINDS:
        raise GraphError(f"unsupported node kind: {kind}")
    if evidence_label not in EVIDENCE_LABELS:
        raise GraphError(f"unsupported evidence label: {evidence_label}")
    return Node(
        id=_node_id(kind, identity),
        kind=kind,
        evidence_label=evidence_label,
        trace_id=trace_id,
        span_id=span_id,
        payload=payload,
        payload_sha256=_digest(payload),
    )


def _edge(source: str, target: str, kind: str, step: int | None) -> Edge:
    if kind not in EDGE_KINDS:
        raise GraphError(f"unsupported edge kind: {kind}")
    return Edge(source=source, target=target, kind=kind, step=step)


def _action_payload(trace_row: dict[str, Any]) -> dict[str, Any]:
    receipt = trace_row.get("decision_receipt")
    if not isinstance(receipt, dict):
        raise GraphError("trace decision_receipt must be an object")
    action = trace_row.get("action")
    if not isinstance(action, dict):
        raise GraphError("trace action must be an object")
    return {
        "step": trace_row.get("step"),
        "ts": trace_row.get("ts"),
        "action": action,
        "policy_version": receipt.get("policy_version"),
        "approval_status": receipt.get("approval_status", "UNKNOWN"),
        "approval_ref": receipt.get("approval_ref"),
        "mocked": receipt.get("mocked"),
        "authority_interpretation": {
            "graph_grants_authority": False,
            "recorded_execution_is_not_future_authority": True,
        },
    }


def build_graph(run_dir: str | Path) -> dict[str, Any]:
    """Verify and normalize a run into the deterministic evidence trajectory schema."""

    run = Path(run_dir)
    try:
        chain_summary = verify_run(run)
    except ChainError as exc:
        raise GraphError(f"existing trust-chain verification failed: {exc}") from exc

    trace = _read_jsonl(run / "trace.jsonl")
    ledger = _read_jsonl(run / "proof_ledger.jsonl")
    manifest = _read_json(run / "run_manifest.json")
    if len(trace) != len(ledger):
        raise GraphError("trace and proof ledger length disagree after verification")

    trace_identity = manifest.get("trace_identity")
    if not isinstance(trace_identity, dict):
        raise GraphError("run_manifest.trace_identity must be an object")
    trace_id = str(trace_identity.get("trace_id") or "").strip()
    run_id = str(trace_identity.get("run_id") or "").strip()
    if not trace_id or not run_id:
        raise GraphError("run_manifest.trace_identity requires trace_id and run_id")

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    expected_structural_edges = 1  # manifest -> final state anchor

    manifest_node = _node(
        kind="RUN_MANIFEST",
        identity=run_id,
        evidence_label="REPORTED",
        trace_id=trace_id,
        span_id=None,
        payload={
            "experiment_id": manifest.get("experiment_id"),
            "run_id": run_id,
            "trace_id": trace_id,
            "final_state_hash": manifest.get("final_state_hash"),
            "repo_commit": (manifest.get("version_lineage") or {}).get("repo_commit"),
            "model_provider": (manifest.get("version_lineage") or {}).get("model_provider"),
            "model_version": (manifest.get("version_lineage") or {}).get("model_version"),
        },
    )
    nodes[manifest_node.id] = manifest_node

    final_state_node_id: str | None = None
    mocked_values: set[bool] = set()
    citation_edge_count = 0
    validator_edge_count = 0

    for index, (trace_row, ledger_row) in enumerate(zip(trace, ledger, strict=True), 1):
        step = int(trace_row.get("step") or index)
        span_id = _span_id(trace_id, step)
        prev_hash = str(trace_row.get("state_prev_hash") or "")
        next_hash = str(trace_row.get("state_next_hash") or "")
        if not prev_hash or not next_hash:
            raise GraphError(f"step {step}: missing state hash")

        prev_state = _node(
            kind="STATE",
            identity=prev_hash,
            evidence_label="MEASURED",
            trace_id=trace_id,
            span_id=span_id,
            payload={"state_hash": prev_hash},
        )
        next_state = _node(
            kind="STATE",
            identity=next_hash,
            evidence_label="MEASURED",
            trace_id=trace_id,
            span_id=span_id,
            payload={"state_hash": next_hash},
        )
        nodes.setdefault(prev_state.id, prev_state)
        nodes.setdefault(next_state.id, next_state)

        action_payload = _action_payload(trace_row)
        mocked = action_payload.get("mocked")
        if not isinstance(mocked, bool):
            raise GraphError(f"step {step}: mocked posture must be boolean")
        mocked_values.add(mocked)
        action_node = _node(
            kind="ACTION",
            identity=f"{run_id}:{step}:{trace_row.get('action_id')}",
            evidence_label="REPORTED",
            trace_id=trace_id,
            span_id=span_id,
            payload=action_payload,
        )
        nodes[action_node.id] = action_node
        edges.append(_edge(prev_state.id, action_node.id, "INPUT_STATE", step))
        expected_structural_edges += 1

        receipt = trace_row["decision_receipt"]
        evidence = receipt.get("evidence")
        if not isinstance(evidence, list):
            raise GraphError(f"step {step}: decision_receipt.evidence must be an array")
        for position, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                raise GraphError(f"step {step}: evidence {position} must be an object")
            ref = str(item.get("ref") or "").strip()
            if not ref:
                raise GraphError(f"step {step}: evidence {position} missing ref")
            evidence_node = _node(
                kind="EVIDENCE_SOURCE",
                identity=ref,
                evidence_label="REPORTED",
                trace_id=trace_id,
                span_id=None,
                payload={"ref": ref, "kind": item.get("kind", "UNKNOWN")},
            )
            nodes.setdefault(evidence_node.id, evidence_node)
            edges.append(_edge(evidence_node.id, action_node.id, "CITES", step))
            citation_edge_count += 1
            expected_structural_edges += 1

        validators = trace_row.get("validators")
        if not isinstance(validators, list):
            raise GraphError(f"step {step}: validators must be an array")
        for position, validator in enumerate(validators, 1):
            if not isinstance(validator, dict):
                raise GraphError(f"step {step}: validator {position} must be an object")
            validator_name = str(validator.get("name") or f"validator-{position}")
            validator_node = _node(
                kind="VALIDATOR",
                identity=f"{run_id}:{step}:{position}:{validator_name}",
                evidence_label="MEASURED",
                trace_id=trace_id,
                span_id=span_id,
                payload=validator,
            )
            nodes[validator_node.id] = validator_node
            edges.append(_edge(validator_node.id, action_node.id, "VERIFIES", step))
            validator_edge_count += 1
            expected_structural_edges += 1

        receipt_id = str(receipt.get("receipt_id") or "").strip()
        if not receipt_id:
            raise GraphError(f"step {step}: receipt_id missing")
        receipt_node = _node(
            kind="RECEIPT",
            identity=receipt_id,
            evidence_label="MEASURED",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "receipt_id": receipt_id,
                "policy_version": receipt.get("policy_version"),
                "approval_status": receipt.get("approval_status", "UNKNOWN"),
                "approval_ref": receipt.get("approval_ref"),
                "mocked": mocked,
                "ledger_state_hash": ledger_row.get("state_hash"),
                "delta_hash": ledger_row.get("delta_hash"),
            },
        )
        nodes[receipt_node.id] = receipt_node
        edges.append(_edge(action_node.id, receipt_node.id, "PRODUCES", step))
        edges.append(_edge(receipt_node.id, next_state.id, "COMMITS", step))
        expected_structural_edges += 2
        final_state_node_id = next_state.id

    if final_state_node_id is None:
        raise GraphError("run has no final state")
    edges.append(_edge(manifest_node.id, final_state_node_id, "ANCHORS", None))

    node_rows = [node.__dict__ for node in sorted(nodes.values(), key=lambda item: item.id)]
    edge_rows = [
        edge.__dict__
        for edge in sorted(
            edges,
            key=lambda item: (item.step or 0, item.kind, item.source, item.target),
        )
    ]
    present = len(edge_rows)
    structural_score = present / expected_structural_edges if expected_structural_edges else 0.0

    graph_without_digest = {
        "schema": SCHEMA,
        "run": run.name,
        "experiment_id": manifest.get("experiment_id"),
        "trace_identity": {
            "run_id": run_id,
            "trace_id": trace_id,
            "span_id_derivation": "sha256(trace_id:step:N)[:16]",
        },
        "source_identity": {
            "repository": "szl-holdings/szl-trust",
            "repo_commit": (manifest.get("version_lineage") or {}).get("repo_commit"),
            "manifest_hash": trace_identity.get("manifest_hash"),
        },
        "chain_verification": chain_summary,
        "authority_boundary": {
            "graph_grants_authority": False,
            "recorded_execution_is_not_future_authority": True,
            "human_or_agent_consumers_must_apply_separate_capability_policy": True,
        },
        "structural_completeness": {
            "numerator": present,
            "denominator": expected_structural_edges,
            "score": structural_score,
            "evidence_label": "MEASURED",
            "claim_boundary": "Structural completeness measures required graph relationships only; it does not prove correctness, authenticity, safety, or external validity.",
        },
        "summary": {
            "steps": len(trace),
            "nodes": len(node_rows),
            "edges": present,
            "citation_edges": citation_edge_count,
            "validator_edges": validator_edge_count,
            "mocked_values": sorted(mocked_values),
            "final_state_hash": chain_summary["final_state_hash"],
        },
        "projections": {
            "human_markdown": "evidence-trajectory.md",
            "agent_instructions": "agents.md",
            "rest_endpoint": "UNAVAILABLE",
            "mcp_endpoint": "UNAVAILABLE",
        },
        "nodes": node_rows,
        "edges": edge_rows,
    }
    return {**graph_without_digest, "graph_sha256": _digest(graph_without_digest)}


def render_markdown(graph: dict[str, Any]) -> str:
    summary = graph["summary"]
    completeness = graph["structural_completeness"]
    lines = [
        f"# Evidence trajectory — {graph['run']}",
        "",
        "> One verified graph for states, actions, citations, validators, receipts, and source identity.",
        "",
        "## Measured structure",
        "",
        f"- Steps: **{summary['steps']}**",
        f"- Nodes: **{summary['nodes']}**",
        f"- Edges: **{summary['edges']}**",
        f"- Citation edges: **{summary['citation_edges']}**",
        f"- Validator edges: **{summary['validator_edges']}**",
        f"- Final state: `{summary['final_state_hash']}`",
        f"- Graph SHA-256: `{graph['graph_sha256']}`",
        f"- Structural completeness: **{completeness['numerator']}/{completeness['denominator']} ({completeness['score']:.3f})** — `{completeness['evidence_label']}`",
        "",
        "Structural completeness does **not** prove correctness, authenticity, safety, authorization, or external validity.",
        "",
        "## Authority boundary",
        "",
        "This graph records what happened; it does not grant permission to repeat, escalate, or automate any action.",
        "",
        "## Step trajectory",
        "",
        "| Step | Span | Action | Approval | Mocked | Receipt |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    actions = [node for node in graph["nodes"] if node["kind"] == "ACTION"]
    receipts = {node["span_id"]: node for node in graph["nodes"] if node["kind"] == "RECEIPT"}
    for action in sorted(actions, key=lambda node: int(node["payload"]["step"])):
        step = int(action["payload"]["step"])
        span = action["span_id"]
        receipt = receipts.get(span)
        action_name = (action["payload"].get("action") or {}).get("name", "UNKNOWN")
        approval = action["payload"].get("approval_status", "UNKNOWN")
        mocked = action["payload"].get("mocked")
        receipt_id = (receipt or {}).get("payload", {}).get("receipt_id", "UNAVAILABLE")
        lines.append(f"| {step} | `{span}` | `{action_name}` | `{approval}` | `{mocked}` | `{receipt_id}` |")
    return "\n".join(lines) + "\n"


def render_agents_md(graph: dict[str, Any]) -> str:
    return f'''# {graph['run']} — evidence graph agent contract

Use `evidence-trajectory.json` as the canonical graph. The Markdown projection is for human review only.

## Authority

- Graph discovery grants **no authority**.
- Recorded actions are historical evidence, not reusable permissions.
- A future REST or MCP projection must apply a separate capability/approval policy before any mutation.
- If a required source, receipt, state edge, or validator is missing, return `UNAVAILABLE` or `UNKNOWN`; do not infer it.

## Evidence vocabulary

- `MEASURED`: computed or verified from the local artifact relationship.
- `REPORTED`: carried from source artifacts without independent external validation.

## Integrity

- Graph SHA-256: `{graph['graph_sha256']}`
- Trace ID: `{graph['trace_identity']['trace_id']}`
- Source commit: `{graph['source_identity']['repo_commit']}`
- Final state hash: `{graph['summary']['final_state_hash']}`
- Structural completeness: `{graph['structural_completeness']['numerator']}/{graph['structural_completeness']['denominator']}` (`MEASURED`)

Structural completeness does not prove correctness, authenticity, safety, authorization, or external validity.

## Interfaces

- Human Markdown: `evidence-trajectory.md`
- JSON graph: `evidence-trajectory.json`
- REST: `UNAVAILABLE`
- MCP: `UNAVAILABLE`
'''


def build_receipt(graph: dict[str, Any], markdown: str, agents_md: str) -> GraphReceipt:
    completeness = graph["structural_completeness"]
    return GraphReceipt(
        schema=RECEIPT_SCHEMA,
        run=graph["run"],
        graph_sha256=graph["graph_sha256"],
        markdown_sha256=_digest(markdown),
        agents_md_sha256=_digest(agents_md),
        node_count=graph["summary"]["nodes"],
        edge_count=graph["summary"]["edges"],
        structural_completeness_numerator=completeness["numerator"],
        structural_completeness_denominator=completeness["denominator"],
    )


def write_outputs(run_dir: str | Path, output_dir: str | Path) -> list[Path]:
    graph = build_graph(run_dir)
    markdown = render_markdown(graph)
    agents_md = render_agents_md(graph)
    receipt = build_receipt(graph, markdown, agents_md)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "evidence-trajectory.json": json.dumps(graph, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        "evidence-trajectory.md": markdown,
        "agents.md": agents_md,
        "evidence-trajectory.receipt.json": receipt.to_json(),
    }
    paths: list[Path] = []
    for name, content in artifacts.items():
        path = output / name
        path.write_text(content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile a verified SZL run into one evidence trajectory graph.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        paths = write_outputs(args.run_dir, args.output)
    except (OSError, GraphError) as exc:
        print(f"FAIL {args.run_dir}: {exc}")
        return 1
    print(f"generated {len(paths)} evidence trajectory artifacts in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
