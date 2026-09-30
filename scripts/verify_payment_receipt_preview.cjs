const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8767';

async function main() {
  const output = path.join(root, 'tmp/ui/payment-receipt-preview');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, locale: 'pt-PT', serviceWorkers: 'block' });
  const errors = [];
  const submissions = [];
  try {
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) {
        return route.fulfill({ status: 204, body: '' });
      }
      if (url.pathname === '/api/index') {
        const payload = route.request().method() === 'POST'
          ? JSON.parse(route.request().postData())
          : Object.fromEntries(url.searchParams);
        if (payload.action === 'submitProfessionalCertificatePayment') submissions.push(payload);
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: {} }) });
      }
      if (url.pathname === '/app.js') {
        const source = await fs.readFile(path.join(root, 'public/app.js'), 'utf8');
        return route.fulfill({
          contentType: 'application/javascript',
          body: `${source}\nwindow.__qaOpenPayment = () => showPaymentDialog('REQ-TEST');`
        });
      }
      if (url.pathname === '/assets/css/styles.css' || url.pathname === '/assets/css/tokens.css') {
        const source = await fs.readFile(path.join(root, 'public', url.pathname), 'utf8');
        return route.fulfill({ contentType: 'text/css', body: source });
      }
      return route.continue();
    });
    await page.addInitScript((origin) => {
      window.COURSE_PLATFORM_API_URL = `${origin}/api/index`;
      localStorage.setItem('courseSessionToken', 'qa-student-session');
    }, base);
    await page.goto(`${base}/index.html`);
    await page.waitForFunction(() => Boolean(window.__qaOpenPayment));
    await page.evaluate(() => window.__qaOpenPayment());

    const dialog = page.getByRole('dialog', { name: 'Enviar comprovativo' });
    assert.equal(await page.locator('.dialog-overlay').evaluate((element) => getComputedStyle(element).position), 'fixed');
    const input = dialog.locator('[name="paymentReceipt"]');
    const submit = dialog.getByRole('button', { name: 'Confirmar e enviar para revisão' });
    assert.equal(await submit.isDisabled(), true, 'submit must remain disabled before preview');

    await input.setInputFiles({
      name: 'recibo-teste.png',
      mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64')
    });
    assert.equal(submissions.length, 0, 'selecting a file must not submit it');
    await dialog.getByText('Confirme o comprovativo', { exact: true }).waitFor();
    assert.ok(await dialog.getByText('recibo-teste.png', { exact: true }).isVisible());
    assert.ok(await dialog.locator('img[alt="Pré-visualização do comprovativo selecionado"]').isVisible());
    assert.equal(await submit.isEnabled(), true);
    await page.screenshot({ path: path.join(output, 'image-desktop.png'), fullPage: true });

    await dialog.getByRole('button', { name: 'Trocar ficheiro' }).click();
    await input.setInputFiles(path.join(root, 'output/pdf/certificado-participacao-validacao.pdf'));
    assert.equal(submissions.length, 0, 'changing a file must not submit it');
    assert.ok(await dialog.locator('iframe[title="Pré-visualização do comprovativo em PDF"]').isVisible());
    assert.ok(await dialog.getByText('PDF', { exact: true }).isVisible());
    assert.ok(await dialog.getByRole('link', { name: 'Abrir em tamanho completo' }).isVisible());

    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'pdf-mobile.png'), fullPage: true });
    const geometry = await dialog.evaluate((element) => ({
      left: element.getBoundingClientRect().left,
      right: element.getBoundingClientRect().right,
      viewport: innerWidth,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth
    }));
    assert.ok(geometry.left >= 0 && geometry.right <= geometry.viewport, `dialog outside viewport: ${JSON.stringify(geometry)}`);
    assert.ok(geometry.scrollWidth <= geometry.clientWidth, `dialog overflows horizontally: ${JSON.stringify(geometry)}`);

    await submit.click();
    await page.waitForFunction(() => document.querySelector('.dialog-overlay') === null);
    assert.equal(submissions.length, 1, 'confirmation must submit exactly once');
    assert.equal(submissions[0].receiptFileName, 'certificado-participacao-validacao.pdf');
    assert.equal(submissions[0].receiptMimeType, 'application/pdf');
    assert.deepEqual(errors, []);
    console.log('Payment receipt preview passed image/PDF, confirmation and mobile layout checks.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
