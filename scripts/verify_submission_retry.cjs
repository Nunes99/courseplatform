const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8766';

async function main() {
  const output = path.join(root, 'tmp/ui/submission-retry');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const errors = [];
  const sent = [];
  const deadline = new Date(Date.now() + 48 * 3600000).toISOString();
  const submission = {
    student: { studentId: 'S1', fullName: 'Estudante de Teste', email: 'teste@example.org' },
    lesson: { lessonId: 'L1', title: 'Trabalho de avaliacao', submissionDurationMinutes: 180 },
    progress: { contentAccessStatus: 'AVAILABLE', evaluationStatus: 'TIME_EXCEEDED', status: 'TIME_EXCEEDED' },
    attempt: { attemptId: 'A1', attemptNumber: 1, status: 'TIME_EXCEEDED', score: null, retryAuthorized: false,
      deadlineAt: new Date(Date.now() - 3600000).toISOString() },
    answers: [], files: [], reviews: [], questions: []
  };
  const attemptData = { attempt: null, answers: [], files: [], latestReview: null };
  try {
    for (const panel of ['admin', 'student']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Africa/Maputo', locale: 'pt-PT', serviceWorkers: 'block' });
      page.on('pageerror', error => errors.push(`${panel}: ${error.message}`));
      page.on('requestfailed', request => errors.push(`${panel}: ${request.url()} ${request.failure()?.errorText}`));
      page.on('dialog', dialog => dialog.accept());
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== new URL(base).origin) {
          const type = route.request().resourceType();
          return route.fulfill({ contentType: type === 'script' ? 'application/javascript' : type === 'stylesheet' ? 'text/css' : type === 'image' ? 'image/svg+xml' : 'application/json',
            body: type === 'image' ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/>' : type === 'script' || type === 'stylesheet' ? '' : '{}' });
        }
        if (url.pathname === '/api/index') {
          const payload = route.request().method() === 'POST' ? JSON.parse(route.request().postData()) : Object.fromEntries(url.searchParams);
          sent.push(payload);
          let data = { mediaConfig: {}, courses: [], database: true };
          if (payload.action === 'adminGetCourseStructure') data = { course: { courseId: 'C1' }, lessons: [] };
          if (payload.action === 'adminListGroups') data = { groups: [] };
          if (payload.action === 'adminListStudents') data = { students: [] };
          if (payload.action === 'adminGetSubmission') data = submission;
          if (payload.action === 'adminAuthorizeRetry' || payload.action === 'adminReviewSubmission') {
            submission.attempt.status = 'CORRECTION_REQUIRED';
            submission.attempt.retryAuthorized = payload.authorized !== false;
            submission.progress.evaluationStatus = 'CORRECTION_REQUIRED';
            if (payload.correctionDeadline) submission.reviews = [{ decision: 'CORRECTION_REQUIRED', comments: payload.comments,
              correctionDeadline: payload.correctionDeadline, reviewedAt: new Date().toISOString() }];
            data = { attempt: submission.attempt };
          }
          if (payload.action === 'adminListPendingSubmissions' || payload.action === 'adminListSubmissions') data = { submissions: [] };
          if (payload.action === 'startAttempt') {
            attemptData.attempt = { ...submission.attempt, attemptId: 'A2', attemptNumber: 2, status: 'IN_PROGRESS', retryAuthorized: false, deadlineAt: deadline };
            data = { attempt: attemptData.attempt };
          }
          if (payload.action === 'getAttemptStatus') data = attemptData;
          if (payload.action === 'uploadFile') {
            attemptData.files = [{ fileId: 'F2', fileName: payload.fileName, sizeBytes: 12, driveUrl: `data:application/pdf;base64,${payload.base64Data}` }];
            data = { file: attemptData.files[0] };
          }
          if (payload.action === 'deleteUploadedFile') { attemptData.files = []; data = { file: { fileId: 'F2' } }; }
          if (payload.action === 'submitAttempt') { attemptData.attempt.status = 'UNDER_REVIEW'; data = { attempt: attemptData.attempt }; }
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data }) });
        }
        const module = panel === 'admin' ? 'admin' : 'app';
        if (url.pathname === `/${module}.js`) {
          const source = await fs.readFile(path.join(root, `public/${module}.js`), 'utf8');
          const hook = panel === 'admin'
            ? `\nwindow.__qaOpen = data => { sessionStorage.setItem('courseAdminToken','qa'); state.admin = {role:'OWNER',fullName:'Administrador de Teste'}; renderAdminShell(); state.selectedSubmission = data; renderSubmission(); };`
            : `\nwindow.__qaOpen = data => { localStorage.setItem('courseSessionToken','qa'); clearTimers(); state.lesson = data; state.attempt = data.attempt; state.attemptData = {latestReview:data.reviews[0]}; root.innerHTML = '<section id="assessmentArea" class="assessment-area"></section>'; document.querySelector('#assessmentArea').innerHTML = assessmentTemplate(data,data.attempt,state.attemptData); bindAssessmentEvents(); };`;
          return route.fulfill({ contentType: 'application/javascript', body: source + hook });
        }
        return route.continue();
      });
      await page.addInitScript(base => { window.COURSE_PLATFORM_API_URL = `${base}/api/index`; }, base);
      await page.goto(`${base}/${panel === 'admin' ? 'admin.html' : 'index.html'}`);
      await page.waitForFunction(() => Boolean(window.__qaOpen));
      await page.locator(panel === 'admin' ? '#adminLoginForm' : '#loginForm').waitFor();
      await page.evaluate(data => window.__qaOpen(data), submission);
      if (panel === 'admin') {
        const review = page.locator('#reviewForm');
        await review.locator('[name="decision"]').selectOption('CORRECTION_REQUIRED');
        assert.ok(await review.locator('[name="authorizeRetry"]').isChecked());
        assert.ok(await review.locator('[name="correctionDeadline"]').isVisible());
        assert.equal(await review.locator('[name="score"]').getAttribute('required'), null);
        const retry = page.locator('#retryForm');
        await retry.locator('[name="comments"]').fill('Carregue o documento correto.');
        await retry.getByRole('button', { name: 'Devolver e autorizar novo envio' }).click();
        await page.locator('#revokeRetry').waitFor();
        const request = sent.find(item => item.action === 'adminAuthorizeRetry' && item.authorized !== false);
        assert.ok(request.correctionDeadline.endsWith('Z'), 'Deadline sent with explicit timezone');
        assert.ok(new Date(request.correctionDeadline) > new Date());
        await page.locator('#revokeRetry').click();
        await page.waitForFunction(() => !document.querySelector('#revokeRetry'));
        assert.ok(sent.some(item => item.action === 'adminAuthorizeRetry' && item.authorized === false));
        await page.locator('#reviewForm [name="decision"]').selectOption('CORRECTION_REQUIRED');
        await page.locator('#reviewForm [name="comments"]').fill('Corrija e volte a enviar.');
        await page.locator('#reviewForm button[type="submit"]').click();
        await page.getByRole('button', { name: 'Aplicar alterações', exact: true }).waitFor();
        assert.ok(sent.some(item => item.action === 'adminReviewSubmission' && item.authorizeRetry && item.correctionDeadline.endsWith('Z')));
        await page.evaluate(data => window.__qaOpen(data), submission);
      } else {
        await page.getByRole('button', { name: 'Corrigir e reenviar documentos' }).click();
        await page.locator('#exerciseFiles').waitFor({ state: 'attached' });
        const upload = () => page.locator('#exerciseFiles').setInputFiles({ name: 'corrigido.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nTEST') });
        await upload();
        await page.locator('[data-delete-file="F2"]').waitFor();
        await page.locator('[data-delete-file="F2"]').click();
        await page.waitForFunction(() => !document.querySelector('[data-delete-file="F2"]'));
        await upload();
        await page.locator('[data-delete-file="F2"]').waitFor();
      }
      for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
        await page.setViewportSize({ width, height });
        assert.equal(await page.locator('.toast-error').count(), 0, await page.locator('.toast-error').allTextContents());
        await page.waitForTimeout(4500);
        if (panel === 'admin') {
          assert.ok(await page.locator('#retryForm').isVisible());
          const formLayout = await page.locator('#reviewForm').evaluate(form => {
            const option = form.querySelector('#reviewRetryOption');
            return { columns: getComputedStyle(form).gridTemplateColumns.split(' ').length, option: getComputedStyle(option).display };
          });
          assert.equal(formLayout.columns, 1, 'Review controls stay in one column');
          assert.equal(formLayout.option, 'flex', 'Checkbox and label remain aligned');
        }
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(output, `${panel}-${label}.png`), fullPage: true });
        const sizes = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
        assert.ok(sizes[0] <= sizes[1], `${panel} ${label}: horizontal overflow`);
      }
      if (panel === 'student') {
        await page.locator('#authorshipConfirmation').check();
        await page.locator('#submitAttempt').click();
        await page.getByRole('heading', { name: 'Atividade em avaliação' }).waitFor();
        assert.equal(await page.locator('#exerciseFiles').count(), 0);
        const expired = structuredClone(submission);
        expired.reviews[0].correctionDeadline = new Date(Date.now() - 10000).toISOString();
        await page.evaluate(data => window.__qaOpen(data), expired);
        assert.equal(await page.locator('#startAttempt').count(), 0);
        assert.ok(await page.getByText('O prazo de reenvio terminou.', { exact: false }).isVisible());
      }
      await page.close();
    }
    assert.deepEqual(errors, []);
    console.log('Admin return/revoke/review and student reupload/delete/submit passed at desktop/mobile sizes (mock API, no production data).');
  } catch (error) {
    console.error('Browser diagnostics:', errors);
    throw error;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
