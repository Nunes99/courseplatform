const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';
const baseOrigin = new URL(base).origin;
const publicRoot = path.join(root, 'public');
const output = path.join(root, 'tmp/ui/password-recovery');

const CONTENT_TYPES = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.ico': 'image/x-icon',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
  '.woff2': 'font/woff2',
};

async function configurePage(page) {
  const failures = [];
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 400 && response.url().startsWith(baseOrigin)) {
      failures.push(`response ${response.status()}: ${response.url()}`);
    }
  });
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const locationUrl = message.location().url || '';
    const expectedBlockedResource = message.text().includes('ERR_BLOCKED_BY_CLIENT')
      || (locationUrl && new URL(locationUrl).origin !== baseOrigin && message.text().startsWith('Failed to load resource'));
    if (!expectedBlockedResource) {
      failures.push(`console: ${message.text()}${locationUrl ? ` (${locationUrl})` : ''}`);
    }
  });
  await page.addInitScript(({ origin }) => {
    window.COURSE_PLATFORM_API_URL = `${origin}/api/index`;
  }, { origin: base });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== baseOrigin) {
      return route.abort('blockedbyclient');
    }
    if (/^\/api\/v1\/catalog\/courses\/[^/]+\/media$/.test(url.pathname)) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { mediaConfig: { logoUrl: '', videos: [] } } }),
      });
    }
    if (url.pathname === '/api/index') {
      const payload = request.method() === 'POST'
        ? (request.postDataJSON() || {})
        : { action: url.searchParams.get('action') || '' };
      if (payload.action === 'completeStudentPasswordReset' && payload.newPassword !== payload.confirmPassword) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: false, error: { code: 'PASSWORD_CONFIRMATION_MISMATCH', message: 'A confirmação da nova palavra-passe não corresponde.' } }),
        });
      }
      const data = payload.action === 'recoverStudentAccess'
        ? { message: 'Se existir uma conta ativa associada a esse email, receberá uma mensagem com as instruções para definir uma nova palavra-passe.' }
        : payload.action === 'completeStudentPasswordReset'
          ? { passwordChanged: true, sessionsRevoked: true }
          : { mediaConfig: { logoUrl: '', videos: [] } };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data }) });
    }
    const pathname = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
    const localPath = path.resolve(publicRoot, `.${pathname}`);
    if (!localPath.startsWith(`${publicRoot}${path.sep}`)) {
      return route.fulfill({ status: 404, body: 'Not found' });
    }
    try {
      return route.fulfill({
        contentType: CONTENT_TYPES[path.extname(localPath).toLowerCase()] || 'application/octet-stream',
        body: await fs.readFile(localPath),
      });
    } catch (error) {
      if (error.code === 'ENOENT') return route.fulfill({ status: 404, body: 'Not found' });
      throw error;
    }
  });
  return failures;
}

async function assertViewport(page) {
  const layout = await page.evaluate(() => {
    const dialog = document.querySelector('.recovery-dialog')?.getBoundingClientRect();
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      dialogLeft: dialog?.left ?? 0,
      dialogRight: dialog?.right ?? 0,
    };
  });
  assert.ok(layout.documentWidth <= layout.viewportWidth, `horizontal overflow: ${JSON.stringify(layout)}`);
  assert.ok(layout.dialogLeft >= 0 && layout.dialogRight <= layout.viewportWidth, `dialog outside viewport: ${JSON.stringify(layout)}`);
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      serviceWorkers: 'block',
    });
    const desktop = await context.newPage();
    const desktopFailures = await configurePage(desktop);
    await desktop.goto(`${base}/index.html`, { waitUntil: 'domcontentloaded' });
    await desktop.getByRole('button', { name: 'Esqueci a palavra-passe de acesso' }).click();
    const requestDialog = desktop.getByRole('dialog', { name: 'Recuperar palavra-passe de acesso' });
    await requestDialog.waitFor();
    assert.equal(await requestDialog.locator('input[name="publicStudentId"]').count(), 0);
    assert.equal(await requestDialog.locator('input[type="email"]').count(), 1);
    await requestDialog.locator('input[type="email"]').fill('synthetic@example.test');
    await requestDialog.getByRole('button', { name: 'Enviar instruções' }).press('Enter');
    await requestDialog.getByText('Se existir uma conta ativa').waitFor();
    await assertViewport(desktop);
    await desktop.screenshot({ path: path.join(output, 'request-desktop.png'), fullPage: true });
    await desktop.keyboard.press('Escape');
    await requestDialog.waitFor({ state: 'detached' });

    await desktop.goto(`${base}/index.html#/reset-access?token=synthetic-one-time-token`, { waitUntil: 'commit' });
    const resetDialog = desktop.getByRole('dialog', { name: 'Definir nova palavra-passe' });
    await resetDialog.waitFor();
    assert.ok(!desktop.url().includes('synthetic-one-time-token'), 'token remained in browser URL');
    await resetDialog.locator('[name="newPassword"]').fill('new-password-123');
    await resetDialog.locator('[name="confirmPassword"]').fill('different-password');
    await resetDialog.getByRole('button', { name: 'Guardar nova palavra-passe' }).click();
    await resetDialog.getByText('A confirmação da nova palavra-passe não corresponde.').waitFor();
    await resetDialog.locator('[name="confirmPassword"]').fill('new-password-123');
    await resetDialog.getByRole('button', { name: 'Guardar nova palavra-passe' }).click();
    await desktop.getByText('Palavra-passe alterada. Já pode iniciar sessão.').waitFor();
    assert.deepEqual(desktopFailures, []);

    await desktop.setViewportSize({ width: 390, height: 844 });
    await desktop.evaluate(() => { location.hash = '#/reset-access?token=mobile-synthetic-token'; });
    const mobileDialog = desktop.getByRole('dialog', { name: 'Definir nova palavra-passe' });
    await mobileDialog.waitFor();
    assert.equal(await mobileDialog.locator('[name="newPassword"]:focus').count(), 1, 'keyboard focus did not enter the dialog');
    await desktop.keyboard.press('Tab');
    assert.equal(await mobileDialog.locator('[name="confirmPassword"]:focus').count(), 1, 'Tab order is not usable');
    await assertViewport(desktop);
    await desktop.screenshot({ path: path.join(output, 'reset-mobile.png'), fullPage: true });
    assert.deepEqual(desktopFailures, []);
    await desktop.close();
    await context.close();
    console.log('Student password recovery UI: desktop/mobile, keyboard, success/error and URL token cleanup passed.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
