# szl-trust

**SZL Holdings Public Trust Portal.** Publishes verifiable run artifacts from the Covenant Proof Standard (CPS) — the proof-chain emitted by every governed execution across the SZL Holdings platform.

[![Thesis](https://img.shields.io/badge/thesis-v11%20published%20%C2%B7%20v12%20in%20review-805AD5?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis)
[![Concept DOI](https://img.shields.io/badge/Concept%20DOI-10.5281%2Fzenodo.19944926-1f78b4?style=flat-square)](https://doi.org/10.5281/zenodo.19944926)
[![Runtime](https://img.shields.io/badge/runtime-ouroboros%20v6.3.0%20·%20218%2F218-2DA44E?style=flat-square)](https://github.com/szl-holdings/ouroboros)
[![Lean](https://img.shields.io/badge/Lean%204-kernel--verified-2D5BB9?style=flat-square&logo=lean&logoColor=white)](https://github.com/szl-holdings/lutar-lean) [![Runtime DOI](https://img.shields.io/badge/runtime%20DOI-10.5281%2Fzenodo.20162352-3b82f6?style=flat-square)](https://doi.org/10.5281/zenodo.20162352)
[![License](https://img.shields.io/badge/artifacts%20license-CC%20BY%204.0-blue?style=flat-square)](#license)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/szl-holdings/szl-trust/badge)](https://securityscorecards.dev/viewer/?uri=github.com/szl-holdings/szl-trust)

## What's here

Each run produces 11 standardized JSON artifacts. The first reference run published here is **E4 Codex Kernel** (April 29, 2026), used as the canonical example for diligence reviewers.

## Reference run: E4 Codex Kernel

Located at [`runs/E4-codex-kernel-2026-04-29/`](runs/E4-codex-kernel-2026-04-29/).

**Identity**
- `experiment_id`: `E4-codex-kernel-governed-loop-unified-replit-all-in-one`
- `run_id`: `run_386723681730b1fd`
- `trace_id`: `trace_86725c2a26210b61`
- `payload_hash`: `624332a9470f8509fcfb57c6c39ac8dc`
- `manifest_hash`: `b977a47f69b7ba0d038c86271c85d234`
- `final_state_hash`: `fe20ecc47445dbd887b5b14ef26ed981`
- `ledger_digest`: `4d0a943cef5b8fa605919db38df5e8e7`

**Outcome**
- `status`: `ok`
- `stop_reason`: `convergence`
- `steps_executed`: 12
- `receipts_emitted`: 12
- `hard_stop_failures`: 0
- `soft_failures`: 1
- `degraded`: false

**Version lineage**
- `payload_version`: 1.0.0
- `kernel_version`: codex-kernel-runner-1.0.0
- `repo_commit`: `7eb623f8b870128e615ac6be9880e0265204b454`
- `model_version`: deterministic
- `resolved_at`: 2026-04-30T20:23:14.612Z

**Evidence**
Receipts cite the Dresden Codex (pp. 24, 46–50, Venus tables) and the IAU synodic period of Venus (583.92d). Every receipt carries `mocked: false`.

**Policy**
- `policy_version`: covenant-v1
- `approval_status`: not_required

## The 11 CPS artifacts

| File | Bytes | Purpose |
|------|-------|---------|
| `run_manifest.json` | 1879 | top-level manifest with hashes for every deliverable |
| `run_identity.json` | 1499 | run_id, trace_id, span_ids (one per step) |
| `run_summary.json` | 1720 | outcome, budget used, ledger digest, lineage |
| `decision_receipt.json` | 811 | last decision receipt (full set in proof_ledger) |
| `proof_ledger.jsonl` | 3255 | append-only ledger — one receipt per step |
| `trace.jsonl` | 26798 | full OpenTelemetry-style trace |
| `final_state.json` | 2970 | terminal state of the governed loop |
| `final_table_preview.json` | 2488 | human-readable preview of final output |
| `deployment_contract.json` | 509 | runtime contract (Replit, healthcheck, logging) |
| `version_lineage.json` | 273 | payload/kernel/repo/model version pins |
| `secrets_status.json` | 267 | secrets audit — required/optional/missing |

## How to verify

Every deliverable in `run_manifest.json` carries an `sha` value computed by the kernel at write-time using the kernel's canonicalization (sorted-key JSON, normalized newlines). The replay harness re-derives those hashes from a fresh deterministic run and compares.

Naive `md5sum` of the on-disk JSON will **not** match the manifest `sha` because the on-disk files are pretty-printed for human reading. To reproduce the manifest hashes, use the kernel's canonicalizer (sorted-key JSON, normalized newlines) as implemented in the platform repo's eval-runner (`apps/eval-runner/run.py`).

The authoritative trust signals are the **top-level hashes** in `run_summary.json` and `run_identity.json`:
- `payload_hash`: `624332a9470f8509fcfb57c6c39ac8dc`
- `manifest_hash`: `b977a47f69b7ba0d038c86271c85d234`
- `final_state_hash`: `fe20ecc47445dbd887b5b14ef26ed981`
- `ledger_digest`: `4d0a943cef5b8fa605919db38df5e8e7`

A full replay should reproduce all four byte-for-byte.

## Replay

The deterministic kernel can be re-run from the same `payload_hash`. Replays produce byte-identical artifacts (modulo `resolved_at` timestamp). See the platform repo's `apps/eval-runner/` for the harness.

## License

Run artifacts: CC BY 4.0.

## Related

- **Runtime**: [szl-holdings/ouroboros](https://github.com/szl-holdings/ouroboros) — the bounded-loop substrate that emits these receipts (Apache-2.0, 218/218 tests verified 2026-05-12)
- **Proofs**: [szl-holdings/lutar-lean](https://github.com/szl-holdings/lutar-lean) — Lean 4 + Mathlib formal proofs of the Λ invariant uniqueness theorem (the kernel is the referee)
- **Platform**: [szl-holdings/platform](https://github.com/szl-holdings/platform) (private) — 1,220 tests across 76 packages, MCP gateway 27/27 e2e, dual-witness diversity, reference-vector parity
- **Cookbook**: [szl-holdings/szl-cookbook](https://github.com/szl-holdings/szl-cookbook) — 9 engineering skills (Anthropic skills pattern)
- **Thesis**: [szl-holdings/ouroboros-thesis](https://github.com/szl-holdings/ouroboros-thesis) — v1→v11 published (concept DOI [10.5281/zenodo.19944926](https://doi.org/10.5281/zenodo.19944926)), v12 in review ([#25](https://github.com/szl-holdings/ouroboros-thesis/pull/25)), v13 in writing
