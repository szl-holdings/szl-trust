#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
# Append-only usage ledger. Recognizes no revenue until a settled record remains settled.

"""Idempotent billing-event lifecycle for a proposed read-only SKU.

The ledger stores no raw payment signature and no request payload. Duplicate
retries with the same event identity return the original record. A different
body under the same event identity is a conflict, not a second charge.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

class LedgerHold(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


TRANSITIONS = {
    "AUTHORIZED": {"PRODUCED", "FAILED", "CANCELLED"},
    "PRODUCED": {"SETTLEMENT_PENDING", "FAILED", "CANCELLED"},
    "SETTLEMENT_PENDING": {"SETTLED", "FAILED", "DISPUTED"},
    "SETTLED": {"DISPUTED", "REFUNDED"},
    "FAILED": set(),
    "CANCELLED": set(),
    "DISPUTED": {"REFUNDED", "SETTLED"},
    "REFUNDED": set(),
}

REQUIRED = (
    "event_id",
    "request_id",
    "tenant_id",
    "principal_id",
    "sku",
    "sku_version",
    "route",
    "request_digest",
    "source_revision",
    "provider_revision",
    "quantity",
    "unit",
    "quoted_max_atomic",
    "currency",
    "network",
    "asset",
    "policy_version",
    "decision_id",
    "occurred_at",
)


def _canonical(row: Mapping) -> bytes:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _views(lifecycle: str) -> tuple[str, str]:
    if lifecycle in {"AUTHORIZED", "PRODUCED"}:
        return "AUTHORIZED", "NOT_STARTED"
    if lifecycle == "SETTLEMENT_PENDING":
        return "AUTHORIZED", "PENDING"
    if lifecycle == "SETTLED":
        return "AUTHORIZED", "SETTLED"
    if lifecycle == "REFUNDED":
        return "AUTHORIZED", "REFUNDED"
    if lifecycle == "DISPUTED":
        return "AUTHORIZED", "DISPUTED"
    if lifecycle == "CANCELLED":
        return "CANCELLED", "NOT_STARTED"
    return "REJECTED", "FAILED"


class UsageLedger:
    def __init__(self, cap_atomic: int) -> None:
        if type(cap_atomic) is not int or cap_atomic < 0:
            raise LedgerHold("BAD_CAP")
        self.cap_atomic = cap_atomic
        self._by_event: dict[str, dict] = {}
        self._by_request: dict[tuple[str, str], str] = {}

    def authorize(self, fields: Mapping, *, payment_signature=None, raw_payload=None) -> dict:
        if payment_signature is not None or raw_payload is not None:
            raise LedgerHold("FORBIDDEN_SENSITIVE_FIELD")
        missing = [name for name in REQUIRED if name not in fields]
        if missing:
            raise LedgerHold("MISSING_FIELD")
        quoted = fields["quoted_max_atomic"]
        quantity = fields["quantity"]
        if type(quoted) is not int or type(quantity) is not int:
            raise LedgerHold("INTEGER_REQUIRED")
        if quoted < 0 or quantity < 0:
            raise LedgerHold("NEGATIVE_QUANTITY")
        if quoted > self.cap_atomic:
            raise LedgerHold("COST_CAP")
        event_id = fields["event_id"]
        request_key = (fields["tenant_id"], fields["request_id"])
        proposed = dict(fields)
        proposed["lifecycle"] = "AUTHORIZED"
        proposed["actual_atomic"] = None
        proposed["provider_reference"] = None
        proposed["evidence_digest"] = None
        auth, settle = _views("AUTHORIZED")
        proposed["authorization_state"] = auth
        proposed["settlement_state"] = settle
        digest = hashlib.sha256(_canonical(proposed)).hexdigest()
        existing = self._by_event.get(event_id)
        if existing is not None:
            if existing["record_digest"] != digest:
                raise LedgerHold("DUPLICATE_CONFLICT")
            return dict(existing)
        prior = self._by_request.get(request_key)
        if prior is not None:
            raise LedgerHold("REPLAY")
        proposed["record_digest"] = digest
        self._by_event[event_id] = proposed
        self._by_request[request_key] = event_id
        return dict(proposed)

    def transition(self, event_id: str, lifecycle: str, **updates: object) -> dict:
        row = self._by_event.get(event_id)
        if row is None:
            raise LedgerHold("UNKNOWN_EVENT")
        if lifecycle not in TRANSITIONS.get(row["lifecycle"], ()):
            raise LedgerHold("ILLEGAL_TRANSITION")
        if "payment_signature" in updates or "raw_payload" in updates:
            raise LedgerHold("FORBIDDEN_SENSITIVE_FIELD")
        if "actual_atomic" in updates and type(updates["actual_atomic"]) is not int:
            raise LedgerHold("INTEGER_REQUIRED")
        if "actual_atomic" in updates:
            actual = updates["actual_atomic"]
            if actual < 0 or actual > row["quoted_max_atomic"]:
                raise LedgerHold("AMOUNT_OUT_OF_BOUNDS")
        row = dict(row)
        row.update(updates)
        row["lifecycle"] = lifecycle
        auth, settle = _views(lifecycle)
        row["authorization_state"] = auth
        row["settlement_state"] = settle
        stored = dict(row)
        stored.pop("record_digest", None)
        row["record_digest"] = hashlib.sha256(_canonical(stored)).hexdigest()
        self._by_event[event_id] = row
        return dict(row)

    def for_tenant(self, tenant_id: str) -> list[dict]:
        return [dict(row) for row in self._by_event.values() if row["tenant_id"] == tenant_id]

    def recognized_revenue_atomic(self) -> int:
        total = 0
        for row in self._by_event.values():
            if row["lifecycle"] == "SETTLED":
                actual = row.get("actual_atomic")
                if type(actual) is not int:
                    raise LedgerHold("UNPRICED_SETTLEMENT")
                total += actual
        return total
