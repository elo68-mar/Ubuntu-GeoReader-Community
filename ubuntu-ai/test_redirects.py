"""Offline redirect regression tests. The only sockets bind to IPv4 loopback."""
import contextlib
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request

import ubuntu_ai as u

# Synthetic test markers only, never real credentials.
FAKE_AUTH = "Bearer synthetic-auth-test-marker"
FAKE_KEY = "synthetic-api-key-test-marker"
FAKE_BODY = "synthetic-body-test-marker"


class LocalServer:
    def __init__(self):
        self.records = []
        self.status = 200
        self.location = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                owner.records.append((self.command, self.path, dict(self.headers), body))
                self.send_response(owner.status)
                if owner.location is not None:
                    self.send_header("Location", owner.location)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.server.server_port

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class RedirectTests(unittest.TestCase):
    def test_handler_rejects_every_3xx_and_origin_transition(self):
        # Pure unit test: includes HTTPS downgrade without contacting any host.
        targets = ["https://source.example/same", "https://source.example:444/port",
                   "http://source.example/downgrade", "https://other.example/cross-host"]
        handler = u.NoRedirectHandler()
        for method in ("GET", "POST"):
            for code in range(300, 400):
                for target in targets:
                    with self.subTest(method=method, code=code, target=target):
                        req = Request("https://source.example/start", method=method,
                                      headers={"Authorization": FAKE_AUTH, "X-API-Key": FAKE_KEY})
                        req.add_unredirected_header("Authorization", FAKE_AUTH)
                        self.assertIsNone(handler.redirect_request(req, None, code, "", {}, target))

    def test_all_3xx_rejected_before_cross_port_get_or_post(self):
        # Use a different server/port on the same host to detect credential leakage.
        with patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}), LocalServer() as source, LocalServer() as sink:
            source.location = sink.base + "/redirect-target"
            for method in ("GET", "POST"):
                for code in range(300, 400):
                    with self.subTest(method=method, code=code):
                        source.status = code
                        before = len(source.records)
                        payload = {"content": FAKE_BODY} if method == "POST" else None
                        with self.assertRaises(u.ResearchError) as caught:
                            u.http_json(source.base + "/start", payload,
                                        {"aUtHoRiZaTiOn": FAKE_AUTH, "X-aPi-KeY": FAKE_KEY})
                        self.assertEqual(len(source.records), before + 1)
                        self.assertEqual(source.records[-1][0], method)
                        self.assertFalse(sink.records, "redirect target was contacted")
                        for secret in (FAKE_AUTH, FAKE_KEY, FAKE_BODY):
                            self.assertNotIn(secret, str(caught.exception))

    def test_same_origin_cross_host_and_redirect_chain_never_followed(self):
        with patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}), LocalServer() as source, LocalServer() as sink:
            source.status = 302
            for location in ("/relative", source.base + "/same-origin",
                             sink.base.replace("127.0.0.1", "localhost") + "/different-host"):
                with self.subTest(location=location):
                    source.location = location
                    before = len(source.records)
                    with self.assertRaises(u.ResearchError):
                        u.http_json(source.base + "/start", headers={"x-api-key": FAKE_KEY})
                    self.assertEqual(len(source.records), before + 1)
                    self.assertFalse(sink.records)
            # Even an anonymous first hop cannot reach a second redirect.
            source.location = sink.base + "/second-hop"
            sink.status = 302
            sink.location = source.base + "/third-hop"
            before = len(source.records)
            with self.assertRaises(u.ResearchError):
                u.http_json(source.base + "/first-hop")
            self.assertEqual(len(source.records), before + 1)
            self.assertFalse(sink.records)

    def test_successful_direct_requests_and_header_delivery(self):
        with patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}), LocalServer() as source:
            self.assertEqual(u.http_json(source.base + "/get", headers={"Authorization": FAKE_AUTH}), {"ok": True})
            self.assertEqual(u.http_json(source.base + "/post", {"content": FAKE_BODY}, {"x-api-key": FAKE_KEY}), {"ok": True})
            self.assertEqual(source.records[0][2].get("Authorization"), FAKE_AUTH)
            self.assertEqual(source.records[1][2].get("X-Api-Key"), FAKE_KEY)
            self.assertEqual(json.loads(source.records[1][3]), {"content": FAKE_BODY})

    def test_redirect_error_does_not_expose_location_or_secret(self):
        with patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}), LocalServer() as source:
            source.status = 302
            source.location = "/target?secret=" + FAKE_KEY
            output = io.StringIO()
            with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
                with self.assertRaises(u.ResearchError) as caught:
                    u.http_json(source.base + "/start?secret=" + FAKE_KEY, headers={"x-api-key": FAKE_KEY})
            self.assertNotIn(FAKE_KEY, str(caught.exception))
            self.assertNotIn(FAKE_KEY, output.getvalue())


if __name__ == "__main__":
    unittest.main()
