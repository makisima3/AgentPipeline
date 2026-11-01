"""Выбор исполнителя и блокировка рабочей базы до её открытия."""
import atexit
import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

AGENT = os.environ.get("PIPELINE_AGENT", "claude").lower()
if "--agent" in sys.argv:
    AGENT = sys.argv[sys.argv.index("--agent") + 1].lower()
if AGENT not in ("claude", "codex"):
    raise SystemExit("Исполнитель должен быть claude или codex")
os.environ["PIPELINE_AGENT"] = AGENT
NAME = "Codex" if AGENT == "codex" else "Claude"
_instance = None
stopping = threading.Event()
launch_lock = threading.RLock()
processes = set()


def popen(*args, **kwargs):
    """Запуск под общим затвором остановки, включая служебные процессы."""
    with launch_lock:
        if stopping.is_set():
            raise RuntimeError("Сервер останавливается")
        if os.name != "nt":
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(*args, **kwargs)
        processes.difference_update(p for p in tuple(processes) if p.poll() is not None)
        processes.add(proc)
        return proc


def kill_process(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait(timeout=10)


def run(args, *, input=None, capture_output=False, timeout=None, **kwargs):
    """Аналог subprocess.run для отменяемой служебной работы."""
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc = popen(args, **kwargs)
    try:
        out, err = proc.communicate(input, timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    except BaseException:
        kill_process(proc)
        proc.communicate()
        raise
    finally:
        with launch_lock:
            processes.discard(proc)


def acquire():
    """Одна блокировка на папку data, независимо от порта и исполнителя."""
    global _instance
    folder = Path(__file__).resolve().parent.parent / "data"
    folder.mkdir(exist_ok=True)
    _instance = open(folder / "server.lock", "a+b")
    _instance.seek(0, 2)
    if not _instance.tell():
        _instance.write(b"0")
        _instance.flush()
    deadline = time.monotonic() + (90 if "--after" in sys.argv else 0)
    while True:
        try:
            _instance.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(_instance.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(_instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit("Трекер с этой базой уже запущен. Закрой его перед сменой исполнителя.")
            time.sleep(0.25)
    atexit.register(_instance.close)
