import assert from "node:assert/strict";
import test from "node:test";
import { exportJWK, generateKeyPair, SignJWT } from "jose";

import {
  JWKS_URL,
  MAX_ATOMIC,
  MIN_ATOMIC,
  PaymentContextError,
  audienceFor,
  createPaymentContextVerifier,
  rejectionReason,
} from "../src/payment-context.mjs";

// Test-only keys stay in memory. No network, wallet, credentials or purchases.
async function signer(kid) {
  const pair = await generateKeyPair("EdDSA");
  return { ...pair, jwk: { ...await exportJWK(pair.publicKey), kid, alg: "EdDSA" } };
}
const first = await signer("first");
const second = await signer("second");
const epoch = Date.UTC(2026, 10, 6);
const seconds = epoch / 1000;
const AUDIENCE = "https://inference.a-11-oy.com/v1/completions";
const claims = {
  aud: AUDIENCE, scheme: "exact", amount: "20000",
  iat: seconds, nbf: seconds, exp: seconds + 120
};

function sign(payload = claims, key = first, header = {}) {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: "EdDSA", kid: key.jwk.kid, ...header })
    .sign(key.privateKey);
}

function harness(respond = () => new Response(JSON.stringify({ keys: [first.jwk] }), {
  headers: { "content-type": "application/json", "cache-control": "max-age=60" }
})) {
  let time = epoch;
  const requests = [];
  const verify = createPaymentContextVerifier({
    now: () => time,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return respond(requests.length);
    }
  });
  return { verify, requests, advance: (ms) => { time += ms; } };
}

async function rejection(promise) {
  try {
    await promise;
  } catch (error) {
    return rejectionReason(error);
  }
  assert.fail("verification unexpectedly succeeded");
}

test("a real Ed25519 exact context verifies against the pinned JWKS", async () => {
  const h = harness();
  assert.deepEqual(await h.verify(await sign(), { audience: AUDIENCE }), {
    audience: AUDIENCE, scheme: "exact", amount: 20000, issuer: null, expires_at: seconds + 120
  });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, JWKS_URL);
  assert.equal(h.requests[0].options.redirect, "error");
});

test("a variable-price (upto) context verifies with its authorized maximum", async () => {
  const verified = await harness().verify(await sign({ ...claims, scheme: "upto", amount: "100000" }), {
    audience: AUDIENCE
  });
  assert.equal(verified.scheme, "upto");
  assert.equal(verified.amount, 100000);
});

test("the audience is the request's exact origin and path, never its query", () => {
  assert.equal(audienceFor(new URL(`${AUDIENCE}?model=x&stream=1`)), AUDIENCE);
  assert.equal(audienceFor(new URL("https://inference.a-11-oy.com:443/v1/completions")), AUDIENCE);
});

for (const [name, changes, reason] of [
  ["a token minted for another resource", { aud: "https://inference.a-11-oy.com/v1/responses" }, "audience"],
  ["an audience array", { aud: [AUDIENCE] }, "audience"],
  ["a missing audience", { aud: undefined }, "audience"],
  ["an unknown scheme", { scheme: "subscription" }, "scheme"],
  ["a missing scheme", { scheme: undefined }, "scheme"],
  ["a non-string scheme", { scheme: ["exact"] }, "scheme"],
  ["a numeric amount", { amount: 20000 }, "amount"],
  ["a non-canonical amount", { amount: "020000" }, "amount"],
  ["an exponent amount", { amount: "2e4" }, "amount"],
  ["a negative amount", { amount: "-20000" }, "amount"],
  ["an amount below the gateway minimum", { amount: String(MIN_ATOMIC - 1) }, "amount"],
  ["an amount above the gateway maximum", { amount: String(MAX_ATOMIC + 1) }, "amount"],
  ["a missing amount", { amount: undefined }, "amount"],
  ["an expired token", { exp: seconds - 6 }, "expired"],
  ["a not-yet-valid token", { nbf: seconds + 6 }, "not_yet_valid"],
  ["a fractional exp", { exp: seconds + 0.5 }, "time_claims"],
  ["a string iat", { iat: String(seconds) }, "claims"],
  ["a missing nbf", { nbf: undefined }, "time_claims"],
  ["a non-string issuer", { iss: 42 }, "issuer"]
]) {
  test(`signed token rejects ${name}`, async () => {
    assert.equal(await rejection(harness().verify(await sign({ ...claims, ...changes }), { audience: AUDIENCE })), reason);
  });
}

test("the documented bounds themselves are accepted", async () => {
  for (const amount of [String(MIN_ATOMIC), String(MAX_ATOMIC)]) {
    await harness().verify(await sign({ ...claims, amount }), { audience: AUDIENCE });
  }
});

test("an issuer is enforced exactly when one is pinned, and recorded otherwise", async () => {
  const issuer = "https://payments.cloudflare.com";
  const withIss = await sign({ ...claims, iss: issuer });
  assert.equal((await harness().verify(withIss, { audience: AUDIENCE })).issuer, issuer);
  assert.equal((await harness().verify(withIss, { audience: AUDIENCE, issuer })).issuer, issuer);
  assert.equal(await rejection(harness().verify(withIss, { audience: AUDIENCE, issuer: "https://other.example" })), "issuer");
  assert.equal(await rejection(harness().verify(await sign(), { audience: AUDIENCE, issuer })), "issuer");
});

test("five-second clock tolerance matches the evidence-snapshot policy", async () => {
  await harness().verify(await sign({ ...claims, exp: seconds - 4 }), { audience: AUDIENCE });
  await harness().verify(await sign({ ...claims, nbf: seconds + 4 }), { audience: AUDIENCE });
});

test("a trusted kid with the wrong signing key fails cryptographically", async () => {
  const token = await sign(claims, second, { kid: first.jwk.kid });
  assert.equal(await rejection(harness().verify(token, { audience: AUDIENCE })), "signature");
});

test("payload and signature tampering are rejected", async () => {
  const token = await sign();
  const [header, , signature] = token.split(".");
  const inflated = Buffer.from(JSON.stringify({ ...claims, amount: "100000000" })).toString("base64url");
  assert.equal(await rejection(harness().verify(`${header}.${inflated}.${signature}`, { audience: AUDIENCE })), "signature");
  const flipped = Buffer.from(signature, "base64url");
  flipped[0] ^= 1;
  assert.equal(
    await rejection(harness().verify(`${token.split(".").slice(0, 2).join(".")}.${flipped.toString("base64url")}`, { audience: AUDIENCE })),
    "signature"
  );
});

test("an unknown kid is not a payment", async () => {
  assert.equal(await rejection(harness().verify(await sign(claims, second), { audience: AUDIENCE })), "unknown_key");
});

test("unsigned, HS256 and malformed tokens never trigger key retrieval", async () => {
  const h = harness();
  const encoded = Buffer.from(JSON.stringify(claims)).toString("base64url");
  for (const token of [
    "not-a-jwt",
    `${Buffer.from('{"alg":"none"}').toString("base64url")}.${encoded}.`,
    await new SignJWT(claims).setProtectedHeader({ alg: "HS256" }).sign(new Uint8Array(32))
  ]) {
    await assert.rejects(h.verify(token, { audience: AUDIENCE }));
  }
  assert.equal(h.requests.length, 0);
});

for (const name of ["jku", "x5u", "jwk", "x5c"]) {
  test(`a token-supplied ${name} header is refused without fetching it`, async () => {
    const h = harness();
    const value = name === "jwk" ? first.jwk : name === "x5c" ? [] : "https://attacker.invalid/keys";
    assert.equal(await rejection(h.verify(await sign(claims, first, { [name]: value }), { audience: AUDIENCE })), "key_header");
    assert.equal(h.requests.length, 0);
  });
}

test("an unreachable or invalid JWKS endpoint means nothing is counted", async () => {
  for (const respond of [
    () => { throw new Error("offline"); },
    () => new Response("unavailable", { status: 503 }),
    () => new Response("{", { headers: { "content-type": "application/json" } })
  ]) {
    assert.equal(await rejection(harness(respond).verify(await sign(), { audience: AUDIENCE })), "keys_unavailable");
  }
});

test("callers must name the audience; the verifier never guesses it", async () => {
  for (const audience of [undefined, "", 42]) {
    assert.equal(await rejection(harness().verify(await sign(), { audience })), "audience");
  }
  assert.ok(new PaymentContextError("audience") instanceof Error);
});
