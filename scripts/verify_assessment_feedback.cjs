const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8766';

async function main() {
  const output = path.join(root, 'tmp/ui/assessment-feedback');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const errors = [];
  const sent = [];
  try {
    for (const panel of ['admin', 'student']) {
      const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
        locale: 'pt-PT',
        serviceWorkers: 'block',
      });
      page.on('pageerror', error => errors.push(`${panel}: ${error.message}`));
      page.on('console', message => {
        if (message.type() === 'error') {
          const location = message.location();
          errors.push(`${panel}: ${message.text()}${location.url ? ` (${location.url})` : ''}`);
        }
      });
      page.on('requestfailed', request => {
        errors.push(`${panel}: request failed ${request.url()} (${request.failure()?.errorText || 'unknown'})`);
      });
      page.on('dialog', dialog => dialog.accept());
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/assets/css/styles.css' || url.pathname === '/assets/css/tokens.css') {
          const fileName = path.basename(url.pathname);
          const source = await fs.readFile(path.join(root, 'public/assets/css', fileName), 'utf8');
          return route.fulfill({ contentType: 'text/css', body: source });
        }
        if (url.origin !== new URL(base).origin) {
          const type = route.request().resourceType();
          return route.fulfill({
            contentType: type === 'script' ? 'application/javascript' : type === 'stylesheet' ? 'text/css' : 'application/json',
            body: type === 'script' || type === 'stylesheet' ? '' : '{}',
          });
        }
        if (url.pathname === '/api/index') {
          const payload = route.request().method() === 'POST'
            ? JSON.parse(route.request().postData())
            : Object.fromEntries(url.searchParams);
          sent.push(payload);
          let data = {};
          if (payload.action === 'adminSaveLesson') data = { lesson: payload };
          if (payload.action === 'adminListCourses') data = { courses: [], pagination: { total: 0 } };
          if (payload.action === 'adminGetCourseStructure') data = { course: { courseId: 'C1' }, lessons: [] };
          if (payload.action === 'adminListGroups') data = { groups: [] };
          if (payload.action === 'adminListStudents') data = { students: [], pagination: { total: 0 } };
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data }) });
        }
        if (/^\/api\/v1\/catalog\/courses\/[^/]+\/media$/.test(url.pathname)) {
          return route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({ success: true, data: { logoUrl: '', videos: [] } }),
          });
        }
        if (url.pathname === `/${panel === 'admin' ? 'admin' : 'app'}.js`) {
          const module = panel === 'admin' ? 'admin' : 'app';
          const source = await fs.readFile(path.join(root, `public/${module}.js`), 'utf8');
          const hook = panel === 'admin'
            ? `
window.__qaAssessmentPolicy = () => {
  sessionStorage.setItem('courseAdminToken', 'qa');
  state.admin = { role: 'OWNER', fullName: 'Administrador de Teste' };
  renderAdminShell();
  state.courseStructure = {
    course: { courseId: 'C1', passingScore: 60 },
    lessons: [{ lesson: {
      lessonId: 'L1', courseId: 'C1', lessonNumber: 1, title: 'Avaliação segura',
      submissionDurationMinutes: 60, passingScore: 60, status: 'ACTIVE',
      feedbackReleaseMode: 'AFTER_REVIEW', showCorrectAnswers: false, showExplanations: true
    }}]
  };
  showLessonDialog('L1');
};`
            : `
window.__qaAssessmentPolicy = data => {
  root.innerHTML = '<section id="assessmentArea" class="assessment-area"></section>';
  document.querySelector('#assessmentArea').innerHTML = reviewStateTemplate(data.attempt, data.latestReview, data);
};`;
          return route.fulfill({ contentType: 'application/javascript', body: source + hook });
        }
        return route.continue();
      });
      await page.addInitScript(origin => {
        window.COURSE_PLATFORM_API_URL = `${origin}/api/index`;
      }, base);
      await page.goto(`${base}/${panel === 'admin' ? 'admin.html' : 'index.html'}`);
      await page.waitForFunction(() => Boolean(window.__qaAssessmentPolicy));

      if (panel === 'admin') {
        await page.evaluate(() => window.__qaAssessmentPolicy());
        const form = page.locator('#lessonForm');
        await form.waitFor();
        assert.equal(await form.locator('[name="feedbackReleaseMode"]').inputValue(), 'AFTER_REVIEW');
        assert.equal(await form.locator('[name="showCorrectAnswers"]').isChecked(), false);
        assert.equal(await form.locator('[name="showExplanations"]').isChecked(), true);
        for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
          await page.setViewportSize({ width, height });
          const dialog = page.locator('.course-lesson-dialog');
          const bounds = await dialog.boundingBox();
          assert.ok(bounds && bounds.width <= width, `admin dialog exceeds ${label} viewport`);
          assert.equal(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth), true);
          await page.screenshot({ path: path.join(output, `admin-dialog-${label}.png`), fullPage: true });
        }
        await page.setViewportSize({ width: 1440, height: 1000 });
        await form.locator('[name="feedbackReleaseMode"]').selectOption('AFTER_SUBMISSION');
        await form.locator('[name="showCorrectAnswers"]').check();
        await form.getByRole('button', { name: 'Guardar módulo' }).click();
        await page.waitForFunction(() => !document.querySelector('#lessonForm'));
        const request = sent.find(item => item.action === 'adminSaveLesson');
        assert.equal(request.feedbackReleaseMode, 'AFTER_SUBMISSION');
        assert.equal(request.showCorrectAnswers, true);
        assert.equal(request.showExplanations, true);
      } else {
        const data = {
          attempt: { attemptId: 'A1', attemptNumber: 1, status: 'APPROVED', score: 100, reviewedAt: new Date().toISOString() },
          latestReview: { comments: 'Bom trabalho.', reviewedAt: new Date().toISOString() },
          feedbackPolicy: { releaseMode: 'AFTER_REVIEW', correctAnswersVisible: true, explanationsVisible: true },
          answers: [{ questionId: 'Q1', selectedOptionId: 'O1' }],
          questions: [{
            questionId: 'Q1', questionOrder: 1, prompt: 'Qual é a opção correta?', correctAnswer: 'O1',
            explanation: 'A primeira opção satisfaz o critério.',
            options: [{ optionId: 'O1', optionLabel: 'A', optionText: 'Primeira', isCorrect: true }],
          }],
          files: [{
            fileId: 'F1', fileName: 'trabalho-final.pdf', sizeBytes: 102400,
            contentUrl: '/api/files/F1/content'
          }],
        };
        await page.evaluate(value => window.__qaAssessmentPolicy(value), data);
        assert.ok(await page.getByText('Resposta correta:', { exact: false }).isVisible());
        assert.ok(await page.getByText('Explicação:', { exact: false }).isVisible());
        assert.ok(await page.getByRole('heading', { name: 'Ficheiros submetidos' }).isVisible());
        assert.equal(await page.getByRole('button', { name: 'Abrir', exact: true }).count(), 1);
        assert.equal(await page.getByRole('button', { name: 'Baixar', exact: true }).count(), 1);
        assert.equal(await page.getByRole('button', { name: 'Eliminar', exact: true }).count(), 0);
      }

      for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
        await page.setViewportSize({ width, height });
        await page.screenshot({ path: path.join(output, `${panel}-${label}.png`), fullPage: true });
        const sizes = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
        assert.ok(sizes.page <= sizes.viewport, `${panel} ${label}: horizontal overflow`);
      }
      await page.close();
    }
    assert.deepEqual(errors, []);
    console.log('Assessment feedback policy passed in admin/student views at desktop/mobile sizes (mock API, no production data).');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
