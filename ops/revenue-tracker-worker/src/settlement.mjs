// Reads the PAYMENT-SETTLEMENT header that the origin's *response* carries for
// a variable-price (`upto`) request. The tracker never alters it: the header is
// passed through untouched for Monetization Gateway, which settles and strips it.

const CANONICAL_AMOUNT = /^(0|[1-9][0-9]*)$/;
const MAX_HEADER_LENGTH = 256;

/**
 * Decide whether an origin-reported settlement is countable for a verified
 * authorization. Mirrors the gateway rules: only `upto`, only status < 400, the
 * value is `{"amount": "<atomic units>"}`, and anything above the authorized
 * maximum settles at that maximum.
 */
export function assessSettlement({ header, scheme, authorized, status }) {
  if (scheme !== "upto") {
    return { ok: false, reason: "not_variable_pricing" };
  }
  if (!Number.isInteger(status) || status >= 400) {
    return { ok: false, reason: "error_status" };
  }
  if (typeof header !== "string" || header.length > MAX_HEADER_LENGTH) {
    return { ok: false, reason: "malformed" };
  }
  let value;
  try {
    value = JSON.parse(header);
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).length !== 1 ||
    typeof value.amount !== "string" ||
    !CANONICAL_AMOUNT.test(value.amount)
  ) {
    return { ok: false, reason: "malformed" };
  }
  const reported = Number(value.amount);
  if (!Number.isSafeInteger(reported)) {
    return { ok: false, reason: "malformed" };
  }
  return {
    ok: true,
    reported,
    effective: Math.min(reported, authorized),
    capped: reported > authorized,
  };
}
