import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { exportJWK, generateKeyPair, SignJWT } from "jose";

import { createPaymentContextVerifier } from "../src/payment-context.mjs";
import { dataPoint, handleRequest } from "../src/index.mjs";

const trusted = await generateKeyPair("EdDSA");
const untrusted = await generateKeyPair("EdDSA");
const trustedJwk = { ...await exportJWK(trusted.publicKey), kid: "cf-1", alg: "EdDSA" };
const epoch = Date.UTC(2026, 10, 6);
const seconds = epoch / 1000;
const URL_PAID = "https://inference.a-11-oy.com/v1/completions";
const REVISION = "0123456789abcdef0123456789abcdef01234567";

function verifier() {
  return createPaymentContextVerifier({
    now: () => epoch,
    fetch: async () => new Response(JSON.stringify({ keys: [trustedJwk] }), {
      headers: { "content-type": "application/json", "cache-control": "max-age=300" }
    })
  });
}

function token({ key = trusted.privateKey, ...overrides } = {}) {
  return new SignJWT({
    aud: URL_PAID, scheme: "exact", amount: "20000",
    iat: seconds, nbf: seconds, exp: seconds + 120, ...overrides
  }).setProtectedHeader({ alg: "EdDSA", kid: "cf-1" }).sign(key);
}

function environment() {
  const points = [];
  return {
    points,
    env: {
      SOURCE_REVISION: REVISION,
      PAYMENT_CONTEXT_ISSUER: "",
      REVENUE_EVENTS: { writeDataPoint: (point) => points.push(structuredClone(point)) }
    }
  };
}

function context() {
  const pending = [];
  return { pending, ctx: { waitUntil: (promise) => pending.push(promise) }, settle: () => Promise.all(pending) };
}

function origin({ status = 200, headers = {}, body = "origin body" } = {}) {
  const seen = [];
  return {
    seen,
    fetchOrigin: async (request) => {
      seen.push(request);
      return new Response(body, { status, headers });
    }
  };
}

async function run({ request, response = {}, verify = verifier(), env } = {}) {
  const store = env ?? environment();
  const upstream = origin(response);
  const background = context();
  const result = await handleRequest(request, store.env, background.ctx, { verify, fetchOrigin: upstream.fetchOrigin });
  await background.settle();
  return { result, points: store.points, seen: upstream.seen, background };
}

const sha256 = (value) => createHash("sha256").update(value).digest("hex");

test("client-supplied payment headers are never trusted or counted", async () => {
  const request = new Request(URL_PAID, {
    method: "POST",
    headers: {
      "x-payment-verified": "1",
      "x-payment-required": "1",
      "cf-bot": "1",
      "payment-settlement": '{"amount":"100000000"}',
      "content-type": "application/json"
    },
    body: '{"prompt":"hi"}'
  });
  const { result, points, seen } = await run({ request });
  assert.deepEqual(points, []);
  assert.equal(result.status, 200);
  assert.equal(await result.text(), "origin body");
  assert.equal(seen.length, 1);
  assert.equal(seen[0], request, "the original request object is forwarded unchanged");
  assert.equal(seen[0].headers.get("x-payment-verified"), "1");
});

test("a forged PAYMENT-CONTEXT is recorded as rejected and counts zero", async () => {
  const forged = await token({ key: untrusted.privateKey, amount: "100000000" });
  const { result, points, seen } = await run({ request: new Request(URL_PAID, { headers: { "payment-context": forged } }) });
  assert.equal(result.status, 200);
  assert.equal(seen[0].headers.get("payment-context"), forged, "the origin still validates it itself");
  assert.deepEqual(points, [dataPoint("payment_context_rejected", {
    audience: URL_PAID, reason: "signature", tokenSha256: sha256(forged), revision: REVISION, status: 200
  })]);
  assert.deepEqual(points[0].doubles, [0, 0, 0, 200]);
});

test("a verified exact context counts its authorized amount without the token", async () => {
  const jwt = await token();
  const { points } = await run({ request: new Request(`${URL_PAID}?stream=1`, { headers: { "payment-context": jwt } }) });
  assert.equal(points.length, 1);
  assert.deepEqual(points[0], {
    indexes: ["payment_authorized"],
    blobs: [URL_PAID, "exact", "", sha256(jwt), "", REVISION],
    doubles: [20000, 0, 0, 200]
  });
  assert.equal(JSON.stringify(points).includes(jwt), false);
});

test("a token for another resource is rejected for this one", async () => {
  const jwt = await token({ aud: "https://inference.a-11-oy.com/v1/responses" });
  const { points } = await run({ request: new Request(URL_PAID, { headers: { "payment-context": jwt } }) });
  assert.equal(points[0].indexes[0], "payment_context_rejected");
  assert.equal(points[0].blobs[2], "audience");
});

test("an origin settlement for a verified upto context is counted, capped, and passed through", async () => {
  const jwt = await token({ scheme: "upto", amount: "100000" });
  const request = () => new Request(URL_PAID, { headers: { "payment-context": jwt } });

  const reported = await run({ request: request(), response: { headers: { "PAYMENT-SETTLEMENT": '{"amount":"25000"}' } } });
  assert.equal(reported.result.headers.get("payment-settlement"), '{"amount":"25000"}', "the gateway still needs it");
  assert.deepEqual(reported.points.map((point) => point.indexes[0]), ["payment_authorized", "settlement_reported"]);
  assert.deepEqual(reported.points[1].doubles, [100000, 25000, 25000, 200]);
  assert.equal(reported.points[1].blobs[2], "");

  const capped = await run({ request: request(), response: { headers: { "payment-settlement": '{"amount":"250000"}' } } });
  assert.deepEqual(capped.points[1].doubles, [100000, 250000, 100000, 200]);
  assert.equal(capped.points[1].blobs[2], "capped_at_authorized");

  const zero = await run({ request: request(), response: { headers: { "payment-settlement": '{"amount":"0"}' } } });
  assert.deepEqual(zero.points[1].doubles, [100000, 0, 0, 200]);
});

test("settlements that the gateway would not honour count zero with a reason", async () => {
  const upto = await token({ scheme: "upto", amount: "100000" });
  const exact = await token();
  for (const [jwt, response, reason] of [
    [upto, { status: 500, headers: { "payment-settlement": '{"amount":"1000"}' } }, "error_status"],
    [upto, { status: 404, headers: { "payment-settlement": '{"amount":"1000"}' } }, "error_status"],
    [exact, { headers: { "payment-settlement": '{"amount":"1000"}' } }, "not_variable_pricing"],
    [upto, { headers: { "payment-settlement": "1000" } }, "malformed"],
    [upto, { headers: { "payment-settlement": '{"amount":1000}' } }, "malformed"],
    [upto, { headers: { "payment-settlement": '{"amount":"01000"}' } }, "malformed"],
    [upto, { headers: { "payment-settlement": '{"amount":"1000","extra":true}' } }, "malformed"],
    [upto, { headers: { "payment-settlement": `{"amount":"${"9".repeat(300)}"}` } }, "malformed"]
  ]) {
    const { points } = await run({ request: new Request(URL_PAID, { headers: { "payment-context": jwt } }), response });
    assert.equal(points[1].indexes[0], "settlement_ignored", reason);
    assert.equal(points[1].blobs[2], reason);
    assert.deepEqual(points[1].doubles.slice(1, 3), [0, 0]);
  }
});

test("a settlement without a verified context is an anomaly, never revenue", async () => {
  const withoutContext = await run({
    request: new Request(URL_PAID),
    response: { headers: { "payment-settlement": '{"amount":"5000"}' } }
  });
  assert.deepEqual(withoutContext.points, [dataPoint("settlement_ignored", {
    audience: URL_PAID, reason: "no_payment_context", tokenSha256: "", revision: REVISION, status: 200
  })]);

  const forged = await token({ key: untrusted.privateKey, scheme: "upto", amount: "100000" });
  const withForgery = await run({
    request: new Request(URL_PAID, { headers: { "payment-context": forged } }),
    response: { headers: { "payment-settlement": '{"amount":"5000"}' } }
  });
  assert.deepEqual(withForgery.points.map((point) => [point.indexes[0], point.blobs[2]]), [
    ["payment_context_rejected", "signature"],
    ["settlement_ignored", "context_not_verified"]
  ]);
  assert.equal(withForgery.points.every((point) => point.doubles[1] === 0 && point.doubles[2] === 0), true);
});

test("verification never delays or alters the origin response", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const slow = async () => { await gate; return { scheme: "exact", amount: 20000, issuer: null }; };
  const store = environment();
  const background = context();
  const upstream = origin({ status: 201, headers: { "x-origin": "kept" } });
  const response = await handleRequest(
    new Request(URL_PAID, { headers: { "payment-context": "opaque.token.value" } }),
    store.env,
    background.ctx,
    { verify: slow, fetchOrigin: upstream.fetchOrigin }
  );
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("x-origin"), "kept");
  assert.deepEqual(store.points, [], "nothing is recorded before verification finishes");
  release();
  await background.settle();
  assert.equal(store.points[0].indexes[0], "payment_authorized");
});

test("an issuer pinned in configuration is enforced", async () => {
  const store = environment();
  store.env.PAYMENT_CONTEXT_ISSUER = "https://payments.cloudflare.com";
  const { points } = await run({ request: new Request(URL_PAID, { headers: { "payment-context": await token() } }), env: store });
  assert.equal(points[0].indexes[0], "payment_context_rejected");
  assert.equal(points[0].blobs[2], "issuer");
});

test("missing or failing Analytics Engine never breaks traffic", async (t) => {
  const logged = [];
  t.mock.method(console, "error", (line) => logged.push(JSON.parse(line)));
  const jwt = await token();

  const unbound = await run({
    request: new Request(URL_PAID, { headers: { "payment-context": jwt } }),
    env: { points: [], env: { SOURCE_REVISION: REVISION } }
  });
  assert.equal(unbound.result.status, 200);

  const failing = await run({
    request: new Request(URL_PAID, { headers: { "payment-context": jwt } }),
    env: { points: [], env: { REVENUE_EVENTS: { writeDataPoint() { throw new TypeError("quota"); } } } }
  });
  assert.equal(failing.result.status, 200);
  assert.deepEqual(logged, [
    { event: "revenue_tracker_unconfigured", dropped: 1 },
    { event: "revenue_event_write_failed", error_class: "TypeError" }
  ]);
  assert.equal(JSON.stringify(logged).includes(jwt), false);
});

test("an origin transport failure propagates and is recorded with status 0", async () => {
  const store = environment();
  const background = context();
  await assert.rejects(
    handleRequest(new Request(URL_PAID, { headers: { "payment-context": await token() } }), store.env, background.ctx, {
      verify: verifier(),
      fetchOrigin: async () => { throw new TypeError("origin unreachable"); }
    }),
    /origin unreachable/
  );
  await background.settle();
  assert.equal(store.points[0].indexes[0], "payment_authorized");
  assert.equal(store.points[0].doubles[3], 0);
});

test("unpaid traffic without settlement writes nothing and schedules nothing", async () => {
  const { points, background } = await run({ request: new Request(URL_PAID) });
  assert.deepEqual(points, []);
  assert.equal(background.pending.length, 0);
});
