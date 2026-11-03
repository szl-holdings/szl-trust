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
  assert.equal(body.package_sha256, "1cb0a5b2b85243f6bb22eaf95b8fc4a50907a6171a4c32fe49c942b5f00e212f");
});

test("the package digest is deterministic", async () => {
  const options = { verify: async () => ({}) };
  const first = await (await handleRequest(request({ token: "one" }), options)).json();
  const second = await (await handleRequest(request({ token: "two" }), options)).json();
  assert.equal(first.package_sha256, second.package_sha256);
});

test("manifest notices distinguish historical public payload from operational processing", async () => {
  const response = await handleRequest(request({ token: "notice-test" }), {
    verify: async () => ({})
  });
  const body = await response.json();
  assert.equal(body.version, "2026-11-03");
  assert.equal(body.attribution.creator, "SZL Holdings");
  assert.equal(body.attribution.license, "CC-BY-4.0");
  assert.equal(body.attribution.license_url, "https://creativecommons.org/licenses/by/4.0/");
  for (const [field, file] of [["source_license_url", "LICENSE"], ["notice_url", "NOTICE"]]) {
    assert.equal(body.attribution[field], `https://github.com/szl-holdings/szl-trust/blob/${SOURCE_REVISION}/${file}`);
  }
  assert.match(body.attribution.changes, /not modified or embedded/);
  assert.match(body.attribution.trademark_notice, /does not grant trademark rights/);
  assert.equal(body.bounds.operation, "read_only_application_state");
  assert.match(body.bounds.effects, /No application-state writes/);
  assert.match(body.bounds.effects, /certificate retrieval and operational logging/);
  assert.match(body.bounds.private_data, /payment headers and request metadata are processed/);
  assert.match(body.bounds.processing, /https:\/\/payments.cloudflare.com\/certs/);
  assert.match(body.bounds.processing, /retention and provider payment processing are outside/);
  assert.match(body.bounds.claim, /Historical static/);
  assert.match(body.bounds.claim, /not model inference, live monitoring, or evidence of income/);
  assert.match(body.bounds.readiness, /unsigned deterministic digest/);
  assert.match(body.bounds.readiness, /payment settlement/);
  assert.equal(body.bounds.source_content_embedded, false);
  for (const key of ["operation", "effects", "private_data", "claim"]) {
    assert.equal(typeof body.bounds[key], "string");
  }
});

test("only the exact URL without a query is served", async () => {
  let calls = 0;
  for (const url of [
    `${AUDIENCE}/extra`, `${AUDIENCE}/`, `${AUDIENCE}?probe=1`,
    AUDIENCE.replace("a-11-oy.com", "other.example"),
    AUDIENCE.replace("https:", "http:"), AUDIENCE.replace("evidence-snapshot", "other")
  ]) {
    const response = await handleRequest(request({ url, token: "verified" }), {
      verify: async () => { calls++; }
    });
    assert.equal(response.status, 404);
  }
  assert.equal(calls, 0);
});

test("methods other than GET are rejected before payment validation", async () => {
  let calls = 0;
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]) {
    const response = await handleRequest(request({ method, token: "verified" }), {
      verify: async () => { calls++; }
    });
    assert.equal(response.status, 405);
    assert.equal(response.headers.get("allow"), "GET");
  }
  assert.equal(calls, 0);
});
