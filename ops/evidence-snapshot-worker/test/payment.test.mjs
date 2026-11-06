import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import test from "node:test";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import { AMOUNT_ATOMIC, AUDIENCE, JWKS_URL, createPaymentVerifier, handleRequest } from "../src/index.mjs";

// Test-only keys remain in memory. No network, wallet, credentials or purchases.
async function signer(kid) {
  const pair = await generateKeyPair("EdDSA");
  return { ...pair, jwk: { ...await exportJWK(pair.publicKey), kid, alg: "EdDSA" } };
}
const first = await signer("first");
const second = await signer("second");
const epoch = Date.UTC(2026, 10, 2);
const seconds = epoch / 1000;
const claims = {
  aud: AUDIENCE, scheme: "exact", amount: AMOUNT_ATOMIC,
  iat: seconds, nbf: seconds, exp: seconds + 3600
};

function sign(payload = claims, key = first, header = {}) {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: "EdDSA", kid: key.jwk.kid, ...header })
    .sign(key.privateKey);
}

function response(keys = [first.jwk], cache = "max-age=60", extraHeaders = {}) {
  return new Response(JSON.stringify({ keys }), {
    headers: { "content-type": "application/json", "cache-control": cache, ...extraHeaders }
  });
}

function harness(respond = () => response()) {
  let time = epoch;
  const requests = [];
  const verify = createPaymentVerifier({
    now: () => time,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return respond(requests.length);
    }
  });
  return { verify, requests, advance: (ms) => { time += ms; } };
}

function rejectsWith(promise, reason) {
  return assert.rejects(promise, (error) => {
    assert.equal(error.reason, reason);
    return true;
  });
}

test("real Ed25519 payment verifies and serves the unchanged manifest", async () => {
  const h = harness();
  const token = await sign();
  const verified = await h.verify(token);
  assert.deepEqual({ ...verified, token_sha256: undefined }, {
    audience: AUDIENCE, scheme: "exact", amount: 1000000,
    iat: seconds, nbf: seconds, exp: seconds + 3600, kid: "first",
    token_sha256: undefined, settlement_evidence: false
  });
  assert.match(verified.token_sha256, /^[0-9a-f]{64}$/);
  const result = await handleRequest(new Request(AUDIENCE, { headers: { "PAYMENT-CONTEXT": token } }), {
    verify: h.verify
  });
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("PAYMENT-SETTLEMENT"), null);
  assert.equal((await result.json()).price.amount_atomic, "1000000");
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, JWKS_URL);
  assert.equal(h.requests[0].options.redirect, "error");
  assert.equal(h.requests[0].options.cache, "no-store");
});

for (const [name, changes] of [
  ["wrong audience", { aud: "https://other.example" }],
  ["audience array", { aud: [AUDIENCE] }],
  ["missing audience", { aud: undefined }],
  ["wrong scheme", { scheme: "upto" }],
  ["missing scheme", { scheme: undefined }],
  ["non-string scheme", { scheme: ["exact"] }],
  ["wrong amount", { amount: "999999" }],
  ["numeric amount", { amount: 1000000 }],
  ["missing amount", { amount: undefined }],
  ["expired", { exp: seconds - 6 }],
  ["future nbf", { nbf: seconds + 6 }]
]) {
  test(`signed token rejects ${name}`, async () => {
    await assert.rejects(harness().verify(await sign({ ...claims, ...changes })));
  });
}

for (const claim of ["iat", "nbf", "exp"]) {
  for (const [name, value] of [["missing", undefined], ["string", String(seconds)], ["fractional", seconds + 0.5]]) {
    test(`signed token rejects ${name} ${claim}`, async () => {
      await assert.rejects(harness().verify(await sign({ ...claims, [claim]: value })));
    });
  }
}

test("existing five-second clock tolerance and no arbitrary iat TTL are preserved", async () => {
  await harness().verify(await sign({ ...claims, iat: seconds - 86400, nbf: seconds + 4 }));
  await harness().verify(await sign({ ...claims, iat: seconds - 60, nbf: seconds - 60, exp: seconds - 4 }));
});

test("a future iat gets the same five-second leeway as nbf", async () => {
  await harness().verify(await sign({ ...claims, iat: seconds + 4 }));
  await rejectsWith(harness().verify(await sign({ ...claims, iat: seconds + 6 })), "NOT_YET_VALID");
});

test("a token issued after it expires is rejected", async () => {
  await rejectsWith(
    harness().verify(await sign({ ...claims, iat: seconds + 2, nbf: seconds, exp: seconds + 1 })),
    "TIME_CLAIMS_INVALID"
  );
});

test("a context signed for a cheaper or pricier rule is rejected", async () => {
  for (const amount of ["10000", "25000", "100000", "999999", "1000001"]) {
    await rejectsWith(harness().verify(await sign({ ...claims, amount })), "AMOUNT_MISMATCH");
  }
  await rejectsWith(harness().verify(await sign({ ...claims, scheme: "upto", amount: "1000" })), "WRONG_SCHEME");
});

test("wrong signer with a trusted kid is rejected cryptographically", async () => {
  await assert.rejects(harness().verify(await sign(claims, second, { kid: first.jwk.kid })));
});

test("signature and payload tampering are rejected", async () => {
  const token = await sign();
  const parts = token.split(".");
  const signature = Buffer.from(parts[2], "base64url");
  signature[0] ^= 1;
  await assert.rejects(harness().verify(`${parts[0]}.${parts[1]}.${signature.toString("base64url")}`));
  const forged = Buffer.from(JSON.stringify({ ...claims, amount: "0" })).toString("base64url");
  await assert.rejects(harness().verify(`${parts[0]}.${forged}.${parts[2]}`));
});

test("unsigned, malformed and HS256 tokens cannot trigger key retrieval", async () => {
  const h = harness();
  const encoded = Buffer.from(JSON.stringify(claims)).toString("base64url");
  for (const token of ["not-a-jwt", `${Buffer.from('{"alg":"none"}').toString("base64url")}.${encoded}.`,
    await new SignJWT(claims).setProtectedHeader({ alg: "HS256" }).sign(new Uint8Array(32))]) {
    await assert.rejects(h.verify(token));
  }
  assert.equal(h.requests.length, 0);
});

test("ES256 is rejected even when the endpoint supplies that public key", async () => {
  const pair = await generateKeyPair("ES256");
  const jwk = await exportJWK(pair.publicKey);
  const h = harness(() => response([jwk]));
  const token = await new SignJWT(claims).setProtectedHeader({ alg: "ES256" }).sign(pair.privateKey);
  await assert.rejects(h.verify(token));
  assert.equal(h.requests.length, 0);
});

for (const name of ["jku", "x5u", "jwk", "x5c"]) {
  test(`token ${name} header is rejected without following token key material`, async () => {
    const h = harness();
    const value = name === "jwk" ? first.jwk : name === "x5c" ? [] : "https://attacker.invalid/keys";
    await assert.rejects(h.verify(await sign(claims, first, { [name]: value })));
    assert.equal(h.requests.length, 0);
  });
}

test("Ed448 endpoint key is explicitly rejected despite EdDSA algorithm", async () => {
  const { publicKey } = generateKeyPairSync("ed448");
  const jwk = publicKey.export({ format: "jwk" });
  await assert.rejects(harness(() => response([{ ...jwk, kid: first.jwk.kid, alg: "EdDSA" }]))
    .verify(await sign()), /PAYMENT_KEYS_ED25519_REQUIRED/);
});

test("max-age freshness uses Age and refreshes exactly at expiry", async () => {
  const h = harness(() => response([first.jwk], "max-age=60", { age: "50" }));
  const token = await sign();
  await h.verify(token);
  h.advance(9999);
  await h.verify(token);
  assert.equal(h.requests.length, 1);
  h.advance(1);
  await h.verify(token);
  assert.equal(h.requests.length, 2);
});

test("Date apparent age and retrieval delay reduce freshness", async () => {
  const h = harness(() => {
    h.advance(2000);
    return response([first.jwk], "max-age=60", { date: new Date(epoch - 55000).toUTCString() });
  });
  const token = await sign();
  await h.verify(token);
  h.advance(2999);
  await h.verify(token);
  assert.equal(h.requests.length, 1);
  h.advance(1);
  await h.verify(token);
  assert.equal(h.requests.length, 2);
});

test("Age includes request delay, not just the received Age header", async () => {
  const h = harness(() => {
    h.advance(2000);
    return response([first.jwk], "max-age=60", { age: "55" });
  });
  const token = await sign();
  await h.verify(token);
  h.advance(2999);
  await h.verify(token);
  assert.equal(h.requests.length, 1);
  h.advance(1);
  await h.verify(token);
  assert.equal(h.requests.length, 2);
});

for (const [cache, headers] of [
  ["max-age=0", {}], ["max-age=60, no-cache", {}], ["max-age=60, no-store", {}],
  ["", {}], ["max-age=garbage", {}], ["max-age=60, max-age=600", {}],
  ["max-age=60", { age: "60" }], ["max-age=60", { age: "invalid" }]
]) {
  test(`no reusable keys for ${cache || "absent freshness"} / Age ${headers.age ?? "0"}`, async () => {
    const h = harness(() => response([first.jwk], cache, headers));
    const token = await sign();
    await h.verify(token);
    await h.verify(token);
    assert.equal(h.requests.length, 2);
  });
}

test("quoted max-age is honored", async () => {
  const h = harness(() => response([first.jwk], 'public, max-age="60"'));
  await h.verify(await sign());
  await h.verify(await sign());
  assert.equal(h.requests.length, 1);
});

test("rotation removes the old signer after expiry", async () => {
  const h = harness((call) => response([call === 1 ? first.jwk : second.jwk], "max-age=1"));
  await h.verify(await sign());
  h.advance(1000);
  await assert.rejects(h.verify(await sign()));
  await h.verify(await sign(claims, second));
  assert.equal(h.requests.length, 2);
});

test("unknown kid does not cause unbounded refreshes during fresh cache lifetime", async () => {
  const h = harness();
  await h.verify(await sign());
  await assert.rejects(h.verify(await sign(claims, second)));
  assert.equal(h.requests.length, 1);
});

for (const [name, badResponse] of [
  ["unavailable fetch", () => { throw new Error("offline"); }],
  ["HTTP error", () => new Response("unavailable", { status: 503 })],
  ["redirect", () => new Response(null, { status: 302, headers: { location: "https://attacker.invalid" } })],
  ["malformed JSON", () => new Response("{", { headers: { "content-type": "application/json" } })],
  ["wrong content type", () => new Response('{"keys":[]}')],
  ["empty keyset", () => response([])],
  ["non-JWKS JSON", () => new Response("null", { headers: { "content-type": "application/json" } })],
  ["oversized body", () => new Response(" ".repeat(65537), { headers: { "content-type": "application/json" } })],
  ["too many keys", () => response(Array(33).fill(first.jwk))],
  ["invalid public key", () => response([{ ...first.jwk, x: "invalid" }])],
  ["private key material", () => response([{ ...first.jwk, d: "forbidden" }])],
  ["wrong key algorithm", () => response([{ ...first.jwk, alg: "ES256" }])]
]) {
  test(`expired keys never survive ${name}; recovery fetch is allowed`, async () => {
    const h = harness((call) => call === 2 ? badResponse() : response([first.jwk], "max-age=1"));
    const token = await sign();
    await h.verify(token);
    h.advance(1000);
    await assert.rejects(h.verify(token));
    assert.equal(h.requests.length, 2);
    await h.verify(token);
    assert.equal(h.requests.length, 3);
  });
}

test("concurrent retrieval is coalesced even with no-store; later calls refetch", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const h = harness(async () => {
    await gate;
    return response([first.jwk], "no-store");
  });
  const token = await sign();
  const verifications = Array.from({ length: 12 }, () => h.verify(token));
  assert.equal(h.requests.length, 1);
  release();
  await Promise.all(verifications);
  await h.verify(token);
  assert.equal(h.requests.length, 2);
});

test("standard JWKS media type is accepted", async () => {
  await harness(() => response([first.jwk], "max-age=60", { "content-type": "application/jwk-set+json" }))
    .verify(await sign());
});

test("a followed redirect or mismatched response URL fails closed", async () => {
  for (const metadata of [{ redirected: true }, { url: "https://attacker.invalid/certs" }]) {
    const h = harness(() => {
      const result = response();
      for (const [name, value] of Object.entries(metadata)) {
        Object.defineProperty(result, name, { value });
      }
      return result;
    });
    await assert.rejects(h.verify(await sign()), /PAYMENT_KEYS_RESPONSE_INVALID/);
  }
});

for (const stage of ["fetch", "body"]) {
  test(`five-second retrieval bound rejects a stalled ${stage}`, async (t) => {
    const token = await sign();
    t.mock.timers.enable({ apis: ["setTimeout"] });
    let signal;
    const verify = createPaymentVerifier({
      now: () => epoch,
      fetch: async (_url, options) => {
        signal = options.signal;
        if (stage === "fetch") return new Promise(() => {});
        return new Response(new ReadableStream({ start() {} }), {
          headers: { "content-type": "application/json" }
        });
      }
    });
    const rejected = assert.rejects(verify(token), /PAYMENT_KEYS_FETCH_TIMEOUT/);
    t.mock.timers.tick(5000);
    await rejected;
    assert.equal(signal.aborted, true);
  });
}

test("concurrent failed refresh rejects every waiter without stale fallback", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const h = harness(async (call) => {
    if (call === 1) return response([first.jwk], "max-age=1");
    await gate;
    throw new Error("offline");
  });
  const token = await sign();
  await h.verify(token);
  h.advance(1000);
  const results = Promise.allSettled(Array.from({ length: 8 }, () => h.verify(token)));
  assert.equal(h.requests.length, 2);
  release();
  assert.ok((await results).every((result) => result.status === "rejected"));
});
