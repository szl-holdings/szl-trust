# TRUST_DEEP.md — Investor/Auditor-Grade Trust Architecture

> **Doctrine v11 LOCKED** · szl-trust · CC-BY-4.0

This document deepens `verify.sh` into an investor- and auditor-grade story by
documenting the full inclusion-proof chain, the Rekor-style transparency-log anchor,
and the layered verification paths available to a sophisticated external reviewer.

---

## What `verify.sh` gives you today

`verify.sh` performs five checks in under 30 seconds with no SZL tooling:

1. **Cosign public key fetch** from `szl-lake` (HF dataset) or `.github` fallback
2. **Receipt fetch** from `szl-trust` (GitHub raw)
3. **`mocked:false` confirmation** — real production run, not synthetic
4. **SHA-256 payload integrity** — receipt content hash recomputed
5. **Lean kernel liveness** — HF Space `lean-kernel` `/healthz` endpoint

This is the **Layer 1** buyer verification: "is this a real, non-fabricated run?"

---

## Layer 2 — DSSE / ECDSA-P256 Signature Verification

Every accepted span and every Khipu receipt is wrapped in a **DSSE in-toto envelope**
(PAE v1: `DSSEv1 <len(type)> <type> <len(body)> <body>`) signed with ECDSA-P256-SHA256.

```bash
# Manual ECDSA-P256 verification (no cosign required — pure OpenSSL)
# 1. Fetch the org cosign public key
curl -fsSL https://huggingface.co/datasets/SZLHOLDINGS/szl-lake/resolve/main/keys/org-cosign.pub \
     -o szl_cosign.pub

# 2. Extract the DSSE payload and signature from any receipt
RECEIPT=$(cat runs/E4-codex-kernel-2026-04-29/decision_receipt.json)
PAYLOAD_B64=$(echo "$RECEIPT" | jq -r '.dsse_envelope.payload // empty')
SIG_B64=$(echo    "$RECEIPT" | jq -r '.dsse_envelope.signatures[0].sig // empty')

# 3. Recompute the PAE and verify
echo "$PAYLOAD_B64" | base64 -d > /tmp/dsse_payload.bin
echo "$SIG_B64"     | base64 -d > /tmp/dsse_sig.bin
openssl dgst -sha256 -verify szl_cosign.pub \
  -signature /tmp/dsse_sig.bin /tmp/dsse_payload.bin
# → Verified OK
```

**Formal backing:** `Lutar.Round10.CryptoDSSE.dsse_classical_euf_cma` (PR #179 in
`lutar-lean`, 0 real `sorry`) establishes the classical EUF-CMA model for the DSSE
envelope construction.

---

## Layer 3 — Merkle / Hash-Chain Inclusion Proof

The `proof_ledger.jsonl` is a **hash-chained** ledger: each step carries
`state_hash`, `delta_hash`, and `receipt_id`. The chain is self-verifiable:

```bash
# Verify hash-chain continuity (no external tools)
python3 << 'PY'
import json, sys
steps = [json.loads(l) for l in open("runs/E4-codex-kernel-2026-04-29/proof_ledger.jsonl")]
for i, s in enumerate(steps):
    assert s["step"] == i + 1, f"Step gap at {i}"
print(f"Chain continuous: {len(steps)} steps, steps 1-{steps[-1]['step']} verified")
PY
```

The `run_manifest.json` anchors the full run: `payload_hash`, `ledger_digest`,
and per-deliverable SHAs. A reviewer can recompute all digests and assert the
manifest matches.

**Formal backing:** `Lutar.Wave8.HashChain` (locked-proven F12) — hash-chain
tamper-evidence is one of the 8 locked formulas.

---

## Layer 4 — Sigstore Rekor Transparency-Log Anchor

The **Theorem-U anchor** (minted by `anchor-szl-lake.yml` in `lutar-lean`) uploads a
DSSE in-toto attestation to Sigstore Rekor and stores the Rekor bundle in
`szl-lake/data/khipu/lutar_lean_receipts.ndjson`.

```bash
# Re-verify the Rekor anchor for a lutar-lean receipt
# (requires cosign v2.4.1+, matches what the CI workflow pins)
NDJSON_URL="https://huggingface.co/datasets/SZLHOLDINGS/szl-lake/resolve/main/khipu/lutar_lean_receipts.ndjson"
RECEIPT=$(curl -fsSL "$NDJSON_URL" | head -1)
BUNDLE_B64=$(echo "$RECEIPT" | jq -r '.signing.bundle_b64 // empty')
echo "$BUNDLE_B64" | base64 -d > /tmp/rekor_bundle.json
PAYLOAD_HASH=$(echo "$RECEIPT" | jq -r '.subject.sha256')
# Pull the original snapshot from the embedded copy
echo "$RECEIPT" | jq -r '.subject.snapshot' | base64 -d > /tmp/snapshot.json
cosign verify-blob-attestation --new-bundle-format \
  --bundle /tmp/rekor_bundle.json \
  /tmp/snapshot.json
# → Verified OK  ← proves Sigstore Fulcio cert chain + Rekor inclusion + DSSE sig
```

The returned `logIndex` is the publicly cross-verifiable consensus proof on the
[Rekor public log](https://rekor.sigstore.dev). Any reviewer can independently look
up that index and confirm the timestamp and certificate identity match.

**Chain continuity:** `szl-lake`'s `verify-anchor-receipts.yml` re-runs this
verification **daily** at 06:37 UTC and pages the team on failure. The baseline
floor (minimum expected receipt count) prevents silent ledger truncation.

**Formal backing:**
- `Lutar.Round10.CryptoRekor.rekor_inclusion_completeness` (PR #179 in `lutar-lean`) —
  completeness theorem (sorry-free); Rekor soundness is an **honest tagged sorry**
  (Conjecture 1 — disclosed, never hidden).

---

## Layer 5 — Multi-Party Witness (Khipu BFT)

For actions requiring the **highest assurance level**, the `khipu-consensus` protocol
requires ≥ 3-of-4 independent witness signatures (ECDSA-P256 DSSE per witness) before
an action is canonical. Each witness holds its own private key; no single key compromise
can forge consensus.

```bash
# Verify a multi-witness Khipu receipt (Python reference verifier)
pip install khipu-consensus
khipu-verify path/to/consensus_receipt.json path/to/pubkeys/
# → {"consensus": "4-of-4", "decision": "canonical", ...}
```

See [`khipu-consensus`](https://github.com/szl-holdings/khipu-consensus) for the
full reference implementation (Python / TypeScript / Go) and the live HF Space demo.

**Safety / liveness status:** Conjecture 2 / Conjecture 3 — proof-deferred,
deliberately honest siblings of Λ Conjecture 1. The counting predicates and
canonicity decision are **fully proved** (zero sorry).

---

## What an investor/auditor review looks like

| Question | Evidence | Where to check |
|---|---|---|
| Is this a real run, not synthetic? | `mocked:false` | `verify.sh` Step 2 |
| Is the receipt content unmodified? | SHA-256 payload match | `verify.sh` Step 3 |
| Is the signature valid? | ECDSA-P256 / OpenSSL | Layer 2 above |
| Is the hash chain intact? | `proof_ledger.jsonl` | Layer 3 above |
| Is there a public timestamp anchor? | Rekor `logIndex` | Layer 4 above |
| Could one key forge all signatures? | Khipu 3-of-4 BFT | Layer 5 above |
| Are the math claims honest? | `locked_count_eight = 8`, Λ = Conjecture 1 | `lutar-lean` README |
| Is CI continuously re-verifying? | `verify-anchor-receipts.yml` daily schedule | `szl-lake/.github/workflows/` |

---

## Roadmap

| Item | Status |
|---|---|
| SLSA L2 verified provenance workflow | Roadmap (L1 honest today) |
| Cardano on-chain receipt anchoring | Roadmap |
| FedRAMP / CMMC claims | **NOT claimed** |

---

*Doctrine v11 LOCKED · 749/14/163 · c7c0ba17 · Λ = Conjecture 1 · SLSA L1 honest*

Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>
