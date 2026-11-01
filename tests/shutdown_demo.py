"""Изолированный настоящий main.main с заглушками моделей/Telegram, для тестов остановки."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
OUTPUT = SOURCE / "output/playwright/task-47"
CHILD = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(600)']); print(p.pid,flush=True); time.sleep(600)"


def launch(root=None, port=0):
    root = Path(root) if root else Path(tempfile.mkdtemp(prefix="pipeline-shutdown-"))
    if not (root / "server").exists():
        for folder in ("server", "web"):
            shutil.copytree(SOURCE / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    if not port:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    env = {**os.environ, "PIPELINE_PORT": str(port), "PIPELINE_AGENT": "claude", "PYTHONIOENCODING": "utf-8"}
    log = (root / "demo.log").open("a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--child", str(root)], env=env,
                            stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log.close()
    for _ in range(150):
        if proc.poll() is not None:
            raise RuntimeError((root / "demo.log").read_text(encoding="utf-8"))
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=.3) as r:
                json.load(r)
            return proc, root, port
        except OSError:
            time.sleep(.1)
    raise RuntimeError("Демо не запустилось")


def child(root):
    sys.path.insert(0, str(Path(root) / "server"))
    import runtime
    runtime.acquire()
    import main
    import db
    import pipeline as pl

    class DemoRun:
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.killed = False
            self.finished = threading.Event()

        def start(self):
            self.proc = runtime.popen([sys.executable, "-u", "-c", CHILD], stdout=subprocess.PIPE,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            nested = int(self.proc.stdout.readline())
            pids.extend([self.proc.pid, nested])
            threading.Thread(target=self.wait, daemon=True).start()
            return self

        def wait(self):
            self.proc.wait()
            self.on_done({"killed": self.killed, "result": "Демо"})
            self.finished.set()

        def kill(self):
            self.killed = True
            runtime.kill_process(self.proc)

    pids = []
    pl.preflight = lambda: None
    pl.agent_run = lambda **kw: DemoRun(**kw)
    pl.titler.loop = lambda: None
    main.updater.loop = lambda: None
    # Боевые пути доставки и браузер Telegram никогда не вызываются.
    main.telegram.loop = lambda: None
    db.set_setting("telegram_auth", "unconfigured")
    if not db.q("SELECT id FROM projects"):
        pid = db.create_project("Демонстрация", str(root))
        db.set_setting("onboarding_status", "completed")
        db.set_setting("git_mode", "off")
        tid = db.create_task(pid, "Сохранённый результат")
        material = Path(root) / "result.txt"
        material.write_text("Материал сохранён до остановки", encoding="utf-8")
        pl.finish_task(tid, "Результат сохранён", "Неизменяемый отчёт", telegram_files=[str(material)])
    pid = db.q("SELECT id FROM projects")[0]["id"]

    @main.route("POST", "/api/demo/work")
    def work(h, body, query):
        tid = db.create_task(pid, "Активная демо-задача")
        with pl.orch.lock:
            pl.orch.start_task(db.get_task(tid))
        cid = db.create_chat(pid)
        db.ex("UPDATE chats SET title_kind='manual' WHERE id=?", (cid,))
        with pl.chat.lock:
            pl.chat.send(cid, "Демо-ответ без модели")
        # Служебная генерация, импорт, Git и Telegram: реальные деревья безопасных Python-заглушек.
        for name in ("title", "import", "git", "telegram"):
            def service(label=name):
                proc = runtime.popen([sys.executable, "-u", "-c", CHILD], stdout=subprocess.PIPE,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                pids.extend([proc.pid, int(proc.stdout.readline())])
                proc.wait()
            threading.Thread(target=service, daemon=True).start()
        time.sleep(.5)
        return {"task_id": tid, "chat_id": cid, "pids": pids, "stub_agents": True}

    @main.route("GET", "/api/demo/info")
    def info(h, body, query):
        return {"stub_agents": True, "pids": pids, "project_id": pid}

    @main.route("POST", "/api/demo/slow")
    def slow(h, body, query):
        marker = str(Path(root) / 'slow-started')
        runtime.run([sys.executable, '-c', "from pathlib import Path; import time; Path(" + repr(marker) + ").touch(); time.sleep(600)"],
                    capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        # Уже принятая мутация должна закончиться до закрытия SQLite.
        tid = db.create_task(pid, 'Квитанция прерванного импорта')
        return {'task_id': tid}

    main.spawn_successor = lambda: (_ for _ in ()).throw(AssertionError("Остановка не должна запускать преемника"))
    sys.argv = [sys.argv[0], "--no-browser"]
    main.main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child")
    parser.add_argument("--reuse")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.child:
        child(args.child)
    else:
        proc, root, port = launch(args.reuse, args.port)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        info = {"pid": proc.pid, "sandbox": str(root), "port": port, "stub_agents": True}
        (OUTPUT / "demo.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(info, ensure_ascii=False))
