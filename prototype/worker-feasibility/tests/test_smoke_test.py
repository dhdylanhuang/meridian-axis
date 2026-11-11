"""Offline checks use an isolated synthetic loopback HTTP server."""

import argparse
import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import smoke_test

PROBE = {
    "scope": "synthetic-local-only",
    "decimal_quantity": "0.125000000000000000000001",
    "decimal_product": "1.55000000000000000000001240",
    "canonical_product": "1.5500000000000000000000124",
    "pydantic_json": {"quantity": "0.125000000000000000000001", "price": "12.40"},
    "sqlalchemy_dialect": "postgresql",
    "sql_compiled": "SELECT %s AS anon_1",
    "pg8000_imported": True,
    "mock_http": {"synthetic": True},
    "database_connected": False,
    "hosted_cpu_measured": False,
}


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.mode = "valid"
        self.paths = []
        self.user_agents = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                owner.paths.append(self.path)
                owner.user_agents.append(self.headers.get("User-Agent"))
                if owner.mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "/secret-target?token=private")
                    self.end_headers()
                    return
                payload = (
                    {"status": "ok", "scope": "synthetic-local-only"}
                    if self.path == "/health"
                    else dict(PROBE)
                )
                if self.path == "/probe" and owner.mode == "numeric":
                    payload["decimal_quantity"] = 0.125
                if self.path == "/probe" and owner.mode == "boolean":
                    payload["database_connected"] = 0
                if self.path == "/probe" and owner.mode == "nested_boolean":
                    payload["mock_http"] = {"synthetic": 1}
                body = json.dumps(payload).encode()
                if owner.mode == "invalid":
                    body = b"not json: private"
                if owner.mode == "oversize":
                    body = b" " * (smoke_test.MAX_RESPONSE_BYTES + 1)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                owner.paths.append("POST " + self.path)
                owner.user_agents.append(self.headers.get("User-Agent"))
                self.send_response(200 if owner.mode == "mutation" else 405)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_full_contract_and_post_denial(self):
        smoke_test.check_probe(self.origin, 2)
        self.assertEqual(self.paths, ["/health", "/probe", "POST /probe"])
        self.assertEqual(self.user_agents, ["MeridianAxis-SyntheticProbe/1.0"] * 3)

    def test_contract_failures(self):
        for mode in ("numeric", "boolean", "nested_boolean", "mutation", "invalid", "oversize"):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(smoke_test.ProbeFailure):
                    smoke_test.check_probe(self.origin, 2)

    def test_redirect_is_never_followed(self):
        self.mode = "redirect"
        with self.assertRaisesRegex(smoke_test.ProbeFailure, "redirected"):
            smoke_test.check_probe(self.origin, 2)
        self.assertEqual(self.paths, ["/health"])

    def test_cli_success(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            smoke_test.main(["--origin", self.origin, "--timeout", "2"])
        self.assertIn("this script measures no hosted CPU or database behavior", output.getvalue())

    def test_safe_network_error(self):
        output = io.StringIO()
        with (
            patch("smoke_test.check_probe", side_effect=OSError("private-secret")),
            contextlib.redirect_stderr(output),
            self.assertRaises(SystemExit) as raised,
        ):
            smoke_test.main([])
        self.assertEqual(raised.exception.code, 1)
        self.assertNotIn("private-secret", output.getvalue())


class InputTests(unittest.TestCase):
    def test_valid_origins(self):
        for origin in (smoke_test.ORIGIN, "https://meridian-axis-probe.synthetic.workers.dev"):
            self.assertEqual(smoke_test.validate_origin(origin + "/"), origin)

    def test_rejects_unsafe_origins_without_echoing_input(self):
        for value in (
            "https://private:secret@probe.example.workers.dev",
            "https://probe.example.workers.dev/?token=secret",
            "https://probe.example.workers.dev/#secret",
            "https://probe.example.workers.dev/path",
            "https://probe.example.workers.dev.evil.test",
            "http://probe.example.workers.dev",
            "https://example.com",
            "http://localhost:8791",
            "http://127.0.0.1:99999",
            "http://127.0.0.1:8791\n",
        ):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError) as raised:
                    smoke_test.validate_origin(value)
                self.assertNotIn("secret", str(raised.exception))

    def test_timeout_bounds(self):
        self.assertEqual(smoke_test.validate_timeout("20"), 20)
        for value in ("nan", "inf", "0", "-1", "61", "bad"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                smoke_test.validate_timeout(value)


if __name__ == "__main__":
    unittest.main()
