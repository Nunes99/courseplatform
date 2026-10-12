const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8767';

const dashboard = {
  operator: { fullName: 'Operador de Teste', role: 'GLOBAL_OWNER' },
  summary: { organizations: 1, activeOrganizations: 1, pendingOnboarding: 1, readyForProvisioning: 0 },
  organizations: [{
    organizationId: 'ORG-TEST', slug: 'instituicao-atual', displayName: 'Instituição Atual',
    status: 'ACTIVE', memberCount: 12, courseCount: 3, createdAt: '2026-01-01T10:00:00Z'
  }],
  onboardingRequests: [{
    requestId: 'ONB-TEST', requestedSlug: 'nova-instituicao', displayName: 'Nova Instituição',
    legalName: 'Nova Instituição, Lda.', contactName: 'Responsável de Teste',
    contactEmail: 'contacto@example.test', contactPhone: '+258 000 000 000', countryCode: 'MZ',
    websiteUrl: 'https://example.test', planCode: 'STANDARD', applicantNotes: 'Pedido sintético para validação.',
    reviewNotes: '', reviewChecklist: {}, status: 'UNDER_REVIEW',
    submittedAt: '2026-10-12T12:00:00Z', updatedAt: '2026-10-12T12:05:00Z'
  }],
  provisioningEnabled: false
};

async function main() {
  const output = path.join(root, 'tmp/ui/platform-onboarding');
  await fs.mkdir(output, { recursive: true });
  const submissions = [];
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, locale: 'pt-PT', serviceWorkers: 'block' });
  const errors = [];
  try {
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== new URL(base).origin) return route.fulfill({ status: 204, body: '' });
      if (url.pathname === '/platform' || url.pathname === '/platform.html') {
        return route.fulfill({ contentType: 'text/html', body: await fs.readFile(path.join(root, 'public/platform.html'), 'utf8') });
      }
      if (url.pathname === '/platform.js') {
        return route.fulfill({ contentType: 'application/javascript', body: await fs.readFile(path.join(root, 'public/platform.js'), 'utf8') });
      }
      if (url.pathname === '/assets/css/platform.css') {
        return route.fulfill({ contentType: 'text/css', body: await fs.readFile(path.join(root, 'public/assets/css/platform.css'), 'utf8') });
      }
      if (url.pathname === '/api/v1/platform/auth/sessions' && request.method() === 'POST') {
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { platformToken: 'qa-token' } }) });
      }
      if (url.pathname === '/api/v1/platform/dashboard') {
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: dashboard }) });
      }
      if (url.pathname === '/api/v1/platform/onboarding-requests/ONB-TEST' && request.method() === 'PATCH') {
        const payload = JSON.parse(request.postData());
        submissions.push(payload);
        const complete = Object.values(payload.reviewChecklist || {}).length === 5
          && Object.values(payload.reviewChecklist).every(Boolean)
          && payload.readinessConfirmation === 'nova-instituicao';
        if (!complete) {
          return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ success: false, error: { code: 'ONBOARDING_CHECKLIST_INCOMPLETE', message: 'Conclua toda a checklist.' } }) });
        }
        dashboard.onboardingRequests[0] = { ...dashboard.onboardingRequests[0], status: 'READY_FOR_PROVISIONING', reviewChecklist: payload.reviewChecklist };
        dashboard.summary = { ...dashboard.summary, pendingOnboarding: 0, readyForProvisioning: 1 };
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { request: dashboard.onboardingRequests[0], provisioningEnabled: false } }) });
      }
      return route.fulfill({ status: 404, body: '' });
    });

    await page.goto(`${base}/platform`);
    await page.getByLabel('Email').fill('operator@example.test');
    await page.getByLabel('Palavra-passe').fill('password');
    await page.getByRole('button', { name: 'Entrar na administração global' }).click();
    await page.getByRole('button', { name: 'Rever pedido' }).click();

    const dialog = page.getByRole('dialog', { name: 'Nova Instituição' });
    await dialog.getByLabel('Decisão').selectOption('READY_FOR_PROVISIONING');
    assert.ok(await dialog.getByText('Separação de responsabilidades').isVisible());
    await dialog.getByRole('button', { name: 'Guardar decisão' }).click();
    await page.getByText('Conclua toda a checklist.').waitFor();
    assert.equal(submissions.length, 1);

    for (const label of Object.values({
      institutionIdentity: 'Identidade e existência legal verificadas',
      contactAuthority: 'Responsável e autoridade de contacto confirmados',
      slugAvailability: 'Identificador público e conflitos verificados',
      dataProtection: 'Responsabilidades de dados e privacidade revistas',
      commercialApproval: 'Plano, limites e condições comerciais aprovados'
    })) await dialog.getByLabel(label).check();
    await dialog.getByLabel(/Confirme o identificador/).fill('nova-instituicao');
    await page.screenshot({ path: path.join(output, 'review-desktop.png'), fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    const geometry = await dialog.evaluate(element => ({
      left: element.getBoundingClientRect().left,
      right: element.getBoundingClientRect().right,
      viewport: innerWidth,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth
    }));
    assert.ok(geometry.left >= 0 && geometry.right <= geometry.viewport, JSON.stringify(geometry));
    assert.ok(geometry.scrollWidth <= geometry.clientWidth, JSON.stringify(geometry));
    await page.screenshot({ path: path.join(output, 'review-mobile.png'), fullPage: true });

    await dialog.getByRole('button', { name: 'Guardar decisão' }).click();
    await page.getByText('Decisão de onboarding guardada.').waitFor();
    assert.equal(submissions.length, 2);
    assert.equal(submissions[1].expectedUpdatedAt, '2026-10-12T12:05:00Z');
    assert.equal(submissions[1].readinessConfirmation, 'nova-instituicao');
    assert.equal(dashboard.provisioningEnabled, false);
    assert.deepEqual(errors, []);
    console.log('Platform onboarding passed workflow, payload, desktop and mobile checks.');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
