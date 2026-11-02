import assert from "node:assert/strict";
import test from "node:test";

import { AMOUNT_ATOMIC, AUDIENCE, INPUTS, SOURCE_REVISION, handleRequest } from "../src/index.mjs";

function request({ method = "GET", url = AUDIENCE, token } = {}) {
  const headers = token ? { "PAYMENT-CONTEXT": token } : {};
  return new Request(url, { method, headers });
}

test("missing payment context fails closed", async () => {
  const response = await handleRequest(request());
  assert.equal(response.status, 402);
  assert.deepEqual(await response.json(), {
    state: "PAYMENT_REQUIRED",
    sku: "evidence_snapshot_v1"
  });
});

test("invalid payment context fails closed without echoing the token", async () => {
  const response = await handleRequest(request({ token: "secret-payment-token" }), {
    verify: async () => { throw new Error("invalid"); }
  });
  assert.equal(response.status, 403);
  assert.equal(await response.text(), '{"state":"PAYMENT_CONTEXT_INVALID"}');
});

test("a verified exact payment returns the bounded ten-input manifest", async () => {
  let observedToken;
  const response = await handleRequest(request({ token: "verified-token" }), {
    verify: async (token) => { observedToken = token; return {}; }
  });
  assert.equal(observedToken, "verified-token");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("PAYMENT-SETTLEMENT"), null);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  const body = await response.json();
  assert.equal(body.schema, "szl.evidence-snapshot.v1");
  assert.equal(body.source.revision, SOURCE_REVISION);
  assert.equal(body.price.amount_atomic, AMOUNT_ATOMIC);
  assert.equal(body.inputs.length, 10);
  assert.deepEqual(body.inputs, INPUTS);
  assert.match(body.package_sha256, /^[0-9a-f]{64}$/);
});

test("the package digest is deterministic", async () => {
  const options = { verify: async () => ({}) };
  const first = await (await handleRequest(request({ token: "one" }), options)).json();
  const second = await (await handleRequest(request({ token: "two" }), options)).json();
  assert.equal(first.package_sha256, second.package_sha256);
});

test("only the exact URL without a query is served", async () => {
  for (const url of [`${AUDIENCE}/extra`, `${AUDIENCE}?probe=1`]) {
    const response = await handleRequest(request({ url, token: "verified" }), {
      verify: async () => ({})
    });
    assert.equal(response.status, 404);
  }
});

test("methods other than GET are rejected before payment validation", async () => {
  const response = await handleRequest(request({ method: "POST", token: "verified" }), {
    verify: async () => { throw new Error("must not run"); }
  });
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET");
});
