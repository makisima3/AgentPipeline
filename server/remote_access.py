"""Диагностика Tailscale без входа, изменения сети и запросов к удалённому адресу."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import runtime

_slot = threading.Lock()


def executable():
    found = shutil.which("tailscale")
    if found:
        return found
    if os.name == "nt":
        path = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe"
        if path.is_file():
            return str(path)
    return None


def _json(cli, *args):
    result = runtime.run([cli, *args], stdin=subprocess.DEVNULL, capture_output=True,
                         timeout=4, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError("command")
    value = json.loads(result.stdout)
    if value is None and args == ("serve", "status", "--json"):
        return {}
    if not isinstance(value, dict):
        raise ValueError("schema")
    return value


def _funnel(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "AllowFunnel":
                if item is not None and (not isinstance(item, dict) or any(type(v) is not bool for v in item.values())):
                    raise ValueError("schema")
                if item and any(item.values()):
                    return True
            if _funnel(item):
                return True
    elif isinstance(value, list):
        return any(_funnel(item) for item in value)
    return False


def inspect(status, config, port):
    """Только проверенные поля, без пользователей, peers и сырых ошибок CLI."""
    base = {"status": "needs_login", "url": None, "acl": "not_checked", "phone": "not_checked"}
    if status.get("BackendState") != "Running":
        return {**base, "message": "Открой Tailscale на ПК, войди и включи подключение. Затем повтори проверку."}
    if _funnel(config):
        return {**base, "status": "funnel_detected", "message": "Обнаружен публичный Funnel на этом ПК. Отключи его в Tailscale перед настройкой закрытого доступа; адрес не выдаётся."}
    if config.get("Foreground"):
        return {**base, "status": "needs_serve", "message": "Есть временная сессия Serve. Проверь её в исходном терминале и заверши перед настройкой постоянного Serve с --bg. Адрес пока не выдаётся."}
    name = (status.get("Self", {}).get("DNSName") or "").rstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\.ts\.net", name):
        return {**base, "status": "needs_dns", "message": "Включи MagicDNS в панели Tailscale и проверь подключение ПК. Закрытое DNS-имя пока не получено."}
    host = name + ":443"
    tcp = config.get("TCP", {}).get("443", {})
    handlers = config.get("Web", {}).get(host, {}).get("Handlers", {})
    proxy = handlers.get("/", {}).get("Proxy")
    if tcp.get("HTTPS") is not True or proxy not in (f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port}/") or set(handlers) != {"/"}:
        return {**base, "status": "needs_serve", "message": "Tailscale подключён. Нужен HTTPS Serve на порту 443 с единственным маршрутом / к локальному трекеру. Проверь текущие маршруты перед командой ниже."}
    return {**base, "status": "serve_configured", "url": "https://" + name,
            "message": "Найден HTTPS Serve к этому трекеру; Funnel в конфигурации не включён. Права tailnet и подключение телефона ещё не проверены."}


def check(port):
    base = {"status": "unavailable", "url": None, "acl": "not_checked", "phone": "not_checked",
            "target": f"http://127.0.0.1:{port}", "command": f"tailscale serve --bg --https=443 http://127.0.0.1:{port}"}
    if not _slot.acquire(blocking=False):
        return {**base, "status": "busy", "message": "Проверка уже идёт. Повтори через несколько секунд."}
    try:
        cli = executable()
        if not cli:
            return {**base, "status": "not_installed", "message": "Tailscale CLI не найден на ПК. Установи Tailscale, войди в него и повтори проверку. Обычная работа трекера доступна."}
        status = _json(cli, "status", "--json")
        config = _json(cli, "serve", "status", "--json") if status.get("BackendState") == "Running" else {}
        return {**base, **inspect(status, config, port)}
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError, RuntimeError):
        return {**base, "message": "Не удалось проверить Tailscale. Проверь службу, вход и версию CLI на ПК; выполни tailscale status и tailscale serve status вручную."}
    finally:
        _slot.release()
