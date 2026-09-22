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
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function json(data) {
  return {
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data }),
  };
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const failures = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, locale: 'pt-PT' });
    page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
    page.on('requestfailed', (request) => {
      if (new URL(request.url()).origin === origin) {
        failures.push(`${request.url()} ${request.failure()?.errorText}`);
      }
    });
    await page.addInitScript((apiOrigin) => {
      window.COURSE_PLATFORM_API_URL = `${apiOrigin}/api/index`;
      sessionStorage.setItem('courseAdminToken', 'qa-admin-session');
    }, origin);
    await page.route('**/*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== origin) return route.abort('blockedbyclient');
      if (url.pathname === '/api/index') {
        const payload = request.method() === 'POST' ? request.postDataJSON() || {} : {};
        if (payload.action === 'adminListStudents') {
          return route.fulfill(json({
            students: [{
              student: {
                studentId: 'STUDENT-QA-1',
                publicStudentId: 'STU-12345',
                fullName: 'Utilizador de Validação',
                email: 'reviewer@example.test',
                status: 'ACTIVE',
              },
              enrollments: [],
              memberships: [],
            }],
            pagination: { total: 1, hasMore: false },
            summary: { active: 1, blocked: 0, completed: 0, averageProgress: 0 },
          }));
        }
        return route.fulfill(json({}));
      }
      if (url.pathname === '/admin.js') {
        const source = await fs.readFile(path.join(publicRoot, 'admin.js'), 'utf8');
        const hook = `
          window.__qaOpenStaffDialog = () => {
            state.admin = { adminId: 'ADMIN-QA', fullName: 'Owner QA', role: 'OWNER' };
            renderAdminShell();
            showStaffDialog();
            clearInterval(adminPresencePollId);
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

    await page.goto(`${base}/admin.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.__qaOpenStaffDialog));
    await page.evaluate(() => window.__qaOpenStaffDialog());
    const userSelect = page.locator('#staffUserSelect');
    await userSelect.locator('option').nth(1).waitFor({ state: 'attached' });
    const options = await userSelect.locator('option').evaluateAll((items) => items.map((item) => ({
      value: item.value,
      text: item.textContent.trim().replace(/\s+/g, ' '),
    })));
    assert.deepEqual(options, [
      { value: '', text: 'Selecione um utilizador' },
      {
        value: 'STUDENT-QA-1',
        text: 'Utilizador de Validação - reviewer@example.test (STU-12345)',
      },
    ]);
    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
  process.stdout.write('Staff assignment lists registered users with stable identity values.\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
