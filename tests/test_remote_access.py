"""Безопасная диагностика Tailscale: только заглушки CLI и отдельная база."""
import json
import subprocess
import unittest
from unittest.mock import patch

import test_pipeline as fixture
import remote_access as ra


def running():
    return {"BackendState": "Running", "Self": {"DNSName": "home.example.ts.net."},
            "User": {"secret": "private-user"}, "Peer": {"secret": "private-device"}}


def served(port=8765):
    return {"TCP": {"443": {"HTTPS": True}},
            "Web": {"home.example.ts.net:443": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{port}"}}}}}


class RemoteTests(unittest.TestCase):
    def check(self, status=None, config=None, port=8765):
        with patch.object(ra, "executable", return_value="tailscale"), patch.object(ra, "_json", side_effect=[status or running(), config if config is not None else served(port)]):
            return ra.check(port)

    def test_private_route_and_custom_port(self):
        for port in (8765, 8989):
            r = self.check(port=port)
            self.assertEqual(r["url"], "https://home.example.ts.net")
            self.assertEqual(r["status"], "serve_configured")
            self.assertIn(f"127.0.0.1:{port}", r["command"])
            self.assertEqual(r["acl"], "not_checked")
            self.assertNotIn("private-", json.dumps(r))

    def test_absent_login_and_command_failures_do_not_break_tracker(self):
        with patch.object(ra, "executable", return_value=None), patch.object(ra.runtime, "run") as run:
            self.assertEqual(ra.check(8765)["status"], "not_installed")
            run.assert_not_called()
        self.assertEqual(self.check({"BackendState": "NeedsLogin"})["status"], "needs_login")
        for error in (OSError("secret"), ValueError("secret"), subprocess.TimeoutExpired("secret", 4), RuntimeError("stop")):
            with patch.object(ra, "executable", return_value="tailscale"), patch.object(ra.runtime, "run", side_effect=error):
                r = ra.check(8765)
                self.assertEqual(r["status"], "unavailable")
                self.assertNotIn("secret", json.dumps(r))
                self.assertIsNone(r["url"])

    def test_wrong_routes_never_return_address(self):
        for config in ({}, served(1234), {"TCP": {"443": {"HTTPS": False}}, "Web": served()["Web"]},
                       {"Foreground": {"session": served()}}, {"TCP": None}):
            r = self.check(config=config)
            self.assertIsNone(r["url"])
            self.assertIn(r["status"], ("needs_serve", "unavailable"))
        config = served()
        config["Web"]["home.example.ts.net:443"]["Handlers"]["/other"] = {"Path": "/private"}
        self.assertEqual(self.check(config=config)["status"], "needs_serve")
        self.assertEqual(self.check(config={**served(), "Foreground": {"session": served()}})["status"], "needs_serve")
        self.assertEqual(self.check(config={**served(), "AllowFunnel": "unknown"})["status"], "unavailable")

    def test_funnel_is_blocked_in_background_foreground_and_other_port(self):
        for public in ({"AllowFunnel": {"home.example.ts.net:443": True}},
                       {"Foreground": {"session": {"AllowFunnel": {"home.example.ts.net:8443": True}}}}):
            r = self.check(config={**served(), **public})
            self.assertEqual(r["status"], "funnel_detected")
            self.assertIsNone(r["url"])
        self.assertEqual(self.check(config={**served(), "AllowFunnel": {"home.example.ts.net:443": False}})["status"], "serve_configured")

    def test_invalid_dns_not_reflected(self):
        for name in ("localhost", "example.com", "bad/<script>.ts.net", "a.ts.net", "user:pass@a.b.ts.net"):
            r = self.check({"BackendState": "Running", "Self": {"DNSName": name}})
            self.assertEqual(r["status"], "needs_dns")
            self.assertIsNone(r["url"])

    def test_cli_only_reads_status_with_timeout_and_no_shell(self):
        def run(args, **kw):
            self.assertIn(args[1:], (["status", "--json"], ["serve", "status", "--json"]))
            self.assertEqual(kw["stdin"], subprocess.DEVNULL)
            self.assertEqual(kw["timeout"], 4)
            self.assertFalse(kw.get("shell"))
            return subprocess.CompletedProcess(args, 0, json.dumps(running() if args[1] == "status" else served()), "")
        with patch.object(ra, "executable", return_value="tailscale"), patch.object(ra.runtime, "run", side_effect=run):
            self.assertEqual(ra.check(8765)["status"], "serve_configured")
        with patch.object(ra.runtime, "run", return_value=subprocess.CompletedProcess([], 0, "null", "")):
            self.assertEqual(ra._json("tailscale", "serve", "status", "--json"), {})

    def test_busy_and_api_no_settings_or_models_mutated(self):
        before = fixture.db.get_settings()
        with ra._slot, patch.object(ra.runtime, "run") as run:
            self.assertEqual(fixture.main.api_remote_access(None, {}, {})["status"], "busy")
            run.assert_not_called()
        with patch.object(ra, "executable", return_value=None), patch.object(fixture.pl, "agent_run") as model:
            self.assertEqual(fixture.main.api_remote_access(None, {}, {})["status"], "not_installed")
            model.assert_not_called()
        self.assertEqual(before, fixture.db.get_settings())


if __name__ == "__main__":
    unittest.main()
