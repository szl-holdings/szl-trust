"""Offline contract for the Workers API post-deploy readback (no network)."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_worker_deployment as readback  # noqa: E402

ACCOUNT = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
TOKEN = "synthetic-test-token-not-a-credential"
SHA = "0123456789abcdef0123456789abcdef01234567"
OLD_SHA = "fedcba9876543210fedcba9876543210fedcba98"
VERSION = "11111111-2222-4333-8444-555555555555"
REQUIRED = [("REVENUE_EVENTS", "analytics_engine")]


def deployments(*versions):
    entries = [{"version_id": vid, "percentage": pct} for vid, pct in versions] or [
        {"version_id": VERSION, "percentage": 100}
    ]
    return {"deployments": [{"id": "d1", "source": "wrangler", "strategy": "percentage", "versions": entries}]}


def version(revision=SHA, extra=None, drop=()):
    bindings = [
        {"name": "SOURCE_REVISION", "type": "plain_text", "text": revision},
        {"name": "REVENUE_EVENTS", "type": "analytics_engine", "dataset": "szl_revenue_events"},
        {"name": "PAYMENT_CONTEXT_ISSUER", "type": "plain_text", "text": ""},
    ]
    bindings = [b for b in bindings if b["name"] not in drop] + list(extra or [])
    return {"id": VERSION, "resources": {"bindings": bindings}}


class Api:
    """Scripted Workers API: answers are consumed in request order."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.paths = []

    def __call__(self, path, token):
        assert token == TOKEN
        self.paths.append(path)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def run(answers, attempts=3):
    api = Api(answers)
    sleeps = []
    try:
        result = readback.verify(
            token=TOKEN, account_id=ACCOUNT, script="szl-revenue-tracker", revision=SHA,
            required=REQUIRED, attempts=attempts, interval=5, get=api, sleep=sleeps.append,
        )
        return result, api, sleeps
    except readback.ReadbackError as error:
        return error, api, sleeps


class VerifyTests(unittest.TestCase):
    def test_exact_revision_at_full_rollout_passes(self):
        result, api, sleeps = run([deployments(), version()])
        self.assertIsInstance(result, readback.Result)
        self.assertEqual(result.revision, SHA)
        self.assertEqual(api.paths, [
            f"/accounts/{ACCOUNT}/workers/scripts/szl-revenue-tracker/deployments",
            f"/accounts/{ACCOUNT}/workers/scripts/szl-revenue-tracker/versions/{VERSION}",
        ])
        self.assertEqual(sleeps, [])

    def test_stale_revision_is_retried_then_fails_with_both_shas(self):
        error, api, sleeps = run([deployments(), version(OLD_SHA)] * 3)
        self.assertEqual(error.category, "REVISION_MISMATCH")
        self.assertIn(OLD_SHA, error.detail)
        self.assertIn(SHA, error.detail)
        self.assertEqual(len(api.paths), 6)
        self.assertEqual(sleeps, [5, 5])

    def test_propagation_then_success(self):
        result, _, sleeps = run([deployments(), version(OLD_SHA), deployments(), version()])
        self.assertIsInstance(result, readback.Result)
        self.assertEqual(sleeps, [5])

    def test_partial_rollout_never_passes(self):
        split = deployments((VERSION, 50), ("22222222-2222-4333-8444-555555555555", 50))
        error, _, _ = run([split] * 3)
        self.assertEqual(error.category, "NOT_FULLY_ROLLED_OUT")
        partial = deployments((VERSION, 99.5))
        error, _, _ = run([partial] * 3)
        self.assertEqual(error.category, "NOT_FULLY_ROLLED_OUT")

    def test_missing_revision_or_required_binding_fails(self):
        error, _, _ = run([deployments(), version(drop=("SOURCE_REVISION",))] * 3)
        self.assertEqual(error.category, "BINDING_MISSING")
        error, _, _ = run([deployments(), version(drop=("REVENUE_EVENTS",))])
        self.assertEqual(error.category, "BINDING_MISSING")
        self.assertIn("REVENUE_EVENTS", error.detail)
        wrong_type = version(drop=("REVENUE_EVENTS",), extra=[{"name": "REVENUE_EVENTS", "type": "plain_text", "text": "x"}])
        error, _, _ = run([deployments(), wrong_type])
        self.assertEqual(error.category, "BINDING_MISSING")

    def test_a_secret_named_source_revision_is_not_evidence(self):
        secret = version(drop=("SOURCE_REVISION",), extra=[{"name": "SOURCE_REVISION", "type": "secret_text"}])
        error, _, _ = run([deployments(), secret] * 3)
        self.assertEqual(error.category, "BINDING_MISSING")

    def test_non_sha_live_values_are_not_echoed(self):
        error, _, _ = run([deployments(), version("d739c95b")] * 3)
        self.assertEqual(error.category, "REVISION_MISMATCH")
        self.assertIn("<not a commit SHA>", error.detail)

    def test_empty_or_invalid_deployment_lists_fail(self):
        error, _, _ = run([{"deployments": []}] * 3)
        self.assertEqual(error.category, "NO_DEPLOYMENT")
        bad = {"deployments": [{"versions": [{"version_id": "../../zones", "percentage": 100}]}]}
        error, api, _ = run([bad])
        self.assertEqual(error.category, "INVALID_RESPONSE")
        self.assertEqual(len(api.paths), 1, "an unsafe version id must never become a request path")

    def test_auth_failures_are_terminal_and_transient_errors_retry(self):
        error, api, _ = run([readback.ReadbackError("HTTP_STATUS", "status=403", False)])
        self.assertEqual(error.category, "HTTP_STATUS")
        self.assertEqual(len(api.paths), 1)
        result, _, _ = run([readback.ReadbackError("TRANSPORT_ERROR", retryable=True), deployments(), version()])
        self.assertIsInstance(result, readback.Result)


class Body(io.BytesIO):
    """A readable urllib-style response usable as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ApiGetTests(unittest.TestCase):
    def opener(self, answer):
        seen = []

        def open_request(request, timeout):
            seen.append(request)
            if isinstance(answer, BaseException):
                raise answer
            return answer

        def create(handler):
            self.assertIsInstance(handler, readback.NoRedirectHandler)
            return SimpleNamespace(open=open_request)

        return create, seen

    def get(self, answer):
        create, seen = self.opener(answer)
        with mock.patch.object(readback, "build_opener", create):
            return readback.api_get("/accounts/x/workers/scripts/y/deployments", TOKEN), seen

    def test_bearer_token_goes_only_to_the_api_host(self):
        result, seen = self.get(Body(json.dumps({"success": True, "result": {"ok": 1}}).encode()))
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(seen[0].full_url, "https://api.cloudflare.com/client/v4/accounts/x/workers/scripts/y/deployments")
        self.assertEqual(seen[0].get_header("Authorization"), f"Bearer {TOKEN}")

    def test_http_and_payload_failures_are_categorised(self):
        cases = [
            (HTTPError("u", 403, "forbidden", Message(), BytesIO(b"{}")), "HTTP_STATUS", False),
            (HTTPError("u", 503, "unavailable", Message(), BytesIO(b"")), "HTTP_STATUS", True),
            (HTTPError("u", 302, "found", Message(), BytesIO(b"")), "HTTP_STATUS", False),
            (URLError("reset"), "TRANSPORT_ERROR", True),
            (Body(b"not json"), "INVALID_RESPONSE", False),
            (Body(json.dumps({"success": False, "errors": [{"code": 10000}]}).encode()), "UNSUCCESSFUL_RESPONSE", False),
            (Body(json.dumps({"success": True, "result": []}).encode()), "INVALID_RESPONSE", False),
            (Body(b" " * (readback.MAX_RESPONSE_BYTES + 1)), "RESPONSE_TOO_LARGE", False),
        ]
        for answer, category, retryable in cases:
            with self.subTest(category=category, answer=type(answer).__name__):
                with self.assertRaises(readback.ReadbackError) as caught:
                    self.get(answer)
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(caught.exception.retryable, retryable)
        with self.assertRaises(readback.ReadbackError) as caught:
            self.get(HTTPError("u", 403, "forbidden", Message(), BytesIO(b"")))
        self.assertIn("Workers Scripts", caught.exception.detail)


class MainTests(unittest.TestCase):
    def invoke(self, argv, env):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = readback.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_inputs_are_validated_before_any_request(self):
        argv = ["--script", "szl-revenue-tracker", "--expect-revision", SHA]
        good_env = {"CLOUDFLARE_API_TOKEN": TOKEN, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT}
        with mock.patch.object(readback, "api_get", side_effect=AssertionError("no request")):
            for bad_argv, env in [
                (argv, {}),
                (argv, {"CLOUDFLARE_API_TOKEN": TOKEN, "CLOUDFLARE_ACCOUNT_ID": "not-an-account"}),
                (["--script", "Bad Name", "--expect-revision", SHA], good_env),
                (["--script", "szl-revenue-tracker", "--expect-revision", SHA[:8]], good_env),
                (argv + ["--require-binding", "lower:analytics_engine"], good_env),
                (argv + ["--attempts", "0"], good_env),
            ]:
                code, _, err = self.invoke(bad_argv, env)
                self.assertEqual(code, 2)
                self.assertIn("::error::", err)
                self.assertNotIn(TOKEN, err)

    def test_success_and_failure_output_never_contains_secrets(self):
        env = {"CLOUDFLARE_API_TOKEN": TOKEN, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT}
        argv = ["--script", "szl-revenue-tracker", "--expect-revision", SHA,
                "--require-binding", "REVENUE_EVENTS:analytics_engine", "--attempts", "1"]
        with mock.patch.object(readback, "api_get", side_effect=Api([deployments(), version()])):
            code, out, err = self.invoke(argv, env)
        self.assertEqual(code, 0)
        self.assertIn(SHA, out)
        with mock.patch.object(readback, "api_get", side_effect=Api([deployments(), version(OLD_SHA)])):
            code, out, err = self.invoke(argv, env)
        self.assertEqual(code, 1)
        self.assertIn("REVISION_MISMATCH", err)
        for secret in (TOKEN, ACCOUNT):
            self.assertNotIn(secret, out + err)


if __name__ == "__main__":
    unittest.main()
