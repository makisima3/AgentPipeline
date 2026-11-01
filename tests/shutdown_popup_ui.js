async (page) => {
  const base = new URL(page.url()).origin;
  for (const other of page.context().pages()) if (other !== page) await other.close();
  const opened = page.waitForEvent('popup');
  await page.evaluate(() => window.open(location.origin, '_blank'));
  const popup = await opened;
  await popup.waitForLoadState();
  await popup.getByRole('button', {name: 'Настройки', exact: true}).click();
  await popup.locator('#stopServer').click();
  await popup.screenshot({path: 'output/playwright/task-47/popup-confirm.png'});
  const closed = popup.waitForEvent('close', {timeout: 30000});
  await popup.locator('#confirmStop').click();
  await closed;
  await page.getByRole('heading', {name: 'Сервер остановлен', exact: true}).waitFor();
  return {idleStop: true, scriptOpenedTabClosed: popup.isClosed()};
}
