#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
"""Two-axis x402 commerce truth envelope (pure Python, offline, no authority).

This computes *conditional* cohort conservation bounds from sanitized, supplied
final-observation records. It does not verify a provider signature, tx finality,
payer identity, revenue, deployment, or the claimed source SHA. In particular,
a hash is not a signature. No network access, keys, payments, or provider writes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from fractions import Fraction

SCHEMA = "szl.x402-truth-envelope/v1"
RESULT_SCHEMA = "szl.x402-truth-envelope-result/v1"
PHASES = frozenset(
    {
        "CHALLENGED",
        "AUTHORIZED",
        "PRODUCED",
        "SETTLEMENT_PENDING",
        "SETTLEMENT_REPORTED",
        "DISPUTED",
        "REFUNDED",
        "FAILED",
        "CANCELLED",
    }
)
UNCERTAIN = frozenset(
    {
        "CHALLENGED",
        "AUTHORIZED",
        "PRODUCED",
        "SETTLEMENT_PENDING",
        "DISPUTED",
    }
)
TERMINAL_NOT_REVENUE = frozenset({"FAILED", "CANCELLED", "REFUNDED"})
SETTLEMENT = frozenset({"SETTLEMENT_REPORTED", "REFUNDED"})
INPUT_KEYS = frozenset(
    {
        "schema",
        "source_revision",
        "provider_export_sha256",
        "observed_at_utc",
        "population_count",
        "unobserved_cap_atomic",
        "denomination",
        "records",
    }
)
RECORD_KEYS = frozenset(
    {
        "request_hmac_sha256",
        "phase",
        "authorized_cap_atomic",
        "reported_settlement_atomic",
        "provider_receipt_sha256",
    }
)
DENOMINATION_KEYS = frozenset({"network_caip2", "asset_id", "asset_decimals"})
CAIP2 = re.compile(r"[-a-z0-9]{3,8}:[-_a-zA-Z0-9]{1,32}\Z")
ASSET = re.compile(r"[-a-z0-9]{2,16}:[-._A-Za-z0-9]{1,128}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEXSHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
MAX_INPUT_BYTES = 2_000_000
MAX_RECORDS = 20_000
MAX_POPULATION = 100_000_000
MAX_ATOMIC = 10**18
RECENT_SOURCE_AGE_SECONDS = 24 * 60 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60


class EnvelopeHold(ValueError):
    """Stable, non-sensitive diagnostic code; no raw input in exception."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EnvelopeHold("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(_value):
    raise EnvelopeHold("NONFINITE_JSON")


def _unsigned(value, maximum=MAX_ATOMIC):
    return type(value) is int and 0 <= value <= maximum


def _parse_utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EnvelopeHold("UTC_TIMESTAMP_REQUIRED")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvelopeHold("UTC_TIMESTAMP_REQUIRED") from exc
    if result.utcoffset() != dt.timedelta(0):
        raise EnvelopeHold("UTC_TIMESTAMP_REQUIRED")
    return result


def _source_observation_time(observed_at_utc, reference_time=None):
    """Classify the *declared* timestamp; never authenticate the provider.

    Historical evidence remains usable for offline conditional mathematics,
    but must never be represented as a fresh payment or a current receipt.
    An observation farther than the allowed UTC clock skew into the future
    fails closed before source-reported settlement counts are returned.
    """
    observed = _parse_utc(observed_at_utc)
    now = dt.datetime.now(dt.timezone.utc) if reference_time is None else reference_time
    if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise EnvelopeHold("OBSERVER_CLOCK_UNAVAILABLE")
    difference = (
        now.astimezone(dt.timezone.utc) - observed.astimezone(dt.timezone.utc)
    ).total_seconds()
    if difference < -MAX_CLOCK_SKEW_SECONDS:
        raise EnvelopeHold("SOURCE_OBSERVATION_IN_FUTURE")

    historical = difference > RECENT_SOURCE_AGE_SECONDS
    if difference < 0:
        state = "CLOCK_SKEW_TOLERATED_NOT_AUTHENTICATED"
    elif historical:
        state = "HISTORICAL_SOURCE_TIMESTAMP"
    else:
        state = "RECENT_TIMESTAMP_ONLY_NOT_AUTHENTICATED"
    return {
        "source_snapshot_temporal_state": state,
        "source_snapshot_age_seconds": max(0, int(difference)),
        "source_snapshot_stale_for_current_claims": historical,
        "current_provider_state_verified": False,
        "observed_at_verified_by_provider": False,
    }


def _ratio(numerator: int, denominator: int) -> str | None:
    if denominator == 0:
        return None
    part = Fraction(numerator, denominator)
    return f"{part.numerator}/{part.denominator}"


def _decode(raw: bytes):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise EnvelopeHold("INPUT_BYTE_LIMIT")
    try:
        decoded = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise EnvelopeHold("INVALID_JSON") from exc
    if not isinstance(decoded, dict) or set(decoded) != INPUT_KEYS:
        raise EnvelopeHold("UNKNOWN_OR_MISSING_TOP_LEVEL_FIELD")
    if decoded["schema"] != SCHEMA:
        raise EnvelopeHold("UNSUPPORTED_SCHEMA")
    if not isinstance(decoded["source_revision"], str) or not HEXSHA.fullmatch(decoded["source_revision"]):
        raise EnvelopeHold("IMMUTABLE_SOURCE_REQUIRED")
    sha = decoded["provider_export_sha256"]
    if not isinstance(sha, str) or not HEX64.fullmatch(sha):
        raise EnvelopeHold("PROVIDER_EXPORT_DIGEST_REQUIRED")
    _parse_utc(decoded["observed_at_utc"])
    count = decoded["population_count"]
    if count is not None and not _unsigned(count, MAX_POPULATION):
        raise EnvelopeHold("INVALID_POPULATION")
    cap = decoded["unobserved_cap_atomic"]
    if cap is not None and not _unsigned(cap):
        raise EnvelopeHold("INVALID_UNOBSERVED_CAP")
    # Atomic sums are meaningful only inside a single supplied denomination.
    denom = decoded["denomination"]
    if not isinstance(denom, dict) or set(denom) != DENOMINATION_KEYS:
        raise EnvelopeHold("DENOMINATION_REQUIRED")
    net, asset, decimals = (denom["network_caip2"], denom["asset_id"], denom["asset_decimals"])
    if not isinstance(net, str) or not CAIP2.fullmatch(net):
        raise EnvelopeHold("CAIP2_NETWORK_REQUIRED")
    if not isinstance(asset, str) or not ASSET.fullmatch(asset):
        raise EnvelopeHold("ASSET_ID_REQUIRED")
    if not _unsigned(decimals, 36):
        raise EnvelopeHold("ASSET_DECIMALS_REQUIRED")
    rows = decoded["records"]
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise EnvelopeHold("RECORD_BUDGET")
    if count is not None and len(rows) > count:
        raise EnvelopeHold("OBSERVED_EXCEEDS_POPULATION")
    seen = set()
    for item in rows:
        if not isinstance(item, dict) or set(item) != RECORD_KEYS:
            raise EnvelopeHold("UNKNOWN_OR_MISSING_RECORD_FIELD")
        request = item["request_hmac_sha256"]
        if not isinstance(request, str) or not HEX64.fullmatch(request):
            raise EnvelopeHold("OPAQUE_REQUEST_HMAC_REQUIRED")
        if request in seen:
            raise EnvelopeHold("DUPLICATE_REQUEST")
        seen.add(request)
        phase = item["phase"]
        if not isinstance(phase, str) or phase not in PHASES:
            raise EnvelopeHold("UNSUPPORTED_PHASE")
        authorized = item["authorized_cap_atomic"]
        if not _unsigned(authorized):
            raise EnvelopeHold("INVALID_AUTHORIZED_CAP")
        amount = item["reported_settlement_atomic"]
        receipt = item["provider_receipt_sha256"]
        if phase in SETTLEMENT:
            if not _unsigned(amount) or amount > authorized:
                raise EnvelopeHold("SETTLEMENT_AMOUNT_OUTSIDE_CAP")
            if not isinstance(receipt, str) or not HEX64.fullmatch(receipt):
                raise EnvelopeHold("SETTLEMENT_RECEIPT_HASH_REQUIRED")
        elif amount is not None or receipt is not None:
            # A signed receipt would need its own checked verification path,
            # so unrecognized claims must never silently upgrade other phases.
            raise EnvelopeHold("UNBOUND_SETTLEMENT_METADATA")
    return decoded


def envelope(raw: bytes, *, reference_time=None) -> dict:
    data = _decode(raw)
    source_time = _source_observation_time(
        data["observed_at_utc"], reference_time=reference_time
    )
    rows = data["records"]
    observed = len(rows)
    population = data["population_count"]
    missing = None if population is None else population - observed
    by_phase = {phase: 0 for phase in sorted(PHASES)}
    reported_gross = 0
    speculative_cap = 0
    for item in rows:
        phase = item["phase"]
        by_phase[phase] += 1
        if phase == "SETTLEMENT_REPORTED":
            reported_gross += item["reported_settlement_atomic"]
        elif phase in UNCERTAIN:
            speculative_cap += item["authorized_cap_atomic"]
    possible_count = sum(by_phase[p] for p in UNCERTAIN)
    # Refunds, failures and cancellations cannot count as reported net revenue.
    reported_settled = by_phase["SETTLEMENT_REPORTED"]
    if missing is not None:
        possible_count += missing
    upper_count = None if missing is None else reported_settled + possible_count
    max_extra = data["unobserved_cap_atomic"]
    if missing is None or (missing and max_extra is None):
        upper_atomic = None
    else:
        upper_atomic = reported_gross + speculative_cap + missing * (max_extra or 0)
    reasons = [
        "PROVIDER_EXPORT_AUTHENTICITY_UNVERIFIED",
        "SOURCE_TO_RUNTIME_IDENTITY_UNVERIFIED",
        "ONCHAIN_FINALITY_AND_REFUNDS_UNVERIFIED",
    ]
    if population is None:
        reasons.append("COHORT_DENOMINATOR_UNOBSERVED")
    elif missing:
        reasons.append("INCOMPLETE_COHORT_COVERAGE")
    if upper_atomic is None:
        reasons.append("POTENTIAL_REVENUE_UPPER_UNAVAILABLE")
    if source_time["source_snapshot_stale_for_current_claims"]:
        reasons.append("HISTORICAL_SOURCE_EXPORT_REQUIRES_CURRENT_READBACK")
    if source_time["source_snapshot_temporal_state"] == "CLOCK_SKEW_TOLERATED_NOT_AUTHENTICATED":
        reasons.append("SOURCE_CLOCK_SKEW_NOT_INDEPENDENTLY_VERIFIED")
    if by_phase["DISPUTED"] or by_phase["REFUNDED"]:
        reasons.append("NET_REFUND_AND_DISPUTE_ACCOUNTING_UNVERIFIED")
    return {
        "schema": RESULT_SCHEMA,
        "observed_at_utc": data["observed_at_utc"],
        "source_revision": data["source_revision"],
        "provider_export_sha256": data["provider_export_sha256"],
        **source_time,
        "denomination_as_declared": data["denomination"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "validation": "STRUCTURAL_ONLY_NOT_PROVIDER_OR_CHAIN_VERIFIED",
        "financial_revenue_verified_atomic": None,
        "production_qualified": False,
        "observed_request_count": observed,
        "population_count_as_declared": population,
        "unobserved_request_count": missing,
        "phase_counts": by_phase,
        "source_reported_settlement_count": reported_settled,
        "source_reported_settlement_atomic": reported_gross,
        "conditional_eventual_settlement_count_range": {
            "lower": reported_settled,
            "upper": upper_count,
        },
        "conditional_eventual_settlement_rate_range": {
            "lower_exact": None if population is None else _ratio(reported_settled, population),
            "upper_exact": None if upper_count is None else _ratio(upper_count, population),
            "unit": "source-reported events per declared cohort request",
        },
        "conditional_gross_atomic_range": {
            "lower_source_reported": reported_gross,
            "upper_possible_if_caps_and_population_true": upper_atomic,
            "unit": "atomic units of denomination_as_declared (not independently verified)",
        },
        "next_evidence_gates": reasons,
        "limitations": (
            "Hypothetical interval conditional on supplied final-phase rows, "
            "claimed population and caps. Hashes do not authenticate providers. "
            "No confirmed revenue, transaction finality, actual conversions, "
            "unobserved data or refunds are inferred. Supplied network, asset "
            "and decimals are not authenticated."
        ),
    }


def main() -> int:
    # Bound CLI input; never echo raw records or the potentially sensitive source.
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    try:
        result = envelope(raw)
    except EnvelopeHold as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
