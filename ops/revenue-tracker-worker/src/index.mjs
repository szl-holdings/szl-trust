// szl-revenue-tracker: a transparent pass-through that records payment events
// to Analytics Engine, counting only what is cryptographically or
// origin-attested:
//
//   payment_authorized       a PAYMENT-CONTEXT JWT verified against the pinned
//                            Cloudflare JWKS (Ed25519, audience = this resource,
//                            exp/nbf enforced, optional pinned issuer);
//   settlement_reported      a PAYMENT-SETTLEMENT the origin's response carried
//                            for a verified `upto` authorization;
//   payment_context_rejected a PAYMENT-CONTEXT that failed verification (0 counted);
//   settlement_ignored       an origin settlement that is not countable (0 counted).
//
// Client-supplied state headers (x-payment-verified, x-payment-required, cf-bot,
// a request-side PAYMENT-SETTLEMENT, ...) are never read. The request and the
// origin response pass through unchanged, and recording happens in waitUntil,
// so verification adds no latency and cannot block or alter traffic. None of
// this is settlement evidence: Monetization Gateway settles payments and
// issues receipts; this Worker only observes the request/response pair.

import {
  audienceFor,
  createPaymentContextVerifier,
  rejectionReason,
} from "./payment-context.mjs";
import { assessSettlement } from "./settlement.mjs";

export const WORKER_NAME = "szl-revenue-tracker";
const SOURCE_REVISION = /^[0-9a-f]{40}$/;
const MAX_AUDIENCE_CHARS = 1024;
const MAX_ISSUER_CHARS = 256;

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function sourceRevision(env) {
  const value = env?.SOURCE_REVISION;
  return typeof value === "string" && SOURCE_REVISION.test(value) ? value : "";
}

/**
 * Analytics Engine row. index1 = event; blobs = audience, scheme, reason,
 * token_sha256, issuer, source_revision; doubles = authorized_atomic,
 * reported_atomic, effective_atomic, origin_status. No token, IP, or UA.
 */
export function dataPoint(event, fields) {
  return {
    indexes: [event],
    blobs: [
      String(fields.audience ?? "").slice(0, MAX_AUDIENCE_CHARS),
      fields.scheme ?? "",
      fields.reason ?? "",
      fields.tokenSha256 ?? "",
      String(fields.issuer ?? "").slice(0, MAX_ISSUER_CHARS),
      fields.revision ?? "",
    ],
    doubles: [
      fields.authorized ?? 0,
      fields.reported ?? 0,
      fields.effective ?? 0,
      fields.status ?? 0,
    ],
  };
}

export function eventsFor({ verification, settlementHeader, status, audience, tokenSha256, revision }) {
  const base = { audience, tokenSha256, revision, status };
  const events = [];
  if (verification?.ok) {
    const { claims } = verification;
    const authorized = {
      ...base,
      scheme: claims.scheme,
      issuer: claims.issuer,
      authorized: claims.amount,
    };
    events.push(dataPoint("payment_authorized", authorized));
    if (settlementHeader !== null) {
      const settlement = assessSettlement({
        header: settlementHeader,
        scheme: claims.scheme,
        authorized: claims.amount,
        status,
      });
      events.push(
        settlement.ok
          ? dataPoint("settlement_reported", {
              ...authorized,
              reason: settlement.capped ? "capped_at_authorized" : "",
              reported: settlement.reported,
              effective: settlement.effective,
            })
          : dataPoint("settlement_ignored", { ...authorized, reason: settlement.reason }),
      );
    }
    return events;
  }
  if (verification) {
    events.push(dataPoint("payment_context_rejected", { ...base, reason: verification.reason }));
  }
  if (settlementHeader !== null) {
    events.push(
      dataPoint("settlement_ignored", {
        ...base,
        reason: verification ? "context_not_verified" : "no_payment_context",
      }),
    );
  }
  return events;
}

async function record(env, pending) {
  const events = eventsFor(await pending);
  if (events.length === 0) {
    return;
  }
  const dataset = env?.REVENUE_EVENTS;
  if (!dataset || typeof dataset.writeDataPoint !== "function") {
    console.error(JSON.stringify({ event: "revenue_tracker_unconfigured", dropped: events.length }));
    return;
  }
  for (const point of events) {
    try {
      dataset.writeDataPoint(point);
    } catch (error) {
      console.error(
        JSON.stringify({
          event: "revenue_event_write_failed",
          error_class: error instanceof Error ? error.name : "UnknownError",
        }),
      );
    }
  }
}

export async function handleRequest(
  request,
  env,
  ctx,
  { verify = verifyPaymentContext, fetchOrigin = (outgoing) => fetch(outgoing) } = {},
) {
  const url = new URL(request.url);
  const audience = audienceFor(url);
  const token = request.headers.get("payment-context");
  const issuer = typeof env?.PAYMENT_CONTEXT_ISSUER === "string" ? env.PAYMENT_CONTEXT_ISSUER : "";

  // Started before the origin fetch and never rejects, so it runs in parallel.
  const verification = token
    ? verify(token, { audience, issuer }).then(
        (claims) => ({ ok: true, claims }),
        (error) => ({ ok: false, reason: rejectionReason(error) }),
      )
    : Promise.resolve(null);
  const tokenSha256 = token ? sha256Hex(token) : Promise.resolve("");
  const revision = sourceRevision(env);

  let response;
  try {
    response = await fetchOrigin(request);
  } catch (error) {
    if (token) {
      ctx.waitUntil(
        record(env, Promise.all([verification, tokenSha256]).then(([outcome, digest]) => ({
          verification: outcome,
          settlementHeader: null,
          status: 0,
          audience,
          tokenSha256: digest,
          revision,
        }))),
      );
    }
    throw error;
  }

  const settlementHeader = response.headers.get("payment-settlement");
  if (token || settlementHeader !== null) {
    ctx.waitUntil(
      record(env, Promise.all([verification, tokenSha256]).then(([outcome, digest]) => ({
        verification: outcome,
        settlementHeader,
        status: response.status,
        audience,
        tokenSha256: digest,
        revision,
      }))),
    );
  }
  return response;
}

const verifyPaymentContext = createPaymentContextVerifier();

export default {
  fetch(request, env, ctx) {
    return handleRequest(request, env, ctx, { verify: verifyPaymentContext });
  },
};
