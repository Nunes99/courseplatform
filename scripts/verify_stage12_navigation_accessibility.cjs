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
  '.mjs': 'application/javascript',
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
    failures.push(`console: ${message.text()}${locationUrl ? ` (${locationUrl})` : ''}`);
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
            adminChatRooms: async () => ({ unreadCount: 0 }),
            adminStudents: async () => ({
              students: [],
              summary: { active: 0, blocked: 0, completed: 0, averageProgress: 0 },
              pagination: { total: 0, returned: 0, hasMore: false, nextCursor: '' }
            }),
            adminGradebook: async () => ({ entries: [], pagination: { returned: 0, hasMore: false } }),
            adminAcademicCalendar: async () => ({ offerings: [], events: [] }),
            adminCertificateRequests: async () => ({ requests: [], pagination: { returned: 0, hasMore: false } }),
            adminCertificates: async () => ({ certificates: [], pagination: { returned: 0, hasMore: false } }),
            adminCourses: async () => ({ courses: [{ course: { courseId: 'COURSE-QA', title: 'Curso QA', status: 'ACTIVE' } }] }),
            adminCertificateSettings: async () => ({ settings: { certificateProfile: {} } }),
            adminCertificateSurveys: async () => ({ surveys: [], pagination: { returned: 0, hasMore: false } })
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
        window.__stage12RenderStudentList = (empty = false) => {
          state.studentFilters = {
            query: empty ? 'sem resultado' : '', status: 'ALL', progress: 'ALL', sort: 'name'
          };
          state.students = empty ? [] : [{
            student: {
              studentId: 'STUDENT-QA', publicStudentId: 'STU-12345',
              fullName: 'Estudante QA', email: 'student@example.test', status: 'ACTIVE'
            },
            enrollments: []
          }];
          state.studentSummary = { active: empty ? 0 : 1, blocked: 0, completed: 0, averageProgress: 0 };
          Object.assign(state.studentPagination, { total: empty ? 0 : 1, returned: empty ? 0 : 1, hasMore: false });
          renderStudentsV2();
        };
        window.__stage12StudentFilters = () => ({ ...state.studentFilters });
        window.__stage12RenderError = () => {
          window.__stage12Retried = false;
          const originalConsoleError = console.error;
          console.error = () => {};
          renderAdminLoadError(new Error('synthetic failure'), () => { window.__stage12Retried = true; });
          console.error = originalConsoleError;
        };
        window.__stage12RenderEmptyView = (view) => {
          if (view === 'gradebook') {
            state.gradebook = [];
            state.gradebookFilters = { query: 'sem resultado', status: 'BLOCKED', courseId: '', offeringId: '', groupId: '' };
            renderGradebook();
          } else if (view === 'calendar') {
            state.academicCalendar = { offerings: [], events: [] };
            state.academicCalendarFilters = { courseId: '', offeringId: '' };
            renderAcademicCalendar();
          } else if (view === 'certifications') {
            state.courses = [{ course: { courseId: 'COURSE-QA', title: 'Curso QA', status: 'ACTIVE' } }];
            state.selectedCourseId = 'COURSE-QA';
            state.certificates = [];
            state.certificateRequests = [];
            state.certificateSettings = { certificateProfile: {} };
            state.certificateFilters = { status: 'REJECTED', certificateStatus: 'BLOCKED', query: 'sem resultado' };
            renderCertifications();
          } else if (view === 'surveys') {
            state.certificateSurveys = [];
            state.certificateSurveyResponses = [];
            state.surveyFilters = { query: 'sem resultado' };
            renderCertificateSurveys();
          }
        };
        window.__stage12State = () => ({
          gradebookFilters: { ...state.gradebookFilters },
          certificateFilters: { ...state.certificateFilters },
          surveyFilters: { ...state.surveyFilters }
        });
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

    await page.evaluate(() => window.__stage12RenderStudentList(false));
    const studentTableRegion = page.locator('.student-admin-list');
    assert.equal(await studentTableRegion.getAttribute('role'), 'region');
    assert.equal(await studentTableRegion.getAttribute('tabindex'), '0');
    assert.equal(await studentTableRegion.locator('thead th').first().getAttribute('scope'), 'col');
    await studentTableRegion.focus();
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('student-admin-list')), true);

    await page.evaluate(() => window.__stage12RenderStudentList(true));
    await page.getByRole('heading', { name: 'Nenhum estudante encontrado' }).waitFor();
    await page.getByRole('button', { name: 'Limpar filtros' }).click();
    await page.waitForFunction(() => window.__stage12StudentFilters().query === '');

    await page.evaluate(() => window.__stage12OpenDialog());
    const dialog = page.getByRole('dialog', { name: 'Recuperar palavra-passe' });
    await dialog.waitFor();
    assert.equal(await dialog.getAttribute('aria-modal'), 'true');
    const emailField = dialog.getByLabel('Email da conta');
    await emailField.fill('');
    await dialog.getByRole('button', { name: 'Enviar instruções' }).click();
    assert.equal(await emailField.getAttribute('aria-invalid'), 'true');
    await dialog.locator('.field-validation-message').waitFor();
    await emailField.fill('qa@example.test');
    assert.equal(await emailField.getAttribute('aria-invalid'), null);
    await dialog.locator('.dialog-close').focus();
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.matches('[data-legacy-admin-recovery]')), true);
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'detached' });
    await page.waitForFunction(() => document.activeElement?.id === 'stage12DialogTrigger');

    await page.evaluate(() => window.__stage12RenderError());
    await page.getByRole('heading', { name: 'Não foi possível carregar esta página' }).waitFor();
    await page.getByRole('button', { name: 'Tentar novamente' }).click();
    assert.equal(await page.evaluate(() => window.__stage12Retried), true);

    await page.evaluate(() => window.__stage12RenderEmptyView('gradebook'));
    await page.getByRole('heading', { name: 'Nenhuma matrícula encontrada' }).waitFor();
    assert.equal(await page.locator('#exportGradebook').isDisabled(), true);
    await page.getByRole('button', { name: 'Limpar filtros' }).click();
    await page.waitForFunction(() => window.__stage12State().gradebookFilters.query === '');

    await page.evaluate(() => window.__stage12RenderEmptyView('calendar'));
    await page.getByRole('heading', { name: 'Nenhuma edição disponível' }).waitFor();

    await page.evaluate(() => window.__stage12RenderEmptyView('certifications'));
    await page.getByRole('heading', { name: 'Nenhum certificado encontrado' }).waitFor();
    await page.locator('#clearCertificateFilters').click();
    await page.waitForFunction(() => window.__stage12State().certificateFilters.query === '');

    await page.evaluate(() => window.__stage12RenderEmptyView('surveys'));
    await page.getByRole('heading', { name: 'Nenhum inquérito encontrado' }).waitFor();
    await page.locator('#clearSurveyDefinitionSearch').click();
    await page.waitForFunction(() => window.__stage12State().surveyFilters.query === '');

    const skipLink = page.locator('.skip-link');
    await skipLink.focus();
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), true);
    await page.waitForTimeout(180);
    assert.ok((await skipLink.boundingBox())?.y >= 0, 'A ligação para saltar conteúdo deve ficar visível ao receber foco.');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);
    assert.equal(await page.locator('.site-header').evaluate((element) => getComputedStyle(element).position), 'fixed');
    const closedSidebar = await page.locator('.admin-sidebar').evaluate((element) => ({
      rect: element.getBoundingClientRect().toJSON(),
      transform: getComputedStyle(element).transform,
      position: getComputedStyle(element).position,
      bodyClass: document.body.className,
      innerWidth: window.innerWidth,
      mobileMedia: matchMedia('(max-width: 1024px)').matches
    }));
    assert.ok(
      closedSidebar.rect.x + closedSidebar.rect.width <= 1,
      `O menu administrativo deve iniciar fora do ecrã móvel: ${JSON.stringify(closedSidebar)}`
    );
    const menuButton = page.locator('#adminMobileMenuButton');
    await menuButton.click();
    assert.equal(await menuButton.getAttribute('aria-expanded'), 'true');
    await page.waitForTimeout(300);
    const openSidebar = await page.locator('.admin-sidebar').boundingBox();
    assert.ok(openSidebar && openSidebar.x >= -1, 'O menu administrativo deve entrar no ecrã quando aberto.');
    await page.keyboard.press('Escape');
    assert.equal(await menuButton.getAttribute('aria-expanded'), 'false');
    await page.waitForTimeout(300);
    const closedAgain = await page.locator('.admin-sidebar').boundingBox();
    assert.ok(closedAgain && closedAgain.x + closedAgain.width <= 1, 'O menu administrativo deve sair do ecrã ao fechar.');

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
