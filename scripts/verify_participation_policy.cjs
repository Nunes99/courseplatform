const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8767';

async function main() {
  const output = path.join(root, 'tmp/ui/participation-policy');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const errors = [], sent = [];
  const course = { courseId: 'C1', title: 'Economia Industrial e Analise de Investimentos', totalHours: 12 };
  const student = { studentId: 'S1', fullName: 'Estudante de Teste', email: 'teste@example.org' };
  let settings = { certificateProfile: { issuerName: 'LMTWEBNAIRS', printAccess: 'paid', printFee: '1000', printCurrency: 'MZN',
    participation: { enabled: true, releaseMode: 'approval', maxDownloads: 2, instructions: 'Confirme os seus dados pessoais antes de solicitar o certificado.' } } };
  const certificate = { certificateId: 'CERT1', certificateType: 'SIMPLE', certificateNumber: 'LSS-2026-TEST123456',
    courseId: 'C1', courseTitle: course.title, studentName: student.fullName, status: 'ISSUED', downloadCount: 0,
    issueDate: new Date().toISOString(), downloadAccess: { allowed: false, code: 'CERTIFICATE_APPROVAL_REQUIRED',
      message: 'Solicite a aprovacao da administracao para baixar o certificado.', maxDownloads: 2, remainingDownloads: 2 } };
  const requests = [];
  try {
    for (const panel of ['admin', 'student']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Africa/Maputo', locale: 'pt-PT', serviceWorkers: 'block' });
      page.on('pageerror', error => errors.push(`${panel}: ${error.message}`));
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
          if (payload.action === 'adminListCourses') data = { courses: [{ course }] };
          if (payload.action === 'adminGetCertificateSettings') data = { course, settings };
          if (payload.action === 'adminListCertificates') data = { certificates: [certificate] };
          if (payload.action === 'adminListCertificateRequests') data = { requests };
          if (payload.action === 'adminSaveCertificateSettings') { settings = { ...settings, certificateProfile: payload.certificateProfile }; data = { settings, course }; }
          if (payload.action === 'getMyCertifications') data = { course, student, completed: true,
            enrollment: { status: 'COMPLETED', progressPercent: 100 }, settings, requests,
            simpleCertificate: settings.certificateProfile.participation.enabled ? certificate : null,
            certificates: settings.certificateProfile.participation.enabled ? [certificate] : [] };
          if (payload.action === 'requestParticipationCertificate') {
            requests.push({ requestId: 'REQ1', requestType: 'PARTICIPATION', status: 'PAYMENT_SUBMITTED', studentName: student.fullName, courseTitle: course.title });
            data = { request: requests[0] };
          }
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data }) });
        }
        const module = panel === 'admin' ? 'admin' : 'app';
        if (url.pathname === `/${module}.js`) {
          const source = await fs.readFile(path.join(root, `public/${module}.js`), 'utf8');
          const hook = panel === 'admin'
            ? `\nwindow.__qaOpen = async data => { sessionStorage.setItem('courseAdminToken','qa'); state.admin = {role:'OWNER',fullName:'Administrador de Teste'}; state.selectedCourseId = 'C1'; state.currentView = 'certifications'; renderAdminShell(); await loadCertifications({force:true}); };`
            : `\nwindow.__qaOpen = async data => { localStorage.setItem('courseSessionToken','qa'); state.selectedCourseId = 'C1'; state.dashboard = data; await renderCertifications(); };`;
          return route.fulfill({ contentType: 'application/javascript', body: source + hook });
        }
        return route.continue();
      });
      await page.addInitScript(base => { window.COURSE_PLATFORM_API_URL = `${base}/api/index`; }, base);
      await page.goto(`${base}/${panel === 'admin' ? 'admin.html' : 'index.html'}`);
      await page.waitForFunction(() => Boolean(window.__qaOpen));
      await page.locator(panel === 'admin' ? '#adminLoginForm' : '#loginForm').waitFor();
      await page.evaluate(data => window.__qaOpen(data), { course, student });
      if (panel === 'admin') {
        await page.locator('[name="participationEnabled"]').uncheck();
        assert.equal(await page.locator('#participationPolicyOptions').isVisible(), false);
        await page.getByRole('button', { name: 'Guardar configuração do curso' }).click();
        await page.waitForFunction(() => document.querySelector('[name="participationEnabled"]')?.checked === false);
        assert.equal(settings.certificateProfile.participation.enabled, false);
        await page.locator('[name="participationEnabled"]').check();
        await page.locator('[name="participationReleaseMode"]').selectOption('approval');
        await page.locator('[name="participationMaxDownloads"]').fill('3');
        await page.locator('[name="participationAvailableFrom"]').fill('2026-09-01T10:00');
        await page.locator('[name="participationAvailableUntil"]').fill('2027-09-01T10:00');
        await page.getByRole('button', { name: 'Guardar configuração do curso' }).click();
        await page.waitForFunction(() => document.querySelector('[name="participationMaxDownloads"]')?.value === '3');
        assert.ok(sent.some(item => item.action === 'adminSaveCertificateSettings' && item.certificateProfile.participation.availableFrom?.endsWith('Z')));
        await page.locator('[name="participationMaxDownloads"]').fill('5');
        await page.getByRole('button', { name: 'Cancelar alterações' }).click();
        assert.equal(await page.locator('[name="participationMaxDownloads"]').inputValue(), '3');
      } else {
        assert.ok(await page.getByText('Gratuito', { exact: true }).isVisible());
        assert.ok(await page.getByText('Até 3 por estudante', { exact: true }).isVisible());
        assert.ok(await page.getByRole('button', { name: 'Indisponível', exact: true }).isDisabled());
        await page.locator('[data-request-participation]').click();
        await page.getByText('Pedido recebido. Aguarde a aprovação da administração.', { exact: true }).waitFor();
        assert.equal(await page.locator('[data-request-participation]').count(), 0);
        assert.ok(await page.getByRole('button', { name: 'Quero certificado profissional' }).isVisible(), 'Participation request must not replace professional flow');
      }
      for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
        await page.setViewportSize({ width, height });
        await page.waitForTimeout(350);
        const target = page.locator(panel === 'admin' ? '.participation-policy' : '.participation-conditions');
        await target.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(output, `${panel}-${label}.png`) });
        const sizes = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
        assert.ok(sizes[0] <= sizes[1], `${panel} ${label}: horizontal overflow ${sizes}`);
      }
      if (panel === 'student') {
        settings.certificateProfile.participation.enabled = false;
        await page.evaluate(data => window.__qaOpen(data), { course, student });
        assert.ok(await page.getByText('Este curso não inclui certificado de participação gratuito.', { exact: false }).isVisible());
        assert.equal(await page.locator('[data-preview-certificate]').count(), 0);
        assert.equal(await page.locator('[data-request-participation]').count(), 0);
        assert.ok(await page.locator('[data-open-professional-survey]').isVisible());
      }
      await page.close();
    }
    assert.deepEqual(errors, []);
    console.log('Participation policy save/reset, student conditions/request and professional-only course passed at desktop/mobile sizes (mock API).');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
