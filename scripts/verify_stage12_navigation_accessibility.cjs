const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';
const origin = new URL(base).origin;
const publicRoot = path.join(root, 'public');

const contentTypes = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
};

async function serveFrontend(page) {
  const failures = [];
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const locationUrl = message.location().url || '';
    if (locationUrl && new URL(locationUrl).origin !== origin) return;
    if (locationUrl && new URL(locationUrl).pathname === '/favicon.ico') return;
    failures.push(`console: ${message.text()}`);
  });
  await page.addInitScript((apiOrigin) => {
    window.COURSE_PLATFORM_API_URL = `${apiOrigin}/api/index`;
  }, origin);
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) return route.abort('blockedbyclient');
    if (url.pathname.startsWith('/api/')) {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { mediaConfig: {} } }),
      });
    }
    if (url.pathname === '/admin.js') {
      const source = await fs.readFile(path.join(publicRoot, 'admin.js'), 'utf8');
      const hook = `
        window.__stage12OpenAdmin = async () => {
          window.clearInterval(adminPresencePollId);
          api = {
            hasAdminSession: () => true,
            adminUpdatePresence: async () => ({}),
            adminChatRooms: async () => ({ unreadCount: 0 })
          };
          state.admin = { adminId: 'ADMIN-QA', fullName: 'Administrador QA', role: 'OWNER' };
          renderAdminShell();
          history.replaceState(null, '', location.pathname + '#/profile');
          await routeAdminView({ focus: true });
          window.clearInterval(adminPresencePollId);
        };
        window.__stage12OpenDialog = () => {
          const trigger = document.createElement('button');
          trigger.id = 'stage12DialogTrigger';
          trigger.textContent = 'Abrir diálogo de teste';
          document.body.appendChild(trigger);
          trigger.focus();
          showAdminRecoveryDialog('qa@example.test');
        };
      `;
      return route.fulfill({ contentType: 'application/javascript', body: source + hook });
    }

    const pathname = decodeURIComponent(url.pathname === '/' ? '/admin.html' : url.pathname);
    const localPath = path.resolve(publicRoot, `.${pathname}`);
    if (!localPath.startsWith(`${publicRoot}${path.sep}`)) {
      return route.fulfill({ status: 404, body: 'Not found' });
    }
    try {
      return route.fulfill({
        contentType: contentTypes[path.extname(localPath).toLowerCase()] || 'application/octet-stream',
        body: await fs.readFile(localPath),
      });
    } catch (error) {
      if (error.code === 'ENOENT') return route.fulfill({ status: 404, body: 'Not found' });
      throw error;
    }
  });
  return failures;
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'pt-PT' });
    const failures = await serveFrontend(page);
    await page.goto(`${base}/admin.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__stage12OpenAdmin));
    await page.evaluate(() => window.__stage12OpenAdmin());

    await page.waitForURL(/#\/profile$/);
    assert.equal(await page.locator('[data-admin-view="profile"]').getAttribute('aria-current'), 'page');
    await page.waitForFunction(() => document.activeElement?.matches('#adminMain h1'));
    assert.match(await page.locator('#adminMain h1').innerText(), /Administrador QA/);

    await page.locator('[data-admin-view="credentials"]').click();
    await page.waitForURL(/#\/credentials$/);
    assert.equal(await page.locator('[data-admin-view="credentials"]').getAttribute('aria-current'), 'page');
    await page.waitForFunction(() => document.activeElement?.matches('#adminMain h1'));
    assert.equal(await page.locator('#adminMain h1').innerText(), 'Credenciais');

    await page.evaluate(() => window.__stage12OpenDialog());
    const dialog = page.getByRole('dialog', { name: 'Recuperar palavra-passe' });
    await dialog.waitFor();
    assert.equal(await dialog.getAttribute('aria-modal'), 'true');
    await dialog.locator('.dialog-close').focus();
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.matches('[data-legacy-admin-recovery]')), true);
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'detached' });
    await page.waitForFunction(() => document.activeElement?.id === 'stage12DialogTrigger');

    const skipLink = page.locator('.skip-link');
    await skipLink.focus();
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), true);
    await page.waitForTimeout(180);
    assert.ok((await skipLink.boundingBox())?.y >= 0, 'A ligação para saltar conteúdo deve ficar visível ao receber foco.');

    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);
    assert.equal(await page.locator('.site-header').evaluate((element) => getComputedStyle(element).position), 'fixed');
    const menuButton = page.locator('#adminMobileMenuButton');
    await menuButton.click();
    assert.equal(await menuButton.getAttribute('aria-expanded'), 'true');
    await page.keyboard.press('Escape');
    assert.equal(await menuButton.getAttribute('aria-expanded'), 'false');

    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
  process.stdout.write('Etapa 12: navegação, foco, modal e viewport móvel validados.\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
