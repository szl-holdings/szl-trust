import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

// The tracker reuses the evidence-snapshot Worker's reviewed JWKS resolver
// verbatim. Each Worker deploys as its own bundle, so the file is copied; this
// test fails the moment the two copies diverge.
const tracker = new URL("../src/payment-keys.mjs", import.meta.url);
const snapshot = new URL("../../evidence-snapshot-worker/src/payment-keys.mjs", import.meta.url);

test("payment-keys.mjs is byte-identical to the evidence-snapshot verifier", () => {
  const digest = (url) => createHash("sha256").update(readFileSync(url)).digest("hex");
  assert.equal(digest(tracker), digest(snapshot));
});
