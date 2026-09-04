#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile one verified SZL trust run into a deterministic evidence trajectory.

The compiler is deliberately offline and fail-closed. It delegates chain,
receipt, state, posture, and manifest verification to ``verify_chain.verify_run``
before it emits any graph. The graph is descriptive only: reading a historical
trajectory never grants authority to repeat an action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_chain import ChainError, verify_run  # noqa: E402

SCHEMA = "szl.evidence-trajectory/v1"
RECEIPT_SCHEMA = "szl.evidence-trajectory-receipt/v1"
SOURCE_REPOSITORY = "szl-holdings/szl-trust"
AUTHORITY_BOUNDARY = (
    "Discovery is descriptive only. A recorded historical action is not "
    "permission to repeat it; any future mutation requires a separate "
    "capability and approval decision."
)
COMPLETENESS_BOUNDARY = (
    "Structural completeness checks required relationships only. It does not "
    "prove correctness, authenticity, safety, authorization, or external validity."
)


class TrajectoryError(ValueError):
    """Raised when verified source material cannot form a complete trajectory."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TrajectoryError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise TrajectoryError(f"{path.name}: malformed JSON ({exc.msg})") from exc
    if not isinstance(value, dict):
        raise TrajectoryError(f"{path.name}: expected a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise TrajectoryError(f"missing required file: {path.name}") from exc
    if not lines:
        raise TrajectoryError(f"{path.name}: empty JSONL file")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TrajectoryError(f"{path.name}:{line_number}: blank JSONL record")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TrajectoryError(
                f"{path.name}:{line_number}: malformed JSON ({exc.msg})"
            ) from exc
        if not isinstance(value, dict):
            raise TrajectoryError(
                f"{path.name}:{line_number}: expected a JSON object"
            )
        records.append(value)
    return records


def _required_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TrajectoryError(f"{context}: expected an object")
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise TrajectoryError(f"{context}: expected non-empty text")
    return value


def _node(node_id: str, node_type: str, **attributes: Any) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "attributes": attributes}


def _edge(
    edge_type: str,
    source: str,
    target: str,
    **attributes: Any,
) -> dict[str, Any]:
    identity = {"type": edge_type, "source": source, "target": target, **attributes}
    return {
        "id": f"edge:{_sha256(identity)[:24]}",
        "type": edge_type,
        "source": source,
        "target": target,
        "attributes": attributes,
    }


def _append_unique(
    nodes: list[dict[str, Any]],
    node_ids: set[str],
    value: dict[str, Any],
) -> None:
    node_id = value["id"]
    if node_id not in node_ids:
        nodes.append(value)
        node_ids.add(node_id)


def compile_trajectory(run_dir: str | Path) -> dict[str, Any]:
    """Verify ``run_dir`` and return one canonical trajectory graph."""

    run = Path(run_dir)
    verified = verify_run(run)
    trace = _read_jsonl(run / "trace.jsonl")
    ledger = _read_jsonl(run / "proof_ledger.jsonl")
    manifest = _read_json(run / "run_manifest.json")

    if len(trace) != verified["steps"] or len(ledger) != verified["steps"]:
        raise TrajectoryError("verified step count changed during graph compilation")

    trace_identity = _required_mapping(
        manifest.get("trace_identity"), "run_manifest.trace_identity"
    )
    version_lineage = _required_mapping(
        manifest.get("version_lineage"), "run_manifest.version_lineage"
    )
    trace_id = _required_text(trace_identity.get("trace_id"), "trace_identity.trace_id")
    run_id = _required_text(trace_identity.get("run_id"), "trace_identity.run_id")
    source_commit = _required_text(
        version_lineage.get("repo_commit"), "version_lineage.repo_commit"
    )
    final_state_hash = _required_text(
        manifest.get("final_state_hash"), "run_manifest.final_state_hash"
    )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    mocked_values: set[bool] = set()

    manifest_id = f"manifest:{_sha256(manifest)[:24]}"
    _append_unique(
        nodes,
        node_ids,
        _node(
            manifest_id,
            "RUN_MANIFEST",
            experiment_id=manifest.get("experiment_id"),
            run_id=run_id,
            trace_id=trace_id,
            final_state_hash=final_state_hash,
            source_repository=SOURCE_REPOSITORY,
            source_commit=source_commit,
            manifest_sha256=_sha256(manifest),
        ),
    )

    expected_relationships = 0
    observed_relationships = 0
    prior_next_state: str | None = None

    for position, (trace_record, ledger_record) in enumerate(
        zip(trace, ledger), start=1
    ):
        step = trace_record.get("step")
        if step != position or ledger_record.get("step") != position:
            raise TrajectoryError(f"step {position}: non-contiguous source records")

        receipt = _required_mapping(
            trace_record.get("decision_receipt"),
            f"trace step {position}.decision_receipt",
        )
        observation = _required_mapping(
            trace_record.get("observation"), f"trace step {position}.observation"
        )
        proposed_delta = _required_mapping(
            trace_record.get("proposed_delta"),
            f"trace step {position}.proposed_delta",
        )
        previous_hash = _required_text(
            trace_record.get("state_prev_hash"),
            f"trace step {position}.state_prev_hash",
        )
        next_hash = _required_text(
            trace_record.get("state_next_hash"),
            f"trace step {position}.state_next_hash",
        )
        receipt_id = _required_text(
            receipt.get("receipt_id"), f"trace step {position}.receipt_id"
        )
        posture = receipt.get("mocked")
        if not isinstance(posture, bool):
            raise TrajectoryError(f"trace step {position}.mocked: expected boolean")
        mocked_values.add(posture)

        if prior_next_state is not None and previous_hash != prior_next_state:
            raise TrajectoryError(f"step {position}: state trajectory is discontinuous")
        prior_next_state = next_hash

        previous_state_id = f"state:{previous_hash}"
        next_state_id = f"state:{next_hash}"
        action_id = f"action:{trace_id}:{position:04d}"
        receipt_node_id = f"receipt:{receipt_id}"
        span_id = f"span:{trace_id}:{position:04d}"

        _append_unique(
            nodes,
            node_ids,
            _node(
                previous_state_id,
                "STATE",
                state_hash=previous_hash,
                role="INPUT",
            ),
        )
        _append_unique(
            nodes,
            node_ids,
            _node(
                next_state_id,
                "STATE",
                state_hash=next_hash,
                role="OUTPUT",
            ),
        )
        _append_unique(
            nodes,
            node_ids,
            _node(
                action_id,
                "ACTION",
                step=position,
                span_id=span_id,
                pipeline_stage=trace_record.get("pipeline_stage"),
                observation=observation,
                proposed_delta=proposed_delta,
                decision_type=receipt.get("decision_type"),
                summary=receipt.get("summary"),
                timestamp=receipt.get("timestamp"),
            ),
        )
        _append_unique(
            nodes,
            node_ids,
            _node(
                receipt_node_id,
                "RECEIPT",
                step=position,
                receipt_id=receipt_id,
                policy_version=receipt.get("policy_version"),
                approval_status=receipt.get("approval_status"),
                mocked=posture,
                payload_sha256=_sha256(receipt),
            ),
        )

        base_edges = [
            _edge("INPUT_STATE", previous_state_id, action_id, step=position),
            _edge("PRODUCES", action_id, next_state_id, step=position),
            _edge("COMMITS", receipt_node_id, action_id, step=position),
            _edge("ANCHORS", receipt_node_id, next_state_id, step=position),
        ]
        edges.extend(base_edges)
        expected_relationships += len(base_edges)
        observed_relationships += len(base_edges)

        evidence_items = receipt.get("evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            raise TrajectoryError(f"step {position}: evidence list is missing or empty")
        for evidence_index, evidence_value in enumerate(evidence_items, start=1):
            evidence = _required_mapping(
                evidence_value,
                f"trace step {position}.evidence[{evidence_index}]",
            )
            evidence_id = f"evidence:{_sha256(evidence)[:24]}"
            _append_unique(
                nodes,
                node_ids,
                _node(
                    evidence_id,
                    "EVIDENCE_SOURCE",
                    kind=evidence.get("kind"),
                    reference=evidence.get("ref"),
                    mocked=evidence.get("mocked"),
                    payload_sha256=_sha256(evidence),
                ),
            )
            edges.append(
                _edge(
                    "CITES",
                    action_id,
                    evidence_id,
                    step=position,
                    ordinal=evidence_index,
                )
            )
            expected_relationships += 1
            observed_relationships += 1

        validators = trace_record.get("validator_results")
        if not isinstance(validators, list) or not validators:
            raise TrajectoryError(f"step {position}: validator results are missing")
        for validator_index, validator_value in enumerate(validators, start=1):
            validator = _required_mapping(
                validator_value,
                f"trace step {position}.validator[{validator_index}]",
            )
            validator_identity = {
                "step": position,
                "ordinal": validator_index,
                "validator": validator,
            }
            validator_id = f"validator:{_sha256(validator_identity)[:24]}"
            _append_unique(
                nodes,
                node_ids,
                _node(
                    validator_id,
                    "VALIDATOR",
                    step=position,
                    ordinal=validator_index,
                    name=validator.get("name"),
                    severity=validator.get("severity"),
                    summary=validator.get("summary"),
                    details=validator.get("details"),
                    payload_sha256=_sha256(validator),
                ),
            )
            edges.append(
                _edge(
                    "VERIFIES",
                    validator_id,
                    action_id,
                    step=position,
                    ordinal=validator_index,
                )
            )
            expected_relationships += 1
            observed_relationships += 1

    final_state_id = f"state:{final_state_hash}"
    if final_state_id not in node_ids:
        raise TrajectoryError("manifest final state is absent from verified trajectory")
    edges.append(_edge("ANCHORS", manifest_id, final_state_id, role="FINAL_STATE"))
    expected_relationships += 1
    observed_relationships += 1

    nodes.sort(key=lambda item: (item["type"], item["id"]))
    edges.sort(
        key=lambda item: (
            item["type"],
            item["source"],
            item["target"],
            item["id"],
        )
    )
    node_counts = Counter(item["type"] for item in nodes)
    edge_counts = Counter(item["type"] for item in edges)
    completeness = observed_relationships / expected_relationships

    graph: dict[str, Any] = {
        "schema": SCHEMA,
        "identity": {
            "run": run.name,
            "run_id": run_id,
            "trace_id": trace_id,
            "source_repository": SOURCE_REPOSITORY,
            "source_commit": source_commit,
            "manifest_sha256": _sha256(manifest),
        },
        "verification": {
            "preflight": "verify_chain.verify_run",
            "steps": verified["steps"],
            "final_state_hash": verified["final_state_hash"],
            "mocked_values": sorted(mocked_values),
            "trust_ceiling": 0.97,
            "lambda_posture": "CONJECTURE_1",
        },
        "interfaces": {"json": "AVAILABLE", "markdown": "AVAILABLE", "rest": "UNAVAILABLE", "mcp": "UNAVAILABLE"},
        "authority": {
            "mutation_authority": "NONE",
            "boundary": AUTHORITY_BOUNDARY,
        },
        "metrics": {
            "structural_completeness": {
                "value": completeness,
                "state": "MEASURED",
                "observed_required_relationships": observed_relationships,
                "expected_required_relationships": expected_relationships,
                "boundary": COMPLETENESS_BOUNDARY,
            },
            "node_counts": dict(sorted(node_counts.items())),
            "edge_counts": dict(sorted(edge_counts.items())),
        },
        "nodes": nodes,
        "edges": edges,
    }
    graph["graph_sha256"] = _sha256(graph)
    return graph


def render_markdown(graph: dict[str, Any]) -> str:
    metrics = graph["metrics"]
    identity = graph["identity"]
    verification = graph["verification"]
    edge_counts = metrics["edge_counts"]
    return "\n".join(
        [
            "# SZL Evidence Trajectory",
            "",
            f"- Run: `{identity['run']}`",
            f"- Trace: `{identity['trace_id']}`",
            f"- Source commit: `{identity['source_commit']}`",
            f"- Verified steps: **{verification['steps']}**",
            f"- Final state: `{verification['final_state_hash']}`",
            f"- Citation edges: **{edge_counts.get('CITES', 0)}**",
            f"- Validator edges: **{edge_counts.get('VERIFIES', 0)}**",
            f"- Graph SHA-256: `{graph['graph_sha256']}`",
            "",
            "## Authority boundary",
            "",
            graph["authority"]["boundary"],
            "",
            "## Structural completeness",
            "",
            metrics["structural_completeness"]["boundary"],
            "",
            "REST and MCP interfaces are `UNAVAILABLE` until separately implemented and verified.",
            "",
        ]
    )


def render_agents(graph: dict[str, Any]) -> str:
    identity = graph["identity"]
    return "\n".join(
        [
            "# Agent interpretation: SZL evidence trajectory",
            "",
            f"Canonical graph: `{graph['graph_sha256']}`",
            f"Run ID: `{identity['run_id']}`",
            f"Trace ID: `{identity['trace_id']}`",
            "",
            "## Allowed",
            "",
            "Read, search, cite, compare, and summarize the verified historical graph.",
            "",
            "## Not granted",
            "",
            "No mutation, deployment, approval, credential, targeting, or execution authority is conveyed by this artifact.",
            "",
            "Missing nodes or relationships must fail closed; they must not be inferred.",
            "",
        ]
    )


def write_trajectory(run_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    graph = compile_trajectory(run_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    graph_path = output / "evidence-trajectory.json"
    markdown_path = output / "evidence-trajectory.md"
    agents_path = output / "agents.md"
    receipt_path = output / "evidence-trajectory.receipt.json"

    graph_bytes = _canonical_bytes(graph)
    markdown_bytes = render_markdown(graph).encode("utf-8")
    agents_bytes = render_agents(graph).encode("utf-8")
    graph_path.write_bytes(graph_bytes)
    markdown_path.write_bytes(markdown_bytes)
    agents_path.write_bytes(agents_bytes)

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "graph_sha256": graph["graph_sha256"],
        "artifacts": {
            graph_path.name: hashlib.sha256(graph_bytes).hexdigest(),
            markdown_path.name: hashlib.sha256(markdown_bytes).hexdigest(),
            agents_path.name: hashlib.sha256(agents_bytes).hexdigest(),
        },
        "authority": "NONE",
    }
    receipt_path.write_bytes(_canonical_bytes(receipt))
    return {
        "graph": graph_path,
        "markdown": markdown_path,
        "agents": agents_path,
        "receipt": receipt_path,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        paths = write_trajectory(args.run_dir, args.output)
    except (ChainError, TrajectoryError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
