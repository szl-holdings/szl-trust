# SZL revenue tracker Worker

`szl-revenue-tracker` is a transparent pass-through Worker that records x402
payment events to a Workers Analytics Engine dataset. It counts a payment only
when it can check the payment itself:

| Event (`index1`) | Recorded when | Amount counted |
|---|---|---|
| `payment_authorized` | the request carries a `PAYMENT-CONTEXT` JWT that verifies against the pinned Cloudflare JWKS (Ed25519 only), with `aud` equal to this request's exact origin + path, `exp`/`nbf` enforced (5 s tolerance), integer `iat`/`nbf`/`exp`, `scheme` `exact` or `upto`, and a canonical `amount` within $0.001-$100 | the signed `amount` (for `upto`, the authorized maximum) |
| `settlement_reported` | the origin's *response* carries `PAYMENT-SETTLEMENT: {"amount":"<atomic>"}` for a verified `upto` authorization with status < 400 | the reported amount, capped at the authorized maximum (as the gateway does) |
| `payment_context_rejected` | a `PAYMENT-CONTEXT` is present but fails any check | 0, with a reason code |
| `settlement_ignored` | an origin settlement the gateway would not honour (`exact` pricing, status >= 400, malformed value, no or unverified context) | 0, with a reason code |

It **never** reads client-supplied state such as `x-payment-verified`,
`x-payment-required`, `cf-bot`, or a request-side `PAYMENT-SETTLEMENT`. The
stub this replaces (deployed 2026-11-05, no source in GitHub) marked revenue
"captured" whenever a client sent `x-payment-verified`, had no Analytics Engine
binding, and logged client-supplied user agents.

The request and the origin response pass through unchanged (including
`PAYMENT-CONTEXT` for the origin's own validation and `PAYMENT-SETTLEMENT` for
the gateway). Verification starts in parallel with the origin fetch and
recording runs in `waitUntil`, so it neither delays nor blocks traffic; a
JWKS outage only means nothing is counted.

## No route by default

`wrangler.toml` declares no route, no custom domain, no workers.dev URL and no
preview URLs. Deploying this Worker attaches it to **nothing**: it receives no
traffic and records nothing until the owner adds a route in front of a
monetized origin. Before attaching it, the owner should confirm with one
controlled paid canary that (a) Monetization Gateway hands the Worker the
`PAYMENT-CONTEXT` and (b) the Worker's subrequest to the origin is not charged
a second time; neither has been observed for this Worker.

## Issuer, audience, expiry

- **Issuer.** Cloudflare's documented `PAYMENT-CONTEXT` claims (`iat`, `nbf`,
  `exp`, `aud`, `scheme`, `amount`) contain no `iss`, so issuer authenticity is
  the key binding: only keys served by `https://payments.cloudflare.com/certs`
  verify (redirects and token-supplied `jku`/`x5u`/`jwk`/`x5c` are refused).
  A present `iss` must be a string and is recorded in `blob5`. Setting the
  `PAYMENT_CONTEXT_ISSUER` var additionally requires `iss` to equal it exactly.
- **Audience.** `aud` must be a single string equal to the request's origin and
  path, without the query. A token minted for another resource is rejected.
- **Expiry.** `exp` and `nbf` are enforced by `jose` with a five-second clock
  tolerance; no other token TTL or replay policy is imposed.

`src/payment-keys.mjs` is a byte-for-byte copy of
`ops/evidence-snapshot-worker/src/payment-keys.mjs` (key retrieval, freshness,
Ed25519-only key checks, 5 s / 64 KiB / 32-key limits);
`test/payment-keys-parity.test.mjs` fails if the copies diverge. Price bounds
match `scripts/x402_payment_context.py`.

## Analytics Engine schema

Binding `REVENUE_EVENTS`, dataset `szl_revenue_events`:

| Column | Meaning |
|---|---|
| `index1` | event name (table above) |
| `blob1` | audience (origin + path, at most 1024 characters) |
| `blob2` | `exact` / `upto` (empty when rejected) |
| `blob3` | reason code (`signature`, `audience`, `expired`, `keys_unavailable`, `capped_at_authorized`, ...) |
| `blob4` | SHA-256 of the `PAYMENT-CONTEXT` token, never the token, for duplicate detection |
| `blob5` | `iss` claim when present |
| `blob6` | `SOURCE_REVISION` of the Worker that wrote the row |
| `double1` | authorized atomic units |
| `double2` | reported settlement atomic units |
| `double3` | effective settlement atomic units (capped) |
| `double4` | origin HTTP status (0 = origin transport failure) |

No IP address, user agent, token, or request body is written. Example query
(Analytics Engine SQL API), verified authorizations per resource and scheme:

```sql
SELECT blob1 AS audience, blob2 AS scheme,
       SUM(_sample_interval) AS authorizations,
       SUM(_sample_interval * double1) AS authorized_atomic
FROM szl_revenue_events
WHERE index1 = 'payment_authorized' AND double4 > 0 AND double4 < 400
GROUP BY audience, scheme
```

Rows with the same `blob4` are the same token; count distinct `blob4` when
replays matter.

## Validate

```shell
cd ops/revenue-tracker-worker
npm ci --ignore-scripts
npm test         # real Ed25519 tokens, fake JWKS/origin/dataset
npm run build    # wrangler deploy --dry-run with the locked Wrangler
```

The post-deploy readback is tested from the repository root with
`python3 -m unittest tests.test_verify_worker_deployment -v`.

## Deploy (GitOps)

`.github/workflows/revenue-tracker-worker.yml` tests every change. On a push to
`main` (or `workflow_dispatch` on `main`) its `deploy` job, gated by the
`cloudflare-production` environment, checks out exactly `github.sha`, deploys
with the SHA-pinned `cloudflare/wrangler-action` in that workflow and the full
SHA as the `SOURCE_REVISION` var, then runs
`scripts/verify_worker_deployment.py`. Both test and deploy jobs verify that
the installed Wrangler CLI matches the exact version in `package.json`,
after `npm ci` validates the lockfile. The deploy action receives that verified
version, so a dependency update cannot leave a separate workflow pin stale.
Because the Worker has no public endpoint, that readback uses the Workers API: the
newest deployment must route 100% of traffic to one version whose
`SOURCE_REVISION` binding equals the SHA and which carries the
`REVENUE_EVENTS` Analytics Engine binding; otherwise the job fails.

## Owner actions

1. GitHub → `szl-holdings/szl-trust` → Settings → Environments → create
   `cloudflare-production` with required reviewers and deployment branches
   limited to `main`.
2. Environment secrets: `CLOUDFLARE_ACCOUNT_ID` (32-hex account ID) and
   `CLOUDFLARE_API_TOKEN`, a custom token with exactly **Account → Workers
   Scripts → Edit** and **Account → Account Settings → Read**, limited to this
   account, with no zone or user permissions (Workers Scripts Edit includes the
   read access the readback needs; Analytics Engine datasets are created on
   first write).
3. Decide attachment (see "No route by default"). A route is a zone-level
   change and needs a separate decision plus **Zone → Workers Routes → Edit**.

## Proof boundary

The tests prove the counting rules: forged, expired, mis-audienced or
malformed contexts count zero; client headers are ignored; settlements are
counted only from the origin response under the gateway's rules; traffic is
never delayed or altered. They do **not** prove that Monetization Gateway
delivers `PAYMENT-CONTEXT` to a route-attached Worker, that any payment was
settled, or any revenue figure: this Worker observes authorizations and
origin-reported settlements, while Monetization Gateway settles payments and
issues receipts. Nothing in this directory has been deployed by the change
that added it.
