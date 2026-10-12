const root = document.querySelector('#platformApp');
const toast = document.querySelector('#platformToast');
const TOKEN_KEY = 'coursePlatformGlobalToken';

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

const statusLabels = {
  ACTIVE: 'Ativa', SUSPENDED: 'Suspensa', ARCHIVED: 'Arquivada',
  SUBMITTED: 'Submetido', UNDER_REVIEW: 'Em análise',
  NEEDS_INFORMATION: 'Aguarda informação', READY_FOR_PROVISIONING: 'Pronto para provisionar',
  REJECTED: 'Rejeitado', CANCELLED: 'Cancelado'
};

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 4500);
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) headers['X-Platform-Token'] = token;
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    const error = new Error(payload?.error?.message || `Erro HTTP ${response.status}.`);
    error.code = payload?.error?.code || 'HTTP_ERROR';
    throw error;
  }
  return payload.data;
}

function renderEntry() {
  root.innerHTML = `
    <div class="auth-shell">
      <section class="auth-panel" aria-labelledby="platformLoginTitle">
        <div class="brand"><span class="brand-mark">CP</span><div><strong>CoursePlatform</strong><small>Administração global</small></div></div>
        <p class="eyebrow">Acesso restrito</p>
        <h1 id="platformLoginTitle">Operações da plataforma</h1>
        <p>Área independente da administração académica de cada instituição.</p>
        <form class="auth-form" id="platformLoginForm">
          <div class="field"><label for="platformEmail">Email</label><input id="platformEmail" name="email" type="email" autocomplete="username" required></div>
          <div class="field"><label for="platformPassword">Palavra-passe</label><input id="platformPassword" name="password" type="password" autocomplete="current-password" required></div>
          <button class="primary-button" type="submit">Entrar na administração global</button>
          <p class="form-error" id="platformLoginError" hidden></p>
        </form>
      </section>
      <section class="onboarding-panel" aria-labelledby="onboardingTitle">
        <div class="onboarding-inner">
          <div class="onboarding-intro">
            <p class="eyebrow">Adesão institucional</p>
            <h2 id="onboardingTitle">Solicitar entrada na plataforma</h2>
            <p>Registe os dados iniciais da instituição. A candidatura será analisada antes de qualquer ambiente ser criado ou ativado.</p>
          </div>
          <form class="onboarding-form" id="onboardingForm">
            <div class="field"><label>Nome da instituição</label><input name="displayName" maxlength="160" required></div>
            <div class="field"><label>Identificador público</label><input name="requestedSlug" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="nome-da-instituicao" maxlength="80" required></div>
            <div class="field"><label>Nome legal</label><input name="legalName" maxlength="200"></div>
            <div class="field"><label>País</label><input name="countryCode" maxlength="3" placeholder="MZ"></div>
            <div class="field"><label>Responsável</label><input name="contactName" maxlength="160" required></div>
            <div class="field"><label>Email institucional</label><input name="contactEmail" type="email" maxlength="320" required></div>
            <div class="field"><label>Telefone</label><input name="contactPhone" maxlength="40"></div>
            <div class="field"><label>Website</label><input name="websiteUrl" type="url" maxlength="500" placeholder="https://"></div>
            <div class="field field-wide"><label>Contexto e necessidades</label><textarea name="applicantNotes" maxlength="2000"></textarea></div>
            <div class="form-actions"><button class="primary-button" type="submit">Submeter candidatura</button><span id="onboardingResult" class="form-success" role="status"></span></div>
          </form>
        </div>
      </section>
    </div>`;
  document.querySelector('#platformLoginForm').addEventListener('submit', login);
  document.querySelector('#onboardingForm').addEventListener('submit', submitOnboarding);
}

async function login(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const errorBox = document.querySelector('#platformLoginError');
  errorBox.hidden = true;
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const data = new FormData(form);
    const result = await request('/api/v1/platform/auth/sessions', {
      method: 'POST', body: JSON.stringify({ email: data.get('email'), password: data.get('password') })
    });
    sessionStorage.setItem(TOKEN_KEY, result.platformToken);
    await loadDashboard();
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally { button.disabled = false; }
}

async function submitOnboarding(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  const resultBox = document.querySelector('#onboardingResult');
  button.disabled = true;
  resultBox.textContent = '';
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const idempotencyKey = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    const result = await request('/api/v1/platform/onboarding-requests', {
      method: 'POST', body: JSON.stringify({ ...values, idempotencyKey, planCode: 'STANDARD', requestedFeatures: {} })
    });
    form.reset();
    resultBox.textContent = `Pedido ${result.request.requestId} recebido.`;
  } catch (error) { resultBox.textContent = error.message; }
  finally { button.disabled = false; }
}

function statusBadge(status) {
  const normalized = String(status || '').toLowerCase().replaceAll('_', '-');
  return `<span class="status status-${escapeHtml(normalized)}">${escapeHtml(statusLabels[status] || status)}</span>`;
}

function reviewOptions(current) {
  const transitions = {
    SUBMITTED: ['UNDER_REVIEW', 'CANCELLED'],
    UNDER_REVIEW: ['NEEDS_INFORMATION', 'READY_FOR_PROVISIONING', 'REJECTED', 'CANCELLED'],
    NEEDS_INFORMATION: ['UNDER_REVIEW', 'CANCELLED'],
    READY_FOR_PROVISIONING: ['UNDER_REVIEW', 'CANCELLED']
  }[current] || [];
  return [current, ...transitions].map(value => `<option value="${value}">${escapeHtml(statusLabels[value] || value)}</option>`).join('');
}

function renderDashboard(data) {
  const operator = data.operator;
  root.innerHTML = `
    <div class="platform-shell">
      <aside class="platform-sidebar">
        <div class="brand"><span class="brand-mark">CP</span><div><strong>CoursePlatform</strong><small>Administração global</small></div></div>
        <p class="nav-label">Plataforma</p>
        <nav class="platform-nav" aria-label="Administração global"><a href="#overview" aria-current="page" data-icon="O"><span>Visão geral</span></a><a href="#organizations" data-icon="I"><span>Instituições</span></a><a href="#onboarding" data-icon="A"><span>Onboarding</span></a></nav>
        <div class="sidebar-account"><strong>${escapeHtml(operator.fullName)}</strong><small>${escapeHtml(operator.role)}</small><button class="quiet-button" id="platformLogout" type="button">Terminar sessão</button></div>
      </aside>
      <header class="platform-header"><strong>Administração global</strong><span class="environment-badge">Provisionamento desativado</span></header>
      <main class="platform-main"><div class="content-width">
        <header class="page-heading"><div><p class="eyebrow">Operações SaaS</p><h1>Organizações e onboarding</h1><p>Supervisão global sem acesso implícito aos dados académicos dos tenants.</p></div><button class="secondary-button" id="refreshPlatform" type="button">Atualizar</button></header>
        <section class="metric-grid" aria-label="Resumo global">
          <div class="metric"><span>Instituições</span><strong>${data.summary.organizations}</strong><small>Total registado</small></div>
          <div class="metric"><span>Ativas</span><strong>${data.summary.activeOrganizations}</strong><small>Estado operacional</small></div>
          <div class="metric"><span>Em onboarding</span><strong>${data.summary.pendingOnboarding}</strong><small>Aguardam decisão</small></div>
          <div class="metric"><span>Prontas</span><strong>${data.summary.readyForProvisioning}</strong><small>Sem ativação automática</small></div>
        </section>
        <section class="section" id="organizations"><div class="section-heading"><div><h2>Instituições</h2><p>Inventário operacional; dados académicos permanecem isolados.</p></div></div><div class="table-wrap"><table><thead><tr><th>Instituição</th><th>Estado</th><th>Membros</th><th>Cursos</th><th>Criação</th></tr></thead><tbody>${data.organizations.map(org => `<tr><td><strong>${escapeHtml(org.displayName)}</strong><small>${escapeHtml(org.slug)} · ${escapeHtml(org.organizationId)}</small></td><td>${statusBadge(org.status)}</td><td>${org.memberCount}</td><td>${org.courseCount}</td><td>${escapeHtml(new Date(org.createdAt).toLocaleDateString('pt-PT'))}</td></tr>`).join('') || '<tr><td colspan="5" class="empty-state">Nenhuma instituição registada.</td></tr>'}</tbody></table></div></section>
        <section class="section" id="onboarding"><div class="section-heading"><div><h2>Pedidos de onboarding</h2><p>A aprovação prepara o pedido; não cria uma instituição.</p></div></div><div class="table-wrap"><table><thead><tr><th>Instituição</th><th>Contacto</th><th>Submissão</th><th>Estado</th><th>Revisão</th></tr></thead><tbody>${data.onboardingRequests.map(item => `<tr><td><strong>${escapeHtml(item.displayName)}</strong><small>${escapeHtml(item.requestedSlug)} · ${escapeHtml(item.requestId)}</small></td><td><strong>${escapeHtml(item.contactName)}</strong><small>${escapeHtml(item.contactEmail)}</small></td><td>${escapeHtml(new Date(item.submittedAt).toLocaleDateString('pt-PT'))}</td><td>${statusBadge(item.status)}</td><td><form class="inline-review" data-review-id="${escapeHtml(item.requestId)}"><select name="status" aria-label="Novo estado de ${escapeHtml(item.displayName)}">${reviewOptions(item.status)}</select><button class="secondary-button" type="submit">Guardar</button></form></td></tr>`).join('') || '<tr><td colspan="5" class="empty-state">Nenhum pedido recebido.</td></tr>'}</tbody></table></div></section>
      </div></main>
    </div>`;
  document.querySelector('#platformLogout').addEventListener('click', logout);
  document.querySelector('#refreshPlatform').addEventListener('click', loadDashboard);
  document.querySelectorAll('[data-review-id]').forEach(form => form.addEventListener('submit', reviewOnboarding));
}

async function reviewOnboarding(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    await request(`/api/v1/platform/onboarding-requests/${encodeURIComponent(form.dataset.reviewId)}`, {
      method: 'PATCH', body: JSON.stringify({ status: new FormData(form).get('status'), reviewNotes: '' })
    });
    showToast('Estado do onboarding atualizado.');
    await loadDashboard();
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; }
}

async function loadDashboard() {
  try {
    const data = await request('/api/v1/platform/dashboard');
    renderDashboard(data);
  } catch (error) {
    if (['INVALID_PLATFORM_SESSION', 'PLATFORM_SESSION_EXPIRED', 'PLATFORM_ACCESS_REVOKED'].includes(error.code)) {
      sessionStorage.removeItem(TOKEN_KEY);
      renderEntry();
      showToast(error.message);
      return;
    }
    throw error;
  }
}

async function logout() {
  try { await request('/api/v1/platform/auth/sessions/current', { method: 'DELETE' }); } catch (_) {}
  sessionStorage.removeItem(TOKEN_KEY);
  renderEntry();
}

if (sessionStorage.getItem(TOKEN_KEY)) loadDashboard().catch(error => { renderEntry(); showToast(error.message); });
else renderEntry();
