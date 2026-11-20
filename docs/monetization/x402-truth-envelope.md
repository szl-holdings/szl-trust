# SZL x402 Commerce Truth Envelope — closed-world mathematics, open-world honesty

**Status:** Source-tested analytical primitive. **Not connected to live payment
providers; not a billing system, settlement verifier, accounting system or
production deployment.** No API credentials, wallet, paid canary or paid job is
needed to run it.

**Canonical source:** `scripts/x402_truth_envelope.py`; tests
`tests/test_x402_truth_envelope.py`. This complements, but does not modify,
`scripts/x402_usage_ledger.py` and the distinct
`ops/revenue-tracker-worker` (whose origin settlement measurements are not
independently chain-confirmed). No existing operator or controller is replaced.

## Research question

What can be *proved about the shape of uncertainty* when an x402 event collector
sees only some requests and payment stages, **without inventing conversion,
completed settlement, or revenue**?

A common mistake is `402 count = paid conversions`, or to treat an origin's
`PAYMENT-SETTLEMENT` report as finalized payment. This tool instead returns
two orthogonal axes:

1. **Structural coverage:** known population N (possibly unknown), observed
   distinct request pseudonyms O, and unknown N-O. An absent denominator is
   **unavailable**, not zero.
2. **Economic finality:** request final phase is source reported; no input
   SHA-256 or receipt file hash is a digital signature or chain confirmation.
   `financial_revenue_verified_atomic` therefore stays `null` regardless of
   the value reported by the source.

The result contains rational intervals **conditional on the supplied records
being truthful, denoting one claimed network/asset, and representing at most one final observed state per request**.
These intervals are *not* verified payment rates or forecasts.

## Safe input: `szl.x402-truth-envelope/v1`

Input is bounded to 2 MB and 20,000 records. A request key MUST be a stable,
private, 64-hex **HMAC** over the original request identifier using a protected
operator-held key; raw IDs, headers, payers, signatures, JWTs and PII are
refused by the exact allowlist and never returned. Do **not** generate it as a
bare SHA-256 of a low-entropy customer identifier.

The strictly admitted top-level fields are:

| Field | Meaning |
|---|---|
| `schema` | Exactly `szl.x402-truth-envelope/v1` |
| `source_revision` | Full immutable 40/64-hex Git SHA supplied by operator; not authenticated by this tool |
| `provider_export_sha256` | Raw provider-export digest (64 lowercase hex); bytes and signature must be validated outside |
| `observed_at_utc` | Source-declared observation cutoff, explicit `Z`; does not prove a live or authenticated export |
| `population_count` | Declared count of distinct cohort requests (integer or `null` if unknown) |
| `unobserved_cap_atomic` | Known per-request maximum for unobserved requests (integer or `null` if unknown) |
| `denomination` | Exactly `network_caip2`, `asset_id`, `asset_decimals`. A single declared network/asset per cohort; no cross-asset summation or automatic fiat conversion. |
| `records` | Sanitized one-final-state-per-request rows, no duplicates |

Every record contains *exactly* `request_hmac_sha256`, `phase`,
`authorized_cap_atomic`, `reported_settlement_atomic`, and
`provider_receipt_sha256`. An amount and receipt digest are required for
`SETTLEMENT_REPORTED` and `REFUNDED`; they are forbidden for other phases.
Amount and cap are nonnegative integer atomic units; no float conversions.

Phases: `CHALLENGED`, `AUTHORIZED`, `PRODUCED`,
`SETTLEMENT_PENDING`, `SETTLEMENT_REPORTED`, `DISPUTED`,
`REFUNDED`, `FAILED`, `CANCELLED`. The tool does not assert that
missing earlier phases occurred or that a state machine transition was valid.
Those require event-level provenance and the governed ledger.

## Source snapshot clock and freshness boundary

A structurally valid, signed-looking digest is **not** evidence that the
Cloudflare, facilitator or on-chain state is current. The offline result
includes the source-declared `observed_at_utc` and an explicitly
observer-relative `source_snapshot_age_seconds`, classified as:

- `RECENT_TIMESTAMP_ONLY_NOT_AUTHENTICATED`: timestamp no more than
  24 hours before the observing clock. No provider signature, payment
  finality, or production status is conferred.
- `HISTORICAL_SOURCE_TIMESTAMP`: more than 24 hours old. Conditional
  arithmetic remains available for retrospective analysis, but the report
  adds `HISTORICAL_SOURCE_EXPORT_REQUIRES_CURRENT_READBACK` and marks
  `source_snapshot_stale_for_current_claims=true`.
- `CLOCK_SKEW_TOLERATED_NOT_AUTHENTICATED`: supplied observation is
  ahead of the observing clock by at most five minutes. The clock-skew
  condition is explicit; it is **not** a freshness pass.
- More than five minutes in the future: `SOURCE_OBSERVATION_IN_FUTURE`
  hard HOLD before any source-reported amount is returned.

`current_provider_state_verified` and
`observed_at_verified_by_provider` always remain `false` in this
v1 offline tool. Time-window classification has no authority to
confirm a settlement, prove a revenue conversion, reconcile refunds or
authorize payment initiation. A deterministic UTC reference clock may be
passed to the Python API for synthetic tests; normal CLI execution uses
the observing system's clock, which itself is not independently attested.

## Interval law (conservative, exact integer arithmetic)

Let **S** be the count of source-reported settlements; **A** the sum of their
reported atomic amounts; **U** all unresolved observed requests (challenged,
authorized, produced, pending, disputed) with individual authorized caps
`c_i`; **M=N-O** the number of unobserved requests, only when N is known;
and **C** the maximum charge for any unobserved request, if known.

Conditional eventual settlement count lies in:
`[S, S + U + M]`. Conditional source-reported gross value lies in:
`[A, A + sum(c_i) + M*C]`.
If N is unknown, count/rate upper and revenue upper are `null`. If C is
unknown and M>0, the value upper is `null`. The rate interval uses exact
fractions over N and is `null` when N=0 or unknown. `FAILED`,
`CANCELLED`, and `REFUNDED` are not sources of reported net revenue.
`DISPUTED` is uncertain, not confirmed revenue.

**These are mathematical constraints under supplied assumptions, not a claim
that revenue was actually earned, recognized, settled, refunded or recovered.**
The tool does not infer a token/network/fiat currency, merchant fees, tax,
partial refunds, chain finality, receipt signer, sampled event weighting or
merchant payouts. The `denomination` fields are validated for shape only:
network identity, token contract and decimals are not authenticated. It intentionally produces `financial_revenue_verified_atomic:
null`. A source-provided `SETTLEMENT_REPORTED` amount is *not* recognized
revenue.

## Synthetic example (never a live assertion)

Four declared cohort requests; three observed: one source-reported settlement
for 30 atomic units, one pending with authorization cap 80, one failed. The
unobserved request has a declared cap of 100. Conditional count `[1,3]`,
conditional exact rate `[1/4,3/4]`, conditional gross `[30,210]`.
**Independently verified revenue remains unavailable.** All numbers are
fictional test fixtures.

## Local use and integration gates

Feed one sanitized JSON snapshot on standard input:

```sh
python3 scripts/x402_truth_envelope.py < docs/monetization/fixtures/x402-truth-envelope.synthetic.json
python3 -m unittest discover -s tests -p 'test_x402_truth_envelope.py' -v
python3 -m unittest discover -s tests -p 'test_x402_usage_ledger.py' -v
```

The CLI emits only aggregated counts, SHA-256 bindings and stable reason codes;
invalid data exits 2 with `{"status":"HOLD","reason":...}` and never echoes
raw input. This is strictly offline and side-effect free; the caller must
supply an authoritative cohort definition and provenance separately.

To qualify future real commerce:

1. Freeze an **authenticated**, revision-bound, rights-cleared provider export.
   The SHA-256 here binds bytes, **not** the provider's identity.
2. Reconcile request sampling, cohort inclusion and missing events across
   Cloudflare Analytics, origin attestation and provider settlement outputs.
3. Verify Cloudflare-signed `PAYMENT-CONTEXT` at origin and separately
   retrieve a legitimate confirmed `PAYMENT-RESPONSE`, facilitator/on-chain
   evidence, refunds, disputes, and merchant settlement payout reconciliation.
4. Prove runtime/source/release identity and publish only sanitized, reviewed
   aggregate receipts through the existing source owner.
5. Maintain `CHALLENGED`, `AUTHORIZED`, `SETTLEMENT_REPORTED`,
   `SETTLED_INDEPENDENTLY_VERIFIED`, and `REVENUE_RECONCILED` as
   **distinct** claims. This v1 tool does **not** implement the last two.

This deliberately avoids creating a new scraper, persistent watcher, wallet
client, billing writer, Cloudflare route or public revenue claim.

### Standards read before implementation

- https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md
- https://developers.cloudflare.com/monetization-gateway/x402/
- https://developers.cloudflare.com/monetization-gateway/

Last reviewed: November 20, 2026. Protocol changes require a new reviewed
contract and negative tests, not silently weakening an admission rule.
