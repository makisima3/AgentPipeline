// Один сценарий для сайта, APK и мастера; сетевые изменения выполняет пользователь.
function remoteAccessPanel() {
  return `<details id="remote-guide" class="remote-guide">
    <summary>Доступ с телефона вне дома · необязательно</summary>
    <p>Агенты и проекты остаются на домашнем ПК. Tailscale соединит ПК и телефон в закрытую сеть (tailnet), а Serve даст один HTTPS-адрес для браузера и APK.</p>
    <ol>
      <li>Установи <a href="https://tailscale.com/download" target="_blank" rel="noopener">Tailscale на Windows и Android</a>. На обоих устройствах войди в одну личную сеть под своим аккаунтом и включи подключение. Вход и системные разрешения выполняешь ты.</li>
      <li>В <a href="https://login.tailscale.com/admin/machines" target="_blank" rel="noopener">панели Tailscale</a> проверь устройства и пользователей. Доступ к трекеру даёт управление агентами и файлами ПК. Для личной сети оставь только свои доверенные устройства, не приглашай других и не включай общий доступ к ПК. В общей сети сначала ограничь доступ к ПК:443 своим пользователем/телефоном через Access controls и убери широкие разрешающие правила. Прежние прокси, туннели и пробросы портов проверяются отдельно: Tailscale их не отключает. <a href="/remote-access.html" target="_blank">Пример правил и проверка запрета</a>.</li>
      <li>На ПК открой PowerShell: <code>tailscale serve status</code>. Если порт 443 или маршрут / занят другим сервисом, сначала выбери с администратором отдельный узел; команда ниже меняет этот маршрут. После проверки прав выполни:<br>
        <code id="remote-command">Проверь состояние, чтобы получить команду с портом трекера.</code>
        <p>Если команда не найдена, открой новый PowerShell после установки или используй <code>&amp; "$env:ProgramFiles\\Tailscale\\tailscale.exe"</code> вместо <code>tailscale</code>. Подтверди предложенное Tailscale включение HTTPS/MagicDNS в браузере. Funnel не включай. Сервер остаётся на 127.0.0.1; проброс портов роутера и открытие порта трекера не нужны.</p></li>
      <li>Нажми «Проверить Tailscale на ПК», скопируй найденный адрес. На телефоне с включённым Tailscale открой его в браузере, затем вставь тот же адрес в APK → «Подключение» → поле адреса → «Подключиться». Используй корневой HTTPS-адрес без :8765 и пути. Сертификат проверяется системой, исключения TLS не нужны.</li>
      <li>Выключи Wi-Fi телефона и проверь через мобильный интернет: создай тестовую задачу, отправь сообщение/вложение в чат, ответь на вопрос, открой результат и скачай материал. Отключи/включи Tailscale, обнови страницу и проверь восстановление. В APK включи фоновую проверку результатов и уведомления, сверни его и проверь новый результат. Android проверяет примерно раз в 15 минут, возможны задержки.</li>
    </ol>
    <p><b>ПК должен быть включён, не спать, иметь интернет; трекер и Tailscale должны работать.</b> После перезагрузки запусти трекер; Serve с --bg сохраняется. На Android одновременно работает только один VPN: другой VPN, включая AdGuard в режиме VPN, придётся выключить. Не исключай браузер, AgentPipeline и системный менеджер загрузок из Tailscale.</p>
    <div class="remote-actions"><button onclick="App.checkRemoteAccess()">Проверить Tailscale на ПК</button></div>
    <p id="remote-status" role="status">Проверка ещё не выполнялась. Она читает локальное состояние и ничего не устанавливает и не меняет.</p>
    <div id="remote-address" class="hidden"><label for="remote-url">Один адрес для сайта и APK</label><input id="remote-url" readonly><button onclick="App.copyRemoteAddress()">Копировать адрес</button></div>
    <p class="hint">Проверка не подтверждает права доступа, сертификат, связь с телефоном или работу мобильной сети. После настройки проверь запрет с постороннего устройства. Если связи нет: проверь питание ПК, Tailscale на обоих устройствах, ограничения VPN/батареи и повтори загрузку в APK кнопкой ↻. <a href="/remote-access.html" target="_blank">Подробная инструкция</a>.</p>
  </details>`;
}

function openRemoteSettings() {
  setView('settings');
  const guide = $('#remote-guide');
  guide.open = true;
  guide.scrollIntoView({block: 'start'});
}

async function checkRemoteAccess() {
  const box = $('#remote-status'), guide = $('#remote-guide');
  if (!box || !guide) return;
  const button = guide.querySelector('.remote-actions button');
  button.disabled = true;
  box.textContent = 'Проверяю Tailscale на ПК…';
  $('#remote-address').classList.add('hidden');
  $('#remote-url').value = '';
  try {
    const r = await api('GET', '/api/remote-access');
    if (box !== $('#remote-status')) return;
    box.textContent = r.message;
    box.dataset.status = r.status;
    $('#remote-command').textContent = r.command;
    if (r.status === 'serve_configured' && /^https:\/\/[a-z0-9.-]+\.ts\.net$/.test(r.url || '')) {
      $('#remote-url').value = r.url;
      $('#remote-address').classList.remove('hidden');
    }
  } catch {
    if (box === $('#remote-status')) box.textContent = 'Проверка недоступна. Проверь связь с сервером и повтори; настройку можно выполнить по инструкции.';
  } finally {
    button.disabled = false;
  }
}

async function copyRemoteAddress() {
  const input = $('#remote-url');
  if (!input?.value) return;
  try { await navigator.clipboard.writeText(input.value); toast('Адрес скопирован'); }
  catch { input.focus(); input.select(); toast('Выделенный адрес можно скопировать вручную'); }
}
