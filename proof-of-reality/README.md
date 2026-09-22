# SZL Proof-of-Reality

An independent verifier for the public SZL Holdings estate, written for someone who does not
trust SZL Holdings. It downloads only public artifacts, recomputes what can be recomputed, and
reports one of four states per check:

| State | Meaning |
|---|---|
| **PASS** | Reproduced from public artifacts |
| **FAIL** | Checked, and false |
| **DIVERGENT** | Ran; the measured value differs from the published one, or the published evidence is incomplete |
| **UNAVAILABLE** | Could not run here. Never counted as PASS |

## Run it

```powershell
python -m pip install cryptography
python verify_all.py                   # checks 2, 4, 5, 6 - network only, no GPU
python verify_all.py --with-lean       # + check 1 (git; lake optional)
python verify_all.py --with-kernels    # + check 3 (pip install torch kernels; executes SZL-published code)
```

Output: `report/proof_of_reality.json` and `.md`. The JSON's SHA-256 is printed so the result can be
cited. Exit code 1 if any check is FAIL.

## The six checks

| # | Claim tested | How |
|---|---|---|
| 1 | Lean library at `c7c0ba17`: 749 declarations, 14 axioms, 163 tracked sorries | Clones `lutar-lean`, counts `sorry` and `axiom` lexically with comments stripped, runs `lake build` if present. A lexical count that differs from the tracked 163 reports DIVERGENT, not FAIL. |
| 2 | Khipu receipts are signed and hash-linked | Downloads `szl-lake` keys and receipts; checks key fingerprints against `keys/MANIFEST.json` (SHA-256 of the stripped PEM); verifies each ECDSA-P256 signature over the published SHA-256 of the DSSE PAE; checks `predicted_hash` equals the previous `actual_hash`. |
| 3 | `szl-blocked` never runs a denied call; one failing axis drives the aggregate to 0; the aggregate is advisory | Loads both kernels from the Hub and exercises them. |
| 4 | Triage adapter: the behavioural gate report is self-consistent and the release is held on contamination | Recomputes the gate report from its own 66 rows, hashes the adapter, reads the card's release decision. |
| 5 | Second Brain public lane: 575 chunks, each hash-bound, with the published fingerprint | Recomputes every chunk hash and tries the documented fingerprint construction. |
| 6 | Public inventory matches the Model BOM | Counts public Hub models, datasets, Spaces and GitHub repositories live. |

## What this proves and what it does not

- A PASS on check 2 proves the holder of the org key signed those digests. It does not prove the
  decision in a receipt was correct, and `receipt_id` cannot be recomputed because full payloads are
  not published.
- Check 4 does not re-run inference; the frozen evaluation rows and a GPU are needed for that, and the
  check says so.
- Check 1 counts tokens. It does not certify which theorems are proved; `lake build` succeeding and the
  locked-eight declarations being `sorry`-free is the stronger test.
- Nothing here authorises any agent to act on any system. That is a separate decision.

## Findings from the author's offline replay (22 September 2026)

- Two amaru receipts verified cryptographically under `keys/org-cosign.pub`: genuine ECDSA-P256.
- Manifest fingerprints are SHA-256 of the stripped PEM text; the amaru fingerprint matches.
- The two sentra receipts are flagged `dsse_signed: true` but carry no `dsse_sig` or `dsse_pae_sha256`,
  and index 1 does not link to index 0. Expect check 2 to report DIVERGENT until that signature
  material is published.
- The triage gate report shows 66 of 66 labels correct, 23 gold refusals, 23 preserved, and 0 false
  labels on refusal. Refusal behaviour was preserved; the release is held on contamination.

## Next step

Ask one person outside SZL Holdings to run this, sign the resulting JSON, and publish it beside your
own run. One independent run is worth more than every card.
