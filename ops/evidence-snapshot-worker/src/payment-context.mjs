// Canonical PAYMENT-CONTEXT validator for the Workers runtime.
//
// Python twin: scripts/x402_payment_context.py. Both must return the result
// recorded for every vector in tests/vectors/x402-payment-context.v1.json
// (test/vectors.test.mjs here, tests/test_x402_payment_context_vectors.py
// there), so a rule change lands in both or the suites fail.
//
// Contract: EdDSA over Ed25519 from the pinned JWKS only; token-supplied key
// material is rejected; required integer iat/nbf/exp; one string aud equal to
// the expected resource URL; the caller states the scheme and the price
// (exact: equal; upto: signed maximum not above it); leeway 5 s by default and
// at most 30 s; optional replay guard keyed on jti or the token's SHA-256.
import { base64url, compactVerify } from "jose";

export const SCHEMES = Object.freeze(["exact", "upto"]);
export const MIN_ATOMIC = 1000;
export const MAX_ATOMIC = 100000000;
export const DEFAULT_LEEWAY_SECONDS = 5;
export const MAX_LEEWAY_SECONDS = 30;
export const MAX_TOKEN_LENGTH = 8192;

const FORBIDDEN_HEADER_PARAMS = Object.freeze(["jku", "jwk", "x5u", "x5c"]);
const UNSUPPORTED_HEADER_PARAMS = Object.freeze(["crit", "b64"]);
const NO_KEY_CODES = new Set(["ERR_JWKS_NO_MATCHING_KEY", "ERR_JWKS_MULTIPLE_MATCHING_KEYS"]);

// ASCII-only patterns; the Python twin uses the same expressions.
const AMOUNT = /^(?:0|[1-9][0-9]*)$/;
const SEGMENT = /^[A-Za-z0-9_-]+$/;
const PATH_CHARS = "[A-Za-z0-9._~!$&'()*+,;=:@%/-]*";
const AUDIENCE = new RegExp(`^https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?/${PATH_CHARS}$`);
const REQUEST_URL = new RegExp(
  `^([A-Za-z][A-Za-z0-9+.-]*)://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?(/${PATH_CHARS})?` +
  "(?:\\?[\\x21\\x22\\x24-\\x7e]*)?(?:#[\\x21-\\x7e]*)?$"
);

// Strict UTF-8; a byte-order mark is kept and then fails JSON.parse, as in Python.
const textDecoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const textEncoder = new TextEncoder();

export class PaymentContextError extends Error {
  constructor(reason, { detail, cause } = {}) {
    super(detail ? `${reason}: ${detail}` : reason, cause === undefined ? undefined : { cause });
    this.name = "PaymentContextError";
    this.reason = reason;
    this.detail = detail;
  }
}

function fail(reason, options) {
  throw new PaymentContextError(reason, options);
}

function atomicText(value, reason) {
  if (typeof value !== "string" || !AMOUNT.test(value)) fail(reason);
  // A canonical value longer than the maximum's digits is above the maximum.
  if (value.length > String(MAX_ATOMIC).length) return MAX_ATOMIC + 1;
  return Number(value);
}

export function checkVerifierConfig({ scheme, leewaySeconds, expectedAudience, expectedAmount, now }) {
  if (typeof scheme !== "string" || !SCHEMES.includes(scheme)) fail("UNKNOWN_SCHEME");
  if (!Number.isSafeInteger(leewaySeconds) || leewaySeconds < 0 || leewaySeconds > MAX_LEEWAY_SECONDS) {
    fail("BAD_LEEWAY");
  }
  if (typeof expectedAudience !== "string" || !AUDIENCE.test(expectedAudience)) fail("BAD_AUDIENCE");
  let expected;
  if (typeof expectedAmount === "number" && Number.isSafeInteger(expectedAmount)) {
    expected = expectedAmount;
  } else if (typeof expectedAmount === "string") {
    expected = atomicText(expectedAmount, "BAD_EXPECTED_AMOUNT");
  } else {
    fail("BAD_EXPECTED_AMOUNT");
  }
  if (expected < MIN_ATOMIC || expected > MAX_ATOMIC) fail("BAD_EXPECTED_AMOUNT");
  if (!Number.isSafeInteger(now)) fail("BAD_NOW");
  return expected;
}

// Compare scheme, lowercased host, port (443 dropped) and exact path; ignore the query.
export function requestMatchesAudience(requestUrl, expectedAudience) {
  if (typeof requestUrl !== "string") return false;
  const match = REQUEST_URL.exec(requestUrl);
  if (!match) return false;
  const scheme = match[1].toLowerCase();
  const port = match[3];
  const portPart = port !== undefined && !(scheme === "https" && port === "443") ? `:${port}` : "";
  return `${scheme}://${match[2].toLowerCase()}${portPart}${match[4] || "/"}` === expectedAudience;
}

function decodeSegment(segment) {
  if (segment === "" || !SEGMENT.test(segment) || segment.length % 4 === 1) fail("MALFORMED_TOKEN");
  let bytes;
  try {
    bytes = base64url.decode(segment);
  } catch (cause) {
    fail("MALFORMED_TOKEN", { cause });
  }
  if (base64url.encode(bytes) !== segment) fail("MALFORMED_TOKEN");
  return bytes;
}

function parseObject(bytes) {
  let value;
  try {
    value = JSON.parse(textDecoder.decode(bytes));
  } catch (cause) {
    fail("MALFORMED_TOKEN", { cause });
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail("MALFORMED_TOKEN");
  return value;
}

function parseHeader(token) {
  if (typeof token !== "string" || token.length > MAX_TOKEN_LENGTH) fail("MALFORMED_TOKEN");
  const segments = token.split(".");
  if (segments.length !== 3) fail("MALFORMED_TOKEN");
  const [header] = segments.map(decodeSegment);
  return parseObject(header);
}

function checkHeader(header) {
  if (header.alg !== "EdDSA") fail("WRONG_ALGORITHM");
  if (FORBIDDEN_HEADER_PARAMS.some((name) => Object.hasOwn(header, name))) fail("TOKEN_SUPPLIED_KEY_MATERIAL");
  if (UNSUPPORTED_HEADER_PARAMS.some((name) => Object.hasOwn(header, name))) fail("UNSUPPORTED_HEADER");
  if (Object.hasOwn(header, "kid") && (typeof header.kid !== "string" || header.kid === "")) {
    fail("MALFORMED_TOKEN");
  }
}

async function verifiedPayload(token, keys) {
  if (typeof keys !== "function") fail("KEYS_UNAVAILABLE", { detail: "PAYMENT_KEYS_SOURCE_INVALID" });
  let keyFailure;
  const resolve = async (protectedHeader, jws) => {
    try {
      return await keys(protectedHeader, jws);
    } catch (cause) {
      keyFailure = cause;
      throw cause;
    }
  };
  try {
    return (await compactVerify(token, resolve, { algorithms: ["EdDSA"] })).payload;
  } catch (cause) {
    if (keyFailure !== undefined) {
      if (NO_KEY_CODES.has(keyFailure?.code)) fail("UNKNOWN_KEY", { cause: keyFailure });
      const message = typeof keyFailure?.message === "string" ? keyFailure.message : "";
      let detail = "PAYMENT_KEYS_FETCH_FAILED";
      if (message.startsWith("PAYMENT_KEYS_")) detail = message;
      else if (keyFailure instanceof SyntaxError) detail = "PAYMENT_KEYS_SET_INVALID"; // JWKS body not JSON
      fail("KEYS_UNAVAILABLE", { detail, cause: keyFailure });
    }
    if (cause?.code === "ERR_JWS_SIGNATURE_VERIFICATION_FAILED") fail("BAD_SIGNATURE", { cause });
    if (cause?.code === "ERR_JOSE_ALG_NOT_ALLOWED") fail("WRONG_ALGORITHM", { cause });
    fail("MALFORMED_TOKEN", { cause });
  }
}

function checkTimes(claims, now, leeway) {
  const [iat, nbf, exp] = ["iat", "nbf", "exp"].map((name) => (
    Number.isSafeInteger(claims[name]) ? claims[name] : null
  ));
  if (iat === null || nbf === null || exp === null) fail("TIME_CLAIMS_INVALID");
  if (iat > exp || nbf > exp) fail("TIME_CLAIMS_INVALID");
  if (exp <= now - leeway) fail("EXPIRED");
  if (nbf > now + leeway || iat > now + leeway) fail("NOT_YET_VALID");
  return { iat, nbf, exp };
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", textEncoder.encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

// Remembers accepted contexts until they expire, inside one isolate or process.
// Cloudflare's documented claims carry no jti or nonce, so the key is the jti
// when present and otherwise the token's SHA-256. Opt-in: whether the gateway
// re-sends one context on an origin retry is unverified, and Workers isolates
// do not share memory. When full of unexpired entries it refuses new contexts.
export class MemoryReplayGuard {
  #maxEntries;
  #seen = new Map();

  constructor({ maxEntries = 10000 } = {}) {
    if (!Number.isSafeInteger(maxEntries) || maxEntries < 1) {
      throw new TypeError("maxEntries must be a positive integer");
    }
    this.#maxEntries = maxEntries;
  }

  checkAndRemember(key, { expiresAt, now }) {
    for (const [seenKey, seenExpiry] of this.#seen) {
      if (seenExpiry <= now) this.#seen.delete(seenKey);
    }
    if (this.#seen.has(key)) return "REPLAYED";
    if (this.#seen.size >= this.#maxEntries) return "REPLAY_CACHE_FULL";
    this.#seen.set(key, expiresAt);
    return null;
  }
}

// Resolves to the verified claims or rejects with a PaymentContextError whose
// `reason` is one of the stable codes shared with the Python twin. `keys` is a
// jose-style key resolver such as createPaymentKeyResolver(); `now` is the
// current time in whole seconds; `expectedAmount` is the catalog price in
// atomic units (the fixed price for exact, the maximum for upto).
export async function verifyPaymentContext(token, {
  keys,
  expectedAudience,
  scheme,
  expectedAmount,
  now,
  leewaySeconds = DEFAULT_LEEWAY_SECONDS,
  requestUrl,
  replayGuard
} = {}) {
  const expected = checkVerifierConfig({ scheme, leewaySeconds, expectedAudience, expectedAmount, now });
  if (token === undefined || token === null || token === "") fail("ABSENT");
  const header = parseHeader(token);
  checkHeader(header);
  const claims = parseObject(await verifiedPayload(token, keys));
  const { iat, nbf, exp } = checkTimes(claims, now, leewaySeconds);
  if (typeof claims.aud !== "string" || claims.aud !== expectedAudience) fail("WRONG_AUDIENCE");
  if (requestUrl !== undefined && requestUrl !== null && !requestMatchesAudience(requestUrl, expectedAudience)) {
    fail("REQUEST_NOT_AUDIENCE");
  }
  if (claims.scheme !== scheme) fail("WRONG_SCHEME");
  const amount = atomicText(claims.amount, "MALFORMED_AMOUNT");
  if (amount < MIN_ATOMIC || amount > MAX_ATOMIC) fail("AMOUNT_OUT_OF_BOUNDS");
  if (scheme === "exact" && amount !== expected) fail("AMOUNT_MISMATCH");
  if (scheme === "upto" && amount > expected) fail("AMOUNT_ABOVE_MAXIMUM");
  const tokenSha256 = await sha256Hex(token);
  if (replayGuard !== undefined && replayGuard !== null) {
    const replayKey = typeof claims.jti === "string" && claims.jti !== ""
      ? `jti:${claims.jti}` : `sha256:${tokenSha256}`;
    const refusal = replayGuard.checkAndRemember(replayKey, { expiresAt: exp + leewaySeconds, now });
    if (refusal !== null && refusal !== undefined) fail(refusal);
  }
  return Object.freeze({
    audience: claims.aud,
    scheme,
    amount,
    iat,
    nbf,
    exp,
    kid: header.kid ?? null,
    token_sha256: tokenSha256,
    settlement_evidence: false
  });
}
