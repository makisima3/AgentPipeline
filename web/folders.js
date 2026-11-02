// Общий выбор рабочей папки сервера: форма под окном остаётся нетронутой.
window.FolderPicker = (() => {
  let dialog, current, target, controller, request = 0, opener, retryPath, openingHeight;
  const el = id => dialog.querySelector('#fp-' + id);
  const node = (tag, text, cls) => {
    const n = document.createElement(tag); n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  function close() {
    if (!dialog) return;
    request++; controller?.abort();
    window.visualViewport?.removeEventListener('resize', resize);
    dialog.close(); dialog.remove(); dialog = null;
    if (opener?.isConnected) opener.focus();
  }
  function resize() {
    if (!dialog) return;
    const height = window.visualViewport?.height || innerHeight;
    dialog.style.maxHeight = Math.max(160, height - 24) + 'px';
    dialog.classList.toggle('compact', height < openingHeight * .75);
  }
  async function load(path, select = false) {
    const seq = ++request;
    controller?.abort(); controller = new AbortController();
    const activeController = controller;
    retryPath = path;
    el('choose').disabled = true;
    el('status').textContent = select ? 'Проверяем выбранную папку…' : 'Читаем папки…';
    el('retry').hidden = true;
    const timer = setTimeout(() => activeController.abort(), 12000);
    try {
      const r = await fetch('/api/folders', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path}), signal: activeController.signal});
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || 'Не удалось прочитать папку');
      if (!dialog || seq !== request) return;
      if (select) {
        if (target.isConnected) {
          target.value = data.path;
          target.dispatchEvent(new Event('input', {bubbles: true}));
          target.dispatchEvent(new Event('change', {bubbles: true}));
          const name = document.querySelector('#np-name');
          if (name && !name.value) name.value = data.path.replace(/[\\/]+$/, '').split(/[\\/]/).pop();
        }
        close(); return;
      }
      current = data;
      el('path').value = data.path || '';
      el('current').textContent = data.path || 'Диски и корни сервера';
      el('up').disabled = !data.path;
      el('list').replaceChildren();
      for (const entry of data.entries) {
        const button = node('button', entry.name, 'folder-entry');
        button.setAttribute('aria-label', entry.name);
        button.type = 'button'; button.title = entry.path;
        button.addEventListener('click', () => load(entry.path));
        el('list').append(button);
      }
      el('list').scrollTop = 0;
      el('status').textContent = data.entries.length ? `${data.path ? 'Папок' : 'Расположений'}: ${data.entries.length}` : 'В этой папке нет вложенных папок';
      el('choose').disabled = !data.path;
    } catch (e) {
      if (!dialog || seq !== request) return;
      el('status').textContent = e.name === 'AbortError'
        ? 'Сервер не ответил вовремя. Проверьте соединение и повторите.'
        : e instanceof TypeError ? 'Нет соединения с сервером. Подключитесь и повторите.' : e.message;
      el('retry').hidden = false;
      // После ошибки нельзя подтвердить прежнюю папку вместо запрошенной.
    } finally { clearTimeout(timer); }
  }
  function open(input) {
    close(); target = input; opener = document.activeElement; current = null;
    dialog = document.createElement('dialog'); dialog.className = 'folder-picker';
    dialog.setAttribute('aria-labelledby', 'fp-title');
    dialog.innerHTML = `<h3 id="fp-title">Папка на ПК с сервером</h3>
      <p class="hint">Выберите рабочую папку проекта. Файлы с телефона не загружаются.</p>
      <form id="fp-form" class="row">
        <input id="fp-path" aria-label="Путь на сервере" placeholder="Полный путь на ПК" autocomplete="off" autocapitalize="off" spellcheck="false">
        <button type="submit">Перейти</button></form>
      <div class="row folder-nav"><button id="fp-roots" type="button">Диски и корни</button><button id="fp-up" type="button" disabled>↑ Выше</button></div>
      <div id="fp-current" class="folder-current"></div>
      <div id="fp-list" class="folder-list" aria-label="Каталоги сервера"></div>
      <div id="fp-status" class="hint" role="status" aria-live="polite"></div>
      <button id="fp-retry" type="button" hidden>Повторить запрос</button>
      <div class="actions"><button id="fp-cancel" type="button">Отмена</button><button id="fp-choose" type="button" class="primary" disabled>Выбрать папку</button></div>`;
    document.body.append(dialog);
    el('form').onsubmit = e => { e.preventDefault(); el('path').blur(); load(el('path').value); };
    el('path').oninput = () => { el('choose').disabled = !current?.path || el('path').value !== current.path; };
    el('roots').onclick = () => load(null);
    el('up').onclick = () => load(current?.parent || null);
    el('cancel').onclick = close;
    el('choose').onclick = () => load(current.path, true);
    el('retry').onclick = () => load(retryPath);
    dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
    dialog.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close(); } });
    openingHeight = window.visualViewport?.height || innerHeight;
    dialog.showModal(); resize(); window.visualViewport?.addEventListener('resize', resize);
    el('cancel').focus();  // На телефоне открытие не вызывает клавиатуру.
    load(input.value || null);
  }
  return {open, close, isOpen: () => !!dialog};
})();
