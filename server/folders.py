"""Просмотр серверных каталогов в ограниченном по времени отдельном процессе."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

TIMEOUT = 5
SLOTS = threading.BoundedSemaphore(4)


class FolderError(Exception):
    def __init__(self, message, code=400):
        self.code = code
        super().__init__(message)


def validate(path):
    if path is None:
        return None
    if not isinstance(path, str) or not path or len(path) > 32760 or any(ord(c) < 32 for c in path):
        raise FolderError("Укажите полный путь к папке на ПК с сервером")
    if os.name == "nt":
        path = path.replace("/", "\\")
        if path.startswith(("\\\\?\\", "\\\\.\\")) or ":" in path[2:]:
            raise FolderError("Служебные пути устройств не поддерживаются")
    if not os.path.isabs(path) or (os.name == "nt" and not os.path.splitdrive(path)[0]):
        raise FolderError("Нужен абсолютный путь, например C:\\Projects")
    return os.path.normpath(path)


def listing(path, check_only=False):
    """Только чтение; вызывается внутри рабочего процесса."""
    if path is None:
        if os.name == "nt":
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            roots = [f"{chr(65 + i)}:\\" for i in range(26) if mask & (1 << i)]
        else:
            roots = ["/"]
        home = str(Path.home())
        return {"path": None, "parent": None, "entries": [
            {"name": "Домашняя папка сервера" if p == home else p, "path": p} for p in dict.fromkeys([*roots, home])]}
    entries = []
    with os.scandir(native_path(path)) as scan:
        if check_only:
            return {"path": path}
        for entry in scan:
            try:
                if entry.is_dir():
                    entries.append({"name": entry.name, "path": os.path.join(path, entry.name)})
            except OSError:
                continue  # Каталог мог исчезнуть при просмотре родителя.
            if len(entries) > 20000:
                raise FolderError("Слишком много папок. Укажите более точный путь вручную", 413)
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else None,
            "entries": sorted(entries, key=lambda e: (e["name"].casefold(), e["name"]))}


def native_path(path):
    """Длинные пути Windows без требования менять системную политику."""
    if os.name != "nt":
        return path
    return "\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path


def browse(path=None, check_only=False):
    path = validate(path)
    if not SLOTS.acquire(blocking=False):
        raise FolderError("Просмотр папок занят. Повторите через несколько секунд", 429)
    try:
        import runtime
        out = runtime.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker"],
                          input=json.dumps({"path": path, "check_only": check_only}).encode("utf-8"), capture_output=True, timeout=TIMEOUT,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if out.returncode:
            raise FolderError("Не удалось прочитать папку. Повторите запрос", 503)
        result = json.loads(out.stdout)
        if "error" in result:
            raise FolderError(result["error"], result["code"])
        return result
    except subprocess.TimeoutExpired:
        raise FolderError("Папка не отвечает. Проверьте доступ к диску и повторите запрос", 504)
    finally:
        SLOTS.release()


def worker():
    try:
        data = json.loads(sys.stdin.buffer.read())
        result = listing(validate(data["path"]), data.get("check_only", False))
    except FolderError as e:
        result = {"error": str(e), "code": e.code}
    except PermissionError:
        result = {"error": "Нет прав на просмотр этой папки", "code": 403}
    except (FileNotFoundError, NotADirectoryError):
        result = {"error": "Папка не найдена или удалена. Выберите другую папку", "code": 404}
    except OSError:
        result = {"error": "Папка или диск недоступны. Проверьте подключение и права", "code": 503}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    worker()
