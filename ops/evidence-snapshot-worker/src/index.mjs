import { createRemoteJWKSet, jwtVerify } from "jose";

export const AUDIENCE = "https://a-11-oy.com/api/v1/evidence-snapshot";
export const AMOUNT_ATOMIC = "1000000";
export const SOURCE_REVISION = "44a384b63e2cc2c6820e8044d3485fc8ee3070f3";
export const JWKS_URL = "https://payments.cloudflare.com/certs";

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

const REMOTE_JWKS = createRemoteJWKSet(new URL(JWKS_URL));

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

export async function verifyPaymentContext(token) {
  const { payload, protectedHeader } = await jwtVerify(token, REMOTE_JWKS, {
    algorithms: ["EdDSA"],
    audience: AUDIENCE,
    clockTolerance: 5
  });

  if (protectedHeader.alg !== "EdDSA") {
    throw new Error("PAYMENT_CONTEXT_ALGORITHM_INVALID");
  }
  if (!Number.isInteger(payload.iat) || !Number.isInteger(payload.nbf) || !Number.isInteger(payload.exp)) {
    throw new Error("PAYMENT_CONTEXT_TIME_CLAIMS_INVALID");
  }
  if (payload.aud !== AUDIENCE) {
    throw new Error("PAYMENT_CONTEXT_AUDIENCE_INVALID");
  }
  if (payload.scheme !== "exact") {
    throw new Error("PAYMENT_CONTEXT_SCHEME_INVALID");
  }
  if (payload.amount !== AMOUNT_ATOMIC) {
    throw new Error("PAYMENT_CONTEXT_AMOUNT_INVALID");
  }

  return payload;
}

function baseSnapshot() {
  return {
    schema: "szl.evidence-snapshot.v1",
    sku: "evidence_snapshot_v1",
    version: "2026-11-02",
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
    checks: [
      { id: "source_revision_pinned", status: "PASS", observed: SOURCE_REVISION },
      { id: "input_count_exact", status: "PASS", observed: INPUTS.length, expected: 10 },
      { id: "source_urls_revision_pinned", status: "PASS", observed: true },
      { id: "payment_context_verified", status: "PASS", observed: "Cloudflare Ed25519 JWT" }
    ],
    bounds: {
      operation: "read_only",
      effects: "none",
      private_data: "none",
      source_content_embedded: false,
      claim: "Pinned public source manifest; receipt truth and performance are not re-evaluated by this endpoint."
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
  } catch {
    console.log(JSON.stringify({ event: "evidence_snapshot", outcome: "payment_context_rejected" }));
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
