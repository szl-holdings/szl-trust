import { DEFAULT_LEEWAY_SECONDS, verifyPaymentContext as verifyContext } from "./payment-context.mjs";
import { createPaymentKeyResolver } from "./payment-keys.mjs";
export { JWKS_URL } from "./payment-keys.mjs";

// Owner-selected price per docs/monetization/evidence-snapshot-activation-2026-11-02.md.
// Not offered yet: no Gateway rule exists for this path and the apex host is a
// free website under the 2026-11-06 owner policy, so the route must move to an
// API host (owner decision) before deployment.
export const AUDIENCE = "https://api.a-11-oy.com/v1/evidence-snapshot";
export const AMOUNT_ATOMIC = "1000000";
export const SCHEME = "exact";
export const SOURCE_REVISION = "44a384b63e2cc2c6820e8044d3485fc8ee3070f3";

const PUBLIC_RUN_PREFIX =
  `https://github.com/szl-holdings/szl-trust/blob/${SOURCE_REVISION}/runs/E4-codex-kernel-2026-04-29/`;

export const INPUTS = Object.freeze([
  ["decision_receipt.json", "80411c8cd07ec0f5ad680cb40a8a975db7e06587", "application/json"],
  ["deployment_contract.json", "c7d6707773f834a72f540cf1dfb85d958300d89a", "application/json"],
  ["final_state.json", "aadc42f5531ab2f470444e2cfbf22ca4c5c60b80", "application/json"],
  ["final_table_preview.json", "6a167182885da56fd9d22da21baf38828cbedc07", "application/json"],
  ["proof_ledger.jsonl", "33d90936ff5dd5f32e8159d7625a33dcf4339d80", "application/x-ndjson"],
  ["run_identity.json", "b21816eed2d264537b1c25efb71457d32f16b3c3", "application/json"],
  ["run_manifest.json", "0152afcc1562149c4efa69f55c96fd8fed64bd6e", "application/json"],
  ["run_summary.json", "873ba05ba036e57b2890b1e4bd79ec3ed1bb3d2c", "application/json"],
  ["trace.jsonl", "dd5336e9ca5b165569ba826f42ee4e558caf86b9", "application/x-ndjson"],
  ["version_lineage.json", "3a0e6259b4d4bc38092547390c102587194f1c2f", "application/json"]
].map(([name, gitBlobSha1, mediaType]) => Object.freeze({
  name,
  path: `runs/E4-codex-kernel-2026-04-29/${name}`,
  git_blob_sha1: gitBlobSha1,
  media_type: mediaType,
  source_url: `${PUBLIC_RUN_PREFIX}${name}`
})));

function json(status, body, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      ...extraHeaders
    }
  });
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map(
      (key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256Hex(value) {
  const encoded = new TextEncoder().encode(stableStringify(value));
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

// Delegates every check to the shared validator (payment-context.mjs), which
// runs the same conformance vectors as scripts/x402_payment_context.py.
export function createPaymentVerifier({ fetch, now = Date.now } = {}) {
  const keys = createPaymentKeyResolver({ fetch, now });
  return (token) => verifyContext(token, {
    keys,
    expectedAudience: AUDIENCE,
    scheme: SCHEME,
    expectedAmount: AMOUNT_ATOMIC,
    now: Math.floor(now() / 1000),
    leewaySeconds: DEFAULT_LEEWAY_SECONDS
  });
}

export const verifyPaymentContext = createPaymentVerifier();

function baseSnapshot() {
  return {
    schema: "szl.evidence-snapshot.v1",
    sku: "evidence_snapshot_v1",
    version: "2026-11-03",
    source: {
      repository: "szl-holdings/szl-trust",
      revision: SOURCE_REVISION,
      run_id: "E4-codex-kernel-2026-04-29"
    },
    price: {
      scheme: "exact",
      amount_atomic: AMOUNT_ATOMIC,
      amount_usd: "1.00"
    },
    inputs: INPUTS,
    attribution: {
      creator: "SZL Holdings",
      license: "CC-BY-4.0",
      license_url: "https://creativecommons.org/licenses/by/4.0/",
      source_license_url: `https://github.com/szl-holdings/szl-trust/blob/${SOURCE_REVISION}/LICENSE`,
      notice_url: `https://github.com/szl-holdings/szl-trust/blob/${SOURCE_REVISION}/NOTICE`,
      changes: "Manifest metadata and links only; historical source artifacts are not modified or embedded.",
      trademark_notice: "CC-BY-4.0 does not grant trademark rights or imply endorsement."
    },
    checks: [
      { id: "source_revision_pinned", status: "PASS", observed: SOURCE_REVISION },
      { id: "input_count_exact", status: "PASS", observed: INPUTS.length, expected: 10 },
      { id: "source_urls_revision_pinned", status: "PASS", observed: true },
      { id: "payment_context_verified", status: "PASS", observed: "Cloudflare Ed25519 JWT" }
    ],
    bounds: {
      operation: "read_only_application_state",
      effects: "No application-state writes; certificate retrieval and operational logging occur.",
      private_data: "No private source content in this manifest; payment headers and request metadata are processed by the Worker and providers.",
      source_content_embedded: false,
      claim: "Historical static public-source manifest and technical pilot, not model inference, live monitoring, or evidence of income. Receipt truth and performance are not re-evaluated by this endpoint.",
      processing: "Payment verification may fetch public certificates from https://payments.cloudflare.com/certs. Success/rejection events are logged and configured provider observability may process request metadata; retention and provider payment processing are outside this manifest.",
      readiness: "Neither this manifest nor its unsigned deterministic digest proves current deployment health, payment settlement, or operational readiness."
    }
  };
}

export async function handleRequest(request, { verify = verifyPaymentContext } = {}) {
  const url = new URL(request.url);

  if (request.method !== "GET") {
    return json(405, { state: "METHOD_NOT_ALLOWED" }, { allow: "GET" });
  }
  if (`${url.origin}${url.pathname}` !== AUDIENCE || url.search !== "") {
    return json(404, { state: "NOT_FOUND" });
  }

  const token = request.headers.get("PAYMENT-CONTEXT");
  if (!token) {
    return json(402, { state: "PAYMENT_REQUIRED", sku: "evidence_snapshot_v1" });
  }

  try {
    await verify(token);
  } catch (error) {
    // Log the stable reason code only; never the token or an error message.
    const reason = typeof error?.reason === "string" ? error.reason : "UNCLASSIFIED";
    console.log(JSON.stringify({ event: "evidence_snapshot", outcome: "payment_context_rejected", reason }));
    return json(403, { state: "PAYMENT_CONTEXT_INVALID" });
  }

  const snapshot = baseSnapshot();
  const packageSha256 = await sha256Hex(snapshot);
  console.log(JSON.stringify({
    event: "evidence_snapshot",
    outcome: "served",
    source_revision: SOURCE_REVISION,
    package_sha256: packageSha256
  }));
  return json(200, { ...snapshot, package_sha256: packageSha256 });
}

export default {
  fetch(request) {
    return handleRequest(request);
  }
};
