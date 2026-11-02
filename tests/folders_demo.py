"""Изолированный HTTP-демо для выбора папки на сайте и в APK, без моделей/Telegram."""
import json
from pathlib import Path

import test_pipeline as fixture
import folders


def run():
    db, main = fixture.db, fixture.main
    db.ex("DELETE FROM projects")
    root = fixture.SANDBOX / "Рабочие проекты"
    root.mkdir()
    for i in range(60):
        (root / f"Проект {i:02d} с пробелами").mkdir()
    empty = root / "Пустая папка"
    empty.mkdir()
    long = root / "Длинные пути"
    for i in range(7):
        long = long / ("Длинный путь проекта " + str(i))
    Path(folders.native_path(str(long))).mkdir(parents=True)
    (root / "Это файл.txt").write_text("Не показывается в выборе папок", encoding="utf-8")
    pid = db.create_project("Демо выбора папки", str(root))
    db.set_setting("onboarding_status", "completed")
    db.set_setting("git_mode", "off")
    db.set_setting("pipeline_enabled", "0")
    @main.route("GET", "/api/demo/info")
    def info(h, body, query):
        return {"stub_agents": True, "project_id": pid, "root": str(root), "empty": str(empty), "long": str(long)}
    srv = main.Server(("127.0.0.1", 0), main.Handler)
    output = fixture.SOURCE / "output/playwright/task-45"
    output.mkdir(parents=True, exist_ok=True)
    (output / "demo.json").write_text(json.dumps({"port": srv.server_address[1], "sandbox": str(fixture.SANDBOX)}), encoding="utf-8")
    print(f"DEMO_PORT={srv.server_address[1]}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    run()
