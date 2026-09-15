const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';

const course = {
  courseId: 'COURSE-QA',
  courseCode: 'QA-001',
  title: 'Gestão de Projetos Energéticos',
  description: 'Curso sintético para validação visual.',
  totalHours: 36,
  passingScore: 70,
  status: 'ACTIVE'
};

const structure = {
  course,
  versions: [
    { courseVersionId: 'CV-2', courseId: course.courseId, versionNumber: 2, status: 'DRAFT', title: course.title },
    { courseVersionId: 'CV-1', courseId: course.courseId, versionNumber: 1, status: 'PUBLISHED', title: course.title,
      publishedAt: '2026-09-01T08:00:00Z' }
  ],
  offerings: [
    { offeringId: 'OFF-2', courseId: course.courseId, courseVersionId: 'CV-1', offeringCode: 'QA-2027-A',
      name: 'Edição de janeiro de 2027', status: 'OPEN', startDate: '2027-01-10T00:00:00Z',
      endDate: '2027-03-30T00:00:00Z', capacity: 40, enrollmentCount: 12 },
    { offeringId: 'OFF-1', courseId: course.courseId, courseVersionId: 'CV-1', offeringCode: 'QA-2026-A',
      name: 'Edição de setembro de 2026', status: 'ACTIVE', startDate: '2026-09-01T00:00:00Z',
      endDate: '2026-11-30T00:00:00Z', capacity: null, enrollmentCount: 24 }
  ],
  lessons: []
};

async function main() {
  const output = path.join(root, 'tmp/ui/course-editions');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  });
  const errors = [];
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      timezoneId: 'Africa/Maputo',
      locale: 'pt-PT',
      serviceWorkers: 'block'
    });
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('requestfailed', (request) => errors.push(`${request.url()} ${request.failure()?.errorText}`));
    page.on('dialog', (dialog) => dialog.accept());
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) {
        const type = route.request().resourceType();
        const contentType = type === 'script' ? 'application/javascript'
          : type === 'stylesheet' ? 'text/css'
            : type === 'image' ? 'image/svg+xml' : 'application/json';
        const body = type === 'image'
          ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/>'
          : type === 'script' || type === 'stylesheet' ? '' : '{}';
        return route.fulfill({ contentType, body });
      }
      if (url.pathname === '/api/index') {
        return route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ success: true, data: { mediaConfig: {}, rooms: [], unreadCount: 0 } })
        });
      }
      if (url.pathname === '/admin.js') {
        const source = await fs.readFile(path.join(root, 'public/admin.js'), 'utf8');
        const hook = `
          window.__qaCourseEditions = (courseStructure) => {
            sessionStorage.setItem('courseAdminToken', 'qa');
            state.admin = { adminId: 'ADM-QA', fullName: 'Administrador QA', role: 'OWNER' };
            state.courses = [{ course: courseStructure.course, lessonCount: 0, groupCount: 0, enrollmentCount: 36 }];
            state.courseStructure = courseStructure;
            state.groups = [];
            state.students = [];
            state.selectedCourseId = courseStructure.course.courseId;
            state.courseMode = 'detail';
            state.courseView = 'editions';
            renderAdminShell();
            setActiveAdminView('courses');
            renderCourses();
            clearInterval(adminPresencePollId);
          };
        `;
        return route.fulfill({ contentType: 'application/javascript', body: source + hook });
      }
      return route.continue();
    });
    await page.addInitScript((url) => {
      window.COURSE_PLATFORM_API_URL = `${url}/api/index`;
    }, base);
    await page.goto(`${base}/admin.html`);
    await page.waitForFunction(() => Boolean(window.__qaCourseEditions));
    await page.evaluate((data) => window.__qaCourseEditions(data), structure);

    await page.getByRole('heading', { name: 'Versões e edições do curso' }).waitFor();
    assert.equal(await page.getByText('Versão 1', { exact: false }).count() > 0, true);
    assert.equal(await page.getByText('Edição de janeiro de 2027', { exact: true }).count(), 1);
    assert.equal(await page.locator('[data-publish-course-version="CV-2"]').count(), 1);

    for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(150);
      const geometry = await page.evaluate(() => ({
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        sidebarPosition: getComputedStyle(document.querySelector('.admin-sidebar')).position,
        headerPosition: getComputedStyle(document.querySelector('.site-header')).position
      }));
      assert.ok(geometry.pageWidth <= geometry.viewportWidth, `${label}: horizontal overflow`);
      assert.equal(geometry.sidebarPosition, 'fixed', `${label}: sidebar must remain fixed`);
      assert.equal(geometry.headerPosition, 'fixed', `${label}: header must remain fixed`);
      await page.screenshot({ path: path.join(output, `${label}.png`), fullPage: true });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Editar edição de janeiro de 2027' }).click();
    await page.getByRole('heading', { name: 'Editar edição' }).waitFor();
    const dialogGeometry = await page.locator('.dialog-card').evaluate((node) => ({
      right: node.getBoundingClientRect().right,
      left: node.getBoundingClientRect().left,
      viewport: window.innerWidth,
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth
    }));
    assert.ok(dialogGeometry.left >= 0 && dialogGeometry.right <= dialogGeometry.viewport, 'mobile dialog outside viewport');
    assert.ok(dialogGeometry.scrollWidth <= dialogGeometry.clientWidth, 'mobile dialog horizontal overflow');
    await page.screenshot({ path: path.join(output, 'mobile-dialog.png'), fullPage: true });

    assert.deepEqual(errors, []);
    console.log('Course versions and offerings passed desktop/mobile layout, fixed navigation and dialog validation.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
