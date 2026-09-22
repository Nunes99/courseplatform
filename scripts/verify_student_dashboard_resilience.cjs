const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';
const baseOrigin = new URL(base).origin;
const publicRoot = path.join(root, 'public');

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

function json(body, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  };
}

function studentHome() {
  const student = {
    studentId: 'STU-QA',
    fullName: 'Synthetic Student',
    email: 'synthetic@example.test',
  };
  const course = {
    courseId: 'COURSE-EAPI-001',
    courseCode: 'QA-001',
    title: 'Curso de validação',
    description: 'Curso sintético para validar o dashboard.',
    totalHours: 12,
    status: 'ACTIVE',
  };
  const enrollment = {
    enrollmentId: 'ENR-QA',
    courseId: course.courseId,
    status: 'ACTIVE',
    progressPercent: 0,
  };
  return {
    student,
    courses: [{ course, enrollment, lessons: [] }],
    selectedCourseId: course.courseId,
    selectedEnrollmentId: enrollment.enrollmentId,
    dashboard: { student, course, enrollment, lessons: [] },
    mediaConfig: { logoUrl: '', videos: [] },
  };
}

async function configurePage(page) {
  const failures = [];
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const locationUrl = message.location().url || '';
    const external = locationUrl && new URL(locationUrl).origin !== baseOrigin;
    const expectedFallback = locationUrl && [
      '/api/v1/students/me/home',
      '/favicon.ico',
    ].includes(new URL(locationUrl).pathname);
    if (!external && !expectedFallback) failures.push(`console: ${message.text()}`);
  });
  await page.addInitScript(({ origin }) => {
    window.COURSE_PLATFORM_API_URL = `${origin}/api/index`;
  }, { origin: base });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== baseOrigin) return route.abort('blockedbyclient');

    if (url.pathname === '/api/v1/students/me/home') {
      return route.fulfill(json({
        success: false,
        error: { code: 'NOT_FOUND', message: 'Rota indisponível.' },
      }, 404));
    }
    if (/^\/api\/v1\/catalog\/courses\/[^/]+\/media$/.test(url.pathname)) {
      return route.fulfill(json({ success: true, data: { mediaConfig: { logoUrl: '', videos: [] } } }));
    }
    if (url.pathname === '/api/index') {
      const payload = request.method() === 'POST'
        ? (request.postDataJSON() || {})
        : { action: url.searchParams.get('action') || '' };
      const dataByAction = {
        login: { sessionToken: 'synthetic-session', student: studentHome().student },
        getStudentHome: studentHome(),
        getMyNotifications: { items: [], unreadCount: 0, total: 0 },
        getPushConfiguration: { pushConfiguration: {}, subscriptionCount: 0 },
        updateStudentPresence: { updated: true },
        getChatUnreadCount: { unreadCount: 0 },
        publicMediaConfig: { mediaConfig: { logoUrl: '', videos: [] } },
      };
      return route.fulfill(json({ success: true, data: dataByAction[payload.action] || {} }));
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

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    const failures = await configurePage(page);
    await page.goto(`${base}/index.html`, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Email').fill('synthetic@example.test');
    await page.getByLabel('Palavra-passe de acesso').fill('synthetic-password');
    await page.getByRole('button', { name: 'Entrar na plataforma' }).click();
    try {
      await page.getByRole('heading', { name: /Synthetic Student/ }).waitFor({ timeout: 10000 });
    } catch (error) {
      const bodyText = await page.locator('body').innerText();
      throw new Error(`${error.message}\nEstado da página:\n${bodyText}\nErros:\n${failures.join('\n')}`);
    }
    await page.getByText('Programa: Curso de validação', { exact: true }).waitFor();
    assert.equal(failures.length, 0, failures.join('\n'));
    await context.close();
  } finally {
    await browser.close();
  }
  process.stdout.write('Dashboard carregou sem depender do service worker ou das rotas auxiliares.\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
