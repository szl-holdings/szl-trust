# SZL Estate Release Audit — 2026-10-08

Status: **IN PROGRESS / NOT RELEASE-CERTIFIED**. This is a bounded, read-only evidence snapshot and an execution queue, not a claim of full coverage.

## Source observations
- GitHub connector enumerated 100 repositories for szl-holdings (page size 100; offset 100 returned none). Repository existence is not source or runtime correctness.
- `platform/package.json` includes pnpm/turbo build, typecheck, lint, Playwright E2E, API and integration test commands. These are commands, not observed passing results.
- `hatun-mcp/README.md` states canonical Python FastMCP gateway and explicitly retires its separate HF publisher. Embedded `platform/packages/hatun-mcp` is noncanonical.
- `nexus/README.md` states its public surface is IMMUNE `/nexus.html`, not a standalone HF Space.
- `a11oy-net/README.md` designates .net as independently hosted RECORD, not an interchangeable .com copy.
- HF public metadata resolved `SZLHOLDINGS/szl-command-lab`; attempted Space lookups `SZLHOLDINGS/nexus` and `SZLHOLDINGS/hatun-mcp` returned not found/auth-required. These do not establish an outage because neither is a claimed current standalone public Space.

## P0: existing blockers (do not bypass)
- https://github.com/szl-holdings/a11oy/issues/2674 : recorded meter.a-11-oy.com Cloudflare 1033/no healthy connector, required-source degradation, exact-source readiness hold. Historical issue evidence; independently re-probe before asserting present condition. Tunnel owner, auth repair path, live NVML delta, maintenance window and canonical publisher needed. Never fabricate energy readings.
- https://github.com/szl-holdings/a11oy/issues/2615 : Tailwind 4 focus/tooltip source/shipped-byte compatibility. Requires isolated browser fixture and narrow signed PR.
- https://github.com/szl-holdings/platform/issues/902 : promote source-of-truth artifact through signed, DCO-complete PR. Do not weaken signature or branch rules.
- https://github.com/szl-holdings/lutar-lean/issues/317 : distinguish conditional Lean theorem from stronger unproven equivalence claim.
- https://github.com/szl-holdings/szl-trust/pull/79 : x402 commercial readiness is draft design only; no live billing.

## Audit and release sequence
1. Enumerate default-branch SHA, visibility, archive state, code owners, build system, dependency lockfiles, CI, security alerts, secrets scanning, open PRs/issues, releases and protected rules per repository. Keep immutable paginated inventory with checked timestamps.
2. Classify active, archived, mirror, source-of-truth, demo, and deployment repositories; never blindly rewrite or reactivate archived assets.
3. Run frontend accessibility/responsive/performance tests and backend unit/integration/contract/security tests; record exact commands, SHA, results and artifacts. Fail closed on missing evidence.
4. For Hatun, test Python FastMCP transport, tool schemas, auth, prompt-injection defenses, approval boundaries, signed receipts, idempotency, tenant isolation, and upstream availability. Preserve canonical-source rule.
5. Enumerate HF public/private models, datasets, kernels and Spaces with authenticated owner API where needed; for each verify revision, card, license, provenance, PII/commercial rights, weights/format, runtime status and reproducible evaluation. Never treat metadata or a URL as deployment parity.
6. Reconcile GitHub SHA -> HF published artifact digest/source identity -> .com runtime/asset bytes -> .net independent proof record. .net must not manufacture live parity from static links.
7. Remediate on isolated single-writer branches, honor existing source ownership, protect main, require native checks, signed commits and reviews. Canary, independently re-probe, rollback if failed.
8. Iterate until no *unreviewed inventory entries* remain; unresolved blocked work must be explicitly marked BLOCKED rather than called complete.

## Acceptance criteria
No asset marked VERIFIED without independent source/runtime proof. No dataset offered commercially without provenance/license review. No production payments enabled by this document. No tunnel, DNS, secret, protected-branch, or deployment mutation authorized by an audit report alone. 
