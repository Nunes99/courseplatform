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
    { courseVersionId: 'CV-2', courseId: course.courseId, versionNumber: 2, status: 'DRAFT', title: course.title,
      updatedAt: '2026-09-25T08:00:00Z' },
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
      if (url.pathname === '/assets/css/styles.css' || url.pathname === '/assets/css/tokens.css') {
        const body = await fs.readFile(path.join(root, 'public', url.pathname.replace(/^\//, '')), 'utf8');
        return route.fulfill({ contentType: 'text/css', body });
      }
      if (url.pathname === '/api/index') {
        const payload = route.request().method() === 'POST' ? route.request().postDataJSON() || {} : {};
        if (payload.action === 'adminPreviewCourseVersion') {
          return route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({
              success: true,
              data: {
                courseVersion: structure.versions[0],
                validation: {
                  valid: true,
                  issues: [],
                  summary: { lessonCount: 2, contentCount: 4, questionCount: 3, errorCount: 0, warningCount: 0 }
                },
                preview: {
                  course,
                  lessons: [
                    { lessonId: 'LESSON-1', lessonNumber: 1, title: 'Fundamentos', contentCount: 2, questionCount: 1 },
                    { lessonId: 'LESSON-2', lessonNumber: 2, title: 'Aplicação', contentCount: 2, questionCount: 2 }
                  ]
                },
                draftEditor: {
                  course,
                  lessons: [
                    {
                      lessonId: 'LESSON-1', lessonNumber: 1, title: 'Fundamentos', summary: 'Conceitos essenciais.',
                      status: 'ACTIVE', questionCount: 1,
                      content: [
                        { contentId: 'CONTENT-1', sectionOrder: 1, sectionType: 'TEXT', title: 'Introdução', bodyHtml: 'Conteúdo introdutório.', estimatedMinutes: 20, isRequired: true, status: 'ACTIVE' },
                        { contentId: 'CONTENT-2', sectionOrder: 2, sectionType: 'VIDEO', title: 'Aula orientada', bodyHtml: '', estimatedMinutes: 35, isRequired: true, status: 'ACTIVE' }
                      ]
                    },
                    {
                      lessonId: 'LESSON-2', lessonNumber: 2, title: 'Aplicação', summary: 'Aplicação prática.',
                      status: 'ACTIVE', questionCount: 2,
                      content: [
                        { contentId: 'CONTENT-3', sectionOrder: 1, sectionType: 'TEXT', title: 'Estudo de caso', bodyHtml: 'Análise aplicada.', estimatedMinutes: 30, isRequired: true, status: 'ACTIVE' }
                      ]
                    }
                  ]
                }
              }
            })
          });
        }
        if (payload.action === 'adminListQuestionBank') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { questions: [{
            bankQuestionId: 'QBANK-1', questionCode: 'QA-Q-001', courseId: course.courseId,
            title: 'Risco de execução do projeto', status: 'ACTIVE',
            latestVersion: { bankQuestionVersionId: 'QBVER-2', versionNumber: 2, status: 'DRAFT', questionType: 'SINGLE_CHOICE', difficulty: 'MEDIUM', points: 2 },
            publishedVersion: { bankQuestionVersionId: 'QBVER-1', versionNumber: 1 }
          }] } }) });
        }
        if (payload.action === 'adminGetQuestionBankItem') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { question: {
            bankQuestionId: 'QBANK-1', questionCode: 'QA-Q-001', courseId: course.courseId,
            title: 'Risco de execução do projeto', status: 'ACTIVE', versions: [{
              bankQuestionVersionId: 'QBVER-2', versionNumber: 2, status: 'DRAFT', questionType: 'SINGLE_CHOICE',
              prompt: 'Qual medida reduz o risco de execução?', explanation: 'O planeamento reduz a incerteza.',
              difficulty: 'MEDIUM', tags: ['risco', 'planeamento'], points: 2, correctAnswer: '',
              options: [{ optionText: 'Planeamento faseado', isCorrect: true }, { optionText: 'Ignorar dependências', isCorrect: false }]
            }]
          } } }) });
        }
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
    await page.locator('#adminLoginForm').waitFor();
    await page.evaluate((data) => window.__qaCourseEditions(data), structure);

    await page.getByRole('heading', { name: 'Versões e edições do curso' }).waitFor();
    assert.equal(await page.getByText('Versão 1', { exact: false }).count() > 0, true);
    assert.equal(await page.getByText('Edição de janeiro de 2027', { exact: true }).count(), 1);
    assert.equal(await page.locator('[data-publish-course-version="CV-2"]').count(), 1);
    assert.equal(await page.locator('[data-refresh-course-version="CV-2"]').count(), 1);
    assert.equal(await page.locator('[data-edit-course-version="CV-2"]').count(), 1);

    await page.getByRole('button', { name: 'Banco de questões' }).click();
    const questionBankDialog = page.locator('.question-bank-dialog');
    await questionBankDialog.getByRole('heading', { name: 'Banco de questões' }).waitFor();
    await questionBankDialog.getByText('Risco de execução do projeto', { exact: true }).click();
    await page.locator('.question-bank-dialog [name="prompt"]').waitFor();
    for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      const geometry = await page.locator('.question-bank-dialog').evaluate((node) => ({
        left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right,
        viewport: window.innerWidth, scrollWidth: node.scrollWidth, clientWidth: node.clientWidth
      }));
      assert.ok(geometry.left >= 0 && geometry.right <= geometry.viewport, `${label}: question bank outside viewport`);
      assert.ok(geometry.scrollWidth <= geometry.clientWidth, `${label}: question bank horizontal overflow`);
      await page.screenshot({ path: path.join(output, `${label}-question-bank.png`), fullPage: true });
    }
    await page.locator('.question-bank-dialog .dialog-close').click();

    for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      try {
        await page.waitForFunction(() => {
          const sidebar = document.querySelector('.admin-sidebar');
          const header = document.querySelector('.site-header');
          return sidebar && header
            && getComputedStyle(sidebar).position === 'fixed'
            && getComputedStyle(header).position === 'fixed';
        }, null, { timeout: 3000 });
      } catch (error) {
        const state = await page.evaluate(() => {
          const sidebar = document.querySelector('.admin-sidebar');
          const header = document.querySelector('.site-header');
          return {
            viewportWidth: window.innerWidth,
            sidebarPosition: sidebar ? getComputedStyle(sidebar).position : 'missing',
            headerPosition: header ? getComputedStyle(header).position : 'missing',
            desktopMedia: matchMedia('(min-width: 1025px)').matches,
            mobileMedia: matchMedia('(max-width: 1024px)').matches
          };
        });
        throw new Error(`${label}: layout did not settle (${JSON.stringify(state)})`, { cause: error });
      }
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
    await page.locator('[data-preview-course-version="CV-2"]').click();
    const previewDialog = page.locator('.course-version-preview-dialog');
    await previewDialog.getByRole('heading', { name: 'Versão 2' }).waitFor();
    await previewDialog.getByText('Pronta para publicar', { exact: true }).waitFor();
    await previewDialog.getByText('Alterações posteriores no editor não são incluídas automaticamente.', { exact: false }).waitFor();
    const previewGeometry = await previewDialog.evaluate((node) => ({
      right: node.getBoundingClientRect().right,
      left: node.getBoundingClientRect().left,
      viewport: window.innerWidth,
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth
    }));
    assert.ok(previewGeometry.left >= 0 && previewGeometry.right <= previewGeometry.viewport, 'mobile preview outside viewport');
    assert.ok(previewGeometry.scrollWidth <= previewGeometry.clientWidth, 'mobile preview horizontal overflow');
    await page.screenshot({ path: path.join(output, 'mobile-version-preview.png'), fullPage: true });
    await page.locator('[data-close-preview]').click();

    await page.locator('[data-edit-course-version="CV-2"]').click();
    const draftDialog = page.locator('.course-version-editor-dialog');
    await draftDialog.getByRole('heading', { name: 'Editar versão 2' }).waitFor();
    await draftDialog.getByText('As alterações são guardadas apenas neste rascunho.', { exact: true }).waitFor();
    const firstLesson = draftDialog.getByText('Fundamentos', { exact: true }).first();
    await firstLesson.waitFor();
    assert.equal(await draftDialog.locator('[data-create-draft-lesson]').count(), 1);
    assert.equal(await draftDialog.locator('[data-create-draft-content]').count(), 2);
    assert.equal(await draftDialog.locator('[data-remove-draft-lesson]').count(), 2);
    assert.equal(await draftDialog.locator('[data-remove-draft-content]').count(), 3);
    assert.equal(await draftDialog.locator('[data-attach-bank-question]').count(), 2);
    await draftDialog.locator('[data-attach-bank-question]').first().click();
    const picker = page.locator('.question-bank-picker');
    await picker.getByRole('heading', { name: 'Adicionar questão publicada' }).waitFor();
    await picker.getByText('Risco de execução do projeto', { exact: true }).waitFor();
    const pickerGeometry = await picker.evaluate((node) => ({
      left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right,
      viewport: window.innerWidth, scrollWidth: node.scrollWidth, clientWidth: node.clientWidth
    }));
    assert.ok(pickerGeometry.left >= 0 && pickerGeometry.right <= pickerGeometry.viewport, 'mobile question picker outside viewport');
    assert.ok(pickerGeometry.scrollWidth <= pickerGeometry.clientWidth, 'mobile question picker horizontal overflow');
    await picker.locator('.dialog-close').click();
    const draftGeometry = await draftDialog.evaluate((node) => ({
      right: node.getBoundingClientRect().right,
      left: node.getBoundingClientRect().left,
      viewport: window.innerWidth,
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth
    }));
    assert.ok(draftGeometry.left >= 0 && draftGeometry.right <= draftGeometry.viewport, 'mobile draft editor outside viewport');
    assert.ok(draftGeometry.scrollWidth <= draftGeometry.clientWidth, 'mobile draft editor horizontal overflow');
    await page.screenshot({ path: path.join(output, 'mobile-draft-editor.png'), fullPage: true });
    await firstLesson.scrollIntoViewIfNeeded();
    const outlineGeometry = await draftDialog.locator('.course-version-editor-outline').evaluate((node) => ({
      right: node.getBoundingClientRect().right,
      left: node.getBoundingClientRect().left,
      width: node.getBoundingClientRect().width,
      scrollWidth: node.scrollWidth
    }));
    assert.ok(outlineGeometry.left >= draftGeometry.left && outlineGeometry.right <= draftGeometry.right, 'draft outline outside dialog');
    assert.ok(outlineGeometry.scrollWidth <= outlineGeometry.width + 1, 'draft outline horizontal overflow');
    await page.screenshot({ path: path.join(output, 'mobile-draft-outline.png'), fullPage: true });
    await draftDialog.locator('[data-close-draft-editor]').click();

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
