// Verifies a Cloudflare Monetization Gateway PAYMENT-CONTEXT JWT for the
// resource a request names. Key retrieval, freshness and the Ed25519-only key
// policy come from payment-keys.mjs, a byte-for-byte copy of the
// evidence-snapshot Worker's resolver (test/payment-keys-parity.test.mjs).

import { jwtVerify } from "jose";

import { createPaymentKeyResolver } from "./payment-keys.mjs";

export { JWKS_URL } from "./payment-keys.mjs";

// Documented Monetization Gateway price bounds, in atomic units ($0.001-$100),
// the same bounds scripts/x402_payment_context.py enforces.
export const MIN_ATOMIC = 1_000;
export const MAX_ATOMIC = 100_000_000;
export const SCHEMES = new Set(["exact", "upto"]);

const CANONICAL_AMOUNT = /^(0|[1-9][0-9]*)$/;

export class PaymentContextError extends Error {
  constructor(reason) {
    super(reason);
    this.name = "PaymentContextError";
    this.reason = reason;
  }
}

/** The audience a request may claim: its exact origin and path, no query. */
export function audienceFor(url) {
  return `${url.origin}${url.pathname}`;
}

function atomicAmount(value) {
  if (typeof value !== "string" || !CANONICAL_AMOUNT.test(value)) {
    throw new PaymentContextError("amount");
  }
  const amount = Number(value);
  if (!Number.isSafeInteger(amount) || amount < MIN_ATOMIC || amount > MAX_ATOMIC) {
    throw new PaymentContextError("amount");
  }
  return amount;
}

/**
 * Returns `verify(token, { audience, issuer })` resolving to the verified
 * claims the tracker records. `fetch`/`now` are a module-level test seam only;
 * the deployed Worker always uses the pinned JWKS URL and the real clock.
 */
export function createPaymentContextVerifier({ fetch, now = Date.now } = {}) {
  const resolve = createPaymentKeyResolver({ fetch, now });
  // Key-selection outcomes (unknown kid, refused key header) keep their own
  // reason; any failure to obtain usable keys means "keys_unavailable".
  const keys = async (header, token) => {
    try {
      return await resolve(header, token);
    } catch (error) {
      if (typeof error?.code === "string" || error?.message === "PAYMENT_CONTEXT_KEY_HEADER_INVALID") {
        throw error;
      }
      throw new PaymentContextError("keys_unavailable");
    }
  };
  return async (token, { audience, issuer = "" } = {}) => {
    if (typeof audience !== "string" || audience === "") {
      throw new PaymentContextError("audience");
    }
    if (typeof issuer !== "string") {
      throw new PaymentContextError("issuer");
    }
    const options = {
      algorithms: ["EdDSA"],
      audience,
      clockTolerance: 5,
      currentDate: new Date(now()),
    };
    if (issuer !== "") {
      options.issuer = issuer;
    }
    const { payload, protectedHeader } = await jwtVerify(token, keys, options);

    if (protectedHeader.alg !== "EdDSA") {
      throw new PaymentContextError("algorithm");
    }
    if (!Number.isInteger(payload.iat) || !Number.isInteger(payload.nbf) || !Number.isInteger(payload.exp)) {
      throw new PaymentContextError("time_claims");
    }
    if (payload.aud !== audience) {
      throw new PaymentContextError("audience");
    }
    if (payload.iss !== undefined && typeof payload.iss !== "string") {
      throw new PaymentContextError("issuer");
    }
    if (issuer !== "" && payload.iss !== issuer) {
      throw new PaymentContextError("issuer");
    }
    if (typeof payload.scheme !== "string" || !SCHEMES.has(payload.scheme)) {
      throw new PaymentContextError("scheme");
    }
    return {
      audience,
      scheme: payload.scheme,
      amount: atomicAmount(payload.amount),
      issuer: payload.iss ?? null,
      expires_at: payload.exp,
    };
  };
}

/** Coarse, token-free reason code for a rejected context. */
export function rejectionReason(error) {
  if (error instanceof PaymentContextError) {
    return error.reason;
  }
  const code = error?.code;
  if (code === "ERR_JWT_EXPIRED") {
    return "expired";
  }
  if (code === "ERR_JWT_CLAIM_VALIDATION_FAILED") {
    if (error.claim === "nbf") {
      return "not_yet_valid";
    }
    if (error.claim === "aud") {
      return "audience";
    }
    if (error.claim === "iss") {
      return "issuer";
    }
    return "claims";
  }
  if (code === "ERR_JWS_SIGNATURE_VERIFICATION_FAILED") {
    return "signature";
  }
  if (code === "ERR_JWKS_NO_MATCHING_KEY" || code === "ERR_JWKS_MULTIPLE_MATCHING_KEYS") {
    return "unknown_key";
  }
  if (code === "ERR_JOSE_ALG_NOT_ALLOWED" || code === "ERR_JOSE_NOT_SUPPORTED") {
    return "algorithm";
  }
  const message = String(error?.message ?? "");
  if (message === "PAYMENT_CONTEXT_KEY_HEADER_INVALID") {
    return "key_header";
  }
  if (message.startsWith("PAYMENT_KEYS_")) {
    return "keys_unavailable";
  }
  if (code === "ERR_JWS_INVALID" || code === "ERR_JWT_INVALID") {
    return "malformed";
  }
  return "invalid";
}
