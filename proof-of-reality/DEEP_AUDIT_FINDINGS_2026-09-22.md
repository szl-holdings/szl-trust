# SZL Deep Audit Findings — 22 September 2026

Status: **working, source-backed audit memo**. This document distinguishes read source, inventory-only metadata, and unresolved gaps. It is not a production certification, a safety certification, or a claim of complete every-file review.

## Executive finding

SZL does not lack an Authority Switch. It contains a **distributed authority lattice** across the Council kernel, IMMUNE, ORO, governed-action receipts, Khipu evidence, HUKLLA tripwires, and the invariant skeleton. The work remaining is to canonicalise their contracts, pin their epochs, prohibit semantic type coercion, and produce one independently verifiable authority receipt.

## Evidence read

- GitHub public estate: 125 repositories inventoried; active/archived/canonical-successor state captured.
- Hugging Face estate: 49 models, 43 datasets, 27 Spaces inventoried.
- Source/card material read: A11oy runtime card; Formula Registry; Lambda kernel source; szl-blocked; szl-ouroboros; szl-invariants; Codex composer; Second Brain; SZL Lake; triage card/gate report; governed-agent-bench; model BOM; thesis v18 card; Lean proof card; doctrine card; public sites.
- Limitation: GitHub connector did not return contents of all repository files. Thesis lineage and v19-v24 source remain NOT_YET_READ directly.

## Authority lattice

```text
Models / advisers       -> submit assessments only
Second Brain            -> retrieve public or approved evidence handles only
Forge                   -> builds, measures, packages, holds, or promotes artifacts
Hub                     -> distributes artifacts/evidence; no authority implied
Lambda / PURIQ          -> advisory ranking and constraints; no authority implied
Council                 -> mandate, capability, target, budget, roles, vetoes
IMMUNE                  -> request-bound assertion + keyed commitment boundary
HUKLLA                  -> halt/tripwire boundary
Khipu / YAWAR           -> receipt and ledger evidence
Egress                  -> scoped effect only after all required controls survive
```

### Existing enforcement points

1. **Council kernel.** `CouncilKernel` compiles committed adviser assessments into one bounded decision. Authority checks mandate, capability, target, and budget. Sentinel and Verifier may issue categorical vetoes. Commitment/reveal digest equality is checked.
2. **IMMUNE.** Tool requests use `verifyAuthority`; the mode is `HMAC_BOUND_ONE_TIME_ASSERTION`. A missing/invalid authority key returns UNAVAILABLE. Tool requests otherwise ALLOW/REVIEW are forced to UNAVAILABLE if authority is not VERIFIED or keyed commitments are not READY.
3. **GovernedAction receipt.** The Round-10 receipt writer rejects authority that was not `evaluated_before_execution`; post-hoc logs are explicitly not governance. Side effect classes are READ_ONLY, REVERSIBLE, IRREVERSIBLE, EXTERNALLY_VISIBLE. Irreversible ALLOW/EXECUTED requires approval.
4. **ORO.** Governed write requests have a bearer authorization boundary; ephemeral signing is rejected as production authority.
5. **Invariants.** Eight falsifiable receipt/ledger checks use HOLDS, VIOLATED, KEY_ROTATED, NO_DATA, and UNAVAILABLE as first-class outcomes.

## Formula taxonomy

The canonical registry has 21 typed pure functions. They are not one universal trust scale.

| Type | Examples | Authority rule |
|---|---|---|
| Advisory aggregation | Lambda, Schur witness | May summarise deliberately measured Yuyay values; never authorise |
| Statistical bounds | PAC-Bayes, Hoeffding, Pinsker, Fisher-Rao | Bound risk/divergence; do not convert silently to trust |
| Integrity primitives | Khipu Merkle root, DSSE, Reed-Solomon, CSS ingress | Identify/verify structure; no quality score |
| Domain/reference mathematics | Bekenstein helper, Gleason, KS-18, Bohr, Madhava, Reidemeister | Typed domain calculation; no generic governance score |

### Lambda

Canonical Lambda is the weighted geometric mean:

    Lambda_w(x) = product_i x_i^w_i, sum_i w_i = 1, w_i > 0, x_i in [0,1]

The canonical 13-axis Yuyay vector has:

- moralGrounding, measurabilityHonesty: floor 0.95
- empiricalGrounding, logicalConsistency, sourceTransparency, reproducibility, licenseHygiene, scopeDiscipline, claimCalibration: floor 0.90
- evalAwareness, deceptionKeywords, conflictingDirectives, reversalDirective: floor 0.90

Lambda is ADVISORY. It is not proven trust. Unconditional uniqueness is Conjecture 1 and is reported false as stated; Theorem U is REAL-conditional and excluded from the locked-proven baseline.

### Prohibited semantic coercion

The current Codex composer maps arbitrary formula outputs into a scalar and feeds that scalar into Lambda. This must not appear in any authority path:

- a Merkle-root byte string maps to a hash-derived pseudo-random scalar;
- a DSSE placeholder envelope maps to 1.0 because it is a dictionary;
- a successfully computed Reed-Solomon parameter maps to 1.0;
- the composer aggregate floor is 0.5, below every canonical Yuyay per-axis floor.

**Recommendation:** only explicitly measured Yuyay axes may enter Lambda. Hashes, signatures, code parameters, structural outputs, and statistical bounds must remain typed evidence claims.

## Ouroboros

Ouroboros is a bounded-loop trace and loop-tax kernel, not a model. It labels:

- modelMs and peakAttemptMs: MEASURED
- overheadMs, serializationTaxMs, deadHopMs: DERIVED
- overheadMs when wall time absent: UNAVAILABLE

`serializationTaxMs` is a counterfactual, never a realized saving.

**Finding:** a meaningful bound requires a maximum budget committed before execution. If `max_budget` defaults to attempts already taken, a long loop can report withinBudget after the fact. Authority receipts must carry an immutable pre-execution maximum budget.

## Invariants

I1 receipt-chain-continuity
I2 ledger-failure-shape
I3 served-run-has-model
I4 signed-columns-atomic
I5 loop-steps-positive
I6 receipt-ed25519-verify
I7 receipt-columns-consistent
I8 flywheel-lineage

A check that cannot fail is excluded as verification theater. The invariant kernel does not prove model-answer correctness and does not upgrade Lambda.

## Receipt verification replay

The public org-cosign ECDSA P-256 key verified 14 of 14 published amaru DSSE PAE digests. All 14 predicted_hash -> actual_hash links were continuous. A one-bit digest change was rejected.

This proves a signature relationship over the published PAE digests and a hash-link relationship. It does not prove decision correctness, full receipt payload integrity, or authority to act.

Sentra receipts are flagged dsse_signed but the published NDJSON rows contain no dsse_sig or dsse_pae_sha256, and index 1 has no previous actual hash. The Proof-of-Reality verifier records this as DIVERGENT, not PASS.

## Triage case

The public gate report has 66 rows, 66 label matches, 23 gold REVIEW/refusal cases, 23 preserved REVIEW/refusal cases, zero false labels on refusal, zero ungrounded spans, and behavioral verdict PROMOTABLE.

The public model card nevertheless says NOT PROMOTABLE because the contamination/corpus-leakage review did not clear. Publication is for inspection and reproducibility only. This is the correct negative case: behavioral evidence does not override contamination.

Any prior draft claiming this run failed refusal preservation is superseded by the artifact card and gate report.

## Version and epoch separation

Do not collapse these states:

- Locked v11 baseline c7c0ba17: 749 declarations / 14 unique axioms / 163 tracked sorries / locked eight formulas.
- Later Theorem-U anchors: 1323 declarations / 22 unique axioms / 254 non-comment sorries. Theorem U is REAL-conditional, not part of the locked baseline.
- HUKLLA v11: T01-T10 baseline.
- Later T23/T24 coherence/reciprocity additions: later doctrine/implementation, not automatically v11 baseline.
- Ayllu Huklla H: MODELED graph-cut metric; not HUKLLA halt authority and not IIT Phi.

## Publication recommendation

1. Correct the triage technical note to state contamination, not refusal regression, as the blocker.
2. Do not deposit the earlier synthetic 11-page preprint as empirical evidence.
3. Use the next flagship paper as an audit/unification paper:

   The Heart of a Governed AI System: Auditing a Distributed Authority Lattice Across Models, Evidence, Invariants, and Systems of Record.

4. Do not claim an unbuilt Authority Switch. Audit the existing lattice and specify the canonical authority receipt needed to join its existing controls.
5. Before a flagship DOI: read thesis v19-v24 source locally, standardise source epochs, repair inventory drift, publish signature material for every claimed signed receipt, and have an independent third party run Proof-of-Reality.
