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
    if (!locationUrl && message.text() === 'An unknown error occurred when fetching the script.') return;
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
    if (url.origin !== origin) {
      if (request.resourceType() === 'script') {
        return route.fulfill({ contentType: 'application/javascript', body: '' });
      }
      if (request.resourceType() === 'stylesheet') {
        return route.fulfill({ contentType: 'text/css', body: '' });
      }
      return route.abort('blockedbyclient');
    }
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
          const trigger = document.querySelector('#stage12DialogTrigger') || document.createElement('button');
          if (!trigger.isConnected) {
            trigger.id = 'stage12DialogTrigger';
            trigger.textContent = 'Abrir diálogo de teste';
            document.body.appendChild(trigger);
          }
          trigger.focus();
          showAdminRecoveryDialog('qa@example.test');
        };
        window.__stage12OpenDialogFixture = (kind) => {
          document.querySelector('[data-stage12-dialog-fixture]')?.remove();
          const trigger = document.querySelector('#stage12FixtureTrigger') || document.createElement('button');
          if (!trigger.isConnected) {
            trigger.id = 'stage12FixtureTrigger';
            trigger.textContent = 'Abrir diálogo interno';
            document.body.appendChild(trigger);
          }
          trigger.focus();
          const fixtures = {
            loading: '<div class="dialog-card student-detail-dialog"><button class="dialog-close" type="button">x</button><div class="loading-state" role="status">A carregar detalhes...</div></div>',
            preview: '<div class="dialog-card certificate-preview-dialog"><button class="dialog-close" type="button">x</button><div class="certificate-preview-sheet"><p>Certificado de participação</p></div><div class="dialog-actions"><button class="button button-secondary" type="button" data-close-dialog>Fechar</button></div></div>',
            nested: '<div class="dialog-card question-bank-picker"><button class="dialog-close" type="button">x</button><h2>Adicionar questão publicada</h2><button class="question-bank-list-item" type="button">Questão de exemplo</button></div>'
          };
          const overlay = document.createElement('div');
          overlay.className = kind === 'nested' ? 'dialog-overlay dialog-overlay-nested' : 'dialog-overlay';
          overlay.dataset.stage12DialogFixture = kind;
          overlay.innerHTML = fixtures[kind];
          document.body.appendChild(overlay);
          overlay.querySelectorAll('.dialog-close, [data-close-dialog]').forEach((button) => {
            button.addEventListener('click', () => overlay.remove());
          });
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
    if (url.pathname === '/app.js') {
      const source = await fs.readFile(path.join(publicRoot, 'app.js'), 'utf8');
      const hook = `
        window.__stage12OpenStudentLogin = () => renderLogin();
        window.__stage12OpenStudentRegistration = () => showStudentRegistrationDialog();
        window.__stage12OpenStudentRecovery = () => showStudentRecoveryDialog('qa@example.test');
        window.__stage12OpenStudentSurvey = () => {
          state.certifications = { settings: { surveyQuestions: [
            { id: 'q1', prompt: 'Como avalia a metodologia do curso?', options: ['Excelente', 'Boa', 'Regular'], required: true }
          ] } };
          showProfessionalSurveyDialog();
        };
        window.__stage12OpenStudentPayment = () => {
          state.certifications = { settings: {
            professionalPrice: 1000,
            professionalCurrency: 'MZN',
            paymentAccountName: 'Conta institucional',
            paymentAccountNumber: '000000',
            paymentInstructions: 'Confirme os dados antes de enviar o comprovativo.'
          } };
          showPaymentDialog('REQUEST-QA');
        };
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

async function auditAccessibility(page, label) {
  const domAudit = await page.evaluate(() => {
    const visibleDialogs = Array.from(document.querySelectorAll('[role="dialog"]'))
      .filter((dialog) => dialog.getClientRects().length > 0);
    const scope = visibleDialogs.at(-1) || document;
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity) > 0
        && rect.width > 0
        && rect.height > 0
        && element.getAttribute('aria-hidden') !== 'true';
    };
    const nameOf = (element) => {
      const labelledBy = String(element.getAttribute('aria-labelledby') || '')
        .split(/\s+/)
        .filter(Boolean)
        .map((id) => document.getElementById(id)?.textContent?.trim() || '')
        .filter(Boolean)
        .join(' ');
      const explicitLabel = element.id
        ? Array.from(document.querySelectorAll('label[for]'))
          .find((label) => label.htmlFor === element.id)?.textContent?.trim()
        : '';
      const wrappingLabel = element.closest('label')?.textContent?.trim() || '';
      return element.getAttribute('aria-label')?.trim()
        || labelledBy
        || explicitLabel
        || wrappingLabel
        || element.getAttribute('alt')?.trim()
        || element.textContent?.trim()
        || element.getAttribute('title')?.trim()
        || '';
    };
    const selectorOf = (element) => {
      if (element.id) return `#${element.id}`;
      const classes = Array.from(element.classList).slice(0, 2).join('.');
      return `${element.tagName.toLowerCase()}${classes ? `.${classes}` : ''}`;
    };
    const parseColor = (value) => {
      const match = String(value).match(/rgba?\(([^)]+)\)/i);
      if (!match) return null;
      const parts = match[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
      if (parts.length < 3 || parts.slice(0, 3).some((part) => !Number.isFinite(part))) return null;
      return [parts[0], parts[1], parts[2], Number.isFinite(parts[3]) ? parts[3] : 1];
    };
    const composite = (top, bottom) => {
      const alpha = top[3] + (bottom[3] * (1 - top[3]));
      if (alpha === 0) return [0, 0, 0, 0];
      return [0, 1, 2].map((index) => (
        ((top[index] * top[3]) + (bottom[index] * bottom[3] * (1 - top[3]))) / alpha
      )).concat(alpha);
    };
    const backgroundOf = (element) => {
      const chain = [];
      for (let node = element; node instanceof Element; node = node.parentElement) chain.unshift(node);
      let background = [255, 255, 255, 1];
      for (const node of chain) {
        const style = getComputedStyle(node);
        if (style.backgroundImage !== 'none') return null;
        const color = parseColor(style.backgroundColor);
        if (color && color[3] > 0) background = composite(color, background);
      }
      return background;
    };
    const luminance = (rgb) => {
      const channels = rgb.map((value) => {
        const normalized = value / 255;
        return normalized <= 0.04045
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2]);
    };
    const ratioOf = (foreground, background) => {
      const lighter = Math.max(luminance(foreground), luminance(background));
      const darker = Math.min(luminance(foreground), luminance(background));
      return (lighter + 0.05) / (darker + 0.05);
    };
    const issues = [];
    const ids = new Map();
    document.querySelectorAll('[id]').forEach((element) => {
      ids.set(element.id, (ids.get(element.id) || 0) + 1);
    });
    ids.forEach((count, id) => {
      if (count > 1) issues.push(`ID duplicado: ${id} (${count})`);
    });

    const interactive = Array.from(scope.querySelectorAll(
      'a[href], button, input:not([type="hidden"]), select, textarea, summary, [role="button"], [tabindex]:not([tabindex="-1"])'
    )).filter((element) => visible(element) && !element.disabled);
    interactive.forEach((element) => {
      if (!nameOf(element)) issues.push(`Controlo sem nome acessível: ${selectorOf(element)}`);
    });

    const headings = Array.from(scope.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter(visible);
    let previousLevel = 0;
    headings.forEach((heading) => {
      const level = Number(heading.tagName.slice(1));
      if (previousLevel && level > previousLevel + 1) {
        issues.push(`Hierarquia de títulos salta de h${previousLevel} para h${level}: ${heading.textContent.trim()}`);
      }
      previousLevel = level;
    });

    const contrastFailures = [];
    const candidates = Array.from(scope.querySelectorAll('*')).filter((element) => {
      if (!visible(element) || element.disabled) return false;
      if (['SCRIPT', 'STYLE', 'OPTION', 'SVG', 'PATH'].includes(element.tagName)) return false;
      return Array.from(element.childNodes).some((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    });
    candidates.forEach((element) => {
      const style = getComputedStyle(element);
      const foreground = parseColor(style.color);
      const background = backgroundOf(element);
      if (!foreground || foreground[3] === 0 || !background) return;
      const renderedForeground = composite(foreground, background).slice(0, 3);
      const renderedBackground = background.slice(0, 3);
      const ratio = ratioOf(renderedForeground, renderedBackground);
      const fontSize = Number.parseFloat(style.fontSize);
      const fontWeight = Number.parseInt(style.fontWeight, 10) || 400;
      const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
      const minimum = isLarge ? 3 : 4.5;
      if (ratio + 0.01 < minimum) {
        contrastFailures.push({
          selector: selectorOf(element),
          text: element.textContent.trim().replace(/\s+/g, ' ').slice(0, 70),
          ratio: Number(ratio.toFixed(2)),
          minimum,
          foreground: style.color,
          background: `rgb(${renderedBackground.map((value) => Math.round(value)).join(', ')})`,
        });
      }
    });

    return {
      issues,
      contrastFailures,
      interactiveCount: interactive.length,
      headingCount: headings.length,
      scopeIsDialog: scope !== document,
      mainCount: document.querySelectorAll('main').length,
      horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    };
  });

  assert.equal(domAudit.mainCount, 1, `${label}: deve existir exatamente um landmark main.`);
  assert.ok(domAudit.scopeIsDialog || domAudit.headingCount > 0, `${label}: deve existir pelo menos um título.`);
  assert.ok(domAudit.interactiveCount > 0, `${label}: deve existir pelo menos um controlo interativo.`);
  assert.deepEqual(domAudit.issues, [], `${label}: problemas semânticos: ${JSON.stringify(domAudit.issues, null, 2)}`);
  assert.deepEqual(
    domAudit.contrastFailures,
    [],
    `${label}: falhas WCAG de contraste: ${JSON.stringify(domAudit.contrastFailures.slice(0, 20), null, 2)}`
  );
  assert.ok(domAudit.horizontalOverflow <= 1, `${label}: overflow horizontal de ${domAudit.horizontalOverflow}px.`);

  const client = await page.context().newCDPSession(page);
  await client.send('Accessibility.enable');
  const tree = await client.send('Accessibility.getFullAXTree');
  const focusableRoles = new Set(['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'searchbox', 'spinbutton']);
  const unnamed = tree.nodes.filter((node) => {
    if (node.ignored || !focusableRoles.has(node.role?.value)) return false;
    const focusable = node.properties?.some((property) => property.name === 'focusable' && property.value?.value === true);
    return focusable && !String(node.name?.value || '').trim();
  });
  assert.deepEqual(
    unnamed.map((node) => node.role?.value),
    [],
    `${label}: a árvore acessível contém controlos focáveis sem nome.`
  );
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
    for (const theme of ['light', 'dark']) {
      await page.evaluate((selectedTheme) => { document.documentElement.dataset.theme = selectedTheme; }, theme);
      await page.waitForTimeout(300);
      await auditAccessibility(page, `admin/pauta vazia/${theme}`);
    }
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

    await page.evaluate(() => window.__stage12OpenDialog());
    await page.getByRole('dialog', { name: 'Recuperar palavra-passe' }).waitFor();
    for (const theme of ['light', 'dark']) {
      await page.evaluate((selectedTheme) => { document.documentElement.dataset.theme = selectedTheme; }, theme);
      await page.waitForTimeout(300);
      await auditAccessibility(page, `admin/diálogo de recuperação/${theme}`);
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(120);

    const dialogFixtures = [
      ['loading', 'Detalhes do estudante'],
      ['preview', 'Pré-visualização do certificado'],
      ['nested', 'Adicionar questão publicada']
    ];
    for (const [kind, accessibleName] of dialogFixtures) {
      await page.evaluate((fixtureKind) => window.__stage12OpenDialogFixture(fixtureKind), kind);
      const fixtureDialog = page.getByRole('dialog', { name: accessibleName });
      await fixtureDialog.waitFor();
      assert.equal(await fixtureDialog.getAttribute('aria-modal'), 'true');
      assert.equal(await fixtureDialog.locator('.dialog-close').getAttribute('aria-label'), 'Fechar');
      for (const theme of ['light', 'dark']) {
        await page.evaluate((selectedTheme) => { document.documentElement.dataset.theme = selectedTheme; }, theme);
        await page.waitForTimeout(300);
        await auditAccessibility(page, `admin/diálogo ${kind}/${theme}`);
      }
      await page.setViewportSize({ width: 320, height: 800 });
      await page.waitForTimeout(300);
      await auditAccessibility(page, `admin/diálogo ${kind}/reflow 320px`);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.keyboard.press('Escape');
      await fixtureDialog.waitFor({ state: 'detached' });
      await page.waitForFunction(() => document.activeElement?.id === 'stage12FixtureTrigger');
    }

    const skipLink = page.locator('.skip-link');
    await skipLink.focus();
    await page.waitForTimeout(180);
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), true);
    const skipLinkBox = await skipLink.boundingBox();
    assert.ok(skipLinkBox?.y >= 0, `A ligação para saltar conteúdo deve ficar visível ao receber foco: ${JSON.stringify(skipLinkBox)}`);

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

    await page.setViewportSize({ width: 640, height: 900 });
    await page.evaluate(() => window.__stage12RenderEmptyView('gradebook'));
    await page.waitForTimeout(300);
    await auditAccessibility(page, 'admin/pauta/zoom 200% equivalente');

    await page.setViewportSize({ width: 320, height: 800 });
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'dark';
      window.__stage12RenderEmptyView('gradebook');
    });
    await page.waitForTimeout(300);
    await auditAccessibility(page, 'admin/pauta/reflow 320px');

    const studentPage = await browser.newPage({ viewport: { width: 1280, height: 800 }, locale: 'pt-PT' });
    const studentFailures = await serveFrontend(studentPage);
    await studentPage.goto(`${base}/index.html`, { waitUntil: 'domcontentloaded' });
    await studentPage.waitForFunction(() => Boolean(window.__stage12OpenStudentLogin));
    await studentPage.evaluate(() => window.__stage12OpenStudentLogin());
    await studentPage.getByRole('heading', { name: 'Área do estudante' }).waitFor();
    for (const theme of ['light', 'dark']) {
      await studentPage.evaluate((selectedTheme) => { document.documentElement.dataset.theme = selectedTheme; }, theme);
      await studentPage.waitForTimeout(300);
      await auditAccessibility(studentPage, `estudante/login/${theme}`);
    }
    await studentPage.getByRole('button', { name: 'Criar uma conta' }).click();
    await studentPage.getByRole('dialog', { name: 'Criar conta' }).waitFor();
    await auditAccessibility(studentPage, 'estudante/criar conta/dark');
    await studentPage.keyboard.press('Escape');
    const studentDialogs = [
      ['__stage12OpenStudentRecovery', 'Recuperar palavra-passe de acesso', 'recuperação'],
      ['__stage12OpenStudentSurvey', 'Antes do certificado profissional', 'inquérito'],
      ['__stage12OpenStudentPayment', 'Enviar comprovativo', 'pagamento']
    ];
    for (const [hookName, accessibleName, label] of studentDialogs) {
      await studentPage.evaluate((name) => window[name](), hookName);
      const studentDialog = studentPage.getByRole('dialog', { name: accessibleName });
      await studentDialog.waitFor();
      assert.equal(await studentDialog.getAttribute('aria-modal'), 'true');
      assert.equal(await studentPage.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]'))), true);
      await auditAccessibility(studentPage, `estudante/diálogo de ${label}/dark`);
      await studentPage.setViewportSize({ width: 320, height: 800 });
      await studentPage.waitForTimeout(300);
      await auditAccessibility(studentPage, `estudante/diálogo de ${label}/reflow 320px`);
      await studentPage.setViewportSize({ width: 1280, height: 800 });
      await studentPage.keyboard.press('Escape');
      await studentDialog.waitFor({ state: 'detached' });
    }
    await studentPage.setViewportSize({ width: 640, height: 900 });
    await studentPage.waitForTimeout(300);
    await auditAccessibility(studentPage, 'estudante/login/zoom 200% equivalente');
    await studentPage.setViewportSize({ width: 320, height: 800 });
    await studentPage.waitForTimeout(300);
    await auditAccessibility(studentPage, 'estudante/login/reflow 320px');
    assert.deepEqual(studentFailures, []);
    await studentPage.close();

    assert.deepEqual(failures, []);
  } finally {
    await browser.close();
  }
  process.stdout.write('Etapa 12: navegação, contraste claro/escuro, árvore acessível, diálogos e reflow validados.\n');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
