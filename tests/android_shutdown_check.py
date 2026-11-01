"""Настоящие нажатия в APK; только эмулятор и shutdown_demo с временной БД."""
import argparse
import json
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', default='emulator-5554')
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / 'output/playwright/task-47'
    demo = json.loads((output / 'demo.json').read_text(encoding='utf-8'))
    base = 'http://127.0.0.1:' + str(demo['port'])
    pkg = 'space.agentpipeline.android'
    checks = {}

    def adb(*argv):
        return subprocess.check_output([args.adb, '-s', args.serial, *argv], timeout=45).decode('utf-8', 'replace').strip()

    def api(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(req, timeout=8))

    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Только эмулятор'
    assert api('/api/demo/info')['stub_agents']
    assert 'versionName=1.1' in adb('shell', 'dumpsys', 'package', pkg)
    adb('reverse', 'tcp:8765', 'tcp:' + str(demo['port']))
    adb('shell', 'input', 'keyevent', '224')
    adb('shell', 'wm', 'dismiss-keyguard')
    adb('shell', 'am', 'force-stop', pkg)  # закрыть pooled HTTP-сокеты предыдущего демо
    adb('shell', 'am', 'start', '-n', pkg + '/.MainActivity')

    def ui():
        for _ in range(5):
            try:
                if 'dumped' in adb('shell', 'uiautomator', 'dump', '/sdcard/shutdown-ui.xml'):
                    return ET.fromstring(adb('shell', 'cat', '/sdcard/shutdown-ui.xml'))
            except (ET.ParseError, subprocess.CalledProcessError):
                pass
            time.sleep(.5)
        raise AssertionError('UIAutomator недоступен')

    def bounds(n):
        return list(map(int, re.findall(r'\d+', n.get('bounds', ''))))

    def find(tree, text, exact=True):
        for n in reversed(list(tree.iter('node'))):
            b = bounds(n)
            if len(b) == 4 and b[2] > b[0] and b[3] > b[1]:
                if any(v == text if exact else text in v for v in (n.get('text', ''), n.get('content-desc', ''))):
                    return n

    def wait(text, exact=True, seconds=35):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            n = find(ui(), text, exact)
            if n is not None:
                return n
        raise AssertionError('Не найдено: ' + text)

    def tap(n):
        l, t, r, b = bounds(n)
        adb('shell', 'input', 'tap', str((l+r)//2), str((t+b)//2))
        time.sleep(.3)

    def click(text, exact=True):
        tap(wait(text, exact))

    def screenshot(name):
        (output / name).write_bytes(subprocess.check_output([args.adb, '-s', args.serial, 'exec-out', 'screencap', '-p']))

    wait('Демонстрация')
    time.sleep(1)  # дождаться первичного render после loadState
    close_chat = find(ui(), '✕')
    if close_chat is not None:
        tap(close_chat)
    checks['upgradePreservedConnection'] = True
    tree = ui()
    nav = find(tree, 'Результаты')
    if nav is None:
        nav = find(tree, 'Результаты Есть непрочитанные результаты')
    assert nav is not None
    tap(nav)
    wait('Результат сохранён', False)
    screenshot('android-results.png')
    checks['results'] = True
    click('Настройки')
    close_chat = find(ui(), '✕')
    if close_chat is not None:
        tap(close_chat)
    for _ in range(12):
        n = find(ui(), 'Остановить сервер')
        if n is not None:
            break
        adb('shell', 'input', 'swipe', '500', '1550', '500', '550', '350')
    assert n is not None, 'Кнопка остановки недоступна'
    screenshot('android-settings.png')
    tap(n)
    wait('Остановить сервер?')
    screenshot('android-confirm.png')
    click('Отмена')
    assert api('/api/shutdown')['status'] == 'running'
    checks['cancel'] = True
    click('Остановить сервер')
    wait('Остановить сервер?')
    # Здесь у сервера есть настоящие деревья процессов-заглушек, а не модель/Telegram.
    work = api('/api/demo/work', {})
    assert len(work['pids']) >= 12
    click('Остановить сервер')
    end = time.monotonic() + 35
    while time.monotonic() < end:
        activities = adb('shell', 'dumpsys', 'activity', 'activities')
        if 'topResumedActivity' in activities and not any(pkg in line and 'ActivityRecord{' in line for line in activities.splitlines()):
            break
        time.sleep(.5)
    else:
        raise AssertionError('Activity не закрылась')
    assert not any(pkg in line and 'ActivityRecord{' in line for line in activities.splitlines()), 'Оболочка осталась в недавних'
    screenshot('android-closed.png')
    checks['activeStopAndNativeClose'] = True
    for _ in range(30):
        try:
            api('/api/state')
        except OSError:
            break
        time.sleep(.2)
    else:
        raise AssertionError('HTTP остался доступен')
    checks['portClosed'] = True
    (output / 'android-shutdown-check.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()
