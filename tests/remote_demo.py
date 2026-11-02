"""Демо Tailscale с заглушкой CLI; настоящие APK/HTTP, временная БД, без моделей/Telegram."""
import android_demo as demo
from test_remote_access import running, served
import remote_access as ra

mode = "serve_configured"
original_check = ra.check


def command(cli, *args):
    if mode == "unavailable":
        raise OSError("Демо недоступной службы")
    if args[0] == "status":
        return {"BackendState": "NeedsLogin"} if mode == "needs_login" else running()
    if mode == "needs_serve":
        return {}
    value = served(demo.main.PORT)
    if mode == "funnel_detected":
        value["AllowFunnel"] = {"home.example.ts.net:443": True}
    return value


def check(port):
    result = original_check(port)
    result["message"] = "ДЕМО, заглушка Tailscale. " + result["message"]
    return result


@demo.main.route("POST", "/api/demo/remote")
def set_mode(h, body, query):
    global mode
    mode = body.get("mode", "serve_configured")
    assert mode in ("serve_configured", "not_installed", "needs_login", "needs_serve", "funnel_detected", "unavailable")
    return {"mode": mode, "stub_tailscale": True}


ra.executable = lambda: None if mode == "not_installed" else "demo-tailscale"
ra._json = command
ra.check = check

if __name__ == "__main__":
    demo.run()
