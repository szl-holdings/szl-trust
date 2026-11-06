import { createLocalJWKSet, importJWK } from "jose";

export const JWKS_URL = "https://payments.cloudflare.com/certs";

const MAX_BYTES = 64 * 1024;
const MAX_KEYS = 32;
const FETCH_TIMEOUT_MS = 5000;

function freshness(headers, startedAt, receivedAt) {
  const directives = new Map();
  for (const part of (headers.get("cache-control") ?? "").split(",")) {
    const [name, ...value] = part.trim().toLowerCase().split("=");
    if (directives.has(name)) return 0;
    directives.set(name, value.join("=").trim());
  }
  if (directives.has("no-cache") || directives.has("no-store")) return 0;
  const maxAge = directives.get("max-age")?.replace(/^"(\d+)"$/, "$1");
  const age = headers.get("age") ?? "0";
  if (!/^\d+$/.test(maxAge ?? "") || !/^\d+$/.test(age)) return 0;
  const lifetime = Number(maxAge) * 1000;
  const ageMs = Number(age) * 1000;
  if (!Number.isSafeInteger(lifetime) || !Number.isSafeInteger(ageMs)) return 0;
  const date = Date.parse(headers.get("date") ?? "");
  const apparentAge = Number.isFinite(date) ? Math.max(0, receivedAt - date) : 0;
  const correctedAge = Math.max(apparentAge, ageMs + Math.max(0, receivedAt - startedAt));
  return Math.max(0, lifetime - correctedAge);
}

async function readKeys(response) {
  if (response.status !== 200 || response.redirected ||
      (response.url && response.url !== JWKS_URL)) {
    throw new Error("PAYMENT_KEYS_RESPONSE_INVALID");
  }
  if (!/^application\/(?:json|jwk-set\+json)(?:\s*;|$)/i.test(response.headers.get("content-type") ?? "")) {
    throw new Error("PAYMENT_KEYS_CONTENT_TYPE_INVALID");
  }
  if (!response.body) throw new Error("PAYMENT_KEYS_BODY_MISSING");
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) throw new Error("PAYMENT_KEYS_BODY_TOO_LARGE");
      chunks.push(value);
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const jwks = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  if (!jwks || !Array.isArray(jwks.keys) || jwks.keys.length === 0 ||
      jwks.keys.length > MAX_KEYS) {
    throw new Error("PAYMENT_KEYS_SET_INVALID");
  }
  for (const key of jwks.keys) {
    if (!key || key.kty !== "OKP" || key.crv !== "Ed25519" ||
        typeof key.x !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(key.x) ||
        "d" in key || (key.alg !== undefined && key.alg !== "EdDSA") ||
        (key.use !== undefined && key.use !== "sig") ||
        (key.kid !== undefined && typeof key.kid !== "string") ||
        (key.key_ops !== undefined &&
          (!Array.isArray(key.key_ops) || key.key_ops.length !== 1 || key.key_ops[0] !== "verify"))) {
      throw new Error("PAYMENT_KEYS_ED25519_REQUIRED");
    }
    await importJWK(key, "EdDSA");
  }
  return createLocalJWKSet(jwks);
}

// Local dependency injection only; the deployed Worker uses the pinned defaults.
export function createPaymentKeyResolver({ fetch: fetchKeys = globalThis.fetch, now = Date.now } = {}) {
  let cached;
  let pending;

  async function retrieve() {
    const startedAt = now();
    const controller = new AbortController();
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new Error("PAYMENT_KEYS_FETCH_TIMEOUT"));
      }, FETCH_TIMEOUT_MS);
    });
    try {
      return await Promise.race([
        (async () => {
          const response = await fetchKeys(JWKS_URL, {
            redirect: "error",
            cache: "no-store",
            signal: controller.signal,
            headers: { accept: "application/json" }
          });
          const receivedAt = now();
          const resolve = await readKeys(response);
          return { resolve, expiresAt: receivedAt + freshness(response.headers, startedAt, receivedAt) };
        })(),
        timeout
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  return async (header, token) => {
    if (header.alg !== "EdDSA" ||
        ["jku", "x5u", "jwk", "x5c"].some((name) => name in header)) {
      throw new Error("PAYMENT_CONTEXT_KEY_HEADER_INVALID");
    }
    let keys = cached;
    if (!keys || now() >= keys.expiresAt) {
      cached = undefined; // Never fall back to stale keys on retrieval failure.
      if (!pending) {
        pending = retrieve().then((result) => {
          if (now() < result.expiresAt) cached = result;
          return result;
        }).finally(() => { pending = undefined; });
      }
      keys = await pending;
    }
    return keys.resolve(header, token);
  };
}
