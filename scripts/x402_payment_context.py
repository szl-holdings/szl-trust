#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
# Offline x402 PAYMENT-CONTEXT validator. Not a payment gateway and not charging.

"""Validate Cloudflare Monetization Gateway PAYMENT-CONTEXT tokens.

The pinned JWKS is https://payments.cloudflare.com/certs. Callers pass keys
already fetched from that URL. A token-supplied jku, jwk, x5u, or x5c is
rejected and is never requested. Production charging cannot be enabled by a
boolean in this module.
"""

from __future__ import annotations

import json
import re
from typing import Mapping

import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    InvalidTokenError,
)

PINNED_JWKS_URL = "https://payments.cloudflare.com/certs"
MIN_ATOMIC = 1_000
MAX_ATOMIC = 100_000_000
PROPOSED_EVIDENCE_SNAPSHOT_ATOMIC = 10_000
PAID_PATH = "/api/v1/evidence-snapshot"
FREE_PATHS = frozenset({
    "/",
    "/healthz",
    "/api/build-info",
    "/api/a11oy/healthz",
    "/.well-known/szl-source.json",
    "/robots.txt",
    "/sitemap.xml",
    "/.well-known/security.txt",
    "/security.txt",
    "/.well-known/mcp.json",
})
FORBIDDEN_HEADER_PARAMS = frozenset({"jku", "jwk", "x5u", "x5c"})
_AMOUNT = re.compile(r"0|[1-9][0-9]*")


class PaymentHold(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def production_charging_enabled(_record: Mapping | None = None) -> bool:
    """This source revision cannot turn charging on."""
    return False


def is_free_path(path: str) -> bool:
    return path in FREE_PATHS


def is_explicit_paid_path(path: str, method: str) -> bool:
    return method == "GET" and path == PAID_PATH


def reject_blanket_rule(path: str) -> None:
    if path in {"/*", "/api/*", "/mcp", "/mcp/*"} or path.endswith("/*"):
        raise PaymentHold("BLANKET_PAYMENT_RULE")


def _header(token: str) -> dict:
    if not isinstance(token, str):
        raise PaymentHold("MALFORMED_TOKEN")
    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise PaymentHold("MALFORMED_TOKEN")
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise PaymentHold("MALFORMED_TOKEN") from exc
    if not isinstance(header, dict):
        raise PaymentHold("MALFORMED_TOKEN")
    if header.get("alg") != "EdDSA":
        raise PaymentHold("WRONG_ALGORITHM")
    if FORBIDDEN_HEADER_PARAMS.intersection(header):
        raise PaymentHold("TOKEN_SUPPLIED_KEY_MATERIAL")
    return header


def _amount(value: object) -> int:
    if type(value) is not str or _AMOUNT.fullmatch(value) is None:
        raise PaymentHold("MALFORMED_AMOUNT")
    amount = int(value)
    if amount < MIN_ATOMIC or amount > MAX_ATOMIC:
        raise PaymentHold("AMOUNT_OUT_OF_BOUNDS")
    return amount


def validate_payment_context(
    token: str,
    *,
    keys: Mapping[str, object],
    expected_audience: str,
    now: int,
    scheme: str,
    leeway: int = 0,
) -> dict:
    """Return verified claims. `now` is reserved for callers that log the check."""
    del now
    if scheme not in {"exact", "upto"}:
        raise PaymentHold("UNKNOWN_SCHEME")
    if type(leeway) is not int or leeway < 0 or leeway > 120:
        raise PaymentHold("BAD_LEEWAY")
    if not isinstance(expected_audience, str) or not expected_audience:
        raise PaymentHold("BAD_AUDIENCE")
    header = _header(token)
    kid = header.get("kid")
    if not isinstance(kid, str) or kid not in keys:
        raise PaymentHold("UNKNOWN_KEY")
    try:
        claims = jwt.decode(
            token,
            keys[kid],
            algorithms=["EdDSA"],
            audience=expected_audience,
            leeway=leeway,
            options={
                "require": ["exp", "nbf", "iat", "aud"],
                "verify_signature": True,
                "verify_aud": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
            },
        )
    except ExpiredSignatureError as exc:
        raise PaymentHold("EXPIRED") from exc
    except ImmatureSignatureError as exc:
        raise PaymentHold("NOT_YET_VALID") from exc
    except InvalidAudienceError as exc:
        raise PaymentHold("WRONG_AUDIENCE") from exc
    except InvalidSignatureError as exc:
        raise PaymentHold("BAD_SIGNATURE") from exc
    except InvalidTokenError as exc:
        raise PaymentHold("INVALID_TOKEN") from exc
    if type(claims.get("aud")) is not str or claims.get("aud") != expected_audience:
        raise PaymentHold("WRONG_AUDIENCE")
    if claims.get("scheme") != scheme:
        raise PaymentHold("WRONG_SCHEME")
    amount = _amount(claims.get("amount"))
    return {
        "audience": claims["aud"],
        "scheme": scheme,
        "amount": amount,
        "iat": claims["iat"],
        "nbf": claims["nbf"],
        "exp": claims["exp"],
        "kid": kid,
        "settlement_evidence": False,
    }


def settlement_value(*, scheme: str, status_code: int, actual: int, authorized: int) -> str | None:
    """Header value for a future activated upto response. Exact pricing sets nothing."""
    if type(status_code) is not int:
        raise PaymentHold("BAD_STATUS")
    if status_code >= 400 or scheme == "exact":
        return None
    if scheme != "upto":
        raise PaymentHold("UNKNOWN_SCHEME")
    if type(actual) is not int or type(authorized) is not int:
        raise PaymentHold("INTEGER_ATOMIC_AMOUNTS_REQUIRED")
    if not 0 <= actual <= authorized:
        raise PaymentHold("AMOUNT_OUT_OF_BOUNDS")
    return json.dumps({"amount": str(actual)}, separators=(",", ":"))


def emit_production_settlement(**_kwargs: object) -> None:
    if production_charging_enabled() is not False:
        raise PaymentHold("ACTIVATION_PATH_INVALID")
    raise PaymentHold("COMMERCIAL_NOT_ENABLED")


def decide_delivery(*, path: str, method: str, context: dict | None) -> dict:
    """Fail closed. A valid context still does not deliver paid bytes."""
    reject_blanket_rule(path)
    if production_charging_enabled() is not False:
        raise PaymentHold("ACTIVATION_PATH_INVALID")
    if method == "OPTIONS" and (is_free_path(path) or path == PAID_PATH):
        return {
            "http_status": 204,
            "state": "DISCOVERY",
            "body": None,
            "cache_control": "private, no-store",
            "settlement": None,
        }
    if is_free_path(path) and method in {"GET", "HEAD"}:
        return {
            "http_status": 200,
            "state": "FREE",
            "body": None if method == "HEAD" else "PUBLIC",
            "cache_control": "public, max-age=60",
            "settlement": None,
        }
    if path == PAID_PATH and method in {"GET", "HEAD"}:
        state = "COMMERCIAL_NOT_ENABLED" if context else "UNPAID"
        return {
            "http_status": 403 if context else 402,
            "state": state,
            "body": None,
            "cache_control": "private, no-store",
            "settlement": None,
        }
    return {
        "http_status": 404,
        "state": "NOT_A_PAID_ROUTE",
        "body": None,
        "cache_control": "no-store",
        "settlement": None,
    }
