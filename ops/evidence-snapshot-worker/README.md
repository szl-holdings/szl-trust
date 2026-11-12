# SZL evidence snapshot Worker

> **Offered in source (`OFFERED = true`). Owner decision (2026-11-12): `api.a-11-oy.com` hosts the route; the apex stays free.** Owner policy (2026-11-06):
> charge API and MCP hosts only; websites (including `a-11-oy.com`), pricing,
> the proof site, health and well-known paths stay free. The approved payTo and
> exact Gateway rule `8f6c7d526b7c4a42a1075671898474b9` are recorded in the
> activation record. Re-enable that rule after merge and Worker redeploy. The
> origin does not return HTTP 402 or an x402 `accepts` list; Cloudflare issues
> the 402 when the rule is enabled. See
> [the activation record](../../docs/monetization/evidence-snapshot-activation-2026-11-02.md).

This Worker source describes one bounded route:

`GET https://api.a-11-oy.com/v1/evidence-snapshot` (owner decision made 2026-11-12: api.a-11-oy.com)

The route is offered in source. `OFFERED` is true, and a request to that exact
URL without a valid `PAYMENT-CONTEXT` returns `403` with `state`
`PAYMENT_CONTEXT_ABSENT`. The origin does not return a payment requirement.
The handler fails closed unless Cloudflare Monetization Gateway supplies a
valid Ed25519 `PAYMENT-CONTEXT` JWT for the exact audience and the fixed
`$1.00` amount (`1,000,000` atomic units). The paid response is a deterministic
manifest of ten public, revision-pinned SZL Trust artifacts. It does not
serve private content, execute models, or claim that the cited receipts are
scientifically or commercially valid.

The configured Worker route is exact; deployment and Gateway routing must still
be checked for noninterference with the rest of `a-11-oy.com`.
The API-only proposal excludes `a11oy.net`; its live billing state must be
verified separately, not assumed to be free.

## Static pilot, attribution, and processing scope

This is a technical pilot, not the model-inference product and not an income
claim. Buyers receive the same historical E4 April 2026 manifest of ten public
GitHub links and Git blob hashes, not the artifact contents, new model output,
live monitoring, a fresh replay, or a scientific evaluation. The manifest version
dates the metadata, not the historical run. Its deterministic SHA256 is unsigned
and is neither a purchase receipt nor evidence of current deployment health,
operational readiness or payment settlement. Historical health, approval and
secret-status declarations in the linked artifacts are not current observations.

The response attributes SZL Holdings and links CC-BY-4.0, the revision-pinned
repository LICENSE and NOTICE. It identifies the manifest-only transformation;
historical files remain unchanged. Preserve attribution, applicable notices and
change disclosures when redistributing. CC-BY-4.0 does not grant trademark rights
or imply endorsement; public availability does not establish exclusive rights.

`bounds.operation` describes application-state access, not an absence of all
effects. Payment verification may fetch the pinned public certificate endpoint.
The Worker logs success/rejection events without logging the payment token;
configured provider observability can process request metadata. The public
manifest contains no private source content, but payment headers are processed
by the Worker and providers. Provider retention, billing and settlement behavior
are outside the manifest; these bounds are not a no-personal-data/no-cost promise.
The existing bounds keys remain strings, but their values are now scoped prose;
the metadata version and deterministic digest change accordingly.

## Payment verification and key freshness

Verification is delegated to `src/payment-context.mjs`, the Workers-runtime
`PAYMENT-CONTEXT` validator. Its Python twin is `scripts/x402_payment_context.py`
at the repository root. Both run the shared vectors in
`tests/vectors/x402-payment-context.v1.json` (here: `test/vectors.test.mjs`)
and must return the same decision and reason code for each one.

The verifier accepts only EdDSA JWTs backed by **Ed25519** public keys from
`https://payments.cloudflare.com/certs`. Redirects and token-supplied key
locations/material (`jku`, `x5u`, `jwk`, `x5c`) are rejected, as are `crit` and
`b64` headers and non-canonical base64url. The exact scalar audience, scheme
`exact` and string amount `1000000` are required: a context signed for any
other amount, such as a cheaper rule's, is rejected (`AMOUNT_MISMATCH`). Integer
`iat`, `nbf` and `exp` claims are required, and `iat` and `nbf` may not be after
`exp`. `nbf`, `exp` and a future `iat` get a five-second leeway (the shared
module accepts 0-30 seconds). No payment TTL is imposed.

Cloudflare's documented claims define no `jti` or nonce. The shared module has
an optional replay guard keyed on the token's SHA-256, but it lives in one
isolate's memory, which is not a guard across Workers isolates, so this Worker
does not enable it. No `PAYMENT-SETTLEMENT` header is issued by this Worker.
A rejection is logged with its stable reason code only, never the token.

Each Worker instance coalesces concurrent certificate retrievals. Cached keys
are reused only for the endpoint's explicit HTTP `max-age`, reduced by `Age`,
request elapsed time, and apparent age from `Date`. `no-cache`, `no-store`,
absent/invalid freshness, or exhausted freshness prevents reuse on a subsequent
request. A new retrieval may verify the current group of waiting requests but
never falls back to expired keys if retrieval fails. Unknown key IDs do not
trigger extra retrievals while the cache is fresh. Retrieval has a five-second
deadline (including the body), a 64 KiB body limit, and a 32-key limit; malformed
or unsuccessful responses fail closed.

## Validate

```shell
npm ci
npm run check
```

For local-only verification without a Wrangler dry run, use `npm test`.
The tests use ephemeral in-memory signing keys, the shared vectors' test-only
keys, fake fetch responses and an injected clock: no external network requests,
real credentials, wallet keys, or purchases. They cover real signature
verification, claim rejection (including cheaper-rule amounts), route guards,
freshness, rotation, errors, size/deadline limits, concurrent fetches and log
contents.
Fetch/clock injection is a module-level testing seam only; there are no
deployment settings to override the pinned certificate URL or trust policy.

## Deploy sequence

0. Owner decision on the API host: done (2026-11-12). The Worker `AUDIENCE`
   and route, `EVIDENCE_SNAPSHOT_AUDIENCE` in `scripts/x402_payment_context.py`,
   and the activation record name `https://api.a-11-oy.com/v1/evidence-snapshot`
   (`tests/test_x402_price_alignment.py` checks them). The SKU is offered in
   source. Exact Gateway rule `8f6c7d526b7c4a42a1075671898474b9` already exists
   and is disabled. The origin does not return HTTP 402; Cloudflare does when
   the rule is enabled.
1. Review and merge the source change.
2. Deploy the Worker with the pinned Wrangler version.
3. Verify the direct origin fails closed without `PAYMENT-CONTEXT`.
4. Re-enable Cloudflare Monetization Gateway rule `8f6c7d52` for the exact GET path.
5. Verify an unpaid request receives Cloudflare's `402` and decoded payment
   requirements show `$1.00` and the approved receiving wallet.
6. Run one controlled paid canary and reconcile settlement before promotion.

Do not create a domain-wide, `/api/*`, or MCP-wide payment rule.
