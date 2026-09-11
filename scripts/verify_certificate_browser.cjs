const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';

async function main() {
  const fixture = JSON.parse(await fs.readFile(path.join(root, 'tests/fixtures/professional_certificate.json'), 'utf8'));
  const certificate = {
    certificateId: 'DEMO', certificateType: 'PROFESSIONAL',
    certificateNumber: fixture.certificate_number, verificationCode: fixture.verification_code,
    studentName: fixture.student_name, courseTitle: fixture.course_title,
    issueDate: fixture.issue_date, finalScore: fixture.final_score, contentSummary: fixture.content_summary,
    templateSnapshot: { profile: fixture.certificate_profile, courseHours: 36 }
  };
  const output = path.join(root, 'tmp/ui/certificate-layout');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const failures = [];
  try {
    for (const panel of ['admin', 'student']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
      page.on('pageerror', (error) => failures.push(`${panel}: ${error.message}`));
      // Run the real page modules with synthetic data and no production requests.
      await page.route('**/*', async (route) => {
        const requestUrl = new URL(route.request().url());
        if (requestUrl.origin !== new URL(base).origin) {
          const type = route.request().resourceType();
          if (type === 'script') return route.fulfill({ contentType: 'application/javascript', body: '' });
          if (type === 'stylesheet') return route.fulfill({ contentType: 'text/css', body: '' });
          if (type === 'image') return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/>' });
          return route.fulfill({ contentType: 'application/json', body: '{}' });
        }
        if (requestUrl.pathname === '/api/index') {
          return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { mediaConfig: {}, courses: [], database: true } }) });
        }
        if (requestUrl.pathname === `/${panel === 'admin' ? 'admin' : 'app'}.js`) {
          const source = await fs.readFile(path.join(root, `public/${panel === 'admin' ? 'admin' : 'app'}.js`), 'utf8');
          const hook = panel === 'admin'
            ? '\nwindow.__qaOpen = openAdminCertificatePreview; window.__qaThumbnail = adminCertificateThumbnailTemplate;'
            : '\nwindow.__qaOpen = (cert) => { state.certifications = {certificates:[cert]}; showCertificatePreview(cert.certificateId); };';
          return route.fulfill({ contentType: 'application/javascript', body: source + hook });
        }
        return route.continue();
      });
      await page.addInitScript(({ base }) => { window.COURSE_PLATFORM_API_URL = `${base}/api/index`; }, { base });
      await page.goto(`${base}/${panel === 'admin' ? 'admin.html' : 'index.html'}`);
      await page.waitForFunction(() => Boolean(window.__qaOpen));
      await page.evaluate((data) => window.__qaOpen(data), certificate);
      const component = page.locator('professional-certificate').last();
      await component.waitFor();
      await page.waitForFunction(() => Boolean(document.querySelector('professional-certificate')?.dataset.ready));
      assert.equal(await component.getAttribute('data-ready'), 'true', await component.textContent());
      const inspect = async () => page.evaluate(async () => {
        const host = document.querySelector('professional-certificate');
        const layout = await fetch('/assets/certificate-layout.json').then((r) => r.json());
        const problems = [];
        const root = host.shadowRoot;
        for (const group of root.querySelectorAll('[data-field]')) {
          const key = group.dataset.field;
          const box = layout.texts[key];
          if (!box) continue;
          const bounds = group.querySelector('text').getBBox();
          if (bounds.x < box.x - .5 || bounds.y < box.y - .5 || bounds.x + bounds.width > box.x + box.w + .5 || bounds.y + bounds.height > box.y + box.h + .5) problems.push({key, x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, box});
        }
        const svg = root.querySelector('.paper > svg');
        const rect = svg.getBoundingClientRect();
        const viewport = root.querySelector('.viewport');
        return { problems, ratio: rect.width / rect.height, width: document.documentElement.scrollWidth, viewport: window.innerWidth, clipped: viewport.scrollHeight > viewport.clientHeight + 1, text: svg.textContent };
      });
      for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844], ['small', 320, 568]]) {
        await page.setViewportSize({ width, height });
        await page.waitForTimeout(100);
        const result = await inspect();
        await page.screenshot({ path: path.join(output, `${panel}-${label}.png`) });
        assert.deepEqual(result.problems, [], `${panel} ${label}: text outside its box`);
        assert.ok(Math.abs(result.ratio - 297 / 210) < .001, 'A4 ratio');
        assert.ok(result.width <= result.viewport, 'Page overflow');
        assert.ok(!result.clipped, 'Full page visible in fit mode');
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      await component.getByRole('button', { name: '100%', exact: true }).click();
      const realWidth = await component.locator('.paper > svg').evaluate((node) => node.getBoundingClientRect().width);
      assert.ok(Math.abs(realWidth - 1122.52) < 1);
      await component.getByRole('button', { name: 'Ajustar', exact: true }).click();
      await component.locator('.paper > svg').screenshot({ path: path.join(output, `${panel}-document.png`) });
      const long = structuredClone(certificate);
      long.studentName = 'Ana Sofia Luís de Almeida e Vasconcelos Chissano';
      long.courseTitle = 'Economia Industrial, Análise de Investimentos e Gestão de Projetos Energéticos';
      long.contentSummary += '\nAvaliação económica de projetos\nSegurança e responsabilidade social';
      await component.evaluate((node, data) => { node.dataset.ready = ''; node.dataset.certificate = JSON.stringify(data); }, long);
      await page.waitForFunction(() => document.querySelector('professional-certificate')?.dataset.ready === 'true');
      const stress = await inspect();
      assert.deepEqual(stress.problems, []);
      assert.ok(stress.text.includes('Chissano'));
      await component.locator('.paper > svg').screenshot({ path: path.join(output, `${panel}-long.png`) });
      await component.evaluate((node, data) => { node.dataset.ready = ''; node.dataset.certificate = JSON.stringify(data); }, { ...certificate, studentName: 'Nome muito longo '.repeat(40) });
      await component.getByRole('alert').waitFor();
      assert.ok(await component.getByRole('alert').textContent());
      if (panel === 'admin') {
        await page.evaluate((data) => {
          document.querySelector('.dialog-overlay')?.remove();
          const container = document.createElement('div');
          container.className = 'certificate-preview-sheet is-professional certificate-admin-mini-preview';
          container.style.cssText = 'width:480px;max-width:100%;margin:auto';
          container.innerHTML = window.__qaThumbnail(data);
          document.body.replaceChildren(container);
        }, certificate);
        const thumbnail = page.locator('professional-certificate');
        await page.waitForFunction(() => document.querySelector('professional-certificate')?.dataset.ready === 'true');
        assert.deepEqual((await inspect()).problems, []);
        assert.equal(await thumbnail.getByRole('button').count(), 0);
        await page.screenshot({ path: path.join(output, 'admin-inline.png') });
        await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
        assert.deepEqual((await inspect()).problems, []);
        await page.screenshot({ path: path.join(output, 'admin-inline-dark.png') });
      }
      await page.close();
    }
    assert.deepEqual(failures, [], 'Browser errors');
    console.log('Admin + student: A4 proportions, bounded text, 3 viewport sizes, zoom and overflow validation passed.');
  } finally { await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
