#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SZL Holdings — offline trust-run chain-integrity verifier
# © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
# Doctrine v11 LOCKED (749/14/163 · c7c0ba17)
#
# Fail-closed, offline integrity verifier for szl-trust run artifacts.
#
# Given a run directory (e.g. runs/E4-codex-kernel-2026-04-29/) this checks the
# internal-consistency invariants that a published Covenant Proof Standard run
# MUST satisfy, WITHOUT any network access or SZL tooling. It is deliberately
# FAIL-CLOSED: a malformed / truncated / re-ordered / tampered record is
# REJECTED (non-zero exit), never silently skipped.
#
# Invariants checked (all derivable from the published data alone):
#   1. proof_ledger.jsonl and trace.jsonl parse line-by-line — any malformed
#      JSON line, or an empty file, is rejected (not skipped).
#   2. Step numbers form a contiguous 1..N sequence (no gaps, dupes, reorder) in
#      BOTH files, and both files declare the same number of steps.
#   3. receipt_id agrees between the ledger step and the trace span for each step.
#   4. State binding: proof_ledger[i].state_hash == trace[i].state_next_hash.
#   5. Hash-chain continuity: trace[i].state_prev_hash == trace[i-1].state_next_hash.
#   6. Manifest anchor: run_manifest.final_state_hash == the final ledger state_hash.
#   7. The top-level decision_receipt.json (last_receipt) agrees with the final
#      trace span on receipt_id and on the `mocked` posture flag.
#   8. Every trace span carries a boolean `mocked` flag (missing / non-boolean
#      posture is rejected).
#
# Honest scope: this is ADVISORY internal-consistency / tamper-evidence, NOT a
# proof of authenticity. It shows the published artifacts are self-consistent and
# that any edit to one record breaks a cross-referenced invariant — it does NOT
# assert the state hashes were produced by a trusted signer, and it never
# fabricates or asserts a cryptographic signature. Λ = Conjecture 1 (advisory,
# not a theorem). Trust ceiling 0.97 by doctrine — never 1.0.
#
# Signed-off-by: stephenlutar2-hash <270976497+stephenlutar2-hash@users.noreply.github.com>

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class ChainError(Exception):
    """Raised on any integrity violation — the caller treats this as fail-closed."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file fail-closed.

    Every non-empty line MUST be a JSON object. A blank line inside the body, a
    truncated / malformed line, or a top-level non-object is a hard error — we do
    NOT skip-and-continue, because a silently dropped record would let a tampered
    ledger pass. An empty file is also an error.
    """
    if not path.is_file():
        raise ChainError(f"{path.name}: file is missing")
    records: list[dict[str, Any]] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    for lineno, line in enumerate(lines, start=1):
        if line.strip() == "":
            raise ChainError(f"{path.name}:{lineno}: blank line inside JSONL body (rejected)")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ChainError(f"{path.name}:{lineno}: malformed JSON ({exc.msg})") from exc
        if not isinstance(obj, dict):
            raise ChainError(f"{path.name}:{lineno}: expected a JSON object, got {type(obj).__name__}")
        records.append(obj)
    if not records:
        raise ChainError(f"{path.name}: no records (empty file rejected)")
    return records


def _require(record: dict[str, Any], field: str, ctx: str) -> Any:
    if field not in record:
        raise ChainError(f"{ctx}: missing required field '{field}'")
    return record[field]


def _check_contiguous_steps(records: list[dict[str, Any]], label: str) -> None:
    for idx, rec in enumerate(records, start=1):
        step = _require(rec, "step", f"{label} record #{idx}")
        if not isinstance(step, int) or isinstance(step, bool):
            raise ChainError(f"{label} record #{idx}: 'step' must be an integer, got {step!r}")
        if step != idx:
            raise ChainError(
                f"{label}: step sequence broken at position {idx} — "
                f"expected step {idx}, found step {step} (gap, duplicate, or reorder)"
            )


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    """Verify a run directory's internal consistency. Returns a summary dict on
    success; raises ChainError on the first violation (fail-closed)."""
    run = Path(run_dir)
    if not run.is_dir():
        raise ChainError(f"run directory not found: {run}")

    ledger = load_jsonl(run / "proof_ledger.jsonl")
    trace = load_jsonl(run / "trace.jsonl")

    # (2) contiguous 1..N in both files + equal length
    _check_contiguous_steps(ledger, "proof_ledger")
    _check_contiguous_steps(trace, "trace")
    if len(ledger) != len(trace):
        raise ChainError(
            f"step-count mismatch: proof_ledger has {len(ledger)} steps but "
            f"trace has {len(trace)} spans"
        )

    prev_next: str | None = None
    for i, (lrec, trec) in enumerate(zip(ledger, trace), start=1):
        lctx = f"proof_ledger step {i}"
        tctx = f"trace span {i}"

        state_hash = _require(lrec, "state_hash", lctx)
        ledger_rid = _require(lrec, "receipt_id", lctx)
        prev_hash = _require(trec, "state_prev_hash", tctx)
        next_hash = _require(trec, "state_next_hash", tctx)

        receipt = _require(trec, "decision_receipt", tctx)
        if not isinstance(receipt, dict):
            raise ChainError(f"{tctx}: 'decision_receipt' must be an object")
        trace_rid = _require(receipt, "receipt_id", f"{tctx}.decision_receipt")

        # (3) receipt_id agreement across files
        if ledger_rid != trace_rid:
            raise ChainError(
                f"step {i}: receipt_id mismatch — ledger={ledger_rid!r} trace={trace_rid!r}"
            )

        # (8) posture flag present + boolean
        posture = _require(receipt, "mocked", f"{tctx}.decision_receipt")
        if not isinstance(posture, bool):
            raise ChainError(
                f"{tctx}.decision_receipt: 'mocked' must be a boolean, got {posture!r}"
            )

        # (4) state binding ledger <-> trace
        if state_hash != next_hash:
            raise ChainError(
                f"step {i}: state binding broken — proof_ledger.state_hash={state_hash!r} "
                f"!= trace.state_next_hash={next_hash!r}"
            )

        # (5) hash-chain continuity between consecutive spans
        if prev_next is not None and prev_hash != prev_next:
            raise ChainError(
                f"step {i}: chain continuity broken — state_prev_hash={prev_hash!r} "
                f"!= previous span's state_next_hash={prev_next!r}"
            )
        prev_next = next_hash

    final_state_hash = ledger[-1]["state_hash"]

    # (6) manifest anchor
    manifest_path = run / "run_manifest.json"
    if not manifest_path.is_file():
        raise ChainError("run_manifest.json is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChainError(f"run_manifest.json: malformed JSON ({exc.msg})") from exc
    manifest_final = manifest.get("final_state_hash")
    if manifest_final is None:
        raise ChainError("run_manifest.json: missing 'final_state_hash'")
    if manifest_final != final_state_hash:
        raise ChainError(
            f"manifest anchor mismatch — run_manifest.final_state_hash={manifest_final!r} "
            f"!= final ledger state_hash={final_state_hash!r}"
        )

    # (7) top-level decision_receipt.json cross-check (if present)
    dr_path = run / "decision_receipt.json"
    if dr_path.is_file():
        try:
            dr = json.loads(dr_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ChainError(f"decision_receipt.json: malformed JSON ({exc.msg})") from exc
        last = dr.get("last_receipt")
        if isinstance(last, dict):
            final_trace_rid = trace[-1]["decision_receipt"]["receipt_id"]
            final_trace_posture = trace[-1]["decision_receipt"]["mocked"]
            if last.get("receipt_id") != final_trace_rid:
                raise ChainError(
                    f"decision_receipt.last_receipt.receipt_id={last.get('receipt_id')!r} "
                    f"!= final trace receipt_id={final_trace_rid!r}"
                )
            if "mocked" in last and last["mocked"] != final_trace_posture:
                raise ChainError(
                    f"decision_receipt.last_receipt.mocked={last.get('mocked')!r} "
                    f"!= final trace posture={final_trace_posture!r}"
                )

    postures = {trec["decision_receipt"]["mocked"] for trec in trace}
    return {
        "run": run.name,
        "steps": len(ledger),
        "final_state_hash": final_state_hash,
        "posture_mocked_values": sorted(postures),
        "advisory": "internal-consistency / tamper-evidence only; not a proof of authenticity",
    }


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        # Default: verify every run/ subdirectory that has a proof ledger.
        repo_root = Path(__file__).resolve().parent.parent
        runs_root = repo_root / "runs"
        if not runs_root.is_dir():
            print("::error::no runs/ directory found", file=sys.stderr)
            return 1
        args = [str(p) for p in sorted(runs_root.iterdir())
                if (p / "proof_ledger.jsonl").is_file()]
        if not args:
            print("::error::no runs with proof_ledger.jsonl found under runs/", file=sys.stderr)
            return 1

    exit_code = 0
    for run_dir in args:
        try:
            summary = verify_run(run_dir)
        except ChainError as exc:
            print(f"FAIL {run_dir}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(
            f"OK   {summary['run']}: {summary['steps']} steps chained, "
            f"final_state_hash={summary['final_state_hash']}, "
            f"mocked={summary['posture_mocked_values']} "
            f"(advisory: {summary['advisory']})"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
