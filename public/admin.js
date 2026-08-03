import { CoursePlatformApi, ApiError } from './api.js';
import { ChatWorkspace } from './chat.js';
import {
  escapeHtml,
  formatBytes,
  formatDate,
  parseSelectedOptions,
  reportHeight,
  setBusy,
  showToast,
  statusClass,
  statusLabel
} from './utils.js';

const config = window.COURSE_PLATFORM_CONFIG;
const root = document.querySelector('#adminApp');
const adminIdentity = document.querySelector('#adminIdentity');
const logoutButton = document.querySelector('#adminLogoutButton');
const themeToggle = document.querySelector('#themeToggle');
const adminMobileMenuButton = document.querySelector('#adminMobileMenuButton');
const lucideIconsBase = 'https://api.iconify.design/lucide';
const lucideIconAliases = Object.freeze({
  'admin-settings-male': 'settings',
  'bar-chart': 'chart-no-axes-combined',
  'book-shelf': 'book-open',
  'cancel': 'circle-x',
  'certificate': 'award',
  'checked-checkbox': 'check-square',
  'classroom': 'layout-dashboard',
  'combo-chart': 'chart-no-axes-combined',
  'conference-call': 'user-round-check',
  'diploma': 'award',
  'documents': 'file-text',
  'graduation-cap': 'graduation-cap',
  'help': 'circle-help',
  'inbox': 'clipboard-list',
  'inspection': 'clipboard-check',
  'key': 'key-round',
  'lock': 'lock-keyhole',
  'ok': 'circle-check',
  'open-book': 'book-open',
  'picture': 'image',
  'reading': 'play-circle',
  'student-male': 'users',
  'survey': 'clipboard-list',
  'task-completed': 'clipboard-check',
  'time': 'clock-3',
  'time-machine': 'history',
  'upload-to-cloud': 'upload',
  'user-male-circle': 'circle-user-round',
  'video-playlist': 'video'
});
const blueIcon = '00365b';
const goldIcon = 'c9a55b';

let api;
let submissionSearchTimer;
let studentSearchTimer;
let courseSearchTimer;
const state = {
  admin: null,
  statistics: null,
  pending: [],
  submissionFilters: {
    status: 'ALL',
    query: ''
  },
  students: [],
  courseStructure: null,
  courses: [],
  groups: [],
  selectedCourseId: config.courseId,
  courseMode: 'list',
  courseView: 'overview',
  courseFilters: {
    query: '',
    status: 'ALL',
    content: 'ALL',
    showDeletedItems: false
  },
  selectedSubmission: null,
  certificateRequests: [],
  certificates: [],
  certificateSurveys: [],
  certificateSurveyResponses: [],
  certificateFilters: {
    status: 'ALL',
    certificateStatus: 'ACTIVE',
    query: ''
  },
  certificateSettings: null,
  studentFilters: {
    query: '',
    status: 'ALL',
    progress: 'ALL',
    sort: 'name'
  },
  media: {
    logoUrl: '',
    videos: []
  },
  staff: [],
  notificationLog: null,
  notificationStudentTotal: 0,
  notificationTemplateKey: ''
};

let activeAdminChatWorkspace = null;
let adminPresencePollId = null;

initialize();

async function initialize() {
  initializeThemeToggle();

  try {
    api = new CoursePlatformApi(config);
  } catch (error) {
    root.innerHTML = `
      <div class="configuration-error">
        <h1>Configuração incompleta</h1>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
    return;
  }

  await loadPublicMediaConfig();
  applyBrandLogo();

  logoutButton.addEventListener('click', logout);
  document.body.classList.toggle('sidebar-collapsed', localStorage.getItem('lssAdminSidebarCollapsed') === 'true');
  root.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-sidebar-toggle]');
    if (!toggle) return;
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('lssAdminSidebarCollapsed', String(collapsed));
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.setAttribute('aria-label', collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral');
    toggle.title = collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral';
    const label = toggle.querySelector('span');
    if (label) label.textContent = collapsed ? 'Expandir menu' : 'Recolher menu';
  });
  adminMobileMenuButton?.addEventListener('click', () => {
    const isOpen = document.body.classList.toggle('admin-menu-open');
    adminMobileMenuButton.setAttribute('aria-expanded', String(isOpen));
    adminMobileMenuButton.setAttribute('aria-label', isOpen ? 'Fechar menu' : 'Abrir menu');
  });
  document.addEventListener('click', (event) => {
    if (
      !document.body.classList.contains('admin-menu-open')
      || root.querySelector('.admin-sidebar')?.contains(event.target)
      || adminMobileMenuButton?.contains(event.target)
    ) {
      return;
    }
    document.body.classList.remove('admin-menu-open');
    adminMobileMenuButton?.setAttribute('aria-expanded', 'false');
    adminMobileMenuButton?.setAttribute('aria-label', 'Abrir menu');
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !document.body.classList.contains('admin-menu-open')) return;
    document.body.classList.remove('admin-menu-open');
    adminMobileMenuButton?.setAttribute('aria-expanded', 'false');
    adminMobileMenuButton?.setAttribute('aria-label', 'Abrir menu');
    adminMobileMenuButton?.focus();
  });
  window.matchMedia('(max-width: 1024px)').addEventListener('change', (event) => {
    if (event.matches) return;
    document.body.classList.remove('admin-menu-open');
    adminMobileMenuButton?.setAttribute('aria-expanded', 'false');
    adminMobileMenuButton?.setAttribute('aria-label', 'Abrir menu');
  });
  adminIdentity.addEventListener('click', () => {
    if (!api?.hasAdminSession()) return;
    setActiveAdminView('profile');
    renderAdminProfile();
  });
  new ResizeObserver(reportHeight).observe(document.body);

  if (api.hasAdminSession()) {
    try {
      const result = await api.adminMe();
      state.admin = result.admin;
      renderAdminShell();
      warmAdminCache();
      loadPlatformStatistics();
    } catch (error) {
      handleAdminError(error);
    }
  } else {
    renderAdminLogin();
  }
}

function renderAdminLogin() {
  logoutButton.hidden = true;
  if (adminMobileMenuButton) adminMobileMenuButton.hidden = true;
  document.body.classList.remove('admin-menu-open');
  adminIdentity.textContent = '';
  adminIdentity.hidden = true;

  root.innerHTML = `
    <section class="auth-shell">
      <div class="auth-card auth-card-modern">
        <div class="auth-card-accent">
          <img src="${iconUrl('admin-settings-male', goldIcon)}" alt="">
          <span>Área reservada</span>
        </div>

        <div class="auth-brand-row">
          ${brandSymbolTemplate('brand-mark')}
          <div>
            <p class="eyebrow">LMTWEBNAIRS Summer School</p>
            <h1 class="admin-login-title">Painel do administrador</h1>
          </div>
        </div>

        <p class="auth-description">
          Organize submissões, acompanhe participantes e registe avaliações com clareza.
        </p>

        <form id="adminLoginForm" class="form-stack">
          <label>
            <span>Email administrativo</span>
            <input type="email" name="email" required>
          </label>
          <label>
            <span>Palavra-passe administrativa</span>
            <input type="password" name="adminKey" required>
          </label>
          <button class="button button-primary button-block" type="submit">
            Entrar
          </button>
          <button class="text-button login-recovery-link" type="button" id="recoverAdminAccessButton">
            Recuperar acesso administrativo
          </button>
        </form>

        <div id="adminLoginError" class="form-message form-message-error" hidden></div>
      </div>
    </section>
  `;

  document.querySelector('#adminLoginForm').addEventListener('submit', login);
  document.querySelector('#recoverAdminAccessButton').addEventListener('click', () => {
    const email = document.querySelector('#adminLoginForm [name="email"]')?.value || '';
    showAdminRecoveryDialog(email);
  });
  reportHeight();
}

async function login(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const data = new FormData(form);
  const button = form.querySelector('button');
  const errorBox = document.querySelector('#adminLoginError');

  setBusy(button, true, 'A autenticar…');
  errorBox.hidden = true;

  try {
    const result = await api.adminLogin(data.get('email'), data.get('adminKey'));
    state.admin = result.admin;
    adminIdentity.textContent = `${result.admin.fullName} · ${result.admin.role}`;
    renderAdminShell();
    warmAdminCache();
    await loadPlatformStatistics();
  } catch (error) {
    if (error instanceof ApiError && error.code === 'INVALID_ADMIN_CREDENTIALS') {
      errorBox.innerHTML = `
        <span>${escapeHtml(error.message)}</span>
        <button class="text-button" type="button" id="recoverAfterAdminLoginError">
          Recuperar acesso
        </button>
      `;
      errorBox.querySelector('#recoverAfterAdminLoginError').addEventListener('click', () => {
        showAdminRecoveryDialog(data.get('email'));
      });
    } else {
      errorBox.textContent = error.message;
    }
    errorBox.hidden = false;
  } finally {
    setBusy(button, false);
    reportHeight();
  }
}

function showAdminRecoveryDialog(prefilledEmail = '') {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card recovery-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <h2>Recuperar acesso administrativo</h2>
      <p class="recovery-note">
        Use a chave de recuperação configurada no backend para gerar uma nova palavra-passe temporária.
      </p>

      <form id="adminRecoveryForm" class="form-stack">
        <label>
          <span>Email administrativo</span>
          <input type="email" name="email" autocomplete="email" required
            value="${escapeHtml(prefilledEmail || '')}" placeholder="admin@email.com">
        </label>
        <label>
          <span>Chave de recuperação</span>
          <input type="password" name="recoveryKey" autocomplete="off" required>
        </label>

        <div id="adminRecoveryResult" class="recovery-result" hidden></div>

        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-recovery>Cancelar</button>
          <button class="button button-primary" type="submit">Gerar palavra-passe temporária</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('[data-cancel-recovery]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#adminRecoveryForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    setBusy(button, true, 'A gerar...');

    try {
      const result = await api.recoverAdminAccess(values.email, values.recoveryKey);
      renderAdminRecoveryResult(overlay, result, values.email);
    } catch (error) {
      const resultBox = overlay.querySelector('#adminRecoveryResult');
      resultBox.hidden = false;
      resultBox.classList.add('is-error');
      resultBox.textContent = error.message || 'Não foi possível recuperar o acesso administrativo.';
    } finally {
      setBusy(button, false);
      reportHeight();
    }
  });
  overlay.querySelector('[name="recoveryKey"]').focus();
  reportHeight();
}

function renderAdminRecoveryResult(overlay, result, email) {
  const resultBox = overlay.querySelector('#adminRecoveryResult');
  resultBox.hidden = false;
  resultBox.classList.remove('is-error');
  resultBox.innerHTML = `
    <span>Palavra-passe temporária criada para ${escapeHtml(result.email || email)}</span>
    <strong>${escapeHtml(result.temporaryAdminKey || '')}</strong>
    <div class="recovery-result-actions">
      <button class="button button-secondary button-small" type="button" data-copy-temporary-admin-key>
        Copiar palavra-passe
      </button>
      <button class="button button-primary button-small" type="button" data-use-temporary-admin-key>
        Usar no login
      </button>
    </div>
  `;
  resultBox.querySelector('[data-copy-temporary-admin-key]').addEventListener('click', () => {
    copyText(result.temporaryAdminKey || '', 'Palavra-passe temporária copiada.');
  });
  resultBox.querySelector('[data-use-temporary-admin-key]').addEventListener('click', () => {
    const loginForm = document.querySelector('#adminLoginForm');
    if (loginForm) {
      loginForm.elements.email.value = email || '';
      loginForm.elements.adminKey.value = result.temporaryAdminKey || '';
    }
    overlay.remove();
    showToast('Palavra-passe temporária preenchida no início de sessão.', 'success');
  });
}

async function logout() {
  window.clearInterval(adminPresencePollId);
  adminPresencePollId = null;
  activeAdminChatWorkspace?.destroy();
  activeAdminChatWorkspace = null;
  try {
    await api.adminLogout();
  } catch {
    sessionStorage.removeItem('courseAdminToken');
  }
  state.admin = null;
  state.statistics = null;
  state.staff = [];
  renderAdminLogin();
}

function warmAdminCache() {
  if (!api?.hasAdminSession()) return;

  window.setTimeout(() => {
    if (!api?.hasAdminSession()) return;
    Promise.allSettled([
      api.adminCourses({ limit: 100 }),
      api.adminMediaConfig(),
      api.adminNotifications({ limit: 20 }),
      canManageStaff() ? (typeof api.adminStaff === 'function' ? api.adminStaff() : api.adminstaff()) : Promise.resolve()
    ]);
  }, 1200);
}

function renderAdminShell() {
  logoutButton.hidden = false;
  if (adminMobileMenuButton) adminMobileMenuButton.hidden = false;
  adminIdentity.hidden = false;
  const sidebarCollapsed = document.body.classList.contains('sidebar-collapsed');
  if (state.admin) {
    adminIdentity.textContent = `${state.admin.fullName} - ${state.admin.role}`;
  }

  root.innerHTML = `
    <div class="admin-layout">
      <aside class="admin-sidebar">
        <div class="admin-sidebar-heading">
          ${brandSymbolTemplate('admin-sidebar-symbol')}
          <h2>Gestão da Summer School</h2>
        </div>
        <button class="admin-nav is-active" data-admin-view="overview" aria-label="Visão geral" title="Visão geral">
          <img src="${iconUrl('classroom', blueIcon)}" alt="">
          <span>Visão geral</span>
        </button>
        <button class="admin-nav" data-admin-view="pending" aria-label="Submissões" title="Submissões">
          <img src="${iconUrl('inbox', blueIcon)}" alt="">
          <span>Submissões</span>
        </button>
        <button class="admin-nav" data-admin-view="notifications" aria-label="Notificações" title="Notificações">
          <img src="${iconUrl('bell', blueIcon)}" alt="">
          <span>Notificações</span>
        </button>
        <button class="admin-nav" data-admin-view="chat" aria-label="Mensagens" title="Mensagens">
          <img src="${iconUrl('message-square', blueIcon)}" alt="">
          <span>Mensagens</span>
          <b class="nav-unread-badge" data-admin-chat-badge hidden>0</b>
        </button>
        <button class="admin-nav" data-admin-view="students" aria-label="Estudantes" title="Estudantes">
          <img src="${iconUrl('student-male', blueIcon)}" alt="">
          <span>Estudantes</span>
        </button>
        <button class="admin-nav" data-admin-view="courses" aria-label="Cursos" title="Cursos">
          <img src="${iconUrl('book-shelf', blueIcon)}" alt="">
          <span>Cursos</span>
        </button>
        <button class="admin-nav" data-admin-view="videos" aria-label="Vídeos" title="Vídeos">
          <img src="${iconUrl('video-playlist', blueIcon)}" alt="">
          <span>Vídeos</span>
        </button>
        <button class="admin-nav" data-admin-view="brand" aria-label="Marca" title="Marca">
          <img src="${iconUrl('picture', blueIcon)}" alt="">
          <span>Marca</span>
        </button>
        <button class="admin-nav" data-admin-view="certifications" aria-label="Certificações" title="Certificações">
          <img src="${iconUrl('diploma', blueIcon)}" alt="">
          <span>Certificações</span>
        </button>
        <button class="admin-nav" data-admin-view="surveys" aria-label="Inquéritos" title="Inquéritos">
          <img src="${iconUrl('survey', blueIcon)}" alt="">
          <span>Inquéritos</span>
        </button>
        ${canManageStaff() ? `
          <button class="admin-nav" data-admin-view="staff" aria-label="Staff" title="Staff">
            <img src="${iconUrl('conference-call', blueIcon)}" alt="">
            <span>Staff</span>
          </button>
        ` : ''}
        ${canManageCredentials() ? `
          <button class="admin-nav" data-admin-view="credentials" aria-label="Credenciais" title="Credenciais">
            <img src="${iconUrl('key', blueIcon)}" alt="">
            <span>Credenciais</span>
          </button>
        ` : ''}
        <button class="admin-nav" data-admin-view="profile" aria-label="Perfil" title="Perfil">
          <img src="${iconUrl('user-male-circle', blueIcon)}" alt="">
          <span>Perfil</span>
        </button>
        <button class="admin-nav sidebar-mobile-logout" type="button" data-admin-logout aria-label="Sair" title="Sair">
          <img src="${iconUrl('log-out', goldIcon)}" alt="">
          <span>Sair</span>
        </button>
        <button class="sidebar-collapse-button" type="button" data-sidebar-toggle
          aria-label="${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu lateral"
          aria-expanded="${String(!sidebarCollapsed)}"
          title="${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu lateral">
          <img src="${iconUrl('panel-left-close', goldIcon)}" alt="">
          <span>${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu</span>
        </button>
      </aside>

      <main class="admin-main" id="adminMain"></main>
    </div>
  `;

  root.querySelectorAll('[data-admin-view]').forEach((button) => {
    button.addEventListener('click', () => {
      document.body.classList.remove('admin-menu-open');
      adminMobileMenuButton?.setAttribute('aria-expanded', 'false');
      setActiveAdminView(button.dataset.adminView);

      if (button.dataset.adminView === 'overview') {
        loadPlatformStatistics();
      } else if (button.dataset.adminView === 'students') {
        loadStudents();
      } else if (button.dataset.adminView === 'notifications') {
        loadNotificationManagement();
      } else if (button.dataset.adminView === 'chat') {
        renderAdminChat();
      } else if (button.dataset.adminView === 'courses') {
        state.courseMode = 'list';
        loadCourses();
      } else if (button.dataset.adminView === 'videos') {
        renderVideos();
      } else if (button.dataset.adminView === 'brand') {
        renderBrandSettings();
      } else if (button.dataset.adminView === 'certifications') {
        loadCertifications();
      } else if (button.dataset.adminView === 'surveys') {
        loadCertificateSurveys();
      } else if (button.dataset.adminView === 'staff') {
        loadStaff();
      } else if (button.dataset.adminView === 'credentials') {
        renderCredentialsManagement();
      } else if (button.dataset.adminView === 'profile') {
        renderAdminProfile();
      } else {
        loadPending();
      }
    });
  });
  root.querySelector('[data-admin-logout]')?.addEventListener('click', logout);
  startAdminPresenceHeartbeat();
  api.adminChatRooms().then((result) => updateAdminChatUnread(result.unreadCount)).catch(() => {});
}

function startAdminPresenceHeartbeat() {
  window.clearInterval(adminPresencePollId);
  const heartbeat = () => {
    if (document.hidden || !api?.hasAdminSession()) return;
    api.adminUpdatePresence(activeAdminChatWorkspace?.activeRoom?.roomId || '').catch(() => {});
  };
  heartbeat();
  adminPresencePollId = window.setInterval(heartbeat, 30000);
}

function setActiveAdminView(view) {
  if (view !== 'chat') {
    activeAdminChatWorkspace?.destroy();
    activeAdminChatWorkspace = null;
  }
  root.querySelectorAll('[data-admin-view]').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.adminView === view);
  });
}

function updateAdminChatUnread(unreadCount) {
  const count = Math.max(0, Number(unreadCount || 0));
  root.querySelectorAll('[data-admin-chat-badge]').forEach((badge) => {
    badge.hidden = count === 0;
    badge.textContent = String(Math.min(count, 99));
  });
}

async function loadPlatformStatistics(options = {}) {
  const adminMain = document.querySelector('#adminMain');
  if (!adminMain) return;
  adminMain.innerHTML = loadingTemplate('A preparar os indicadores da plataforma...');
  try {
    state.statistics = await api.adminPlatformStatistics(options);
    renderPlatformStatistics();
  } catch (error) {
    handleAdminError(error);
  }
}

function statisticsMetric(iconName, label, value, note = '', tone = '') {
  return `
    <article class="platform-stat-card ${tone ? `is-${tone}` : ''}">
      <span class="platform-stat-icon"><img src="${iconUrl(iconName, goldIcon)}" alt=""></span>
      <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong><small>${escapeHtml(note)}</small></div>
    </article>
  `;
}

function renderPlatformStatistics() {
  const main = document.querySelector('#adminMain');
  if (!main) return;
  const data = state.statistics || {};
  const summary = data.summary || {};
  const engagement = data.engagement || {};
  const performance = data.performance || {};
  const operations = data.operations || {};
  const courses = Array.isArray(data.courses) ? data.courses : [];
  const activity = Array.isArray(data.activity) ? data.activity : [];
  const maximumActivity = Math.max(1, ...activity.flatMap((item) => [Number(item.messages || 0), Number(item.submissions || 0)]));
  const operationalItems = [
    ['Falhas de envio', operations.failedDeliveries, 'triangle-alert', 'Notificações externas que precisam de nova tentativa.'],
    ['Certificados pendentes', operations.pendingCertificates, 'award', 'Pedidos aguardando análise ou confirmação.'],
    ['Relatos no chat', operations.openChatReports, 'flag', 'Mensagens denunciadas aguardando moderação.'],
    ['Prazos excedidos', operations.expiredAttempts, 'clock-alert', 'Tentativas cujo tempo terminou.'],
    ['Contas inativas', operations.inactiveStudents, 'user-round-x', 'Estudantes bloqueados ou inativos.']
  ];
  main.innerHTML = `
    <section class="admin-page-heading platform-statistics-heading">
      <div>
        <p class="eyebrow">Visão operacional</p>
        <h1>Indicadores da plataforma</h1>
        <p>Acompanhe participação, desempenho académico e pontos que exigem atenção.</p>
      </div>
      <button class="button button-secondary button-small" type="button" id="refreshPlatformStatistics">
        <img src="${iconUrl('refresh-cw', blueIcon)}" alt="">Atualizar
      </button>
    </section>

    <section class="platform-stat-grid" aria-label="Indicadores principais">
      ${statisticsMetric('users', 'Estudantes ativos', Number(summary.activeStudents || 0), `${Number(engagement.active30Days || 0)} ativos nos últimos 30 dias`)}
      ${statisticsMetric('radio', 'Online agora', Number(summary.onlineStudents || 0), 'Presença atualizada em tempo real', 'online')}
      ${statisticsMetric('book-open', 'Cursos ativos', Number(summary.activeCourses || 0), `${Number(summary.enrollments || 0)} matrículas ativas`)}
      ${statisticsMetric('clipboard-check', 'Avaliações pendentes', Number(summary.pendingReviews || 0), 'Submissões por analisar', Number(summary.pendingReviews || 0) ? 'attention' : '')}
      ${statisticsMetric('award', 'Certificados emitidos', Number(summary.issuedCertificates || 0), `${Number(operations.pendingCertificates || 0)} pedidos pendentes`)}
      ${statisticsMetric('message-square', 'Mensagens em 7 dias', Number(engagement.messages7Days || 0), 'Comunicação interna da plataforma')}
    </section>

    <section class="platform-stat-layout">
      <article class="admin-content-panel platform-performance-panel">
        <div class="platform-panel-heading"><div><p class="eyebrow">Resultados</p><h2>Desempenho académico</h2></div></div>
        ${[
          ['Progresso médio', performance.averageProgress],
          ['Taxa de conclusão', performance.completionRate],
          ['Taxa de aprovação', performance.approvalRate]
        ].map(([label, value]) => `
          <div class="platform-progress-row">
            <div><span>${escapeHtml(label)}</span><strong>${Number(value || 0).toFixed(1)}%</strong></div>
            <span class="platform-progress-track"><i style="width:${Math.max(0, Math.min(100, Number(value || 0)))}%"></i></span>
          </div>
        `).join('')}
        <div class="platform-engagement-grid">
          <div><span>Ativos hoje</span><strong>${Number(engagement.activeToday || 0)}</strong></div>
          <div><span>Ativos em 7 dias</span><strong>${Number(engagement.active7Days || 0)}</strong></div>
          <div><span>Submissões em 30 dias</span><strong>${Number(engagement.submissions30Days || 0)}</strong></div>
          <div><span>Notificações em 30 dias</span><strong>${Number(engagement.notifications30Days || 0)}</strong></div>
        </div>
      </article>

      <article class="admin-content-panel platform-activity-panel">
        <div class="platform-panel-heading">
          <div><p class="eyebrow">Últimos 7 dias</p><h2>Atividade diária</h2></div>
          <div class="platform-chart-legend"><span class="is-messages">Mensagens</span><span class="is-submissions">Submissões</span></div>
        </div>
        <div class="platform-activity-chart" role="img" aria-label="Mensagens e submissões dos últimos sete dias">
          ${activity.map((item) => {
            const date = new Date(item.date);
            const label = Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('pt-PT', { weekday: 'short' }).format(date).replace('.', '');
            const messageHeight = Math.max(Number(item.messages || 0) ? 8 : 2, Number(item.messages || 0) / maximumActivity * 100);
            const submissionHeight = Math.max(Number(item.submissions || 0) ? 8 : 2, Number(item.submissions || 0) / maximumActivity * 100);
            return `<div class="platform-activity-day"><div><i class="is-messages" style="height:${messageHeight}%" title="${Number(item.messages || 0)} mensagens"></i><i class="is-submissions" style="height:${submissionHeight}%" title="${Number(item.submissions || 0)} submissões"></i></div><span>${escapeHtml(label)}</span></div>`;
          }).join('') || '<div class="empty-note">Ainda não existem dados de atividade.</div>'}
        </div>
      </article>
    </section>

    <section class="admin-content-panel platform-operations-panel">
      <div class="platform-panel-heading"><div><p class="eyebrow">Atenção operacional</p><h2>Situações a acompanhar</h2></div></div>
      <div class="platform-operation-grid">
        ${operationalItems.map(([label, value, itemIcon, description]) => `
          <article class="platform-operation-item ${Number(value || 0) ? 'has-alert' : 'is-clear'}">
            <span><img src="${iconUrl(Number(value || 0) ? itemIcon : 'circle-check', Number(value || 0) ? 'c9a55b' : '168764')}" alt=""></span>
            <div><strong>${Number(value || 0)}</strong><b>${escapeHtml(label)}</b><small>${escapeHtml(Number(value || 0) ? description : 'Sem ocorrências pendentes.')}</small></div>
          </article>
        `).join('')}
      </div>
    </section>

    <section class="admin-content-panel platform-course-panel">
      <div class="platform-panel-heading"><div><p class="eyebrow">Cursos</p><h2>Desempenho por curso</h2></div><small>Atualizado ${escapeHtml(formatDate(data.generatedAt || new Date().toISOString(), true))}</small></div>
      <div class="table-scroll">
        <table class="platform-course-table">
          <thead><tr><th>Curso</th><th>Estudantes</th><th>Concluíram</th><th>Progresso médio</th><th>Pendentes</th></tr></thead>
          <tbody>${courses.map((course) => `
            <tr>
              <td><strong>${escapeHtml(course.title)}</strong><small>${escapeHtml(course.courseCode || '')}</small></td>
              <td>${Number(course.studentCount || 0)}</td>
              <td>${Number(course.completedCount || 0)}</td>
              <td><span class="platform-table-progress"><i style="width:${Math.max(0, Math.min(100, Number(course.averageProgress || 0)))}%"></i></span><b>${Number(course.averageProgress || 0).toFixed(1)}%</b></td>
              <td><span class="status-pill ${Number(course.pendingReviews || 0) ? 'status-pending' : 'status-approved'}">${Number(course.pendingReviews || 0)}</span></td>
            </tr>
          `).join('') || '<tr><td colspan="5"><div class="empty-note">Ainda não existem cursos ativos.</div></td></tr>'}</tbody>
        </table>
      </div>
    </section>
  `;
  main.querySelector('#refreshPlatformStatistics')?.addEventListener('click', () => loadPlatformStatistics({ force: true }));
  reportHeight();
}

async function renderAdminChat() {
  const adminMain = document.querySelector('#adminMain');
  if (!adminMain) return;
  activeAdminChatWorkspace?.destroy();
  adminMain.innerHTML = `
    <section class="admin-page-heading admin-chat-heading">
      <div>
        <p class="eyebrow">Comunicação interna</p>
        <h1>Mensagens</h1>
        <p>Converse com estudantes nos canais de apoio, curso, grupo e comunidade.</p>
      </div>
    </section>
    <div id="adminChatWorkspace"></div>
  `;
  activeAdminChatWorkspace = new ChatWorkspace({
    api,
    mount: document.querySelector('#adminChatWorkspace'),
    mode: 'admin',
    onUnreadChange: updateAdminChatUnread
  });
  try {
    await activeAdminChatWorkspace.start();
  } catch (error) {
    showToast(error.message || 'Não foi possível abrir as mensagens.', 'error');
  }
  reportHeight();
}

function canManageNotifications() {
  return ['OWNER', 'ADMIN'].includes(state.admin?.role);
}

function notificationDeliveryLabel(status, channel = '') {
  const labels = {
    SENT: channel === 'WHATSAPP'
      ? 'Aceite pela Meta'
      : channel === 'TELEGRAM'
        ? 'Aceite pelo Telegram'
        : channel === 'PUSH'
          ? 'Entregue ao dispositivo'
          : 'Enviado',
    PENDING: 'Pendente',
    FAILED: 'Falhou',
    SKIPPED: 'Não solicitado',
    NOT_REQUESTED: 'Apenas interna'
  };
  return labels[status] || status || 'Apenas interna';
}

function notificationSearchText(...values) {
  return values.join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function notificationRecipientTemplate(student) {
  const phone = String(student.phone || '').trim();
  const phoneDigits = phone.replace(/\D/g, '');
  const hasValidPhone = phoneDigits.length >= 8 && phoneDigits.length <= 15;
  const whatsappReady = Boolean(student.whatsappOptIn && hasValidPhone);
  const whatsappLabel = whatsappReady
    ? 'WhatsApp autorizado'
    : student.whatsappOptIn
      ? (phone ? 'Telefone inválido' : 'Telefone em falta')
      : 'Sem autorização';
  const whatsappClass = whatsappReady ? 'is-ready' : 'is-unavailable';
  const email = String(student.email || '').trim();
  const hasValidEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const emailReady = Boolean(student.emailOptIn && hasValidEmail);
  const emailLabel = emailReady
    ? 'Email autorizado'
    : !email
      ? 'Email em falta'
      : student.emailOptIn
      ? 'Email inválido'
      : 'Email sem autorização';
  const telegramLinked = Boolean(student.telegramLinked);
  const telegramReady = Boolean(student.telegramOptIn && telegramLinked);
  const telegramLabel = telegramReady
    ? 'Telegram autorizado'
    : student.telegramOptIn
      ? 'Telegram não associado'
      : 'Telegram sem autorização';
  const pushReady = Number(student.pushSubscriptionCount || 0) > 0;
  const pushLabel = pushReady
    ? `${Number(student.pushSubscriptionCount)} dispositivo(s) com Push`
    : 'Push não ativado';
  const publicId = studentPublicIdLabel(student.publicStudentId);
  const searchText = notificationSearchText(student.fullName, publicId, email, phone);
  return `
    <label class="notification-recipient-row" data-recipient-row data-search="${escapeHtml(searchText)}">
      <input type="checkbox" name="studentIds" value="${escapeHtml(student.studentId)}">
      <span class="notification-recipient-avatar" aria-hidden="true">${escapeHtml(studentInitials(student.fullName))}</span>
      <span class="notification-recipient-copy">
        <strong>${escapeHtml(student.fullName || 'Estudante')}</strong>
        <span>${escapeHtml(publicId)} · ${escapeHtml(email || 'Sem email')}</span>
        <small>${escapeHtml(phone || 'Sem telefone registado')}</small>
      </span>
      <span class="notification-recipient-channels" aria-label="Disponibilidade dos canais">
        <span class="status-pill notification-channel-state ${emailReady ? 'is-ready' : 'is-unavailable'}" aria-label="${escapeHtml(emailLabel)}" title="${escapeHtml(emailLabel)}">Email · ${emailReady ? 'Sim' : 'Não'}</span>
        <span class="status-pill notification-channel-state ${whatsappClass}" aria-label="${escapeHtml(whatsappLabel)}" title="${escapeHtml(whatsappLabel)}">WhatsApp · ${whatsappReady ? 'Sim' : 'Não'}</span>
        <span class="status-pill notification-channel-state ${telegramReady ? 'is-ready' : 'is-unavailable'}" aria-label="${escapeHtml(telegramLabel)}" title="${escapeHtml(telegramLabel)}">Telegram · ${telegramReady ? 'Sim' : 'Não'}</span>
        <span class="status-pill notification-channel-state ${pushReady ? 'is-ready' : 'is-unavailable'}" aria-label="${escapeHtml(pushLabel)}" title="${escapeHtml(pushLabel)}">Push · ${pushReady ? 'Sim' : 'Não'}</span>
      </span>
    </label>
  `;
}

function notificationTemplateEditor(templates = []) {
  if (!templates.length) return '<div class="empty-note">Os modelos ainda não estão disponíveis.</div>';
  const selectedKey = state.notificationTemplateKey && templates.some((item) => item.templateKey === state.notificationTemplateKey)
    ? state.notificationTemplateKey
    : templates[0].templateKey;
  state.notificationTemplateKey = selectedKey;
  const template = templates.find((item) => item.templateKey === selectedKey) || templates[0];
  const variableChips = (template.allowedVariables || []).map((variable) => (
    `<code>{{${escapeHtml(variable)}}}</code>`
  )).join('');
  return `
    <div class="notification-template-toolbar">
      <label>
        <span>Evento automático</span>
        <select id="notificationTemplateSelect">
          ${templates.map((item) => `<option value="${escapeHtml(item.templateKey)}" ${item.templateKey === selectedKey ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}
        </select>
      </label>
      <span class="status-pill ${template.customized ? 'status-approved' : 'status-pending'}">${template.customized ? 'Personalizado' : 'Modelo padrão'}</span>
    </div>
    <form id="notificationTemplateForm" class="form-stack notification-template-form">
      <input type="hidden" name="templateKey" value="${escapeHtml(template.templateKey)}">
      <div class="notification-template-variables" aria-label="Variáveis disponíveis">
        <strong>Variáveis disponíveis</strong>${variableChips}
      </div>
      <div class="notification-template-channel-block">
        <div><p class="eyebrow">Plataforma</p><h3>Notificação interna</h3></div>
        <label><span>Título</span><input name="internalTitleTemplate" maxlength="180" value="${escapeHtml(template.internalTitleTemplate || '')}" required></label>
        <label><span>Mensagem</span><textarea name="internalMessageTemplate" rows="3" maxlength="1800" required>${escapeHtml(template.internalMessageTemplate || '')}</textarea></label>
      </div>
      <div class="notification-template-channel-block">
        <div><p class="eyebrow">Email</p><h3>Mensagem enviada por SMTP</h3></div>
        <label><span>Assunto</span><input name="emailSubjectTemplate" maxlength="180" value="${escapeHtml(template.emailSubjectTemplate || '')}" required></label>
        <label><span>Conteúdo</span><textarea name="emailMessageTemplate" rows="4" maxlength="5000" required>${escapeHtml(template.emailMessageTemplate || '')}</textarea></label>
      </div>
      <div class="notification-template-channel-block">
        <div><p class="eyebrow">Push</p><h3>Aviso no dispositivo</h3></div>
        <label><span>Título curto</span><input name="pushTitleTemplate" maxlength="120" value="${escapeHtml(template.pushTitleTemplate || '')}" required></label>
        <label><span>Mensagem curta</span><textarea name="pushMessageTemplate" rows="3" maxlength="300" required>${escapeHtml(template.pushMessageTemplate || '')}</textarea></label>
      </div>
      <div class="notification-template-preview-grid">
        <article><span>Pré-visualização interna</span><strong>${escapeHtml(template.internalTitleTemplate || '')}</strong><p>${escapeHtml(template.internalMessageTemplate || '')}</p></article>
        <article><span>Pré-visualização Push</span><strong>${escapeHtml(template.pushTitleTemplate || '')}</strong><p>${escapeHtml(template.pushMessageTemplate || '')}</p></article>
      </div>
      <div class="notification-template-actions">
        <button class="button button-primary" type="submit">Guardar modelo</button>
        <button class="button button-secondary" id="resetNotificationTemplate" type="button" ${template.customized ? '' : 'disabled'}>Repor modelo padrão</button>
      </div>
    </form>
  `;
}

async function loadNotificationManagement(options = {}) {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar notificações...');
  try {
    const [notificationLog, studentResult] = await Promise.all([
      api.adminNotifications({ limit: 120 }, options),
      api.adminStudents({ status: 'ACTIVE', limit: 2000 }, options)
    ]);
    state.notificationLog = notificationLog;
    state.students = studentResult.students || [];
    state.notificationStudentTotal = Number(studentResult.total ?? state.students.length);
    renderNotificationManagement();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderNotificationManagement() {
  const main = document.querySelector('#adminMain');
  const data = state.notificationLog || {};
  const summary = data.summary || {};
  const whatsapp = data.whatsappConfiguration || {};
  const email = data.emailConfiguration || {};
  const telegram = data.telegramConfiguration || {};
  const push = data.pushConfiguration || {};
  const notificationTemplates = data.notificationTemplates || [];
  const emailPasswordConfigured = Boolean(email.passwordConfigured ?? email.smtpPasswordConfigured);
  const emailStoredPasswordConfigured = Boolean(email.storedPasswordConfigured ?? email.storedSmtpPasswordConfigured);
  const activeStudents = state.students.filter(({ student }) => student?.status === 'ACTIVE');
  const activeStudentTotal = Math.max(activeStudents.length, state.notificationStudentTotal || 0);
  const pendingDeliveries = Number(summary.whatsappPending || 0) + Number(summary.emailPending || 0) + Number(summary.telegramPending || 0) + Number(summary.pushPending || 0);
  const failedDeliveries = Number(summary.whatsappFailed || 0) + Number(summary.emailFailed || 0) + Number(summary.telegramFailed || 0) + Number(summary.pushFailed || 0);

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Comunicação académica</p>
        <h1>Notificações</h1>
        <p>Envie atualizações internas, por email, WhatsApp, Telegram ou Push, em simultâneo ou separadamente.</p>
      </div>
      ${canManageNotifications() && (pendingDeliveries || failedDeliveries) ? `
        <button class="button button-secondary" id="retryNotificationDeliveries" type="button">
          Repetir envios pendentes
        </button>
      ` : ''}
    </div>

    <section class="admin-summary-grid notification-summary-grid">
      <article class="insight-card"><img src="${iconUrl('bell', goldIcon)}" alt=""><div><span>Internas</span><strong>${Number(summary.internalTotal || 0)}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('mail-check', goldIcon)}" alt=""><div><span>Emails enviados</span><strong>${Number(summary.emailSent || 0)}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('message-circle-check', goldIcon)}" alt=""><div><span>WhatsApp aceites</span><strong>${Number(summary.whatsappSent || 0)}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('send', goldIcon)}" alt=""><div><span>Telegram aceites</span><strong>${Number(summary.telegramSent || 0)}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('bell-ring', goldIcon)}" alt=""><div><span>Push entregues</span><strong>${Number(summary.pushSent || 0)}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('clock-3', goldIcon)}" alt=""><div><span>Entregas pendentes</span><strong>${pendingDeliveries}</strong></div></article>
      <article class="insight-card"><img src="${iconUrl('circle-alert', goldIcon)}" alt=""><div><span>Entregas com falha</span><strong>${failedDeliveries}</strong></div></article>
    </section>

    <section class="notification-admin-grid">
      ${canManageNotifications() ? `
        <article class="admin-content-panel notification-composer-card">
          <div class="section-heading">
            <div><p class="eyebrow">Nova atualização</p><h2>Enviar aos estudantes</h2></div>
          </div>
          <form id="notificationComposer" class="form-stack" data-recipient-total="${activeStudentTotal}">
            <fieldset class="notification-recipient-picker" aria-describedby="notificationRecipientHelp notificationRecipientStatus">
              <legend>Destinatários</legend>
              <div class="notification-recipient-toolbar">
                <label class="notification-recipient-search">
                  <span class="sr-only">Pesquisar estudantes</span>
                  <img src="${iconUrl('search', goldIcon)}" alt="">
                  <input id="notificationStudentSearch" type="search"
                    placeholder="Pesquisar por nome, ID público, email ou telefone"
                    aria-controls="notificationRecipientList" autocomplete="off" spellcheck="false">
                </label>
                <div class="notification-recipient-actions">
                  <button class="button button-secondary button-small" type="button" data-select-visible>Selecionar visíveis</button>
                  <button class="button button-secondary button-small" type="button" data-clear-recipients>Limpar seleção</button>
                </div>
              </div>
              <div class="notification-recipient-summary">
                <label class="checkbox-line">
                  <input type="checkbox" name="notifyAll" value="true">
                  Enviar a todos os estudantes ativos
                </label>
                <span id="notificationRecipientStatus" role="status" aria-live="polite" aria-atomic="true">
                  <strong id="notificationSelectedCount">0</strong> de ${activeStudentTotal} selecionados ·
                  <span id="notificationVisibleCount">${activeStudents.length}</span> visíveis
                </span>
              </div>
              <div class="notification-recipient-list" id="notificationRecipientList" role="group" aria-label="Seleção de estudantes ativos">
                ${activeStudents.length
                  ? activeStudents.map(({ student }) => notificationRecipientTemplate(student)).join('')
                  : '<p class="empty-state compact">Não existem estudantes ativos.</p>'}
              </div>
              <p class="notification-recipient-empty" id="notificationRecipientEmpty" hidden>Nenhum estudante corresponde à pesquisa.</p>
              <p class="notification-recipient-help" id="notificationRecipientHelp">${activeStudents.length < activeStudentTotal
                ? `A lista apresenta ${activeStudents.length} de ${activeStudentTotal} estudantes ativos. Use “Enviar a todos” para incluir todos.`
                : 'Pesquise e marque os destinatários individualmente ou selecione todos os estudantes ativos.'}</p>
            </fieldset>
            <div class="profile-form-grid">
              <label>
                <span>Tipo</span>
                <select name="category">
                  <option value="GENERAL">Comunicado geral</option>
                  <option value="MODULE_AVAILABLE">Módulos e exercícios</option>
                  <option value="SUBMISSION_STATUS">Estado de submissão</option>
                  <option value="REVIEW_FEEDBACK">Avaliação e feedback</option>
                </select>
              </label>
              <label>
                <span>Prioridade</span>
                <select name="priority"><option value="NORMAL">Normal</option><option value="HIGH">Alta</option></select>
              </label>
            </div>
            <label><span>Título</span><input name="title" maxlength="180" required></label>
            <label><span>Mensagem</span><textarea name="message" rows="5" maxlength="1800" required></textarea></label>
            <label><span>Destino ao abrir</span><input name="actionUrl" value="#/notifications" placeholder="#/lessons"></label>
            <details class="notification-channel-overrides">
              <summary>Personalizar Email e Push desta mensagem</summary>
              <p>Deixe os campos vazios para reutilizar o título e a mensagem internos.</p>
              <div class="profile-form-grid">
                <label><span>Assunto do email</span><input name="emailSubject" maxlength="180"></label>
                <label><span>Título Push</span><input name="pushTitle" maxlength="120"></label>
              </div>
              <label><span>Conteúdo do email</span><textarea name="emailMessage" rows="4" maxlength="5000"></textarea></label>
              <label><span>Mensagem Push</span><textarea name="pushMessage" rows="3" maxlength="300"></textarea></label>
            </details>
            <fieldset class="notification-channel-selector">
              <legend>Canais de envio</legend>
              <p>A notificação interna é sempre registada. Selecione nenhum, um ou vários canais externos.</p>
              <div class="notification-channel-selector-grid">
                <label class="checkbox-line notification-channel-option">
                  <input type="checkbox" name="sendEmail" value="true" ${email.configured ? '' : 'disabled'}>
                  <span><strong>Email</strong><small>${email.configured ? 'Exige consentimento e um endereço válido.' : 'Configure e ative o SMTP para utilizar este canal.'}</small></span>
                </label>
                <label class="checkbox-line notification-channel-option">
                  <input type="checkbox" name="sendWhatsApp" value="true" ${whatsapp.configured ? '' : 'disabled'}>
                  <span><strong>WhatsApp</strong><small>${whatsapp.configured ? 'Exige consentimento e telefone válido.' : 'Configure e ative o WhatsApp para utilizar este canal.'}</small></span>
                </label>
                <label class="checkbox-line notification-channel-option">
                  <input type="checkbox" name="sendTelegram" value="true" ${telegram.configured ? '' : 'disabled'}>
                  <span><strong>Telegram</strong><small>${telegram.configured ? 'Exige consentimento e uma conta associada.' : 'Configure e ative o bot para utilizar este canal.'}</small></span>
                </label>
                <label class="checkbox-line notification-channel-option">
                  <input type="checkbox" name="sendPush" value="true" ${push.configured ? '' : 'disabled'}>
                  <span><strong>Push</strong><small>${push.configured ? 'Envia aos dispositivos autorizados pelo estudante.' : 'Configure as chaves VAPID no servidor para utilizar este canal.'}</small></span>
                </label>
              </div>
            </fieldset>
            <button class="button button-primary" type="submit">Enviar atualização</button>
          </form>
        </article>
      ` : ''}

      <div class="notification-configuration-stack">
      <article class="admin-content-panel notification-configuration-card whatsapp-configuration-card">
        <div class="section-heading">
          <div><p class="eyebrow">Canal externo</p><h2>WhatsApp Business</h2></div>
          <span class="status-pill ${whatsapp.configured ? 'status-approved' : 'status-pending'}">${whatsapp.configured ? 'Configurado' : 'Configuração pendente'}</span>
        </div>
        ${canManageNotifications() ? `
          <form id="whatsappConfigurationForm" class="form-stack whatsapp-configuration-form">
            <label class="checkbox-line notification-channel-option">
              <input type="checkbox" name="enabled" value="true" ${whatsapp.enabled ? 'checked' : ''}>
              <span><strong>Ativar o envio pelo WhatsApp</strong><small>As notificações internas continuam disponíveis mesmo quando este canal está desativado.</small></span>
            </label>
            <div class="profile-form-grid">
              <label>
                <span>Phone Number ID</span>
                <input name="phoneNumberId" inputmode="numeric" pattern="[0-9]{6,30}" value="${escapeHtml(whatsapp.phoneNumberId || '')}" placeholder="Ex.: 104567890123456">
              </label>
              <label>
                <span>Versão da Graph API</span>
                <input name="graphApiVersion" pattern="v[0-9]+[.][0-9]+" value="${escapeHtml(whatsapp.graphApiVersion || 'v23.0')}" placeholder="v23.0">
              </label>
              <label>
                <span>Modelo aprovado</span>
                <input name="templateName" pattern="[a-z0-9_]+" value="${escapeHtml(whatsapp.templateName || '')}" placeholder="atualizacao_academica">
              </label>
              <label>
                <span>Idioma do modelo</span>
                <input name="templateLanguage" pattern="[a-z]{2,3}(_[A-Z]{2})?" value="${escapeHtml(whatsapp.templateLanguage || 'pt_PT')}" placeholder="pt_PT">
              </label>
            </div>
            <label>
              <span>Endereço público da plataforma</span>
              <input name="platformUrl" type="url" value="${escapeHtml(whatsapp.platformUrl || '')}" placeholder="https://formacao.exemplo.org">
            </label>
            <label>
              <span>Token de acesso permanente</span>
              <input name="accessToken" type="password" autocomplete="new-password" maxlength="8192"
                placeholder="${whatsapp.tokenConfigured ? 'Token configurado — deixe vazio para manter' : 'Cole o token da Meta'}"
                ${whatsapp.encryptionKeyConfigured ? '' : 'disabled'}>
            </label>
            ${whatsapp.storedTokenConfigured ? `
              <label class="checkbox-line whatsapp-remove-token">
                <input type="checkbox" name="removeAccessToken" value="true">
                Remover o token guardado no painel
              </label>
            ` : ''}
            <div class="whatsapp-security-note ${whatsapp.encryptionKeyConfigured ? 'is-secure' : 'is-warning'}">
              <img src="${iconUrl(whatsapp.encryptionKeyConfigured ? 'shield-check' : 'triangle-alert', whatsapp.encryptionKeyConfigured ? blueIcon : goldIcon)}" alt="">
              <span>${whatsapp.encryptionKeyConfigured
                ? 'O token é encriptado antes de ser guardado e nunca é apresentado novamente.'
                : 'Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY no servidor para guardar ou substituir credenciais por este painel.'}</span>
            </div>
            ${whatsapp.tokenError ? `<p class="field-error">${escapeHtml(whatsapp.tokenError)}</p>` : ''}
            <div class="whatsapp-configuration-meta">
              <span>Origem: <strong>${whatsapp.source === 'ADMIN' ? 'Painel administrativo' : 'Servidor'}</strong></span>
              <span>Token: <strong>${whatsapp.tokenConfigured ? 'Protegido' : 'Em falta'}</strong></span>
            </div>
            <p class="management-field-hint">O modelo aprovado deve conter quatro campos no corpo: nome, título, mensagem e link.</p>
            <button class="button button-primary" type="submit">Guardar configuração</button>
          </form>
        ` : `
          <dl class="notification-config-list">
            <div><dt>Integração ativa</dt><dd>${whatsapp.enabled ? 'Sim' : 'Não'}</dd></div>
            <div><dt>Número empresarial</dt><dd>${whatsapp.phoneNumberConfigured ? 'Configurado' : 'Em falta'}</dd></div>
            <div><dt>Modelo aprovado</dt><dd>${escapeHtml(whatsapp.templateName || 'Em falta')}</dd></div>
            <div><dt>Idioma</dt><dd>${escapeHtml(whatsapp.templateLanguage || 'pt_PT')}</dd></div>
          </dl>
        `}
      </article>
      <article class="admin-content-panel notification-configuration-card email-configuration-card">
        <div class="section-heading">
          <div><p class="eyebrow">Canal externo</p><h2>Email por SMTP</h2></div>
          <span class="status-pill ${email.configured ? 'status-approved' : 'status-pending'}">${email.configured ? 'Configurado' : 'Configuração pendente'}</span>
        </div>
        ${canManageNotifications() ? `
          <form id="emailConfigurationForm" class="form-stack notification-configuration-form">
            <label class="checkbox-line notification-channel-option">
              <input type="checkbox" name="enabled" value="true" ${email.enabled ? 'checked' : ''}>
              <span><strong>Ativar o envio por email</strong><small>Utiliza o servidor SMTP da instituição sem interferir nas notificações internas.</small></span>
            </label>
            <div class="profile-form-grid">
              <label>
                <span>Servidor SMTP</span>
                <input name="smtpHost" value="${escapeHtml(email.smtpHost || '')}" placeholder="smtp.exemplo.org" autocomplete="off">
              </label>
              <label>
                <span>Porta SMTP</span>
                <input name="smtpPort" type="number" inputmode="numeric" min="1" max="65535" value="${escapeHtml(email.smtpPort || 587)}">
              </label>
              <label>
                <span>Utilizador SMTP</span>
                <input name="smtpUsername" value="${escapeHtml(email.smtpUsername || '')}" placeholder="notificacoes@exemplo.org" autocomplete="username">
              </label>
              <label>
                <span>Nome do remetente</span>
                <input name="fromName" value="${escapeHtml(email.fromName || '')}" placeholder="Formação académica">
              </label>
              <label>
                <span>Email do remetente</span>
                <input name="fromEmail" type="email" value="${escapeHtml(email.fromEmail || '')}" placeholder="notificacoes@exemplo.org">
              </label>
              <label>
                <span>Palavra-passe SMTP</span>
                <input name="smtpPassword" type="password" autocomplete="new-password" maxlength="8192"
                  placeholder="${emailPasswordConfigured ? 'Palavra-passe configurada — deixe vazio para manter' : 'Introduza a palavra-passe SMTP'}"
                  ${email.encryptionKeyConfigured === false ? 'disabled' : ''}>
              </label>
            </div>
            <label class="checkbox-line notification-channel-option">
              <input type="checkbox" name="useTls" value="true" ${email.useTls !== false ? 'checked' : ''}>
              <span><strong>Usar ligação segura TLS</strong><small>Recomendado para proteger as credenciais e o conteúdo durante o envio.</small></span>
            </label>
            ${emailStoredPasswordConfigured ? `
              <label class="checkbox-line notification-remove-secret">
                <input type="checkbox" name="removeSmtpPassword" value="true">
                Remover a palavra-passe guardada no painel
              </label>
            ` : ''}
            <div class="notification-security-note ${email.encryptionKeyConfigured === false ? 'is-warning' : 'is-secure'}">
              <img src="${iconUrl(email.encryptionKeyConfigured === false ? 'triangle-alert' : 'shield-check', email.encryptionKeyConfigured === false ? goldIcon : blueIcon)}" alt="">
              <span>${email.encryptionKeyConfigured === false
                ? 'Configure a chave de encriptação no servidor antes de guardar a palavra-passe SMTP.'
                : 'A palavra-passe é encriptada antes de ser guardada e nunca é apresentada novamente.'}</span>
            </div>
            ${email.passwordError ? `<p class="field-error">${escapeHtml(email.passwordError)}</p>` : ''}
            <div class="notification-configuration-meta">
              <span>Origem: <strong>${email.source === 'ADMIN' ? 'Painel administrativo' : 'Servidor'}</strong></span>
              <span>Credencial: <strong>${emailPasswordConfigured ? 'Protegida' : 'Em falta'}</strong></span>
            </div>
            <button class="button button-primary" type="submit">Guardar configuração</button>
          </form>
        ` : `
          <dl class="notification-config-list">
            <div><dt>Integração ativa</dt><dd>${email.enabled ? 'Sim' : 'Não'}</dd></div>
            <div><dt>Servidor SMTP</dt><dd>${email.smtpHostConfigured || email.smtpHost ? 'Configurado' : 'Em falta'}</dd></div>
            <div><dt>Remetente</dt><dd>${escapeHtml(email.fromEmail || 'Em falta')}</dd></div>
            <div><dt>Ligação segura</dt><dd>${email.useTls !== false ? 'TLS' : 'Sem TLS'}</dd></div>
          </dl>
        `}
      </article>

      <article class="admin-content-panel notification-configuration-card telegram-configuration-card">
        <div class="section-heading">
          <div><p class="eyebrow">Canal externo</p><h2>Telegram Bot</h2></div>
          <span class="status-pill ${telegram.configured ? 'status-approved' : 'status-pending'}">${telegram.configured ? 'Configurado' : 'Configuração pendente'}</span>
        </div>
        ${canManageNotifications() ? `
          <form id="telegramConfigurationForm" class="form-stack notification-configuration-form">
            <label class="checkbox-line notification-channel-option">
              <input type="checkbox" name="enabled" value="true" ${telegram.enabled ? 'checked' : ''}>
              <span><strong>Ativar o envio pelo Telegram</strong><small>Os estudantes precisam de autorizar o canal e associar a conta no perfil.</small></span>
            </label>
            <div class="profile-form-grid">
              <label>
                <span>Utilizador do bot</span>
                <input name="botUsername" value="${escapeHtml(telegram.botUsername || '')}" pattern="@?[A-Za-z][A-Za-z0-9_]{4,31}" placeholder="@instituicao_bot" autocomplete="off">
              </label>
              <label>
                <span>Formatação das mensagens</span>
                <select name="parseMode">
                  <option value="HTML" ${telegram.parseMode === 'HTML' || telegram.parseMode == null ? 'selected' : ''}>HTML</option>
                  <option value="MarkdownV2" ${telegram.parseMode === 'MarkdownV2' ? 'selected' : ''}>Markdown V2</option>
                  <option value="NONE" ${telegram.parseMode === '' || telegram.parseMode === 'NONE' ? 'selected' : ''}>Sem formatação</option>
                </select>
              </label>
            </div>
            <label>
              <span>Token do bot</span>
              <input name="botToken" type="password" autocomplete="new-password" maxlength="256"
                placeholder="${telegram.tokenConfigured ? 'Token configurado — deixe vazio para manter' : 'Cole o token fornecido pelo BotFather'}"
                ${telegram.encryptionKeyConfigured === false ? 'disabled' : ''}>
            </label>
            ${telegram.storedTokenConfigured ? `
              <label class="checkbox-line notification-remove-secret">
                <input type="checkbox" name="removeBotToken" value="true">
                Remover o token guardado no painel
              </label>
            ` : ''}
            <div class="notification-security-note ${telegram.encryptionKeyConfigured === false ? 'is-warning' : 'is-secure'}">
              <img src="${iconUrl(telegram.encryptionKeyConfigured === false ? 'triangle-alert' : 'shield-check', telegram.encryptionKeyConfigured === false ? goldIcon : blueIcon)}" alt="">
              <span>${telegram.encryptionKeyConfigured === false
                ? 'Configure a chave de encriptação no servidor antes de guardar o token do bot.'
                : 'O token é encriptado antes de ser guardado e nunca é apresentado novamente.'}</span>
            </div>
            ${telegram.tokenError ? `<p class="field-error">${escapeHtml(telegram.tokenError)}</p>` : ''}
            <div class="notification-configuration-meta">
              <span>Origem: <strong>${telegram.source === 'ADMIN' ? 'Painel administrativo' : 'Servidor'}</strong></span>
              <span>Token: <strong>${telegram.tokenConfigured ? 'Protegido' : 'Em falta'}</strong></span>
            </div>
            <p class="management-field-hint">O estudante deve iniciar uma conversa com o bot antes de receber notificações.</p>
            <button class="button button-primary" type="submit">Guardar configuração</button>
          </form>
        ` : `
          <dl class="notification-config-list">
            <div><dt>Integração ativa</dt><dd>${telegram.enabled ? 'Sim' : 'Não'}</dd></div>
            <div><dt>Bot</dt><dd>${escapeHtml(telegram.botUsername || 'Em falta')}</dd></div>
            <div><dt>Token</dt><dd>${telegram.tokenConfigured ? 'Protegido' : 'Em falta'}</dd></div>
            <div><dt>Formatação</dt><dd>${escapeHtml(telegram.parseMode || 'Sem formatação')}</dd></div>
          </dl>
        `}
      </article>
      <article class="admin-content-panel notification-configuration-card push-configuration-card">
        <div class="section-heading">
          <div><p class="eyebrow">Canal externo</p><h2>Web Push</h2></div>
          <span class="status-pill ${push.configured ? 'status-approved' : 'status-pending'}">${push.configured ? 'Configurado' : 'Configuração pendente'}</span>
        </div>
        <dl class="notification-config-list">
          <div><dt>Integração ativa</dt><dd>${push.enabled ? 'Sim' : 'Não'}</dd></div>
          <div><dt>Chave pública VAPID</dt><dd>${push.publicKey ? 'Configurada' : 'Em falta'}</dd></div>
          <div><dt>Chave privada</dt><dd>${push.configured ? 'Protegida no servidor' : 'Em falta ou inválida'}</dd></div>
          <div><dt>Service worker</dt><dd>Incluído na aplicação</dd></div>
        </dl>
        <div class="notification-security-note ${push.configured ? 'is-secure' : 'is-warning'}">
          <img src="${iconUrl(push.configured ? 'shield-check' : 'triangle-alert', push.configured ? blueIcon : goldIcon)}" alt="">
          <span>${push.configured
            ? 'Os estudantes podem autorizar notificações individualmente em cada dispositivo.'
            : 'Defina WEB_PUSH_ENABLED, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY e VAPID_SUBJECT nas variáveis do servidor.'}</span>
        </div>
        <p class="management-field-hint">No iPhone e iPad, a aplicação deve ser adicionada ao ecrã principal antes de solicitar autorização.</p>
      </article>
      </div>
    </section>

    ${canManageNotifications() ? `
      <section class="admin-content-panel notification-template-panel">
        <div class="section-heading">
          <div><p class="eyebrow">Conteúdo por evento</p><h2>Modelos de notificações</h2></div>
        </div>
        <p class="management-field-hint">Personalize separadamente o texto interno, o email institucional e o aviso Push. Os modelos são aplicados apenas a novas notificações.</p>
        ${notificationTemplateEditor(notificationTemplates)}
      </section>
    ` : ''}

    <section class="admin-content-panel notification-history-panel">
      <div class="section-heading"><div><p class="eyebrow">Histórico</p><h2>Atualizações enviadas</h2></div></div>
      <div class="admin-table-wrap">
        <table class="admin-table notification-admin-table">
          <thead><tr><th>Estudante</th><th>Atualização</th><th>Interna</th><th>Email</th><th>WhatsApp</th><th>Telegram</th><th>Push</th><th>Data</th></tr></thead>
          <tbody>
            ${(data.notifications || []).length ? data.notifications.map((notification) => `
              <tr>
                <td data-label="Estudante"><strong>${escapeHtml(notification.studentName || 'Estudante')}</strong></td>
                <td data-label="Atualização"><strong>${escapeHtml(notification.title || '')}</strong><small>${escapeHtml(notification.message || '')}</small></td>
                <td data-label="Interna"><span class="status-pill status-approved">Registada</span></td>
                <td data-label="Email"><span class="status-pill notification-delivery-${String(notification.email?.status || '').toLowerCase()}">${escapeHtml(notificationDeliveryLabel(notification.email?.status, 'EMAIL'))}</span>${notification.email?.lastError ? `<small title="${escapeHtml(notification.email.lastError)}">Verificar configuração</small>` : ''}</td>
                <td data-label="WhatsApp"><span class="status-pill notification-delivery-${String(notification.whatsapp?.status || '').toLowerCase()}">${escapeHtml(notificationDeliveryLabel(notification.whatsapp?.status, 'WHATSAPP'))}</span>${notification.whatsapp?.lastError ? `<small title="${escapeHtml(notification.whatsapp.lastError)}">Verificar configuração</small>` : ''}</td>
                <td data-label="Telegram"><span class="status-pill notification-delivery-${String(notification.telegram?.status || '').toLowerCase()}">${escapeHtml(notificationDeliveryLabel(notification.telegram?.status, 'TELEGRAM'))}</span>${notification.telegram?.lastError ? `<small title="${escapeHtml(notification.telegram.lastError)}">Verificar configuração</small>` : ''}</td>
                <td data-label="Push"><span class="status-pill notification-delivery-${String(notification.push?.status || '').toLowerCase()}">${escapeHtml(notificationDeliveryLabel(notification.push?.status, 'PUSH'))}</span>${notification.push?.lastError ? `<small title="${escapeHtml(notification.push.lastError)}">Verificar dispositivo</small>` : ''}</td>
                <td data-label="Data">${escapeHtml(formatDate(notification.createdAt))}</td>
              </tr>
            `).join('') : '<tr><td colspan="8" class="empty-table">Ainda não existem notificações.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
  `;

  const form = document.querySelector('#notificationComposer');
  bindNotificationRecipientPicker(form);
  form?.addEventListener('submit', submitAdminNotification);
  document.querySelector('#whatsappConfigurationForm')?.addEventListener('submit', saveWhatsAppConfiguration);
  document.querySelector('#emailConfigurationForm')?.addEventListener('submit', saveEmailConfiguration);
  document.querySelector('#telegramConfigurationForm')?.addEventListener('submit', saveTelegramConfiguration);
  document.querySelector('#notificationTemplateSelect')?.addEventListener('change', (event) => {
    state.notificationTemplateKey = event.currentTarget.value;
    renderNotificationManagement();
  });
  document.querySelector('#notificationTemplateForm')?.addEventListener('submit', saveNotificationTemplate);
  document.querySelector('#resetNotificationTemplate')?.addEventListener('click', resetNotificationTemplate);
  document.querySelector('#retryNotificationDeliveries')?.addEventListener('click', retryNotificationDeliveries);
  reportHeight();
}

function bindNotificationRecipientPicker(form) {
  if (!form) return;
  const search = form.querySelector('#notificationStudentSearch');
  const list = form.querySelector('#notificationRecipientList');
  const rows = [...form.querySelectorAll('[data-recipient-row]')];
  const recipientTotal = Math.max(rows.length, Number(form.dataset.recipientTotal || 0));
  const notifyAll = form.elements.notifyAll;
  const selectedCount = form.querySelector('#notificationSelectedCount');
  const visibleCount = form.querySelector('#notificationVisibleCount');
  const status = form.querySelector('#notificationRecipientStatus');
  const emptyMessage = form.querySelector('#notificationRecipientEmpty');
  const selectVisibleButton = form.querySelector('[data-select-visible]');
  const clearButton = form.querySelector('[data-clear-recipients]');

  const update = () => {
    const useAllStudents = Boolean(notifyAll?.checked);
    let selected = 0;
    let visible = 0;
    let visibleSelected = 0;
    rows.forEach((row) => {
      const checkbox = row.querySelector('input[name="studentIds"]');
      checkbox.disabled = useAllStudents;
      row.classList.toggle('is-selected', checkbox.checked);
      if (checkbox.checked) selected += 1;
      if (!row.hidden) {
        visible += 1;
        if (checkbox.checked) visibleSelected += 1;
      }
    });
    list?.classList.toggle('is-disabled', useAllStudents);
    list?.setAttribute('aria-disabled', String(useAllStudents));
    if (search) search.disabled = useAllStudents;
    if (selectVisibleButton) selectVisibleButton.disabled = useAllStudents || visible === 0;
    if (clearButton) clearButton.disabled = useAllStudents || selected === 0;
    if (selectedCount) selectedCount.textContent = String(useAllStudents ? recipientTotal : selected);
    if (visibleCount) visibleCount.textContent = String(visible);
    if (status) {
      status.setAttribute('aria-label', useAllStudents
        ? `Todos os ${recipientTotal} estudantes ativos selecionados. ${visible} visíveis.`
        : `${selected} de ${recipientTotal} estudantes selecionados. ${visible} visíveis.`);
    }
    if (selectVisibleButton) {
      const allVisibleSelected = visible > 0 && visibleSelected === visible;
      selectVisibleButton.textContent = allVisibleSelected ? 'Desmarcar visíveis' : 'Selecionar visíveis';
      selectVisibleButton.setAttribute('aria-pressed', String(allVisibleSelected));
    }
    if (emptyMessage) {
      emptyMessage.hidden = rows.length === 0 || visible > 0 || !search?.value.trim();
    }
  };

  search?.addEventListener('input', () => {
    const query = notificationSearchText(search.value.trim());
    rows.forEach((row) => {
      row.hidden = Boolean(query && !row.dataset.search.includes(query));
    });
    update();
  });
  search?.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !search.value) return;
    search.value = '';
    rows.forEach((row) => { row.hidden = false; });
    update();
  });
  rows.forEach((row) => row.querySelector('input')?.addEventListener('change', update));
  notifyAll?.addEventListener('change', update);
  selectVisibleButton?.addEventListener('click', () => {
    const visibleRows = rows.filter((row) => !row.hidden);
    const shouldSelect = visibleRows.some((row) => !row.querySelector('input[name="studentIds"]').checked);
    visibleRows.forEach((row) => {
      row.querySelector('input[name="studentIds"]').checked = shouldSelect;
    });
    update();
  });
  clearButton?.addEventListener('click', () => {
    rows.forEach((row) => {
      row.querySelector('input[name="studentIds"]').checked = false;
    });
    update();
  });
  update();
}

async function submitAdminNotification(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const notifyAll = values.get('notifyAll') === 'true';
  const studentIds = values.getAll('studentIds');
  if (!notifyAll && !studentIds.length) {
    showToast('Selecione pelo menos um estudante.', 'warning');
    return;
  }
  if (notifyAll && !confirmAdminAction(`Enviar esta atualização aos ${state.notificationStudentTotal || state.students.length} estudantes ativos?`)) return;
  setBusy(button, true, 'A enviar...');
  try {
    const result = await api.adminCreateNotification({
      studentIds,
      notifyAll,
      category: values.get('category'),
      priority: values.get('priority'),
      title: values.get('title'),
      message: values.get('message'),
      actionUrl: values.get('actionUrl'),
      emailSubject: values.get('emailSubject') || '',
      emailMessage: values.get('emailMessage') || '',
      pushTitle: values.get('pushTitle') || '',
      pushMessage: values.get('pushMessage') || '',
      sendWhatsApp: values.get('sendWhatsApp') === 'true',
      sendEmail: values.get('sendEmail') === 'true',
      sendTelegram: values.get('sendTelegram') === 'true',
      sendPush: values.get('sendPush') === 'true'
    });
    showToast(`${result.notificationCount} notificação${result.notificationCount === 1 ? '' : 'ões'} criada${result.notificationCount === 1 ? '' : 's'}.`, 'success');
    await loadNotificationManagement({ force: true });
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function saveNotificationTemplate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = Object.fromEntries(new FormData(form).entries());
  setBusy(button, true, 'A guardar...');
  try {
    const result = await api.adminSaveNotificationTemplate(values);
    state.notificationLog.notificationTemplates = result.notificationTemplates || [];
    showToast('Modelo de notificação guardado.', 'success');
    renderNotificationManagement();
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function resetNotificationTemplate(event) {
  const button = event.currentTarget;
  const templateKey = document.querySelector('#notificationTemplateForm [name="templateKey"]')?.value || '';
  if (!templateKey || !confirmAdminAction('Repor todos os textos deste evento para o modelo padrão?')) return;
  setBusy(button, true, 'A repor...');
  try {
    const result = await api.adminResetNotificationTemplate(templateKey);
    state.notificationLog.notificationTemplates = result.notificationTemplates || [];
    showToast('Modelo padrão reposto.', 'success');
    renderNotificationManagement();
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function saveWhatsAppConfiguration(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  setBusy(button, true, 'A guardar...');
  try {
    const result = await api.adminSaveWhatsAppConfiguration({
      enabled: values.get('enabled') === 'true',
      phoneNumberId: values.get('phoneNumberId') || '',
      graphApiVersion: values.get('graphApiVersion') || 'v23.0',
      templateName: values.get('templateName') || '',
      templateLanguage: values.get('templateLanguage') || 'pt_PT',
      platformUrl: values.get('platformUrl') || '',
      accessToken: values.get('accessToken') || '',
      removeAccessToken: values.get('removeAccessToken') === 'true'
    });
    state.notificationLog.whatsappConfiguration = result.whatsappConfiguration;
    showToast('Configuração do WhatsApp guardada.', 'success');
    await loadNotificationManagement({ force: true });
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function saveEmailConfiguration(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  setBusy(button, true, 'A guardar...');
  try {
    const result = await api.adminSaveEmailConfiguration({
      enabled: values.get('enabled') === 'true',
      smtpHost: values.get('smtpHost') || '',
      smtpPort: Number(values.get('smtpPort') || 587),
      smtpUsername: values.get('smtpUsername') || '',
      smtpPassword: values.get('smtpPassword') || '',
      fromEmail: values.get('fromEmail') || '',
      fromName: values.get('fromName') || '',
      useTls: values.get('useTls') === 'true',
      removeSmtpPassword: values.get('removeSmtpPassword') === 'true'
    });
    state.notificationLog.emailConfiguration = result.emailConfiguration;
    showToast('Configuração de email guardada.', 'success');
    await loadNotificationManagement({ force: true });
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function saveTelegramConfiguration(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  setBusy(button, true, 'A guardar...');
  try {
    const result = await api.adminSaveTelegramConfiguration({
      enabled: values.get('enabled') === 'true',
      botToken: values.get('botToken') || '',
      botUsername: values.get('botUsername') || '',
      parseMode: values.get('parseMode') || '',
      removeBotToken: values.get('removeBotToken') === 'true'
    });
    state.notificationLog.telegramConfiguration = result.telegramConfiguration;
    showToast('Configuração do Telegram guardada.', 'success');
    await loadNotificationManagement({ force: true });
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

async function retryNotificationDeliveries(event) {
  const button = event.currentTarget;
  setBusy(button, true, 'A repetir...');
  try {
    const result = await api.adminRetryNotificationDeliveries(20);
    showToast(`${result.delivery?.sent || 0} envio${result.delivery?.sent === 1 ? '' : 's'} concluído${result.delivery?.sent === 1 ? '' : 's'}.`, 'success');
    await loadNotificationManagement({ force: true });
  } catch (error) {
    handleAdminError(error);
    setBusy(button, false);
  }
}

function confirmAdminAction(message) {
  return window.confirm(message);
}

function bindDialogClose(overlay) {
  overlay.querySelector('.dialog-close')?.addEventListener('click', () => overlay.remove());
  overlay.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => overlay.remove());
  });
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
}

function renderPreservingFocus(renderFn) {
  const active = document.activeElement;
  const activeId = active?.id;
  const selectionStart = typeof active?.selectionStart === 'number' ? active.selectionStart : null;
  const selectionEnd = typeof active?.selectionEnd === 'number' ? active.selectionEnd : null;

  renderFn();

  if (!activeId) return;
  const nextActive = document.getElementById(activeId);
  if (!nextActive) return;
  nextActive.focus();
  if (
    selectionStart !== null &&
    selectionEnd !== null &&
    typeof nextActive.setSelectionRange === 'function'
  ) {
    nextActive.setSelectionRange(selectionStart, selectionEnd);
  }
}

function canManageStaff() {
  return ['OWNER', 'ADMIN'].includes(state.admin?.role);
}

function canManageCredentials() {
  return ['OWNER', 'ADMIN'].includes(state.admin?.role);
}

function renderCredentialsManagement() {
  const main = document.querySelector('#adminMain');
  const canRestoreStaff = state.admin?.role === 'OWNER';

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Segurança de acesso</p>
        <h1>Credenciais</h1>
      </div>
    </div>

    <section class="credential-management-grid">
      <article class="credential-management-card">
        <img src="${iconUrl('student-male', goldIcon)}" alt="">
        <div>
          <span>Estudantes</span>
          <h2>Restaurar acesso dos participantes</h2>
          <p>Cria palavras-passe temporárias para contas importadas ou selecionadas.</p>
        </div>
        <button class="button button-primary" type="button" data-open-credential-target="STUDENTS">
          Abrir restauração
        </button>
      </article>

      ${canRestoreStaff ? `
        <article class="credential-management-card">
          <img src="${iconUrl('conference-call', goldIcon)}" alt="">
          <div>
            <span>Staff</span>
            <h2>Restaurar acesso administrativo</h2>
            <p>Disponível apenas para o proprietário e com invalidação das sessões antigas.</p>
          </div>
          <button class="button button-primary" type="button" data-open-credential-target="ADMINS">
            Abrir restauração
          </button>
        </article>

        <article class="credential-management-card">
          <img src="${iconUrl('key', goldIcon)}" alt="">
          <div>
            <span>Lote completo</span>
            <h2>Tratar estudantes e staff</h2>
            <p>Usar em migrações ou na correção geral de contas sem palavra-passe.</p>
          </div>
          <button class="button button-secondary" type="button" data-open-credential-target="ALL">
            Abrir lote
          </button>
        </article>
      ` : ''}
    </section>
  `;

  root.querySelectorAll('[data-open-credential-target]').forEach((button) => {
    button.addEventListener('click', () => showCredentialRecoveryDialog(button.dataset.openCredentialTarget));
  });
  reportHeight();
}

async function loadStaff(options = {}) {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar staff...');

  try {
    const result = await (typeof api.adminStaff === 'function' ? api.adminStaff(options) : api.adminstaff(options));
    state.staff = result.staff || [];
    state.admin = result.currentAdmin || state.admin;
    renderStaff();
  } catch (error) {
    if (options.silent) {
      console.warn('Falha ao atualizar staff em segundo plano:', error);
      return;
    }
    handleAdminError(error);
  }
}

function renderStaff() {
  const main = document.querySelector('#adminMain');
  const activeCount = state.staff.filter((admin) => admin.status === 'ACTIVE').length;
  const reviewerCount = state.staff.filter((admin) => admin.role === 'REVIEWER' && admin.status === 'ACTIVE').length;

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Gestão de Staff</p>
        <h1>Administradores e revisores</h1>
      </div>
      <div class="admin-heading-actions">
        ${state.admin?.role === 'OWNER' ? `
          <button class="button button-secondary" id="restoreStaffCredentials" type="button">Restaurar credenciais</button>
          <button class="button button-primary" id="newStaff" type="button">Adicionar staff</button>
        ` : ''}
      </div>
    </div>

    <section class="admin-summary-grid">
      <article class="insight-card">
        <img src="${iconUrl('conference-call', goldIcon)}" alt="">
        <div><span>Total</span><strong>${state.staff.length}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('ok', goldIcon)}" alt="">
        <div><span>Ativos</span><strong>${activeCount}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('inspection', goldIcon)}" alt="">
        <div><span>Revisores</span><strong>${reviewerCount}</strong></div>
      </article>
    </section>

    <div class="admin-table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Email</th>
            <th>Permissão</th>
            <th>Estado</th>
            <th>Atualizado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${state.staff.length ? state.staff.map(staffRowTemplate).join('') : `
            <tr><td colspan="6" class="empty-table">Nenhum membro de staff registado.</td></tr>
          `}
        </tbody>
      </table>
    </div>
  `;

  document.querySelector('#newStaff')?.addEventListener('click', () => showStaffDialog());
  document.querySelector('#restoreStaffCredentials')?.addEventListener('click', () => showCredentialRecoveryDialog('ADMINS'));
  root.querySelectorAll('[data-edit-staff]').forEach((button) => {
    button.addEventListener('click', () => showStaffDialog(button.dataset.editStaff));
  });
  root.querySelectorAll('[data-staff-status]').forEach((button) => {
    button.addEventListener('click', () => setStaffStatus(button.dataset.staffStatus, button.dataset.status));
  });
  reportHeight();
}

function staffRowTemplate(admin) {
  const isCurrent = admin.adminId === state.admin?.adminId;
  const canEdit = state.admin?.role === 'OWNER';
  const canRemove = canEdit && !isCurrent && admin.status !== 'DELETED';
  const canActivate = canEdit && admin.status !== 'ACTIVE';

  return `
    <tr>
      <td>
        <strong>${escapeHtml(admin.fullName)}</strong>
        ${isCurrent ? '<small>Perfil atual</small>' : ''}
      </td>
      <td>${escapeHtml(admin.email)}</td>
      <td>${escapeHtml(admin.role)}</td>
      <td><span class="status-pill ${statusClass(admin.status)}">${statusLabel(admin.status)}</span></td>
      <td>${escapeHtml(formatDate(admin.updatedAt || admin.createdAt))}</td>
      <td>
        <div class="admin-row-actions">
          ${canEdit ? `
            <button class="button button-small button-secondary" type="button"
              data-edit-staff="${escapeHtml(admin.adminId)}">
              Editar
            </button>
          ` : '<span class="empty-note">Sem permissão para editar</span>'}
          ${canRemove ? `
            <button class="button button-small button-danger" type="button"
              data-staff-status="${escapeHtml(admin.adminId)}" data-status="DELETED">
              Remover
            </button>
          ` : ''}
          ${canActivate ? `
            <button class="button button-small button-secondary" type="button"
              data-staff-status="${escapeHtml(admin.adminId)}" data-status="ACTIVE">
              Ativar
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `;
}

function showStaffDialog(adminId = '') {
  const admin = state.staff.find((item) => item.adminId === adminId) || {
    adminId: '',
    fullName: '',
    email: '',
    role: 'REVIEWER',
    status: 'ACTIVE'
  };

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>${adminId ? 'Editar staff' : 'Adicionar staff'}</h2>
      <form id="staffForm" class="form-stack">
        <input type="hidden" name="adminId" value="${escapeHtml(admin.adminId || '')}">
        <label>
          <span>Nome completo</span>
          <input name="fullName" value="${escapeHtml(admin.fullName || '')}" required>
        </label>
        <label>
          <span>Email</span>
          <input type="email" name="email" value="${escapeHtml(admin.email || '')}" required>
        </label>
        <div class="course-form-grid">
          <label>
            <span>Permissão</span>
            <select name="role">
              ${studentFilterOption('OWNER', 'Owner', admin.role || 'REVIEWER')}
              ${studentFilterOption('ADMIN', 'Administrador', admin.role || 'REVIEWER')}
              ${studentFilterOption('REVIEWER', 'Revisor', admin.role || 'REVIEWER')}
            </select>
          </label>
          <label>
            <span>Estado</span>
            <select name="status">
              ${studentFilterOption('ACTIVE', 'Ativo', admin.status || 'ACTIVE')}
              ${studentFilterOption('INACTIVE', 'Inativo', admin.status || 'ACTIVE')}
              ${studentFilterOption('BLOCKED', 'Bloqueado', admin.status || 'ACTIVE')}
            </select>
          </label>
        </div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar staff</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#staffForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!confirmAdminAction('Deseja guardar estas permissões de staff?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    setBusy(button, true, 'A guardar...');
    try {
      const result = await api.adminSaveStaff(values);
      if (result.adminPassword) {
        alert(`Staff guardado.\n\nPalavra-passe temporária: ${result.adminPassword}\n\nGuarde a palavra-passe antes de fechar.`);
      }
      showToast('Staff guardado.', 'success');
      overlay.remove();
      await loadStaff();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

async function setStaffStatus(adminId, status) {
  const verb = status === 'DELETED' ? 'remover permissões deste membro' : 'alterar o estado deste membro';
  if (!confirmAdminAction(`Tem certeza que deseja ${verb}?`)) return;

  try {
    await api.adminSetStaffStatus(adminId, status);
    showToast('Permissões atualizadas.', 'success');
    await loadStaff();
  } catch (error) {
    handleAdminError(error);
  }
}

async function showCredentialRecoveryDialog(defaultTarget = 'STUDENTS') {
  await ensureCredentialRecoveryData(defaultTarget);

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card credential-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>Restaurar credenciais</h2>
      <p class="credential-dialog-note">
        Gere novas palavras-passe temporárias para contas já existentes no Supabase. O progresso,
        inscrições, grupos e submissões não são alterados.
      </p>

      <form id="credentialRecoveryForm" class="form-stack">
        <div class="course-form-grid">
          <label>
            <span>Tipo de conta</span>
            <select name="targetType" id="credentialTarget">
              ${credentialTargetOptions(defaultTarget)}
            </select>
          </label>
          <label>
            <span>Modo</span>
            <select name="mode" id="credentialMode">
              <option value="missing" selected>Apenas contas sem palavra-passe</option>
              <option value="rotate">Substituir palavras-passe selecionadas</option>
            </select>
          </label>
        </div>

        <label class="credential-checkbox-line">
          <input type="checkbox" name="includeInactive">
          <span>Incluir contas inativas ou bloqueadas</span>
        </label>

        <div class="select-all-toolbar">
          <button class="button button-small button-secondary" type="button" data-select-credentials="all">Selecionar todos</button>
          <button class="button button-small button-secondary" type="button" data-select-credentials="none">Limpar seleção</button>
        </div>

        <div id="credentialCandidateList" class="credential-candidate-list">
          ${credentialCandidateListTemplate(defaultTarget)}
        </div>

        <div id="credentialRecoveryResult" class="credential-result" hidden></div>

        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Gerar palavras-passe</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#credentialTarget').addEventListener('change', async (event) => {
    const targetType = event.currentTarget.value;
    await ensureCredentialRecoveryData(targetType);
    overlay.querySelector('#credentialCandidateList').innerHTML = credentialCandidateListTemplate(targetType);
  });
  overlay.querySelectorAll('[data-select-credentials]').forEach((button) => {
    button.addEventListener('click', () => {
      const checked = button.dataset.selectCredentials === 'all';
      overlay.querySelectorAll('[name="credentialAccount"]').forEach((input) => {
        input.checked = checked;
      });
    });
  });
  overlay.querySelector('#credentialRecoveryForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const selected = [...form.querySelectorAll('[name="credentialAccount"]:checked')]
      .map((input) => input.value.split('|'));
    if (!selected.length) {
      showToast('Selecione pelo menos uma conta.', 'warning');
      return;
    }

    const mode = form.elements.mode.value;
    const message = mode === 'rotate'
      ? 'Isto vai substituir as palavras-passe atuais das contas selecionadas e encerrar as sessões abertas. Continuar?'
      : 'Gerar palavra-passe temporária apenas para contas selecionadas que ainda não possuem palavra-passe?';
    if (!confirmAdminAction(message)) return;

    const studentIds = selected.filter(([type]) => type === 'STUDENT').map(([, id]) => id);
    const adminIds = selected.filter(([type]) => type === 'ADMIN').map(([, id]) => id);
    setBusy(button, true, 'A gerar...');

    try {
      const result = await api.adminRestoreCredentials({
        targetType: form.elements.targetType.value,
        studentIds,
        adminIds,
        onlyMissingPassword: mode === 'missing',
        includeInactive: form.elements.includeInactive.checked
      });
      renderCredentialRecoveryResult(overlay, result.credentials || [], result.summary || {});
      showToast('Credenciais restauradas.', 'success');
      await refreshCredentialSources(form.elements.targetType.value);
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
  reportHeight();
}

async function ensureCredentialRecoveryData(targetType) {
  const target = String(targetType || '').toUpperCase();
  const promises = [];
  if ((target === 'STUDENTS' || target === 'ALL') && !state.students.length) {
    promises.push(api.adminStudents({ limit: 500 }, { force: true }).then((result) => {
      state.students = result.students || [];
    }));
  }
  if ((target === 'ADMINS' || target === 'ALL') && state.admin?.role === 'OWNER' && !state.staff.length) {
    promises.push(api.adminStaff({ force: true }).then((result) => {
      state.staff = result.staff || [];
      state.admin = result.currentAdmin || state.admin;
    }));
  }
  if (promises.length) {
    try {
      await Promise.all(promises);
    } catch (error) {
      handleAdminError(error);
    }
  }
}

async function refreshCredentialSources(targetType) {
  const target = String(targetType || '').toUpperCase();
  if (target === 'STUDENTS' || target === 'ALL') {
    const result = await api.adminStudents({ limit: 500 }, { force: true });
    state.students = result.students || [];
  }
  if ((target === 'ADMINS' || target === 'ALL') && state.admin?.role === 'OWNER') {
    const result = await api.adminStaff({ force: true });
    state.staff = result.staff || [];
    state.admin = result.currentAdmin || state.admin;
  }
}

function credentialTargetOptions(selected) {
  const options = [
    ['STUDENTS', 'Estudantes']
  ];
  if (state.admin?.role === 'OWNER') {
    options.push(['ADMINS', 'Staff administrativo'], ['ALL', 'Estudantes e staff']);
  }
  return options.map(([value, label]) => studentFilterOption(value, label, selected)).join('');
}

function credentialCandidates(targetType) {
  const target = String(targetType || 'STUDENTS').toUpperCase();
  const students = target === 'ADMINS' ? [] : state.students.map(({ student }) => ({
    type: 'STUDENT',
    id: student.studentId,
    title: student.fullName,
    meta: `${studentPublicIdLabel(student.publicStudentId)} - ${student.email}`,
    status: student.status
  }));
  const admins = target === 'STUDENTS' ? [] : state.staff.map((admin) => ({
    type: 'ADMIN',
    id: admin.adminId,
    title: admin.fullName,
    meta: `${admin.role} - ${admin.email}`,
    status: admin.status
  }));
  return [...students, ...admins];
}

function credentialCandidateListTemplate(targetType) {
  const candidates = credentialCandidates(targetType);
  if (!candidates.length) {
    return '<p class="empty-note">Nenhuma conta disponível para este filtro.</p>';
  }
  return candidates.map((item) => `
    <label class="credential-candidate">
      <input type="checkbox" name="credentialAccount" value="${escapeHtml(item.type)}|${escapeHtml(item.id)}" checked>
      <span>
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml(item.meta)}</small>
      </span>
      <em class="status-pill ${statusClass(item.status)}">${statusLabel(item.status)}</em>
    </label>
  `).join('');
}

function renderCredentialRecoveryResult(overlay, credentials, summary) {
  const resultBox = overlay.querySelector('#credentialRecoveryResult');
  resultBox.hidden = false;
  resultBox.innerHTML = `
    <div class="credential-result-heading">
      <div>
        <span>Resultado</span>
        <strong>${Number(summary.total || credentials.length)} palavra(s)-passe temporária(s) criada(s)</strong>
      </div>
      <div class="admin-heading-actions">
        <button class="button button-small button-secondary" type="button" data-copy-credentials>Copiar lista</button>
        <button class="button button-small button-secondary" type="button" data-download-credentials>Exportar CSV</button>
      </div>
    </div>
    ${credentials.length ? `
      <div class="credential-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>Tipo</th>
              <th>Nome</th>
              <th>Email</th>
              <th>ID</th>
              <th>Palavra-passe temporária</th>
            </tr>
          </thead>
          <tbody>
            ${credentials.map((item) => `
              <tr>
                <td>${item.type === 'ADMIN' ? 'Staff' : 'Estudante'}</td>
                <td>${escapeHtml(item.fullName || '')}</td>
                <td>${escapeHtml(item.email || '')}</td>
                <td>${escapeHtml(item.type === 'ADMIN'
                  ? (item.publicId || item.id || '')
                  : studentPublicIdLabel(item.publicId))}</td>
                <td><code>${escapeHtml(item.temporaryPassword || '')}</code></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : '<p class="empty-note">Nenhuma conta precisava de uma nova palavra-passe neste modo.</p>'}
  `;
  resultBox.querySelector('[data-copy-credentials]')?.addEventListener('click', () => {
    copyText(credentialsCsv(credentials, '\t'), 'Lista de credenciais copiada.');
  });
  resultBox.querySelector('[data-download-credentials]')?.addEventListener('click', () => {
    downloadCredentialsCsv(credentials);
  });
}

function credentialsCsv(credentials, separator = ',') {
  const rows = [
    ['tipo', 'nome', 'email', 'id', 'senha_temporaria'],
    ...credentials.map((item) => [
      item.type === 'ADMIN' ? 'staff' : 'estudante',
      item.fullName || '',
      item.email || '',
      item.type === 'ADMIN' ? (item.publicId || item.id || '') : studentPublicIdLabel(item.publicId),
      item.temporaryPassword || ''
    ])
  ];
  return rows.map((row) => row.map((cell) => {
    const value = String(cell).replace(/"/g, '""');
    return `"${value}"`;
  }).join(separator)).join('\n');
}

function downloadCredentialsCsv(credentials) {
  const blob = new Blob([credentialsCsv(credentials)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `credenciais-temporarias-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function renderAdminProfile() {
  const main = document.querySelector('#adminMain');
  const admin = state.admin || {};

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Perfil administrativo</p>
        <h1>${escapeHtml(admin.fullName || 'Administrador')}</h1>
      </div>
    </div>

    <section class="admin-profile-grid">
      <article class="profile-card">
        <div class="student-detail-header">
          <span class="student-avatar student-avatar-large">${escapeHtml(studentInitials(admin.fullName || admin.email))}</span>
          <div>
            <span class="status-pill ${statusClass(admin.status)}">${statusLabel(admin.status)}</span>
            <h2>${escapeHtml(admin.fullName || '')}</h2>
            <p>${escapeHtml(admin.email || '')}</p>
          </div>
        </div>
        <dl class="student-detail-grid">
          <div><dt>ID</dt><dd>${escapeHtml(admin.adminId || '-')}</dd></div>
          <div><dt>Permissão</dt><dd>${escapeHtml(admin.role || '-')}</dd></div>
          <div><dt>Criado em</dt><dd>${escapeHtml(formatDate(admin.createdAt))}</dd></div>
          <div><dt>Atualizado em</dt><dd>${escapeHtml(formatDate(admin.updatedAt))}</dd></div>
        </dl>
      </article>

      <article class="profile-card">
        <div class="profile-section-heading">
          <div>
            <p class="eyebrow">Sessão</p>
            <h2>Acesso atual</h2>
          </div>
        </div>
        <p class="profile-security-note">Use sair quando terminar a gestão administrativa neste dispositivo.</p>
        <button class="button button-secondary" id="adminProfileLogout" type="button">Sair da conta</button>
      </article>
    </section>
  `;

  document.querySelector('#adminProfileLogout').addEventListener('click', logout);
  reportHeight();
}

async function loadCertifications(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar certificações...');
  }

  try {
    const [requestsResult, certificatesResult, coursesResult] = await Promise.all([
      api.adminCertificateRequests({
        status: state.certificateFilters.status,
        query: state.certificateFilters.query,
        limit: 300
      }, options),
      api.adminCertificates({
        status: state.certificateFilters.certificateStatus,
        query: state.certificateFilters.query,
        limit: 300
      }, options),
      api.adminCourses({ limit: 500 }, options)
    ]);
    state.certificateRequests = requestsResult.requests || [];
    state.certificates = certificatesResult.certificates || [];
    state.courses = coursesResult.courses || state.courses || [];
    const firstCourse = state.courses.find((item) => item.course?.status !== 'DELETED')?.course;
    state.selectedCourseId = state.selectedCourseId || firstCourse?.courseId || config.courseId;
    const settingsResult = await api.adminCertificateSettings(state.selectedCourseId, options);
    state.certificateSettings = settingsResult.settings || {};
    renderCertifications();
  } catch (error) {
    if (options.silent) {
      console.warn('Falha ao atualizar certificações em segundo plano:', error);
      return;
    }
    handleAdminError(error);
  }
}

function renderCertifications() {
  const main = document.querySelector('#adminMain');
  const settings = state.certificateSettings || {};
  const requests = state.certificateRequests || [];
  const certificates = state.certificates || [];
  const pendingCount = requests.filter((item) => ['REQUESTED', 'PAYMENT_SUBMITTED'].includes(item.status)).length;
  const approvedCount = requests.filter((item) => item.status === 'APPROVED').length;
  const blockedCount = certificates.filter((item) => item.status === 'BLOCKED').length;
  const deletedCount = certificates.filter((item) => item.status === 'DELETED').length;
  const rejectedCount = requests.filter((item) => item.status === 'REJECTED').length;

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Certificações</p>
        <h1>Certificados e pedidos profissionais</h1>
      </div>
      <div class="certificate-admin-toolbar">
        <label class="certificate-global-search">
          <span class="sr-only">Pesquisar certificados</span>
          <input id="certificateSearch" type="search" value="${escapeHtml(state.certificateFilters.query)}"
            placeholder="Nome, email, ID, curso ou certificado">
        </label>
        <button class="button button-secondary" id="refreshCertificateData" type="button">Atualizar dados</button>
        <button class="button button-primary" id="refreshCertificateFormat" type="button">Atualizar formato</button>
      </div>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de certificações">
      <article class="insight-card">
        <img src="${iconUrl('time', goldIcon)}" alt="">
        <div><span>Pendentes</span><strong>${pendingCount}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('ok', goldIcon)}" alt="">
        <div><span>Emitidos</span><strong>${certificates.length || approvedCount}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('lock', goldIcon)}" alt="">
        <div><span>Bloqueados</span><strong>${blockedCount}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('cancel', goldIcon)}" alt="">
        <div><span>Rejeitados/apagados</span><strong>${rejectedCount + deletedCount}</strong></div>
      </article>
    </section>

    <section class="admin-content-panel certificate-register-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Conquistas verificaveis</p>
          <h2>Certificados</h2>
        </div>
        <span>${certificates.length} registos</span>
      </div>
      <section class="admin-filter-bar certificate-filter-bar">
        <label>
          <span>Acesso</span>
          <select id="certificateAccessStatusFilter">
            ${studentFilterOption('ACTIVE', 'Ativos', state.certificateFilters.certificateStatus)}
            ${studentFilterOption('ISSUED', 'Emitidos', state.certificateFilters.certificateStatus)}
            ${studentFilterOption('BLOCKED', 'Bloqueados', state.certificateFilters.certificateStatus)}
            ${studentFilterOption('DELETED', 'Apagados', state.certificateFilters.certificateStatus)}
            ${studentFilterOption('ALL', 'Todos', state.certificateFilters.certificateStatus)}
          </select>
        </label>
      </section>
      <div class="certificate-record-table">
        <div class="certificate-record-row certificate-record-head">
          <span>Código</span>
          <span>Formando</span>
          <span>Curso</span>
          <span>Resultado</span>
          <span>Emissão</span>
          <span>Gerações PDF</span>
          <span>Ações</span>
        </div>
        ${certificates.length ? certificates.map(adminCertificateRowTemplate).join('') : `
          <div class="student-empty-state">Sem certificados para os filtros atuais.</div>
        `}
      </div>
    </section>

    <section class="admin-content-panel certificate-requests-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Pagamentos e libertações</p>
          <h2>Pedidos de certificado profissional</h2>
        </div>
        <span>${requests.length} pedidos</span>
      </div>
      <section class="admin-filter-bar certificate-filter-bar">
        <label>
          <span>Estado do pedido</span>
          <select id="certificateStatusFilter">
            ${studentFilterOption('ALL', 'Todos', state.certificateFilters.status)}
            ${studentFilterOption('REQUESTED', 'Solicitados', state.certificateFilters.status)}
            ${studentFilterOption('PAYMENT_SUBMITTED', 'Prontos para revisão', state.certificateFilters.status)}
            ${studentFilterOption('APPROVED', 'Aprovados', state.certificateFilters.status)}
            ${studentFilterOption('REJECTED', 'Rejeitados', state.certificateFilters.status)}
          </select>
        </label>
      </section>
      <div class="certificate-request-list">
        ${requests.length ? requests.map(certificateRequestCardTemplate).join('') : `
          <div class="student-empty-state">Sem pedidos para os filtros atuais.</div>
        `}
      </div>
    </section>

    <section class="certificate-admin-grid certificate-model-grid">
      <article class="admin-content-panel">
        <div class="course-section-heading">
          <div>
            <p class="eyebrow">Modelo e identidade</p>
            <h2>Configuração do curso</h2>
          </div>
        </div>
        <form id="certificateSettingsForm" class="form-stack">
          <label>
            <span>Curso</span>
            <select id="certificateCourse" name="courseId">
              ${certificateCourseOptions()}
            </select>
          </label>
          ${certificateProfileFormFields(settings.certificateProfile || {})}
          <div class="dialog-actions">
            <button class="button button-secondary" type="reset">Cancelar alterações</button>
            <button class="button button-primary" type="submit">Guardar identidade do curso</button>
          </div>
        </form>
      </article>

      <article class="admin-content-panel certificate-model-preview-panel">
        <div class="course-section-heading">
          <div>
            <p class="eyebrow">Dois modelos disponíveis</p>
            <h2>Pré-visualização do certificado profissional</h2>
          </div>
        </div>
        <div class="certificate-preview-sheet is-professional certificate-admin-mini-preview">
          ${adminCertificateThumbnailTemplate({
            certificateType: 'PROFESSIONAL',
            certificateNumber: 'LSS-2026-F5B649DE76',
            verificationCode: 'LSS2026F5B649DE76',
            studentName: 'Nome do Formando',
            courseTitle: (state.courses || []).find(({ course }) => course.courseId === state.selectedCourseId)?.course?.title || 'Curso profissional',
            contentSummary: settings.certificateProfile?.certifiedContents || '',
            templateSnapshot: { profile: settings.certificateProfile || {} },
            issueDate: new Date().toISOString(),
            finalScore: 100
          })}
        </div>
        <p class="empty-note">A pré-visualização acompanha o modelo atual. Use “Atualizar formato” para reprocessar certificados emitidos quando alterar a identidade ou os conteúdos.</p>
      </article>
    </section>
  `;

  document.querySelector('#certificateCourse').addEventListener('change', async (event) => {
    state.selectedCourseId = event.currentTarget.value;
    const settingsResult = await api.adminCertificateSettings(state.selectedCourseId, { force: true });
    state.certificateSettings = settingsResult.settings || {};
    renderCertifications();
  });
  document.querySelector('#certificateSettingsForm').addEventListener('submit', saveCertificateSettings);
  root.querySelectorAll('[data-certificate-asset]').forEach((input) => {
    input.addEventListener('change', uploadCertificateAsset);
  });
  root.querySelector('[data-use-standard-certificate-logo]')?.addEventListener('click', useStandardCertificateLogo);
  document.querySelector('#certificateStatusFilter').addEventListener('change', (event) => {
    state.certificateFilters.status = event.currentTarget.value;
    loadCertifications();
  });
  document.querySelector('#certificateAccessStatusFilter').addEventListener('change', (event) => {
    state.certificateFilters.certificateStatus = event.currentTarget.value;
    loadCertifications();
  });
  document.querySelector('#certificateSearch').addEventListener('input', (event) => {
    state.certificateFilters.query = event.currentTarget.value;
    loadCertifications({ silent: true }).then(renderCertifications);
  });
  document.querySelector('#refreshCertificateData').addEventListener('click', () => loadCertifications({ force: true }));
  document.querySelector('#refreshCertificateFormat').addEventListener('click', refreshCertificateFormatAll);
  root.querySelectorAll('[data-review-certificate-request]').forEach((button) => {
    button.addEventListener('click', () => reviewCertificateRequest(
      button.dataset.reviewCertificateRequest,
      button.dataset.decision
    ));
  });
  root.querySelectorAll('[data-delete-certificate-request]').forEach((button) => {
    button.addEventListener('click', () => deleteCertificateRequest(button.dataset.deleteCertificateRequest));
  });
  root.querySelectorAll('[data-open-admin-certificate]').forEach((button) => {
    button.addEventListener('click', () => openAdminCertificatePreview(certificateForAdminButton(button)));
  });
  root.querySelectorAll('[data-download-admin-certificate]').forEach((button) => {
    button.addEventListener('click', () => downloadAdminCertificate(certificateForAdminButton(button)));
  });
  root.querySelectorAll('[data-set-certificate-status]').forEach((button) => {
    button.addEventListener('click', () => setCertificateStatusFromButton(button));
  });
  root.querySelectorAll('[data-refresh-certificate-format]').forEach((button) => {
    button.addEventListener('click', () => refreshCertificateFormatFromButton(button));
  });
  root.querySelectorAll('[data-delete-certificate]').forEach((button) => {
    button.addEventListener('click', () => deleteCertificateFromButton(button));
  });
  reportHeight();
}

function certificateCourseOptions() {
  const courses = state.courses || [];
  return courses.map(({ course }) => `
    <option value="${escapeHtml(course.courseId)}" ${course.courseId === state.selectedCourseId ? 'selected' : ''}>
      ${escapeHtml(course.title || course.courseCode || course.courseId)}
    </option>
  `).join('');
}

function certificateProfileFormFields(profile = {}) {
  const assets = profile.assets || {};
  const standardLogoUrl = brandLogoUrl();
  return `
    <div class="certificate-template-form-grid">
      <label>
        <span>Entidade emissora</span>
        <input name="issuerName" value="${escapeHtml(profile.issuerName || 'LMTWEBNAIRS')}">
      </label>
      <label>
        <span>Título do certificado</span>
        <input name="certificateTitle" value="${escapeHtml(profile.certificateTitle || 'Certificado de Qualificação')}">
      </label>
      <label>
        <span>Tipo de qualificação</span>
        <input name="qualificationType" value="${escapeHtml(profile.qualificationType || 'Qualificação profissional')}">
      </label>
      <label>
        <span>Local de emissão</span>
        <input name="issueLocation" value="${escapeHtml(profile.issueLocation || 'Cidade de Maputo, Moçambique')}">
      </label>
      <label>
        <span>Nome do responsável académico</span>
        <input name="directorName" value="${escapeHtml(profile.directorName || 'Direção Académica')}">
      </label>
      <label>
        <span>Cargo do responsável académico</span>
        <input name="directorTitle" value="${escapeHtml(profile.directorTitle || 'Diretor Académico')}">
      </label>
      <label>
        <span>Nome do coordenador</span>
        <input name="coordinatorName" value="${escapeHtml(profile.coordinatorName || 'Coordenação do Programa')}">
      </label>
      <label>
        <span>Cargo do coordenador</span>
        <input name="coordinatorTitle" value="${escapeHtml(profile.coordinatorTitle || 'Coordenador do Programa')}">
      </label>
      <label class="form-span-2">
        <span>Identificação do produto</span>
        <input name="productCredit" value="${escapeHtml(profile.productCredit || '')}">
      </label>
      <label class="form-span-2">
        <span>Conteúdos certificados</span>
        <textarea name="certifiedContents" rows="5" placeholder="Um conteúdo por linha">${escapeHtml(profile.certifiedContents || '')}</textarea>
      </label>
    </div>
    <div class="certificate-payment-policy">
      <div class="profile-section-heading">
        <h3>Política de impressão</h3>
        <p>Defina se o certificado profissional exige pagamento e aprovação administrativa.</p>
      </div>
      <div class="certificate-template-form-grid">
        <label>
        <span>Acesso à impressão</span>
          <select name="printAccess">
            ${studentFilterOption('free', 'Impressão livre', profile.printAccess || 'paid')}
            ${studentFilterOption('paid', 'Pagamento obrigatório', profile.printAccess || 'paid')}
            ${studentFilterOption('blocked', 'Bloqueado por padrão', profile.printAccess || 'paid')}
          </select>
        </label>
        <label>
          <span>Valor</span>
          <input name="printFee" value="${escapeHtml(profile.printFee || '')}" placeholder="1000">
        </label>
        <label>
          <span>Moeda</span>
          <select name="printCurrency">
            ${studentFilterOption('MZN', 'MZN - Metical', profile.printCurrency || 'MZN')}
            ${studentFilterOption('USD', 'USD - Dólar', profile.printCurrency || 'MZN')}
            ${studentFilterOption('EUR', 'EUR - Euro', profile.printCurrency || 'MZN')}
          </select>
        </label>
        <label>
          <span>Titular da conta</span>
          <input name="paymentAccountName" value="${escapeHtml(profile.paymentAccountName || '')}">
        </label>
        <label class="form-span-2">
          <span>Número da conta ou carteira móvel</span>
          <input name="paymentAccountNumber" value="${escapeHtml(profile.paymentAccountNumber || '')}">
        </label>
        <label class="form-span-2">
          <span>Instruções de pagamento</span>
          <textarea name="paymentInstructions" rows="3">${escapeHtml(profile.paymentInstructions || '')}</textarea>
        </label>
      </div>
    </div>
    <div class="certificate-assets-heading">
      <strong>Elementos gráficos opcionais</strong>
      <small>PNG, JPEG ou WebP, até 3 MB por ficheiro. O upload passa pelo backend administrativo.</small>
    </div>
    <div class="certificate-standard-logo">
      ${standardLogoUrl
        ? `<img src="${escapeHtml(standardLogoUrl)}" alt="Logótipo padrão da instituição">`
        : '<span class="certificate-standard-logo-placeholder">Marca não definida</span>'}
      <span class="certificate-standard-logo-copy">
        <strong>Logótipo padrão da instituição</strong>
        <small>A marca definida na área “Marca” é aplicada automaticamente. O ficheiro específico abaixo substitui-a apenas nos certificados deste curso.</small>
      </span>
      <button class="button button-small button-secondary" type="button" data-use-standard-certificate-logo>
        Usar logótipo padrão
      </button>
    </div>
    <div class="certificate-asset-grid">
      ${certificateAssetField('logoUrl', 'Logótipo específico do certificado', assets.logoUrl)}
      ${certificateAssetField('productLogoUrl', 'Logótipo do produto', assets.productLogoUrl)}
      ${certificateAssetField('directorSignatureUrl', 'Assinatura académica', assets.directorSignatureUrl)}
      ${certificateAssetField('academicStampUrl', 'Carimbo académico', assets.academicStampUrl)}
      ${certificateAssetField('coordinatorSignatureUrl', 'Assinatura da coordenação', assets.coordinatorSignatureUrl)}
      ${certificateAssetField('institutionalSealUrl', 'Selo institucional', assets.institutionalSealUrl)}
    </div>
  `;
}

function certificateAssetField(name, label, value = '') {
  return `
    <label class="asset-upload-card">
      <span>${escapeHtml(label)}</span>
      <img src="${escapeHtml(value || '')}" alt="" ${value ? '' : 'hidden'}>
      <input type="hidden" name="${escapeHtml(name)}" value="${escapeHtml(value || '')}">
      <input type="file" accept="image/png,image/jpeg,image/webp" data-certificate-asset="${escapeHtml(name)}">
    </label>
  `;
}

function adminCertificateThumbnailTemplate(certificate) {
  const profile = certificate.templateSnapshot?.profile || {};
  const assets = profile.assets || {};
  const logoUrl = assets.logoUrl || brandLogoUrl();
  const topics = String(certificate.contentSummary || '')
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 3);
  return `
    <div class="certificate-thumbnail">
      <div class="certificate-thumbnail-left">
        ${logoUrl ? `<img src="${escapeHtml(logoUrl)}" alt="Logótipo institucional">` : '<span>Marca institucional</span>'}
        <strong>${escapeHtml(profile.issuerName || config.organizationName || 'Summer School')}</strong>
        <h3>${escapeHtml(profile.certificateTitle || 'Certificado de Qualificação')}</h3>
        <small>${escapeHtml(certificate.certificateNumber || '')}</small>
      </div>
      <div class="certificate-thumbnail-right">
        <p>O presente documento certifica que</p>
        <h2>${escapeHtml(certificate.studentName || 'Nome do Formando')}</h2>
        <strong>${escapeHtml(certificate.courseTitle || 'Curso profissional')}</strong>
        <ul>
          ${topics.map((topic) => `<li>${escapeHtml(topic)}</li>`).join('')}
        </ul>
      </div>
    </div>
  `;
}

function adminCertificateRowTemplate(certificate) {
  const deleted = certificate.status === 'DELETED';
  const blocked = certificate.status === 'BLOCKED';
  const accessLabel = deleted ? 'Atribuir novamente' : (blocked ? 'Liberar acesso' : 'Remover acesso');
  const nextStatus = blocked || deleted ? 'ISSUED' : 'BLOCKED';
  const dataset = adminCertificateActionDataset(certificate);
  const certificateType = certificate.certificateType === 'PROFESSIONAL' ? 'Profissional' : 'Participação';
  const downloads = Number(certificate.downloadCount || 0);
  const maxDownloads = certificate.maxDownloads || (certificate.certificateType === 'PROFESSIONAL' ? 5 : 'Livre');
  return `
    <div class="certificate-record-row ${deleted ? 'is-deleted' : ''} ${blocked ? 'is-blocked' : ''}">
      <div>
        <code>${escapeHtml(adminCertificateDisplayNumber(certificate) || certificate.certificateId)}</code>
        <span class="status-pill ${statusClass(certificate.status)}">${statusLabel(certificate.status)}</span>
        <small>${escapeHtml(certificateType)}</small>
      </div>
      <div>
        <strong>${escapeHtml(certificate.studentName || 'Estudante')}</strong>
      </div>
      <div>${escapeHtml(certificate.courseTitle || certificate.courseId || 'Curso')}</div>
      <div>${certificate.finalScore == null || certificate.finalScore === '' ? '-' : `${escapeHtml(certificate.finalScore)}%`}</div>
      <div>${escapeHtml(formatDate(certificate.issueDate))}</div>
      <div><span class="certificate-generation-pill">${escapeHtml(downloads)} / ${escapeHtml(maxDownloads)}</span></div>
      <div class="certificate-record-actions">
        ${deleted ? '' : `
          <button class="button button-small button-secondary" type="button" data-open-admin-certificate ${dataset}>Visualizar</button>
          <button class="button button-small button-secondary" type="button" data-download-admin-certificate ${dataset}>Baixar</button>
          <button class="button button-small button-secondary" type="button" data-refresh-certificate-format ${dataset}>Atualizar</button>
        `}
        <button class="button button-small ${blocked || deleted ? 'button-primary' : 'button-secondary'}" type="button"
          data-set-certificate-status="${escapeHtml(nextStatus)}" ${dataset}>
          ${accessLabel}
        </button>
        ${deleted ? '' : `
          <button class="button button-small button-danger" type="button" data-delete-certificate ${dataset}>Apagar</button>
        `}
      </div>
      ${certificate.statusNote ? `<p class="certificate-policy-note">${escapeHtml(certificate.statusNote)}</p>` : ''}
    </div>
  `;
}

function adminCertificateCardTemplate(certificate) {
  const blocked = certificate.status === 'BLOCKED';
  const accessLabel = blocked ? 'Liberar acesso' : 'Remover acesso';
  const nextStatus = blocked ? 'ISSUED' : 'BLOCKED';
  const dataset = adminCertificateActionDataset(certificate);
  return `
    <article class="certificate-request-card certificate-issued-card ${blocked ? 'is-blocked' : ''}">
      <div class="certificate-issued-main">
        <span class="certificate-seal${brandLogoUrl() ? ' has-brand-logo' : ''}" aria-hidden="true">${brandLogoUrl() ? `<img src="${escapeHtml(brandLogoUrl())}" alt="">` : 'LSS'}</span>
        <div>
          <span class="status-pill ${statusClass(certificate.status)}">${statusLabel(certificate.status)}</span>
          <p class="eyebrow">${certificate.certificateType === 'PROFESSIONAL' ? 'Certificado profissional' : 'Certificado de Participação'}</p>
          <h3>${escapeHtml(certificate.courseTitle || certificate.courseId || 'Curso')}</h3>
          <p>${escapeHtml(certificate.studentName || 'Estudante')} &middot; ${escapeHtml(formatDate(certificate.issueDate))}</p>
          <code>${escapeHtml(adminCertificateDisplayNumber(certificate) || certificate.certificateId)}</code>
        </div>
      </div>
      ${certificate.statusNote ? `<p class="certificate-policy-note">${escapeHtml(certificate.statusNote)}</p>` : ''}
      <div class="admin-row-actions">
        <button class="button button-small button-secondary" type="button" data-open-admin-certificate ${dataset}>Ver</button>
        <button class="button button-small button-primary" type="button" data-download-admin-certificate ${dataset}>Baixar</button>
        <button class="button button-small ${blocked ? 'button-primary' : 'button-secondary'}" type="button"
          data-set-certificate-status="${escapeHtml(nextStatus)}" ${dataset}>
          ${accessLabel}
        </button>
        <button class="button button-small button-danger" type="button" data-delete-certificate ${dataset}>
          Apagar
        </button>
      </div>
    </article>
  `;
}

function adminCertificateActionDataset(certificate) {
  return `
    data-certificate-id="${escapeHtml(certificate.certificateId)}"
    data-certificate-number="${escapeHtml(certificate.certificateNumber || '')}"
    data-certificate-type="${escapeHtml(certificate.certificateType || '')}"
    data-student-name="${escapeHtml(certificate.studentName || '')}"
    data-course-title="${escapeHtml(certificate.courseTitle || '')}"
    data-issue-date="${escapeHtml(certificate.issueDate || '')}"
    data-final-score="${escapeHtml(certificate.finalScore == null ? '' : certificate.finalScore)}"
    data-verification-code="${escapeHtml(certificate.verificationCode || '')}"
    data-content-summary="${escapeHtml(certificate.contentSummary || '')}"
  `;
}

function certificateRequestCardTemplate(request) {
  const receipt = request.paymentReceiptUrl ? adminFileCardTemplate({
    fileName: request.paymentReceiptName || 'Comprovativo',
    driveUrl: request.paymentReceiptUrl,
    mimeType: request.paymentReceiptMimeType,
    uploadedAt: request.submittedAt
  }) : '<p class="empty-note">Sem comprovativo anexado. Em cursos com emissão livre, o pedido pode ser aprovado sem pagamento.</p>';
  const canReview = request.status === 'PAYMENT_SUBMITTED';
  const canDelete = ['REQUESTED', 'REJECTED'].includes(request.status)
    && !request.certificateId
    && !request.paymentReceiptUrl
    && !request.submittedAt;
  const certificateActions = request.certificateId ? `
    <button class="button button-small button-secondary" type="button"
      data-open-admin-certificate
      data-certificate-id="${escapeHtml(request.certificateId)}"
      data-certificate-number="${escapeHtml(request.certificateNumber || '')}"
      data-certificate-type="${escapeHtml(request.certificateType || 'PROFESSIONAL')}"
      data-student-name="${escapeHtml(request.studentName || '')}"
      data-course-title="${escapeHtml(request.courseTitle || '')}"
      data-issue-date="${escapeHtml(request.certificateIssueDate || '')}"
      data-final-score="${escapeHtml(request.certificateFinalScore == null ? '' : request.certificateFinalScore)}"
      data-verification-code="${escapeHtml(request.verificationCode || '')}"
      data-content-summary="${escapeHtml(request.contentSummary || '')}">
      Ver certificado
    </button>
    <button class="button button-small button-primary" type="button"
      data-download-admin-certificate
      data-certificate-id="${escapeHtml(request.certificateId)}"
      data-certificate-number="${escapeHtml(request.certificateNumber || '')}"
      data-certificate-type="${escapeHtml(request.certificateType || 'PROFESSIONAL')}"
      data-student-name="${escapeHtml(request.studentName || '')}"
      data-course-title="${escapeHtml(request.courseTitle || '')}">
      Baixar PDF
    </button>
  ` : '';

  return `
    <article class="certificate-request-card">
      <div>
        <span class="status-pill ${statusClass(request.status)}">${statusLabel(request.status)}</span>
        <h3>${escapeHtml(request.studentName || request.studentEmail || 'Estudante')}</h3>
        <p>${escapeHtml(request.courseTitle || request.courseId)} &middot; ${escapeHtml(request.requestId)}</p>
      </div>
      ${receipt}
      <div class="admin-row-actions">
        <button class="button button-small button-primary" type="button"
          data-review-certificate-request="${escapeHtml(request.requestId)}"
          data-decision="APPROVED" ${canReview ? '' : 'disabled'}>
          Aprovar
        </button>
        <button class="button button-small button-danger" type="button"
          data-review-certificate-request="${escapeHtml(request.requestId)}"
          data-decision="REJECTED" ${canReview ? '' : 'disabled'}>
          Rejeitar
        </button>
        ${certificateActions}
        ${canDelete ? `
          <button class="button button-small button-danger" type="button"
            data-delete-certificate-request="${escapeHtml(request.requestId)}">
            Apagar pedido
          </button>
        ` : ''}
      </div>
    </article>
  `;
}

function surveyAnswersTemplate(value = {}) {
  const entries = Object.entries(value || {});
  if (!entries.length) return '<p class="empty-note">Sem respostas de inquérito.</p>';
  return entries.map(([question, answer]) => `
    <div class="survey-answer-line">
      <strong>${escapeHtml(question)}</strong>
      <span>${escapeHtml(answer || 'Sem resposta')}</span>
    </div>
  `).join('');
}

function adminSurveyQuestionFields(questions = []) {
  const normalized = normalizeAdminSurveyQuestions(questions);
  return normalized.map((question, index) => `
    <article class="admin-survey-question-card" data-admin-survey-question="${index}">
      <label>
        <span>Pergunta ${index + 1}</span>
        <input name="surveyPrompt-${index}" value="${escapeHtml(question.prompt)}" required>
      </label>
      <label>
        <span>Opções (uma por linha)</span>
        <textarea name="surveyOptions-${index}" rows="4" required>${escapeHtml(question.options.join('\n'))}</textarea>
      </label>
    </article>
  `).join('');
}

function normalizeAdminSurveyQuestions(questions = []) {
  const fallback = [
    'Como avalia a qualidade geral do curso?',
    'A metodologia facilitou a sua aprendizagem?',
    'Os conteúdos foram relevantes para os seus objetivos?',
    'Como avalia os materiais disponibilizados?',
    'As atividades práticas ajudaram a consolidar o conhecimento?',
    'Como classifica o nível de dificuldade do curso?',
    'Como avalia o apoio recebido durante o curso?',
    'Como foi a experiencia de uso da plataforma?',
    'Pretende aplicar os conhecimentos aprendidos?',
    'Recomendaria este curso a outra pessoa?'
  ];
  const defaultOptions = ['Excelente', 'Bom', 'Regular', 'Precisa melhorar'];
  const source = Array.isArray(questions) && questions.length ? questions : fallback;
  return Array.from({ length: 10 }, (_, index) => {
    const item = source[index] || fallback[index] || '';
    if (typeof item === 'string') {
      return {
        id: `q${index + 1}`,
        prompt: item,
        options: defaultOptions
      };
    }
    return {
      id: item.id || `q${index + 1}`,
      prompt: item.prompt || item.question || fallback[index] || '',
      options: Array.isArray(item.options) && item.options.length ? item.options : defaultOptions
    };
  });
}

function surveyQuestionsFromSettingsForm(form) {
  return Array.from({ length: 10 }, (_, index) => {
    const prompt = form.querySelector(`[name="surveyPrompt-${index}"]`)?.value.trim() || '';
    const options = String(form.querySelector(`[name="surveyOptions-${index}"]`)?.value || '')
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean);
    return {
      id: `q${index + 1}`,
      prompt,
      options,
      required: true
    };
  }).filter((item) => item.prompt && item.options.length);
}

async function loadCertificateSurveys(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar inquéritos...');
  }
  try {
    const [result, responsesResult] = await Promise.all([
      api.adminCertificateSurveys(options),
      api.adminCertificateRequests({ status: 'ALL', query: '', limit: 300 }, options)
    ]);
    state.certificateSurveys = result.surveys || [];
    state.certificateSurveyResponses = (responsesResult.requests || [])
      .filter((request) => Object.keys(request.surveyAnswers || {}).length);
    renderCertificateSurveys();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderCertificateSurveys() {
  const main = document.querySelector('#adminMain');
  const surveys = state.certificateSurveys || [];
  const responses = state.certificateSurveyResponses || [];
  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Feedback pedagógico</p>
        <h1>Inquéritos por curso</h1>
        <p>Configure as perguntas apresentadas ao estudante antes do pedido do certificado profissional.</p>
      </div>
      <button class="button button-secondary" id="refreshSurveys" type="button">Atualizar lista</button>
    </div>

    <section class="admin-content-panel survey-admin-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Lista de inquéritos</p>
          <h2>Cursos configurados</h2>
        </div>
        <span>${surveys.length} registos</span>
      </div>
      <div class="survey-admin-list">
        ${surveys.length ? surveys.map(certificateSurveyRowTemplate).join('') : `
          <div class="student-empty-state">Ainda não existem cursos para configurar inquéritos.</div>
        `}
      </div>
    </section>

    <section class="admin-content-panel survey-admin-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Respostas recebidas</p>
          <h2>Feedback dos estudantes</h2>
        </div>
        <span>${responses.length} respostas</span>
      </div>
      <div class="survey-response-list">
        ${responses.length ? responses.map(certificateSurveyResponseTemplate).join('') : `
          <div class="student-empty-state">Ainda não existem respostas de inquéritos.</div>
        `}
      </div>
    </section>
  `;
  document.querySelector('#refreshSurveys')?.addEventListener('click', () => loadCertificateSurveys({ force: true }));
  root.querySelectorAll('[data-edit-certificate-survey]').forEach((button) => {
    button.addEventListener('click', () => openCertificateSurveyDialog(button.dataset.editCertificateSurvey));
  });
  reportHeight();
}

function certificateSurveyResponseTemplate(request) {
  return `
    <article class="survey-response-card">
      <header>
        <div>
          <p class="eyebrow">${escapeHtml(request.courseTitle || request.courseId || 'Curso')}</p>
          <h3>${escapeHtml(request.studentName || request.studentEmail || 'Estudante')}</h3>
        </div>
        <span class="status-pill ${statusClass(request.status)}">${statusLabel(request.status)}</span>
      </header>
      <div class="certificate-survey-preview">
        ${surveyAnswersTemplate(request.surveyAnswers)}
      </div>
    </article>
  `;
}

function certificateSurveyRowTemplate(item) {
  const course = item.course || {};
  return `
    <article class="survey-admin-row">
      <div>
        <span class="survey-row-icon">${escapeHtml(String(item.questionCount || 0).padStart(2, '0'))}</span>
      </div>
      <div>
        <p class="eyebrow">Inquérito de conclusão</p>
        <h3>${escapeHtml(course.title || course.courseCode || course.courseId || 'Curso')}</h3>
        <p>${escapeHtml(item.congratulationsMessage || 'Mensagem de conclusão ainda não personalizada.')}</p>
      </div>
      <dl>
        <div><dt>Perguntas</dt><dd>${escapeHtml(item.questionCount || 0)}</dd></div>
        <div><dt>Atualizado</dt><dd>${escapeHtml(formatDate(item.updatedAt))}</dd></div>
      </dl>
      <button class="button button-secondary" type="button" data-edit-certificate-survey="${escapeHtml(course.courseId)}">
        Abrir editor
      </button>
    </article>
  `;
}

function openCertificateSurveyDialog(courseId) {
  const item = (state.certificateSurveys || []).find((survey) => survey.course?.courseId === courseId);
  if (!item) return;
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card survey-editor-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <div class="dialog-heading">
        <p class="eyebrow">Inquérito do curso</p>
        <h2>${escapeHtml(item.course?.title || 'Curso')}</h2>
      </div>
      <form id="certificateSurveyForm" class="form-stack">
        <input type="hidden" name="courseId" value="${escapeHtml(item.course?.courseId || '')}">
        <label>
          <span>Mensagem de parabens</span>
          <textarea name="congratulationsMessage" rows="3">${escapeHtml(item.congratulationsMessage || '')}</textarea>
        </label>
        <div class="certificate-survey-builder">
          ${adminSurveyQuestionFields(item.surveyQuestions || [])}
        </div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-close-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar inquérito</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('#certificateSurveyForm').addEventListener('submit', saveCertificateSurvey);
  reportHeight();
}

async function saveCertificateSurvey(event) {
  event.preventDefault();
  if (!confirmAdminAction('Deseja guardar este inquérito?')) return;
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  setBusy(button, true, 'A guardar...');
  try {
    await api.adminSaveCertificateSurvey({
      courseId: values.get('courseId'),
      congratulationsMessage: values.get('congratulationsMessage'),
      surveyQuestions: surveyQuestionsFromSettingsForm(form)
    });
    showToast('Inquérito guardado.', 'success');
    form.closest('.dialog-overlay')?.remove();
    await loadCertificateSurveys({ force: true });
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function saveCertificateSettings(event) {
  event.preventDefault();
  if (!confirmAdminAction('Deseja guardar a configuração de certificações deste curso?')) return;
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  setBusy(button, true, 'A guardar...');
  try {
    const profile = certificateProfileFromForm(form);
    const result = await api.adminSaveCertificateSettings({
      courseId: values.get('courseId'),
      certificateProfile: profile,
      professionalPrice: profile.printFee,
      paymentInstructions: profile.paymentInstructions,
      professionalPreviewUrl: profile.verificationBaseUrl
    });
    state.certificateSettings = result.settings || {};
    showToast('Configuração de certificações guardada.', 'success');
    renderCertifications();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

function certificateProfileFromForm(form) {
  const values = new FormData(form);
  return {
    issuerName: values.get('issuerName'),
    certificateTitle: values.get('certificateTitle'),
    qualificationType: values.get('qualificationType'),
    issueLocation: values.get('issueLocation'),
    directorName: values.get('directorName'),
    directorTitle: values.get('directorTitle'),
    coordinatorName: values.get('coordinatorName'),
    coordinatorTitle: values.get('coordinatorTitle'),
    productCredit: values.get('productCredit'),
    certifiedContents: values.get('certifiedContents'),
    printAccess: values.get('printAccess'),
    printFee: values.get('printFee'),
    printCurrency: values.get('printCurrency'),
    paymentAccountName: values.get('paymentAccountName'),
    paymentAccountNumber: values.get('paymentAccountNumber'),
    paymentInstructions: values.get('paymentInstructions'),
    verificationBaseUrl: values.get('professionalPreviewUrl') || '',
    assets: {
      logoUrl: values.get('logoUrl'),
      productLogoUrl: values.get('productLogoUrl'),
      directorSignatureUrl: values.get('directorSignatureUrl'),
      academicStampUrl: values.get('academicStampUrl'),
      coordinatorSignatureUrl: values.get('coordinatorSignatureUrl'),
      institutionalSealUrl: values.get('institutionalSealUrl')
    }
  };
}

async function uploadCertificateAsset(event) {
  const input = event.currentTarget;
  const file = input.files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    showToast('Use PNG, JPEG ou WebP.', 'error');
    input.value = '';
    return;
  }
  if (file.size > 3 * 1024 * 1024) {
    showToast('O ficheiro deve ter até 3 MB.', 'error');
    input.value = '';
    return;
  }
  const dataUrl = await fileToDataUrl(file);
  const assetKey = input.dataset.certificateAsset;
  input.disabled = true;
  try {
    const result = await api.adminUploadCertificateAsset({
      courseId: state.selectedCourseId,
      assetKey,
      fileName: file.name,
      mimeType: file.type,
      dataUrl
    });
    const card = input.closest('.asset-upload-card');
    const preview = card?.querySelector('img');
    const hidden = card?.querySelector(`input[type="hidden"][name="${assetKey}"]`);
    if (preview) {
      preview.src = result.assetUrl || dataUrl;
      preview.hidden = false;
    }
    if (hidden) hidden.value = result.assetUrl || dataUrl;
    showToast(result.storageSaved ? 'Asset carregado no Supabase Storage.' : 'Asset preparado no backend administrativo.', 'success');
  } catch (error) {
    handleAdminError(error);
  } finally {
    input.disabled = false;
  }
}

function useStandardCertificateLogo() {
  const form = document.querySelector('#certificateSettingsForm');
  const input = form?.querySelector('[data-certificate-asset="logoUrl"]');
  const card = input?.closest('.asset-upload-card');
  const preview = card?.querySelector('img');
  const hidden = card?.querySelector('input[type="hidden"][name="logoUrl"]');
  if (!input || !hidden) return;
  input.value = '';
  hidden.value = '';
  if (preview) {
    preview.src = '';
    preview.hidden = true;
  }
  showToast('O logótipo padrão será aplicado depois de guardar as alterações.', 'success');
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function reviewCertificateRequest(requestId, decision) {
  const label = decision === 'APPROVED' ? 'aprovar' : 'rejeitar';
  if (!confirmAdminAction(`Deseja ${label} este pedido de certificado profissional?`)) return;
  const adminNotes = window.prompt('Observações administrativas (opcional):', '') || '';
  try {
    await api.adminReviewCertificateRequest({ requestId, decision, adminNotes });
    showToast('Pedido de certificado atualizado.', 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  }
}

async function deleteCertificateRequest(requestId) {
  if (!confirmAdminAction('Deseja apagar definitivamente este pedido sem comprovativo? Esta ação não pode ser anulada.')) return;
  try {
    await api.adminDeleteCertificateRequest(requestId);
    showToast('Pedido de certificado apagado.', 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  }
}

function certificateFromDataset(dataset = {}) {
  return {
    certificateId: dataset.certificateId || '',
    certificateNumber: dataset.certificateNumber || '',
    certificateType: dataset.certificateType || 'SIMPLE',
    studentName: dataset.studentName || '',
    courseTitle: dataset.courseTitle || '',
    issueDate: dataset.issueDate || '',
    finalScore: dataset.finalScore || '',
    verificationCode: dataset.verificationCode || '',
    contentSummary: dataset.contentSummary || ''
  };
}

function certificateForAdminButton(button) {
  const fallback = certificateFromDataset(button.dataset);
  return (state.certificates || []).find((item) => item.certificateId === fallback.certificateId) || fallback;
}

function adminCertificateDisplayNumber(certificate = {}) {
  return String(certificate.certificateNumber || '')
    .replace(/SIMPLE/gi, 'PART')
    .replace(/PARTICIPATION/gi, 'PART');
}

function openAdminCertificatePreview(certificate) {
  if (!certificate?.certificateId) return;
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card certificate-preview-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <div class="certificate-preview-sheet ${certificate.certificateType === 'PROFESSIONAL' ? 'is-professional' : ''}">
        ${adminCertificatePreviewTemplate(certificate)}
      </div>
      <div class="dialog-actions">
        <button class="button button-secondary" type="button" data-close-dialog>Fechar</button>
        <button class="button button-primary" type="button" data-download-admin-certificate>
          Baixar PDF oficial
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('[data-download-admin-certificate]')?.addEventListener('click', () => downloadAdminCertificate(certificate, overlay));
  reportHeight();
}

function adminCertificatePreviewTemplate(certificate) {
  const isProfessional = certificate.certificateType === 'PROFESSIONAL';
  const title = isProfessional ? 'CERTIFICADO PROFISSIONAL DE CONCLUSÃO' : 'CERTIFICADO DE PARTICIPAÇÃO';
  const profile = certificate.templateSnapshot?.profile || {};
  const assets = profile.assets || {};
  const logoUrl = assets.logoUrl || brandLogoUrl();
  const summary = String(certificate.contentSummary || '')
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 6);
  const professionalHours = Number(certificate.templateSnapshot?.courseHours || 30);
  const finalScoreLabel = certificate.finalScore == null ? '--' : `${certificate.finalScore}%`;
  if (isProfessional) {
    return `
      <div class="certificate-preview-inner certificate-document certificate-document-professional">
        <div class="certificate-professional-layout">
          <section class="certificate-professional-left">
            ${logoUrl ? `<img class="certificate-logo-image" src="${escapeHtml(logoUrl)}" alt="Logótipo institucional">` : '<div class="certificate-logo-placeholder">Logótipo institucional</div>'}
            <p class="certificate-institution">${escapeHtml(profile.issuerName || config.organizationName || 'LMTWEBNAIRS Summer School')}</p>
            <p class="certificate-brand-subtitle">FORMAÇÃO TÉCNICA APLICADA</p>
            <span class="certificate-column-divider" aria-hidden="true"></span>
            <h1>${escapeHtml(profile.certificateTitle || 'Certificado de Qualificação')}</h1>
            <p>${escapeHtml(profile.qualificationType || 'sobre o aumento da qualificação profissional')}</p>
            <strong>${escapeHtml(adminCertificateDisplayNumber(certificate) || certificate.certificateId)}</strong>
            <span>Documento de qualificação</span>
            <small>Número de registo</small>
            <strong>${escapeHtml(certificate.verificationCode || '')}</strong>
            <div class="certificate-place-date">
              <b>${escapeHtml(profile.issueLocation || 'Cidade de Maputo, Moçambique')}</b>
              <span>${escapeHtml(formatDate(certificate.issueDate))}</span>
            </div>
            <div class="certificate-signature-block">
              ${assets.academicStampUrl ? `<img class="certificate-stamp-image" src="${escapeHtml(assets.academicStampUrl)}" alt="">` : ''}
              ${assets.directorSignatureUrl ? `<img class="certificate-signature-image" src="${escapeHtml(assets.directorSignatureUrl)}" alt="">` : ''}
              <span></span>
              <b>${escapeHtml(profile.directorName || 'Diretor Académico')}</b>
              <small>${escapeHtml(profile.directorTitle || 'LMTWEBNAIRS')}</small>
            </div>
          </section>
          <section class="certificate-professional-right">
            <p class="certificate-preview-lead">O presente documento certifica que</p>
            <h2>${escapeHtml(certificate.studentName || 'Nome do Formando')}</h2>
            <p>concluiu com sucesso o programa de aumento de qualificação profissional na ${escapeHtml(profile.issuerName || config.organizationName || 'Summer School')}</p>
            <span class="certificate-course-label">CURSO / PROGRAMA</span>
            <h3>${escapeHtml(certificate.courseTitle || 'Curso profissional')}</h3>
            <p>demonstrando aproveitamento satisfatório em atividades académicas, estudos de caso, discussões técnicas e avaliação final.</p>
            ${summary.length ? `
              <div class="certificate-content-summary">
                <strong>O programa abordou:</strong>
                <ul>${summary.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>
              </div>
            ` : ''}
            <div class="certificate-professional-metrics">
              <strong>Carga horária: ${escapeHtml(professionalHours)} horas</strong>
              <strong>Resultado final: ${escapeHtml(finalScoreLabel)}</strong>
            </div>
            <div class="certificate-professional-footer">
              <div class="certificate-verification-compact">
                <span class="certificate-qr-placeholder" aria-hidden="true">QR</span>
                <small>Verifique o certificado<b>${escapeHtml(certificate.verificationCode || '')}</b></small>
              </div>
              <div class="certificate-signature-block">
                ${assets.coordinatorSignatureUrl ? `<img class="certificate-signature-image" src="${escapeHtml(assets.coordinatorSignatureUrl)}" alt="">` : ''}
                <span></span>
                <b>${escapeHtml(profile.coordinatorName || 'Coordenador do Programa')}</b>
                <small>${escapeHtml(profile.coordinatorTitle || 'LMTWEBNAIRS')}</small>
              </div>
              ${assets.institutionalSealUrl ? `<img class="certificate-seal-image" src="${escapeHtml(assets.institutionalSealUrl)}" alt="">` : '<div class="certificate-preview-seal">L</div>'}
              <div class="certificate-product-credit">
                ${assets.productLogoUrl ? `<img src="${escapeHtml(assets.productLogoUrl)}" alt="Marca do produto">` : ''}
                <small>${escapeHtml(profile.productCredit || '')}</small>
              </div>
            </div>
          </section>
        </div>
      </div>
    `;
  }
  return `
    <div class="certificate-preview-inner certificate-document ${isProfessional ? 'certificate-document-professional' : 'certificate-document-participation'}">
      <span class="certificate-corner certificate-corner-tl"></span>
      <span class="certificate-corner certificate-corner-tr"></span>
      <span class="certificate-corner certificate-corner-bl"></span>
      <span class="certificate-corner certificate-corner-br"></span>
      <div class="certificate-document-main">
        <p class="certificate-institution">${escapeHtml(config.organizationName || 'LMTWEBNAIRS Summer School')}</p>
        <h1>${escapeHtml(title)}</h1>
        <p class="certificate-preview-lead">certifica que</p>
        <h2>${escapeHtml(certificate.studentName || 'Nome do participante')}</h2>
        <p>${isProfessional ? 'concluiu com êxito o programa profissional' : 'participou com sucesso do curso'}</p>
        <h3>${escapeHtml(certificate.courseTitle || 'Curso')}</h3>
        ${isProfessional && summary.length ? `
          <div class="certificate-content-summary">
            <strong>O programa abordou:</strong>
            <ul>
              ${summary.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
      </div>
      ${isProfessional ? `
        <div class="certificate-preview-metrics">
          <span><small>Carga horária</small><strong>30 HORAS</strong></span>
          <span><small>Data de emissão</small><strong>${escapeHtml(formatDate(certificate.issueDate))}</strong></span>
          <span><small>Nota final</small><strong>${certificate.finalScore ? `${escapeHtml(certificate.finalScore)}/100` : '--/100'}</strong></span>
        </div>
      ` : ''}
      <div class="certificate-preview-seal${logoUrl ? ' has-brand-logo' : ''}">${logoUrl ? `<img src="${escapeHtml(logoUrl)}" alt="Logotipo institucional">` : 'LSS'}</div>
      ${isProfessional ? `
        <div class="certificate-signature-row">
          <span>Direção académica</span>
          <span>Coordenação do programa</span>
        </div>
      ` : ''}
      <div class="certificate-preview-meta">
        <span>N. do certificado: ${escapeHtml(adminCertificateDisplayNumber(certificate) || certificate.certificateId)}</span>
        <span>${escapeHtml(formatDate(certificate.issueDate))}</span>
        <span>Código: ${escapeHtml(certificate.verificationCode || '')}</span>
      </div>
    </div>
  `;
}

async function downloadAdminCertificate(certificate, overlay = null) {
  if (!certificate?.certificateId) return;
  try {
    const model = certificate.certificateType === 'PROFESSIONAL' ? 'professional' : 'participation';
    const blob = await api.adminCertificatePdf(certificate.certificateId, model);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${adminCertificateDisplayNumber(certificate) || certificate.certificateId}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('Certificado descarregado.', 'success');
    overlay?.remove();
  } catch (error) {
    handleAdminError(error);
  }
}

async function setCertificateStatusFromButton(button) {
  const certificate = certificateFromDataset(button.dataset);
  const status = button.dataset.setCertificateStatus;
  if (!certificate.certificateId || !status) return;
  const label = status === 'ISSUED' ? 'liberar/atribuir novamente' : 'remover o acesso de';
  if (!confirmAdminAction(`Deseja ${label} este certificado?`)) return;
  const statusNote = window.prompt('Motivo/observação administrativa (opcional):', '') || '';
  setBusy(button, true, 'A guardar...');
  try {
    await api.adminSetCertificateStatus(certificate.certificateId, status, statusNote);
    showToast('Acesso do certificado atualizado.', 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function refreshCertificateFormatFromButton(button) {
  const certificate = certificateFromDataset(button.dataset);
  if (!certificate.certificateId) return;
  if (!confirmAdminAction('Deseja atualizar o formato e os conteúdos deste certificado?')) return;
  setBusy(button, true, 'A atualizar...');
  try {
    await api.adminRefreshCertificateFormat({ certificateId: certificate.certificateId });
    showToast('Formato do certificado atualizado.', 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function refreshCertificateFormatAll(event) {
  const button = event?.currentTarget || document.querySelector('#refreshCertificateFormat');
  if (!confirmAdminAction('Deseja atualizar o formato dos certificados ativos deste curso?')) return;
  setBusy(button, true, 'A atualizar...');
  try {
    const result = await api.adminRefreshCertificateFormat({ courseId: state.selectedCourseId });
    showToast(`${result.updated || 0} certificado(s) atualizados.`, 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteCertificateFromButton(button) {
  const certificate = certificateFromDataset(button.dataset);
  if (!certificate.certificateId) return;
  if (!confirmAdminAction('Deseja apagar este certificado? Esta ação remove o certificado das áreas do estudante.')) return;
  const statusNote = window.prompt('Motivo/observação administrativa (opcional):', 'Apagado pelo administrador.') || '';
  setBusy(button, true, 'A apagar...');
  try {
    await api.adminDeleteCertificate(certificate.certificateId, statusNote);
    showToast('Certificado apagado.', 'success');
    await loadCertifications({ force: true });
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function loadPending(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar submissões...');
  }

  try {
    const result = await api.adminSubmissions({
      status: state.submissionFilters.status,
      query: state.submissionFilters.query,
      limit: 300
    }, options);
    state.pending = result.submissions;
    await loadAccessContext(options);
    if (!options.silent) {
      renderSubmissionsV2();
    }
  } catch (error) {
    if (options.silent) {
      console.warn('Falha ao atualizar submissões em segundo plano:', error);
      return;
    }
    handleAdminError(error);
  }
}

function renderPending() {
  const main = document.querySelector('#adminMain');
  const uniqueStudents = new Set(state.pending.map((item) => item.student.email)).size;
  const fileTotal = state.pending.reduce((sum, item) => sum + Number(item.fileCount || 0), 0);

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Avaliação</p>
        <h1>Submissões pendentes</h1>
      </div>
      <button class="button button-secondary" id="refreshPending">Atualizar</button>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de avaliação">
      <article class="insight-card">
        <img src="${iconUrl('inbox', goldIcon)}" alt="">
        <div>
          <span>Submissões</span>
          <strong>${state.pending.length}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('student-male', goldIcon)}" alt="">
        <div>
          <span>Participantes</span>
          <strong>${uniqueStudents}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('documents', goldIcon)}" alt="">
        <div>
          <span>Ficheiros</span>
          <strong>${fileTotal}</strong>
        </div>
      </article>
    </section>

    <div class="admin-table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Estudante</th>
            <th>Aula</th>
            <th>Submetido</th>
            <th>Ficheiros</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${state.pending.length
            ? state.pending.map((item) => `
              <tr>
                <td>
                  <strong>${escapeHtml(item.student.fullName)}</strong>
                  <small>${escapeHtml(item.student.email)}</small>
                </td>
                <td>
                  Aula ${item.lesson.lessonNumber}
                  <small>${escapeHtml(item.lesson.title)}</small>
                </td>
                <td>${formatDate(item.attempt.submittedAt)}</td>
                <td>${item.fileCount}</td>
                <td>
                  <button class="button button-small button-primary"
                    data-open-submission="${escapeHtml(item.attempt.attemptId)}">
                    Avaliar
                  </button>
                </td>
              </tr>
            `).join('')
            : '<tr><td colspan="5" class="empty-table">Não existem submissões pendentes.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;

  document.querySelector('#refreshPending').addEventListener('click', () => loadPending({ force: true }));

  root.querySelectorAll('[data-open-submission]').forEach((button) => {
    button.addEventListener('click', () => {
      openSubmission(button.dataset.openSubmission);
    });
  });

  reportHeight();
}

function renderSubmissionsV2() {
  const main = document.querySelector('#adminMain');
  const visibleSubmissions = filteredSubmissions();
  const pendingCount = state.pending.filter(({ attempt }) => attempt.status === 'UNDER_REVIEW').length;
  const reviewedCount = state.pending.filter(({ attempt }) => ['APPROVED', 'CORRECTION_REQUIRED', 'FAILED'].includes(attempt.status)).length;
  const approvedCount = state.pending.filter(({ attempt }) => attempt.status === 'APPROVED').length;
  const fileTotal = visibleSubmissions.reduce((sum, item) => sum + Number(item.fileCount || 0), 0);
  const uniqueStudents = new Set(visibleSubmissions.map((item) => item.student?.email).filter(Boolean)).size;

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Avaliação</p>
        <h1>Submissões</h1>
      </div>
      <button class="button button-secondary" id="refreshPending">Atualizar</button>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de avaliação">
      <article class="insight-card">
        <img src="${iconUrl('inbox', goldIcon)}" alt="">
        <div>
          <span>Visíveis</span>
          <strong>${visibleSubmissions.length}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('time-machine', goldIcon)}" alt="">
        <div>
          <span>Pendentes</span>
          <strong>${pendingCount}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('ok', goldIcon)}" alt="">
        <div>
          <span>Aprovadas</span>
          <strong>${approvedCount}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('student-male', goldIcon)}" alt="">
        <div>
          <span>Participantes</span>
          <strong>${uniqueStudents}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('documents', goldIcon)}" alt="">
        <div>
          <span>Ficheiros</span>
          <strong>${fileTotal}</strong>
        </div>
      </article>
    </section>

    <section class="admin-filter-bar" aria-label="Filtros de submissões">
      <label>
        <span>Estado</span>
        <select id="submissionStatusFilter">
          ${submissionStatusOption('ALL', 'Todas', state.submissionFilters.status)}
          ${submissionStatusOption('IN_PROGRESS', 'Em curso', state.submissionFilters.status)}
          ${submissionStatusOption('UNDER_REVIEW', 'Pendentes', state.submissionFilters.status)}
          ${submissionStatusOption('REVIEWED', 'Já avaliadas', state.submissionFilters.status)}
          ${submissionStatusOption('APPROVED', 'Aprovadas', state.submissionFilters.status)}
          ${submissionStatusOption('CORRECTION_REQUIRED', 'Correção solicitada', state.submissionFilters.status)}
          ${submissionStatusOption('FAILED', 'Não aprovadas', state.submissionFilters.status)}
          ${submissionStatusOption('TIME_EXCEEDED', 'Tempo excedido', state.submissionFilters.status)}
        </select>
      </label>
      <label class="admin-filter-search">
        <span>Pesquisar</span>
        <input id="submissionSearch" type="search" value="${escapeHtml(state.submissionFilters.query)}"
          placeholder="Estudante, email, aula ou comentário">
      </label>
    </section>

    <section class="access-control-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Gestão de módulos e avaliações</p>
          <h2>Definir acesso, estado e tempo de submissão</h2>
        </div>
      </div>
      <form id="lessonAccessForm" class="access-control-form">
        <label>
          <span>Curso</span>
          <select name="courseId" id="accessCourse">
            ${accessCourseOptions()}
          </select>
        </label>
        <div class="assessment-management-fields">
          <label>
            <span>Acesso ao conteúdo</span>
            <select name="contentAccessStatus">
              <option value="UNCHANGED">Não alterar</option>
              <option value="AVAILABLE">Disponível para leitura</option>
              <option value="LOCKED">Conteúdo bloqueado</option>
            </select>
          </label>
          <label>
            <span>Estado da avaliação</span>
            <select name="evaluationStatus">
              <option value="UNCHANGED">Não alterar</option>
              <option value="NOT_STARTED">Não iniciada</option>
              <option value="IN_PROGRESS">Em curso</option>
              <option value="UNDER_REVIEW">Em avaliação</option>
              <option value="CORRECTION_REQUIRED">Correção solicitada</option>
              <option value="APPROVED">Aprovada</option>
              <option value="FAILED">Não aprovada</option>
              <option value="TIME_EXCEEDED">Tempo excedido</option>
            </select>
          </label>
          <label>
            <span>Tempo de submissão (minutos)</span>
            <input type="number" name="submissionDurationMinutes" min="1" max="43200"
              placeholder="Não alterar">
          </label>
        </div>
        <p class="field-hint management-field-hint">
          O acesso ao conteúdo é independente da avaliação. Assim, um módulo pode continuar disponível para leitura enquanto a submissão está em avaliação.
        </p>
        <fieldset>
          <legend>Módulos</legend>
          ${selectAllToolbar('lessonIds')}
          <div class="access-checkbox-list">
            ${accessLessonCheckboxes()}
          </div>
        </fieldset>
        <fieldset>
          <legend>Turmas</legend>
          ${selectAllToolbar('groupIds')}
          <div class="access-checkbox-list">
            ${accessGroupCheckboxes()}
          </div>
        </fieldset>
        <fieldset>
          <legend>Estudantes especificos</legend>
          ${selectAllToolbar('studentIds')}
          <div class="access-checkbox-list">
            ${accessStudentCheckboxes()}
          </div>
        </fieldset>
        <button class="button button-primary" type="submit">Aplicar alterações</button>
      </form>
    </section>

    <div class="admin-table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Estudante</th>
            <th>Aula</th>
            <th>Estados</th>
            <th>Nota</th>
            <th>Última decisão</th>
            <th>Ficheiros</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${visibleSubmissions.length
            ? visibleSubmissions.map(submissionRowTemplate).join('')
            : '<tr><td colspan="7" class="empty-table">Não existem submissões para os filtros atuais.</td></tr>'}
        </tbody>
      </table>
    </div>
  `;

  document.querySelector('#refreshPending').addEventListener('click', () => loadPending({ force: true }));
  document.querySelector('#submissionStatusFilter').addEventListener('change', (event) => {
    state.submissionFilters.status = event.currentTarget.value;
    loadPending();
  });
  document.querySelector('#submissionSearch').addEventListener('input', (event) => {
    state.submissionFilters.query = event.currentTarget.value;
    renderPreservingFocus(renderSubmissionsV2);
    scheduleSubmissionRefresh();
  });
  document.querySelector('#accessCourse').addEventListener('change', async (event) => {
    state.selectedCourseId = event.currentTarget.value;
    await loadAccessContext();
    renderSubmissionsV2();
  });
  document.querySelector('#lessonAccessForm').addEventListener('submit', applyLessonAccess);
  bindSelectAllControls(root);

  root.querySelectorAll('[data-open-submission]').forEach((button) => {
    button.addEventListener('click', () => openSubmission(button.dataset.openSubmission));
  });

  reportHeight();
}

function scheduleSubmissionRefresh(delay = 450) {
  clearTimeout(submissionSearchTimer);
  const expectedFilters = JSON.stringify(state.submissionFilters);
  submissionSearchTimer = setTimeout(() => {
    loadPending({ silent: true }).then(() => {
      if (expectedFilters === JSON.stringify(state.submissionFilters) && document.querySelector('#submissionSearch')) {
        renderPreservingFocus(renderSubmissionsV2);
      }
    });
  }, delay);
}

function filteredSubmissions() {
  const query = state.submissionFilters.query.trim().toLowerCase();
  if (!query) return state.pending;
  return state.pending.filter((item) => submissionSearchText(item).includes(query));
}

function submissionSearchText(item) {
  return [
    item.student?.fullName,
    item.student?.email,
    item.lesson?.title,
    item.lesson?.lessonNumber,
    item.attempt?.status,
    item.latestReview?.decision,
    item.latestReview?.comments,
    item.attempt?.reviewComments
  ].join(' ').toLowerCase();
}

function submissionStatusOption(value, label, selected) {
  return `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`;
}

function submissionRowTemplate(item) {
  const review = item.latestReview;
  const score = item.attempt?.score ?? review?.score ?? '';
  const actionLabel = item.attempt.status === 'UNDER_REVIEW' ? 'Avaliar' : 'Abrir';

  return `
    <tr>
      <td>
        <strong>${escapeHtml(item.student?.fullName || 'Estudante')}</strong>
        <small>${escapeHtml(item.student?.email || '')}</small>
      </td>
      <td>
        Aula ${escapeHtml(item.lesson?.lessonNumber || '')}
        <small>${escapeHtml(item.lesson?.title || item.attempt.lessonId)}</small>
        <small>Prazo: ${escapeHtml(formatDate(item.attempt?.deadlineAt))}</small>
      </td>
      <td>
        ${adminModuleStatusPairTemplate(item.progress || {}, item.attempt)}
      </td>
      <td>${score === '' || score == null ? '-' : `${escapeHtml(score)}%`}</td>
      <td>
        ${review ? escapeHtml(statusLabel(review.decision)) : '-'}
        <small>${escapeHtml(formatDate(item.attempt.reviewedAt || review?.reviewedAt))}</small>
      </td>
      <td>${item.fileCount || 0}</td>
      <td>
        <button class="button button-small button-primary submission-action-button"
          data-open-submission="${escapeHtml(item.attempt.attemptId)}">
          ${actionLabel}
        </button>
      </td>
    </tr>
  `;
}

async function loadAccessContext(options = {}) {
  const coursesResult = await api.adminCourses({ limit: 500 }, options);
  state.courses = coursesResult.courses || [];
  if (!state.selectedCourseId) {
    state.selectedCourseId = state.courses[0]?.course?.courseId || config.courseId;
  }
  state.courseStructure = await api.adminCourseStructureFor(state.selectedCourseId || config.courseId, options);
  const groupsResult = await api.adminGroups(state.courseStructure.course.courseId, { limit: 500 }, options);
  state.groups = groupsResult.groups || [];
  await ensureStudentsForMedia(options);
}

function accessCourseOptions() {
  return (state.courses || []).map((item) => {
    const course = item.course;
    return studentFilterOption(course.courseId, course.title, state.courseStructure?.course?.courseId || state.selectedCourseId);
  }).join('');
}

function accessLessonCheckboxes() {
  const lessons = state.courseStructure?.lessons || [];
  if (!lessons.length) return '<p class="empty-note">Sem módulos neste curso.</p>';
  return lessons.map(({ lesson }) => `
    <label class="access-checkbox-option">
      <input type="checkbox" name="lessonIds" value="${escapeHtml(lesson.lessonId)}">
      <span>Aula ${escapeHtml(lesson.lessonNumber)} - ${escapeHtml(lesson.title)}</span>
    </label>
  `).join('');
}

function accessGroupCheckboxes() {
  if (!state.groups.length) return '<p class="empty-note">Sem turmas neste curso.</p>';
  return state.groups.map(({ group, memberCount }) => `
    <label class="access-checkbox-option">
      <input type="checkbox" name="groupIds" value="${escapeHtml(group.groupId)}">
      <span>${escapeHtml(group.name)} (${memberCount || 0})</span>
    </label>
  `).join('');
}

function accessStudentCheckboxes() {
  const courseId = state.courseStructure?.course?.courseId || state.selectedCourseId;
  const students = state.students.filter(({ enrollments }) => {
    return (enrollments || []).some((enrollment) => enrollment.courseId === courseId);
  });
  if (!students.length) return '<p class="empty-note">Sem estudantes inscritos neste curso.</p>';
  return students.map(({ student }) => `
    <label class="access-checkbox-option">
      <input type="checkbox" name="studentIds" value="${escapeHtml(student.studentId)}">
      <span>${escapeHtml(studentPublicIdLabel(student.publicStudentId))} - ${escapeHtml(student.fullName)}</span>
    </label>
  `).join('');
}

function selectAllToolbar(inputName) {
  return `
    <div class="select-all-toolbar">
      <button class="button button-secondary button-small" type="button"
        data-select-all="${escapeHtml(inputName)}">Selecionar todos</button>
      <button class="button button-secondary button-small" type="button"
        data-clear-all="${escapeHtml(inputName)}">Limpar seleção</button>
      <span data-selected-count="${escapeHtml(inputName)}">0 selecionados</span>
    </div>
  `;
}

function bindSelectAllControls(scope = root) {
  const names = new Set();
  scope.querySelectorAll('[data-select-all], [data-clear-all], [data-selected-count]').forEach((item) => {
    const name = item.dataset.selectAll || item.dataset.clearAll || item.dataset.selectedCount;
    if (name) names.add(name);
  });

  scope.querySelectorAll('[data-select-all]').forEach((button) => {
    button.addEventListener('click', () => {
      setCheckboxesForName(scope, button.dataset.selectAll, true);
    });
  });
  scope.querySelectorAll('[data-clear-all]').forEach((button) => {
    button.addEventListener('click', () => {
      setCheckboxesForName(scope, button.dataset.clearAll, false);
    });
  });
  names.forEach((name) => {
    checkboxesForName(scope, name).forEach((checkbox) => {
      checkbox.addEventListener('change', () => updateSelectedCount(scope, name));
    });
    updateSelectedCount(scope, name);
  });
}

function checkboxesForName(scope, inputName) {
  const escapedName = window.CSS?.escape ? CSS.escape(inputName) : inputName.replace(/"/g, '\\"');
  return Array.from(scope.querySelectorAll(`input[type="checkbox"][name="${escapedName}"]`));
}

function setCheckboxesForName(scope, inputName, checked) {
  checkboxesForName(scope, inputName).forEach((checkbox) => {
    checkbox.checked = checked;
  });
  updateSelectedCount(scope, inputName);
}

function updateSelectedCount(scope, inputName) {
  const boxes = checkboxesForName(scope, inputName);
  const selected = boxes.filter((checkbox) => checkbox.checked).length;
  scope.querySelectorAll(`[data-selected-count="${inputName}"]`).forEach((item) => {
    item.textContent = `${selected} de ${boxes.length} selecionados`;
  });
}

async function applyLessonAccess(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const payload = {
    courseId: values.get('courseId'),
    contentAccessStatus: values.get('contentAccessStatus'),
    evaluationStatus: values.get('evaluationStatus'),
    submissionDurationMinutes: values.get('submissionDurationMinutes'),
    lessonIds: values.getAll('lessonIds'),
    groupIds: values.getAll('groupIds'),
    studentIds: values.getAll('studentIds')
  };

  if (!payload.lessonIds.length) {
    showToast('Selecione pelo menos um módulo.', 'warning');
    return;
  }

  const changesProgress = payload.contentAccessStatus !== 'UNCHANGED' || payload.evaluationStatus !== 'UNCHANGED';
  const changesDuration = Boolean(payload.submissionDurationMinutes);
  if (!changesProgress && !changesDuration) {
    showToast('Escolha pelo menos uma alteração.', 'warning');
    return;
  }
  if (changesProgress && !payload.groupIds.length && !payload.studentIds.length) {
    showToast('Selecione pelo menos uma turma ou estudante para alterar os estados.', 'warning');
    return;
  }

  if (!confirmAdminAction('Deseja aplicar estas alterações aos módulos e estudantes selecionados?')) return;

  setBusy(button, true, 'A aplicar...');
  try {
    const result = await api.adminManageLessonProgress(payload);
    showToast(`Gestão atualizada em ${result.lessonCount} módulo(s) para ${result.studentCount} estudante(s).`, 'success');
    await loadPending();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function openSubmission(attemptId) {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A abrir a submissão…');

  try {
    state.selectedSubmission = await api.adminSubmission(attemptId);
    renderSubmission();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderSubmission() {
  const data = state.selectedSubmission;
  const main = document.querySelector('#adminMain');
  const latestReview = [...(data.reviews || [])].sort((a, b) => dateValue(b.reviewedAt) - dateValue(a.reviewedAt))[0] || null;
  const currentDecision = latestReview?.decision || decisionFromAttemptStatus(data.attempt.status);
  const currentScore = data.attempt.score ?? latestReview?.score ?? '';
  const currentComments = data.attempt.reviewComments || latestReview?.comments || '';
  const currentDeadline = latestReview?.correctionDeadline
    ? toDatetimeLocalValue(latestReview.correctionDeadline)
    : '';
  const attemptDeadline = data.attempt.deadlineAt ? toDatetimeLocalValue(data.attempt.deadlineAt) : '';
  const contentAccessStatus = data.progress?.contentAccessStatus
    || (data.progress?.status === 'LOCKED' ? 'LOCKED' : 'AVAILABLE');

  const answers = data.answers.map(({ question, answer }) => `
    <article class="admin-answer">
      <p class="eyebrow">Questão ${question?.questionOrder || ''}</p>
      <h3>${escapeHtml(question?.prompt || answer.questionId)}</h3>
      <div class="answer-value">
        ${answer.answerText
          ? `<p>${escapeHtml(answer.answerText).replaceAll('\n', '<br>')}</p>`
          : `<code>${escapeHtml(String(answer.selectedOptionId || 'Sem resposta'))}</code>`}
      </div>
    </article>
  `).join('');

  const files = data.files.map((file) => `
    <a class="admin-file-card" href="${escapeHtml(file.driveUrl)}"
      target="_blank" rel="noopener">
      <strong>${escapeHtml(file.fileName)}</strong>
      <span>${formatBytes(file.sizeBytes)} · ${formatDate(file.uploadedAt)}</span>
    </a>
  `).join('');

  const enhancedAnswers = data.answers.map(answerReviewTemplate).join('');
  const enhancedFiles = data.files.map(adminFileCardTemplate).join('');

  main.innerHTML = `
    <button class="text-button" id="backPending">Voltar para submissões</button>

    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Tentativa ${data.attempt.attemptNumber}</p>
        <h1>${escapeHtml(data.student.fullName)}</h1>
        <p>${escapeHtml(data.lesson.title)}</p>
      </div>

      ${adminModuleStatusPairTemplate(data.progress || {}, data.attempt)}
    </div>

    <div class="submission-columns">
      <section>
        <h2>Respostas</h2>
        ${enhancedAnswers || '<p class="empty-note">Nenhuma resposta registada.</p>'}
      </section>

      <aside>
        <div class="review-form-card">
          <h2>Avaliação</h2>
          ${latestReview ? `
            <p class="review-history-note">
              Última decisão: ${escapeHtml(statusLabel(latestReview.decision))}
              em ${escapeHtml(formatDate(latestReview.reviewedAt))}
            </p>
          ` : ''}

          <form id="reviewForm" class="form-stack">
            <label>
              <span>Decisão</span>
              <select name="decision" required>
                <option value="APPROVED">Aprovado</option>
                <option value="APPROVED_WITH_NOTES">Aprovado com observações</option>
                <option value="CORRECTION_REQUIRED">Correção necessária</option>
                <option value="FAILED">Não aprovado</option>
              </select>
            </label>

            <label>
              <span>Classificação</span>
              <input type="number" name="score" min="0" max="100" required>
            </label>

            <label>
              <span>Comentarios</span>
              <textarea name="comments" rows="7" required></textarea>
            </label>

            <label>
              <span>Prazo para correção — opcional</span>
              <input type="datetime-local" name="correctionDeadline">
            </label>

            <button class="button button-primary button-block" type="submit">
              Guardar avaliação
            </button>
          </form>
        </div>

        <div class="review-files">
          <h2>Ficheiros</h2>
          ${enhancedFiles || '<p class="empty-note">Nenhum ficheiro.</p>'}
        </div>

        <div class="review-files attempt-management-card">
          <div>
            <p class="eyebrow">Controlo administrativo</p>
            <h2>Estado, prazo e leitura</h2>
            <p class="field-hint">O conteúdo pode permanecer disponível mesmo quando a atividade está em avaliação.</p>
          </div>
          <form id="attemptManagementForm" class="form-stack">
            <label>
              <span>Estado da tentativa</span>
              <select name="status" required>
                ${submissionStatusOption('IN_PROGRESS', 'Em curso', data.attempt.status)}
                ${submissionStatusOption('UNDER_REVIEW', 'Em avaliação', data.attempt.status)}
                ${submissionStatusOption('CORRECTION_REQUIRED', 'Correção solicitada', data.attempt.status)}
                ${submissionStatusOption('APPROVED', 'Aprovada', data.attempt.status)}
                ${submissionStatusOption('FAILED', 'Não aprovada', data.attempt.status)}
                ${submissionStatusOption('TIME_EXCEEDED', 'Tempo excedido', data.attempt.status)}
              </select>
            </label>
            <label>
              <span>Prazo da submissão</span>
              <input type="datetime-local" name="deadlineAt" value="${escapeHtml(attemptDeadline)}">
            </label>
            <label>
              <span>Acesso ao conteúdo</span>
              <select name="contentAccessStatus">
                ${submissionStatusOption('AVAILABLE', 'Disponível para leitura', contentAccessStatus)}
                ${submissionStatusOption('LOCKED', 'Conteúdo bloqueado', contentAccessStatus)}
              </select>
            </label>
            <button class="button button-primary button-block" type="submit">Guardar gestão da tentativa</button>
          </form>
        </div>
      </aside>
    </div>
  `;

  document.querySelector('#backPending').addEventListener('click', loadPending);
  const reviewForm = document.querySelector('#reviewForm');
  reviewForm.elements.decision.value = currentDecision || 'APPROVED';
  reviewForm.elements.score.value = currentScore === null ? '' : currentScore;
  reviewForm.elements.comments.value = currentComments;
  reviewForm.elements.correctionDeadline.value = currentDeadline;
  reviewForm.addEventListener('submit', submitReview);
  document.querySelector('#attemptManagementForm')?.addEventListener('submit', submitAttemptManagement);
  root.querySelectorAll('[data-student-access]').forEach((button) => {
    button.addEventListener('click', () => applySingleStudentAccess(button.dataset.studentAccess));
  });
  reportHeight();
}

function answerReviewTemplate({ question, answer }) {
  const studentAnswer = answerDisplayValue(question, answer);
  const correctAnswer = correctAnswerDisplayValue(question);
  const explanation = question?.explanation ? `
    <div class="answer-feedback-note">
      <strong>Explicação:</strong>
      <span>${escapeHtml(question.explanation)}</span>
    </div>
  ` : '';

  return `
    <article class="admin-answer admin-answer-compare">
      <p class="eyebrow">Questão ${escapeHtml(question?.questionOrder || '')}</p>
      <h3>${escapeHtml(question?.prompt || answer?.questionId || 'Questão')}</h3>
      <div class="answer-comparison-grid">
        <div class="answer-value">
          <span>Resposta do estudante</span>
          <strong>${studentAnswer || 'Sem resposta'}</strong>
        </div>
        <div class="answer-value answer-value-correct">
          <span>Resposta correta</span>
          <strong>${correctAnswer || 'Sem resposta correta registada'}</strong>
        </div>
      </div>
      ${explanation}
    </article>
  `;
}

function answerDisplayValue(question, answer = {}) {
  const selected = parseSelectedOptions(answer?.selectedOptionId);
  if (selected.length) {
    return selected.map((optionId) => escapeHtml(optionLabel(question, optionId))).join('<br>');
  }
  return escapeHtml(answer?.answerText || '').replaceAll('\n', '<br>');
}

function correctAnswerDisplayValue(question = {}) {
  const options = Array.isArray(question.options) ? question.options : [];
  const correctOptions = options.filter((option) => option.isCorrect);
  if (correctOptions.length) {
    return correctOptions.map((option) => escapeHtml(optionDisplayText(option))).join('<br>');
  }
  return escapeHtml(question.correctAnswer || '').replaceAll('\n', '<br>');
}

function optionLabel(question = {}, optionId) {
  const option = (question.options || []).find((item) => item.optionId === optionId);
  return option ? optionDisplayText(option) : optionId;
}

function optionDisplayText(option = {}) {
  return [option.optionLabel, option.optionText].filter(Boolean).join(' - ') || option.optionId || '';
}

function adminFileCardTemplate(file) {
  const openUrl = fileOpenUrl(file);
  const downloadUrl = fileDownloadUrl(file);
  const canOpen = Boolean(openUrl);
  const canDownload = Boolean(downloadUrl);

  return `
    <article class="admin-file-card">
      <div>
        <strong>${escapeHtml(file.fileName || 'Ficheiro')}</strong>
        <span>${formatBytes(file.sizeBytes)} &middot; ${formatDate(file.uploadedAt)}</span>
      </div>
      <div class="admin-file-actions">
        ${canOpen ? `
          <a class="button button-small button-secondary" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener">
            Abrir
          </a>
        ` : '<span class="status-pill status-failed">Sem link</span>'}
        ${canDownload ? `
          <a class="button button-small button-primary" href="${escapeHtml(downloadUrl)}"
            download="${escapeHtml(file.fileName || 'ficheiro')}">
            Baixar
          </a>
        ` : ''}
      </div>
    </article>
  `;
}

function fileOpenUrl(file = {}) {
  return file.driveUrl || '';
}

function fileDownloadUrl(file = {}) {
  const rawUrl = file.driveUrl || '';
  if (!rawUrl) return '';
  if (rawUrl.startsWith('data:')) return rawUrl;
  const driveId = file.driveFileId || googleDriveFileId(rawUrl);
  if (driveId) {
    return `https://drive.google.com/uc?export=download&id=${encodeURIComponent(driveId)}`;
  }
  return rawUrl;
}

function googleDriveFileId(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!url.hostname.includes('drive.google.com')) return '';
    return url.searchParams.get('id') || url.pathname.match(/\/file\/d\/([^/]+)/)?.[1] || '';
  } catch {
    return '';
  }
}

function decisionFromAttemptStatus(status) {
  if (status === 'APPROVED') return 'APPROVED';
  if (status === 'CORRECTION_REQUIRED') return 'CORRECTION_REQUIRED';
  if (status === 'FAILED' || status === 'TIME_EXCEEDED') return 'FAILED';
  return 'APPROVED';
}

function toDatetimeLocalValue(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

async function submitAttemptManagement(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const rawDeadline = values.get('deadlineAt');
  const deadlineAt = rawDeadline ? new Date(rawDeadline).toISOString() : '';

  if (!confirmAdminAction('Deseja guardar o estado, o prazo e o acesso desta tentativa?')) return;

  setBusy(button, true, 'A guardar...');
  try {
    await api.adminUpdateAttempt({
      attemptId: state.selectedSubmission.attempt.attemptId,
      status: values.get('status'),
      deadlineAt,
      contentAccessStatus: values.get('contentAccessStatus')
    });
    showToast('Gestão da tentativa atualizada.', 'success');
    await openSubmission(state.selectedSubmission.attempt.attemptId);
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function applySingleStudentAccess(status) {
  const data = state.selectedSubmission;
  if (!data) return;

  const label = status === 'AVAILABLE' ? 'disponibilizar' : 'restringir';
  if (!window.confirm(`Deseja ${label} este módulo para ${data.student.fullName}?`)) return;

  try {
    await api.adminSetLessonAccess({
      courseId: data.lesson.courseId,
      status,
      lessonIds: [data.lesson.lessonId],
      studentIds: [data.student.studentId],
      groupIds: []
    });
    showToast('Acesso atualizado.', 'success');
    await openSubmission(data.attempt.attemptId);
  } catch (error) {
    handleAdminError(error);
  }
}

async function submitReview(event) {
  event.preventDefault();

  if (!confirmAdminAction('Deseja guardar esta avaliação? Esta decisão pode alterar o progresso do estudante.')) return;

  const form = event.currentTarget;
  const button = form.querySelector('button');
  const values = new FormData(form);

  setBusy(button, true, 'A guardar…');

  try {
    await api.adminReview({
      attemptId: state.selectedSubmission.attempt.attemptId,
      decision: values.get('decision'),
      score: Number(values.get('score')),
      comments: values.get('comments'),
      correctionDeadline: values.get('correctionDeadline') || ''
    });

    showToast('Avaliação guardada.', 'success');
    await loadPending();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function loadStudents(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar estudantes...');
  }

  try {
    const result = await api.adminStudents({
      query: state.studentFilters.query,
      status: state.studentFilters.status,
      progress: state.studentFilters.progress,
      sort: state.studentFilters.sort,
      limit: 500
    }, options);
    state.students = result.students;
    if (!options.silent) {
      renderStudentsV2();
    }
  } catch (error) {
    if (options.silent) {
      console.warn('Falha ao atualizar estudantes em segundo plano:', error);
      return;
    }
    handleAdminError(error);
  }
}

function renderStudents() {
  const main = document.querySelector('#adminMain');
  const activeStudents = state.students.filter(({ student }) => student.status === 'ACTIVE').length;
  const avgProgress = state.students.length
    ? Math.round(state.students.reduce((sum, { enrollments }) => {
        return sum + Number(enrollments[0]?.progressPercent || 0);
      }, 0) / state.students.length)
    : 0;

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Participantes</p>
        <h1>Estudantes</h1>
      </div>
      <button class="button button-primary" id="newStudent">
        Adicionar estudante
      </button>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de participantes">
      <article class="insight-card">
        <img src="${iconUrl('conference-call', goldIcon)}" alt="">
        <div>
          <span>Total</span>
          <strong>${state.students.length}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('ok', goldIcon)}" alt="">
        <div>
          <span>Ativos</span>
          <strong>${activeStudents}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('combo-chart', goldIcon)}" alt="">
        <div>
          <span>Progresso medio</span>
          <strong>${avgProgress}%</strong>
        </div>
      </article>
    </section>

    <div class="student-admin-grid">
      ${state.students.map(({ student, enrollments }) => `
        <article class="student-admin-card">
          <div>
            <span class="status-pill ${statusClass(student.status)}">
              ${statusLabel(student.status)}
            </span>
            <h3>${escapeHtml(student.fullName)}</h3>
            <p>${escapeHtml(student.email)}</p>
          </div>

          <div class="student-progress-line">
            <span>Progresso</span>
            <strong>${enrollments[0]?.progressPercent || 0}%</strong>
          </div>

          <div class="student-admin-actions">
            <button type="button" data-reset-access="${escapeHtml(student.studentId)}">
              Novo código
            </button>
            <button type="button"
              data-toggle-student="${escapeHtml(student.studentId)}"
              data-current-status="${escapeHtml(student.status)}">
              ${student.status === 'ACTIVE' ? 'Bloquear' : 'Ativar'}
            </button>
          </div>
        </article>
      `).join('')}
    </div>
  `;

  document.querySelector('#newStudent').addEventListener('click', showStudentDialog);

  root.querySelectorAll('[data-reset-access]').forEach((button) => {
    button.addEventListener('click', () => resetAccess(button.dataset.resetAccess));
  });

  root.querySelectorAll('[data-toggle-student]').forEach((button) => {
    button.addEventListener('click', () => toggleStudent(
      button.dataset.toggleStudent,
      button.dataset.currentStatus
    ));
  });

  reportHeight();
}

function renderStudentsV2() {
  const main = document.querySelector('#adminMain');
  const activeStudents = state.students.filter(({ student }) => student.status === 'ACTIVE').length;
  const blockedStudents = state.students.filter(({ student }) => student.status === 'BLOCKED').length;
  const completedStudents = state.students.filter(({ enrollments }) => {
    return enrollments.some((enrollment) => (
      enrollment.status === 'COMPLETED' ||
      Number(enrollment.progressPercent || 0) >= 100
    ));
  }).length;
  const avgProgress = state.students.length
    ? Math.round(state.students.reduce((sum, { enrollments }) => sum + primaryProgress(enrollments), 0) / state.students.length)
    : 0;
  const visibleStudents = filteredStudents();

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Participantes</p>
        <h1>Estudantes</h1>
      </div>
      <div class="admin-heading-actions">
        <button class="button button-secondary" id="restoreStudentCredentials" type="button">
          Restaurar credenciais
        </button>
        <button class="button button-primary" id="newStudent" type="button">
          Adicionar estudante
        </button>
      </div>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de participantes">
      <article class="insight-card">
        <img src="${iconUrl('conference-call', goldIcon)}" alt="">
        <div>
          <span>Total</span>
          <strong>${state.students.length}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('ok', goldIcon)}" alt="">
        <div>
          <span>Ativos</span>
          <strong>${activeStudents}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('combo-chart', goldIcon)}" alt="">
        <div>
          <span>Progresso medio</span>
          <strong>${avgProgress}%</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('diploma', goldIcon)}" alt="">
        <div>
          <span>Concluidos</span>
          <strong>${completedStudents}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('lock', goldIcon)}" alt="">
        <div>
          <span>Bloqueados</span>
          <strong>${blockedStudents}</strong>
        </div>
      </article>
    </section>

    <section class="student-admin-toolbar" aria-label="Ferramentas de estudantes">
      <label class="student-search-field">
        <span>Pesquisar</span>
        <input id="studentSearch" type="search" value="${escapeHtml(state.studentFilters.query)}"
          placeholder="Nome, email, país ou organização">
      </label>
      <label>
        <span>Estado</span>
        <select id="studentStatusFilter">
          ${studentFilterOption('ALL', 'Todos os estados', state.studentFilters.status)}
          ${studentFilterOption('ACTIVE', 'Ativos', state.studentFilters.status)}
          ${studentFilterOption('BLOCKED', 'Bloqueados', state.studentFilters.status)}
          ${studentFilterOption('INACTIVE', 'Inativos', state.studentFilters.status)}
        </select>
      </label>
      <label>
        <span>Progresso</span>
        <select id="studentProgressFilter">
          ${studentFilterOption('ALL', 'Todos', state.studentFilters.progress)}
          ${studentFilterOption('NOT_STARTED', '0%', state.studentFilters.progress)}
          ${studentFilterOption('IN_PROGRESS', '1% a 99%', state.studentFilters.progress)}
          ${studentFilterOption('COMPLETED', '100%', state.studentFilters.progress)}
        </select>
      </label>
      <label>
        <span>Ordenar</span>
        <select id="studentSort">
          ${studentFilterOption('name', 'Nome', state.studentFilters.sort)}
          ${studentFilterOption('progressDesc', 'Maior progresso', state.studentFilters.sort)}
          ${studentFilterOption('progressAsc', 'Menor progresso', state.studentFilters.sort)}
          ${studentFilterOption('recentLogin', 'Último acesso', state.studentFilters.sort)}
        </select>
      </label>
      <button class="button button-secondary" id="exportStudents" type="button">
        Exportar CSV
      </button>
    </section>

    <div class="student-list-meta">
      <strong>${visibleStudents.length}</strong>
      <span>de ${state.students.length} estudantes visíveis</span>
    </div>

    <div class="student-admin-list">
      ${visibleStudents.length ? `
        <table class="student-list-table">
          <thead>
            <tr>
              <th scope="col">Estudante</th>
              <th scope="col">Estado</th>
              <th class="student-col-organization" scope="col">Organização</th>
              <th class="student-col-country" scope="col">País</th>
              <th scope="col">Curso</th>
              <th scope="col">Progresso</th>
              <th scope="col">Último acesso</th>
              <th class="student-list-actions-heading" scope="col">Ações</th>
            </tr>
          </thead>
          <tbody>
            ${visibleStudents.map(studentCardTemplate).join('')}
          </tbody>
        </table>
      ` : `
        <div class="student-empty-state">
          Nenhum estudante corresponde aos filtros atuais.
        </div>
      `}
    </div>
  `;

  document.querySelector('#newStudent').addEventListener('click', showStudentDialog);
  document.querySelector('#restoreStudentCredentials').addEventListener('click', () => showCredentialRecoveryDialog('STUDENTS'));
  document.querySelector('#studentSearch').addEventListener('input', (event) => {
    state.studentFilters.query = event.currentTarget.value;
    renderPreservingFocus(renderStudentsV2);
    scheduleStudentRefresh();
  });
  document.querySelector('#studentStatusFilter').addEventListener('change', (event) => {
    state.studentFilters.status = event.currentTarget.value;
    loadStudents();
  });
  document.querySelector('#studentProgressFilter').addEventListener('change', (event) => {
    state.studentFilters.progress = event.currentTarget.value;
    loadStudents();
  });
  document.querySelector('#studentSort').addEventListener('change', (event) => {
    state.studentFilters.sort = event.currentTarget.value;
    loadStudents();
  });
  document.querySelector('#exportStudents').addEventListener('click', () => {
    exportStudentsCsv(visibleStudents);
  });

  root.querySelectorAll('[data-view-student]').forEach((button) => {
    button.addEventListener('click', () => showStudentDetailsV2(button.dataset.viewStudent));
  });

  root.querySelectorAll('[data-student-row]').forEach((row) => {
    const openDetails = () => showStudentDetailsV2(row.dataset.studentRow);
    row.addEventListener('click', (event) => {
      if (event.target.closest('button, a, input, select, textarea')) return;
      openDetails();
    });
    row.addEventListener('keydown', (event) => {
      if (event.target !== row || !['Enter', ' '].includes(event.key)) return;
      event.preventDefault();
      openDetails();
    });
  });

  root.querySelectorAll('[data-copy-email]').forEach((button) => {
    button.addEventListener('click', () => copyText(button.dataset.copyEmail, 'Email copiado.'));
  });

  root.querySelectorAll('[data-reset-access]').forEach((button) => {
    button.addEventListener('click', () => resetAccess(button.dataset.resetAccess));
  });

  root.querySelectorAll('[data-toggle-student]').forEach((button) => {
    button.addEventListener('click', () => toggleStudent(
      button.dataset.toggleStudent,
      button.dataset.currentStatus
    ));
  });

  reportHeight();
}

function studentCardTemplate({ student, enrollments }) {
  const primary = primaryEnrollment(enrollments);
  const progress = primaryProgress(enrollments);
  const lastLogin = student.lastLoginAt ? formatDate(student.lastLoginAt) : 'Sem acesso registado';
  const organization = student.organization || 'Sem organização';
  const country = student.country || 'Sem país';
  const course = primary?.courseTitle || primary?.courseCode || primary?.courseId || 'Sem inscrição';

  return `
    <tr class="student-list-row" data-student-row="${escapeHtml(student.studentId)}"
      tabindex="0" aria-label="Abrir detalhes de ${escapeHtml(student.fullName)}">
      <td data-label="Estudante">
        <div class="student-list-identity">
          <span class="student-avatar">${escapeHtml(studentInitials(student.fullName))}</span>
          <span class="student-list-primary">
            <strong>${escapeHtml(student.fullName)}</strong>
            <small>${escapeHtml(studentPublicIdLabel(student.publicStudentId))}</small>
            <small>${escapeHtml(student.email)}</small>
          </span>
        </div>
      </td>
      <td data-label="Estado">
        <span class="status-pill ${statusClass(student.status)}">
          ${statusLabel(student.status)}
        </span>
      </td>
      <td class="student-col-organization" data-label="Organização">
        <span class="student-list-value">${escapeHtml(organization)}</span>
      </td>
      <td class="student-col-country" data-label="País">
        <span class="student-list-value">${escapeHtml(country)}</span>
      </td>
      <td data-label="Curso">
        <span class="student-list-value">${escapeHtml(course)}</span>
      </td>
      <td data-label="Progresso">
        <div class="student-list-progress">
          <strong>${progress}%</strong>
          <span class="student-progress-track" aria-hidden="true">
            <span style="width:${progress}%"></span>
          </span>
        </div>
      </td>
      <td data-label="Último acesso">
        <span class="student-list-value">${escapeHtml(lastLogin)}</span>
      </td>
      <td class="student-list-actions" data-label="Ações">
        <button class="button button-secondary button-small student-list-action" type="button"
          data-view-student="${escapeHtml(student.studentId)}">
          <img src="${iconUrl('eye', blueIcon)}" alt="">
          Ver detalhes
        </button>
      </td>
    </tr>
  `;
}

function scheduleStudentRefresh(delay = 450) {
  clearTimeout(studentSearchTimer);
  const expectedFilters = JSON.stringify(state.studentFilters);
  studentSearchTimer = setTimeout(() => {
    loadStudents({ silent: true }).then(() => {
      if (expectedFilters === JSON.stringify(state.studentFilters) && document.querySelector('#studentSearch')) {
        renderPreservingFocus(renderStudentsV2);
      }
    });
  }, delay);
}

function filteredStudents() {
  const query = state.studentFilters.query.trim().toLowerCase();
  const status = state.studentFilters.status;
  const progress = state.studentFilters.progress;
  const sort = state.studentFilters.sort;

  return state.students
    .filter((record) => {
      const { student, enrollments } = record;
      if (status !== 'ALL' && student.status !== status) return false;
      if (progress !== 'ALL' && progressBucket(primaryProgress(enrollments)) !== progress) return false;
      if (!query) return true;
      return studentSearchText(record).includes(query);
    })
    .sort((a, b) => {
      if (sort === 'progressDesc') return primaryProgress(b.enrollments) - primaryProgress(a.enrollments);
      if (sort === 'progressAsc') return primaryProgress(a.enrollments) - primaryProgress(b.enrollments);
      if (sort === 'recentLogin') return dateValue(b.student.lastLoginAt) - dateValue(a.student.lastLoginAt);
      return String(a.student.fullName || '').localeCompare(String(b.student.fullName || ''), 'pt');
    });
}

function studentFilterOption(value, label, selected) {
  return `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`;
}

function studentSearchText({ student, enrollments }) {
  return [
    student.fullName,
    student.email,
    student.country,
    student.organization,
    student.status,
    ...(enrollments || []).flatMap((enrollment) => [
      enrollment.courseId,
      enrollment.status,
      enrollment.certificateId
    ])
  ].join(' ').toLowerCase();
}

function primaryEnrollment(enrollments = []) {
  return [...enrollments].sort((a, b) => {
    const progressDiff = Number(b.progressPercent || 0) - Number(a.progressPercent || 0);
    if (progressDiff) return progressDiff;
    return dateValue(b.updatedAt || b.enrolledAt) - dateValue(a.updatedAt || a.enrolledAt);
  })[0] || null;
}

function primaryProgress(enrollments = []) {
  return Math.max(0, Math.min(100, Number(primaryEnrollment(enrollments)?.progressPercent || 0)));
}

function progressBucket(progress) {
  if (progress <= 0) return 'NOT_STARTED';
  if (progress >= 100) return 'COMPLETED';
  return 'IN_PROGRESS';
}

function dateValue(value) {
  const date = new Date(value || 0);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function studentInitials(fullName) {
  const parts = String(fullName || '').trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] || 'E';
  const last = parts.length > 1 ? parts.at(-1)[0] : '';
  return `${first}${last}`.toUpperCase();
}

function studentPublicIdLabel(value) {
  const publicId = String(value || '').trim().toUpperCase();
  return /^STU-\d{5}$/.test(publicId) ? publicId : 'Sem ID público';
}

async function showStudentDetailsV2(studentId) {
  const record = state.students.find(({ student }) => student.studentId === studentId);
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card student-detail-dialog student-detail-dialog-wide">
      <button class="dialog-close" type="button">x</button>
      ${loadingTemplate('A carregar detalhes do estudante...')}
    </div>
  `;
  document.body.appendChild(overlay);
  bindDialogClose(overlay);

  try {
    const details = await api.adminStudentDetails(studentId, { force: true });
    renderStudentDetailsOverlay(overlay, details);
  } catch (error) {
    overlay.remove();
    handleAdminError(error);
    if (record) showStudentDetails(studentId);
  }
}

function renderStudentDetailsOverlay(overlay, details) {
  const student = details.student;
  const enrollments = details.enrollments || [];
  const lessonProgress = details.lessonProgress || [];
  const groups = details.groups || [];
  const certificates = details.certificates || [];
  const requests = details.certificateRequests || [];
  const progress = primaryProgress(enrollments);
  const card = overlay.querySelector('.dialog-card');

  card.innerHTML = `
    <button class="dialog-close" type="button">x</button>
    <div class="student-detail-header">
      <span class="student-avatar student-avatar-large">${escapeHtml(studentInitials(student.fullName))}</span>
      <div>
        <span class="status-pill ${statusClass(student.status)}">${statusLabel(student.status)}</span>
        <h2>${escapeHtml(student.fullName)}</h2>
        <p>${escapeHtml(studentPublicIdLabel(student.publicStudentId))} &middot; ${escapeHtml(student.email)}</p>
      </div>
    </div>

    <dl class="student-detail-grid student-detail-grid-expanded">
      <div><dt>ID público</dt><dd>${escapeHtml(studentPublicIdLabel(student.publicStudentId))}</dd></div>
      <div><dt>Email</dt><dd>${escapeHtml(student.email || 'Sem registo')}</dd></div>
      <div><dt>Telefone</dt><dd>${escapeHtml(student.phone || 'Sem registo')}</dd></div>
      <div><dt>País</dt><dd>${escapeHtml(student.country || 'Sem registo')}</dd></div>
      <div><dt>Organização</dt><dd>${escapeHtml(student.organization || 'Sem registo')}</dd></div>
      <div><dt>Função</dt><dd>${escapeHtml(student.jobTitle || 'Sem registo')}</dd></div>
      <div><dt>Interesses</dt><dd>${escapeHtml(student.interests || 'Sem registo')}</dd></div>
      <div><dt>Último acesso</dt><dd>${escapeHtml(formatDate(student.lastLoginAt))}</dd></div>
    </dl>

    <section class="student-detail-section">
      <div class="student-detail-section-heading">
        <h3>Percurso académico</h3>
        <strong>${progress}%</strong>
      </div>
      <div class="student-progress-track">
        <span style="width:${progress}%"></span>
      </div>
      <div class="student-enrollment-list">
        ${enrollments.length ? enrollments.map(studentDetailEnrollmentTemplate).join('') : `
          <div class="student-empty-state">Sem inscrições registadas.</div>
        `}
      </div>
    </section>

    <section class="student-detail-section">
      <div class="student-detail-section-heading">
        <h3>Acesso por módulo</h3>
        <span>${lessonProgress.length} registos</span>
      </div>
      <div class="student-module-access-list">
        ${lessonProgress.length ? lessonProgress.map(studentLessonAccessTemplate).join('') : `
          <div class="student-empty-state">Sem progresso por módulo registado.</div>
        `}
      </div>
    </section>

    <section class="student-detail-section">
      <div class="student-detail-section-heading">
        <h3>Grupos, certificados e pedidos</h3>
      </div>
      <div class="student-detail-columns">
        <div>
          <h4>Grupos</h4>
          ${groups.length ? groups.map(studentGroupTemplate).join('') : '<p class="empty-note">Sem grupos associados.</p>'}
        </div>
        <div>
          <h4>Certificados</h4>
          ${certificates.length ? certificates.map(adminStudentCertificateTemplate).join('') : '<p class="empty-note">Sem certificados emitidos.</p>'}
          <h4>Pedidos profissionais</h4>
          ${requests.length ? requests.map(adminStudentCertificateRequestTemplate).join('') : '<p class="empty-note">Sem pedidos profissionais.</p>'}
        </div>
      </div>
    </section>

    <div class="student-detail-actions">
      <button class="button button-secondary" type="button" data-copy-email="${escapeHtml(student.email)}">
        Copiar email
      </button>
      ${canManageCredentials() ? `
        <button class="button button-secondary" type="button" data-change-student-email>
          Alterar email
        </button>
      ` : ''}
      <button class="button button-secondary" type="button" data-reset-access="${escapeHtml(student.studentId)}">
        Nova palavra-passe
      </button>
      <button class="button button-primary" type="button"
        data-toggle-student="${escapeHtml(student.studentId)}"
        data-current-status="${escapeHtml(student.status)}">
        ${student.status === 'ACTIVE' ? 'Bloquear estudante' : 'Ativar estudante'}
      </button>
    </div>
  `;

  bindDialogClose(overlay);
  overlay.querySelector('[data-copy-email]')?.addEventListener('click', (event) => {
    copyText(event.currentTarget.dataset.copyEmail, 'Email copiado.');
  });
  overlay.querySelector('[data-change-student-email]')?.addEventListener('click', () => {
    showAdminStudentEmailChangeDialog(student, details, overlay);
  });
  overlay.querySelector('[data-reset-access]')?.addEventListener('click', () => resetAccess(student.studentId));
  overlay.querySelector('[data-toggle-student]')?.addEventListener('click', async () => {
    overlay.remove();
    await toggleStudent(student.studentId, student.status);
  });
  overlay.querySelectorAll('[data-student-lesson-access]').forEach((button) => {
    button.addEventListener('click', () => updateStudentLessonAccessFromDetails(
      student,
      button.dataset.lessonId,
      button.dataset.courseId,
      button.dataset.studentLessonAccess,
      overlay
    ));
  });
  overlay.querySelectorAll('[data-open-admin-certificate]').forEach((button) => {
    button.addEventListener('click', () => openAdminCertificatePreview(certificateFromDataset(button.dataset)));
  });
  overlay.querySelectorAll('[data-download-admin-certificate]').forEach((button) => {
    button.addEventListener('click', () => downloadAdminCertificate(certificateFromDataset(button.dataset)));
  });
  overlay.querySelectorAll('[data-set-certificate-status]').forEach((button) => {
    button.addEventListener('click', () => setCertificateStatusFromButton(button));
  });
  overlay.querySelectorAll('[data-delete-certificate]').forEach((button) => {
    button.addEventListener('click', () => deleteCertificateFromButton(button));
  });
  reportHeight();
}

function showAdminStudentEmailChangeDialog(student, studentDetails, detailOverlay) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay dialog-overlay-elevated';
  overlay.innerHTML = `
    <div class="dialog-card email-change-dialog" role="dialog" aria-modal="true" aria-labelledby="adminEmailChangeTitle">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <p class="eyebrow">Operação protegida</p>
      <h2 id="adminEmailChangeTitle">Corrigir email do estudante</h2>
      <p class="recovery-note">A alteração encerra as sessões do estudante, cancela entregas pendentes para o endereço antigo e suspende o consentimento de email.</p>
      <form id="adminStudentEmailChangeForm" class="form-stack">
        <label>
          <span>Estudante</span>
          <input value="${escapeHtml(student.fullName || '')} · ${escapeHtml(studentPublicIdLabel(student.publicStudentId))}" readonly>
        </label>
        <label>
          <span>Email atual</span>
          <input type="email" value="${escapeHtml(student.email || '')}" readonly>
        </label>
        <label>
          <span>Novo email</span>
          <input type="email" name="newEmail" autocomplete="off" maxlength="254" required>
        </label>
        <label>
          <span>Confirmar novo email</span>
          <input type="email" name="confirmEmail" autocomplete="off" maxlength="254" required>
        </label>
        <label>
          <span>Motivo da correção</span>
          <textarea name="reason" rows="3" minlength="5" maxlength="300" required placeholder="Ex.: endereço introduzido incorretamente no registo"></textarea>
        </label>
        <label>
          <span>Confirmar com a sua palavra-passe administrativa</span>
          <input type="password" name="adminPassword" autocomplete="current-password" required>
        </label>
        <label class="checkbox-line email-change-confirmation">
          <input type="checkbox" name="acknowledge" value="true" required>
          <span>Confirmo que verifiquei o novo endereço com o estudante.</span>
        </label>
        <div class="form-message form-message-error" id="adminStudentEmailChangeError" role="alert" hidden></div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-close-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar novo email</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('#adminStudentEmailChangeForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const errorBox = form.querySelector('#adminStudentEmailChangeError');
    const button = form.querySelector('button[type="submit"]');
    const newEmail = String(values.newEmail || '').trim().toLowerCase();
    const confirmEmail = String(values.confirmEmail || '').trim().toLowerCase();
    if (newEmail !== confirmEmail) {
      errorBox.textContent = 'A confirmação do novo email não corresponde.';
      errorBox.hidden = false;
      form.elements.confirmEmail.focus();
      return;
    }
    errorBox.hidden = true;
    setBusy(button, true, 'A guardar...');
    try {
      const result = await api.adminChangeStudentEmail({
        studentId: student.studentId,
        newEmail,
        confirmEmail,
        reason: values.reason,
        adminPassword: values.adminPassword,
        verifiedWithStudent: values.acknowledge === 'true'
      });
      state.students = state.students.map((record) => record.student?.studentId === student.studentId
        ? { ...record, student: result.student }
        : record);
      renderStudentsV2();
      overlay.remove();
      if (detailOverlay?.isConnected) {
        renderStudentDetailsOverlay(detailOverlay, { ...studentDetails, student: result.student });
      }
      showToast('Email corrigido. As sessões do estudante foram encerradas.', 'success');
    } catch (error) {
      errorBox.textContent = error.message || 'Não foi possível alterar o email.';
      errorBox.hidden = false;
      form.elements.adminPassword.value = '';
      form.elements.adminPassword.focus();
    } finally {
      setBusy(button, false);
      reportHeight();
    }
  });
  overlay.querySelector('[name="newEmail"]')?.focus();
  reportHeight();
}

function studentDetailEnrollmentTemplate(enrollment) {
  const progress = Math.max(0, Math.min(100, Number(enrollment.progressPercent || 0)));
  return `
    <article class="student-enrollment-card">
      <div>
        <span class="status-pill ${statusClass(enrollment.status)}">${statusLabel(enrollment.status)}</span>
        <h4>${escapeHtml(enrollment.courseTitle || enrollment.courseId || 'Curso')}</h4>
        <p>${escapeHtml(enrollment.courseCode || enrollment.courseId || '')}</p>
      </div>
      <dl>
        <div><dt>Progresso</dt><dd>${progress}%</dd></div>
        <div><dt>Grupo</dt><dd>${escapeHtml(enrollment.groupName || enrollment.groupId || '-')}</dd></div>
        <div><dt>Nota final</dt><dd>${enrollment.finalScore == null ? '-' : escapeHtml(enrollment.finalScore)}</dd></div>
        <div><dt>Certificado</dt><dd>${escapeHtml(enrollment.certificateId || '-')}</dd></div>
      </dl>
    </article>
  `;
}

function adminContentAccessStatus(progress = {}) {
  if (['AVAILABLE', 'LOCKED'].includes(progress.contentAccessStatus)) return progress.contentAccessStatus;
  return progress.status === 'LOCKED' ? 'LOCKED' : 'AVAILABLE';
}

function adminEvaluationStatus(progress = {}, attempt = null) {
  const supported = ['NOT_STARTED', 'IN_PROGRESS', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'FAILED', 'TIME_EXCEEDED'];
  if (supported.includes(progress.evaluationStatus)) return progress.evaluationStatus;
  if (supported.includes(attempt?.status)) return attempt.status;
  return supported.includes(progress.status) ? progress.status : 'NOT_STARTED';
}

function adminModuleStatusPairTemplate(progress = {}, attempt = null) {
  const accessStatus = adminContentAccessStatus(progress);
  const evaluationStatus = adminEvaluationStatus(progress, attempt);
  return `
    <div class="module-status-pair" aria-label="Estados do módulo">
      <span class="module-status-item"><small>Conteúdo</small><span class="status-pill ${statusClass(accessStatus)}">${escapeHtml(statusLabel(accessStatus))}</span></span>
      <span class="module-status-item"><small>Avaliação</small><span class="status-pill ${statusClass(evaluationStatus)}">${escapeHtml(statusLabel(evaluationStatus))}</span></span>
    </div>
  `;
}

function studentLessonAccessTemplate(item) {
  const lesson = item.lesson || {};
  const progress = item.progress || {};
  const attempt = item.attempt;
  return `
    <article class="student-module-access-card">
      <div>
        ${adminModuleStatusPairTemplate(progress, attempt)}
        <h4>Módulo ${escapeHtml(lesson.lessonNumber || '')}: ${escapeHtml(lesson.title || lesson.lessonId || '')}</h4>
        <p>${escapeHtml(item.courseId || '')} &middot; ${item.fileCount || 0} ficheiro(s)</p>
      </div>
      <dl>
        <div><dt>Tentativa</dt><dd>${attempt ? escapeHtml(attempt.attemptNumber) : '-'}</dd></div>
        <div><dt>Estado</dt><dd>${attempt ? escapeHtml(statusLabel(attempt.status)) : '-'}</dd></div>
        <div><dt>Nota</dt><dd>${attempt?.score == null ? '-' : escapeHtml(attempt.score)}</dd></div>
        <div><dt>Submetido</dt><dd>${escapeHtml(formatDate(attempt?.submittedAt))}</dd></div>
      </dl>
      <div class="admin-row-actions">
        <button class="button button-small button-secondary" type="button"
          data-student-lesson-access="AVAILABLE"
          data-course-id="${escapeHtml(item.courseId || '')}"
          data-lesson-id="${escapeHtml(lesson.lessonId || progress.lessonId || '')}">
          Liberar
        </button>
        <button class="button button-small button-danger" type="button"
          data-student-lesson-access="LOCKED"
          data-course-id="${escapeHtml(item.courseId || '')}"
          data-lesson-id="${escapeHtml(lesson.lessonId || progress.lessonId || '')}">
          Restringir
        </button>
      </div>
    </article>
  `;
}

function studentGroupTemplate(item) {
  const group = item.group || {};
  const member = item.groupMember || {};
  return `
    <article class="student-mini-record">
      <strong>${escapeHtml(group.name || group.groupId || 'Grupo')}</strong>
      <span>${escapeHtml(group.courseId || '')} &middot; ${escapeHtml(statusLabel(member.status))}</span>
    </article>
  `;
}

function adminStudentCertificateTemplate(certificate) {
  const blocked = certificate.status === 'BLOCKED';
  const nextStatus = blocked ? 'ISSUED' : 'BLOCKED';
  const dataset = adminCertificateActionDataset(certificate);
  return `
    <article class="student-mini-record">
      <strong>${escapeHtml(certificate.certificateNumber || certificate.certificateId)}</strong>
      <span>${escapeHtml(certificate.courseTitle || certificate.courseId)} &middot; ${escapeHtml(certificate.certificateType || 'SIMPLE')} &middot; ${escapeHtml(statusLabel(certificate.status))}</span>
      <div class="admin-row-actions">
        <button class="button button-small button-secondary" type="button" data-open-admin-certificate ${dataset}>
          Ver
        </button>
        <button class="button button-small button-primary" type="button" data-download-admin-certificate ${dataset}>
          Baixar
        </button>
        <button class="button button-small button-secondary" type="button"
          data-set-certificate-status="${escapeHtml(nextStatus)}" ${dataset}>
          ${blocked ? 'Liberar' : 'Bloquear'}
        </button>
        <button class="button button-small button-danger" type="button" data-delete-certificate ${dataset}>
          Apagar
        </button>
      </div>
    </article>
  `;
}

function adminStudentCertificateRequestTemplate(request) {
  return `
    <article class="student-mini-record">
      <strong>${escapeHtml(request.requestId)}</strong>
      <span>${escapeHtml(request.courseTitle || request.courseId)} &middot; ${escapeHtml(statusLabel(request.status))}</span>
    </article>
  `;
}

async function updateStudentLessonAccessFromDetails(student, lessonId, courseId, status, overlay) {
  const label = status === 'AVAILABLE' ? 'liberar' : 'restringir';
  if (!lessonId || !courseId) return;
  if (!confirmAdminAction(`Deseja ${label} este módulo para ${student.fullName}?`)) return;
  try {
    await api.adminSetLessonAccess({
      courseId,
      status,
      lessonIds: [lessonId],
      studentIds: [student.studentId],
      groupIds: []
    });
    showToast('Acesso do módulo atualizado.', 'success');
    const details = await api.adminStudentDetails(student.studentId, { force: true });
    renderStudentDetailsOverlay(overlay, details);
  } catch (error) {
    handleAdminError(error);
  }
}

function showStudentDetails(studentId) {
  const record = state.students.find(({ student }) => student.studentId === studentId);
  if (!record) return;

  const { student, enrollments } = record;
  const progress = primaryProgress(enrollments);
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card student-detail-dialog">
      <button class="dialog-close" type="button">x</button>
      <div class="student-detail-header">
        <span class="student-avatar student-avatar-large">${escapeHtml(studentInitials(student.fullName))}</span>
        <div>
          <span class="status-pill ${statusClass(student.status)}">${statusLabel(student.status)}</span>
          <h2>${escapeHtml(student.fullName)}</h2>
          <p>${escapeHtml(student.email)}</p>
        </div>
      </div>

      <dl class="student-detail-grid">
        <div><dt>ID público</dt><dd>${escapeHtml(studentPublicIdLabel(student.publicStudentId))}</dd></div>
        <div><dt>País</dt><dd>${escapeHtml(student.country || 'Sem registo')}</dd></div>
        <div><dt>Organização</dt><dd>${escapeHtml(student.organization || 'Sem registo')}</dd></div>
        <div><dt>Criado em</dt><dd>${escapeHtml(formatDate(student.createdAt))}</dd></div>
        <div><dt>Atualizado em</dt><dd>${escapeHtml(formatDate(student.updatedAt))}</dd></div>
        <div><dt>Último acesso</dt><dd>${escapeHtml(formatDate(student.lastLoginAt))}</dd></div>
      </dl>

      <section class="student-detail-section">
        <div class="student-detail-section-heading">
          <h3>Percurso académico</h3>
          <strong>${progress}%</strong>
        </div>
        <div class="student-progress-track">
          <span style="width:${progress}%"></span>
        </div>
        <div class="student-enrollment-list">
          ${enrollments.length ? enrollments.map(enrollmentTemplate).join('') : `
            <div class="student-empty-state">Sem inscrições registadas.</div>
          `}
        </div>
      </section>

      <div class="student-detail-actions">
        <button class="button button-secondary" type="button" data-copy-email="${escapeHtml(student.email)}">
          Copiar email
        </button>
        <button class="button button-secondary" type="button" data-reset-access="${escapeHtml(student.studentId)}">
          Nova palavra-passe
        </button>
        <button class="button button-primary" type="button"
          data-toggle-student="${escapeHtml(student.studentId)}"
          data-current-status="${escapeHtml(student.status)}">
          ${student.status === 'ACTIVE' ? 'Bloquear estudante' : 'Ativar estudante'}
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('[data-copy-email]').addEventListener('click', (event) => {
    copyText(event.currentTarget.dataset.copyEmail, 'Email copiado.');
  });
  overlay.querySelector('[data-reset-access]').addEventListener('click', () => resetAccess(student.studentId));
  overlay.querySelector('[data-toggle-student]').addEventListener('click', async () => {
    overlay.remove();
    await toggleStudent(student.studentId, student.status);
  });
  reportHeight();
}

function enrollmentTemplate(enrollment) {
  const progress = Math.max(0, Math.min(100, Number(enrollment.progressPercent || 0)));
  return `
    <article class="student-enrollment-card">
      <div>
        <span class="status-pill ${statusClass(enrollment.status)}">${statusLabel(enrollment.status)}</span>
        <h4>${escapeHtml(enrollment.courseId || 'Curso')}</h4>
        <p>Inscrito em ${escapeHtml(formatDate(enrollment.enrolledAt))}</p>
      </div>
      <dl>
        <div><dt>Progresso</dt><dd>${progress}%</dd></div>
        <div><dt>Nota final</dt><dd>${enrollment.finalScore === '' || enrollment.finalScore == null ? '-' : escapeHtml(enrollment.finalScore)}</dd></div>
        <div><dt>Certificado</dt><dd>${escapeHtml(enrollment.certificateId || '-')}</dd></div>
        <div><dt>Atualizado</dt><dd>${escapeHtml(formatDate(enrollment.updatedAt))}</dd></div>
      </dl>
    </article>
  `;
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage, 'success');
  } catch {
    window.prompt('Copie o texto:', text);
  }
}

function exportStudentsCsv(records) {
  const rows = [
    ['ID público', 'Nome', 'Email', 'Estado', 'País', 'Organização', 'Progresso', 'Último acesso']
  ];

  records.forEach(({ student, enrollments }) => {
    rows.push([
      studentPublicIdLabel(student.publicStudentId),
      student.fullName || '',
      student.email || '',
      statusLabel(student.status),
      student.country || '',
      student.organization || '',
      `${primaryProgress(enrollments)}%`,
      student.lastLoginAt || ''
    ]);
  });

  const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `estudantes-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

async function loadCourses(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar cursos...');
  }

  try {
    const coursePayload = state.courseMode === 'detail'
      ? { limit: 500 }
      : {
          query: state.courseFilters.query,
          status: state.courseFilters.status,
          content: state.courseFilters.content,
          limit: 500
        };
    const coursesResult = await api.adminCourses(coursePayload, options);
    state.courses = coursesResult.courses || [];

    if (state.courseMode !== 'detail') {
      state.courseStructure = null;
      state.groups = [];
      if (!options.silent) {
        renderCourseList();
      }
      return;
    }

    const activeCourses = state.courses.filter((item) => item.course.status !== 'DELETED');
    if (!activeCourses.length) {
      state.selectedCourseId = '';
      state.courseStructure = null;
      state.groups = [];
      state.courseMode = 'list';
      if (!options.silent) {
        renderCourseList();
      }
      return;
    }
    if (
      (!state.selectedCourseId || !activeCourses.some((item) => item.course.courseId === state.selectedCourseId)) &&
      activeCourses.length
    ) {
      state.selectedCourseId = activeCourses[0].course.courseId;
    }
    state.courseStructure = await api.adminCourseStructureFor(state.selectedCourseId || config.courseId, options);
    const groupsResult = await api.adminGroups(state.courseStructure.course.courseId, { limit: 500 }, options);
    state.groups = groupsResult.groups || [];
    await ensureStudentsForMedia(options);
    if (!options.silent) {
      renderCourses();
    }
  } catch (error) {
    if (options.silent) {
      console.warn('Falha ao atualizar cursos em segundo plano:', error);
      return;
    }
    handleAdminError(error);
  }
}

function renderCourseList() {
  const main = document.querySelector('#adminMain');
  const visibleCourses = filteredAdminCourses();
  const activeCount = state.courses.filter((item) => item.course?.status === 'ACTIVE').length;
  const inactiveCount = state.courses.filter((item) => item.course?.status === 'INACTIVE').length;
  const moduleCount = state.courses.reduce((sum, item) => sum + Number(item.lessonCount || 0), 0);
  const groupCount = state.courses.reduce((sum, item) => sum + Number(item.groupCount || 0), 0);

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Catalogo académico</p>
        <h1>Cursos</h1>
      </div>
      <div class="admin-heading-actions">
        <button class="button button-primary" id="newCourse" type="button">Novo curso</button>
      </div>
    </div>

    <section class="admin-content-overview">
      <article class="content-metric-card">
        <span>Total</span>
        <strong>${state.courses.length}</strong>
        <small>Cursos registados</small>
      </article>
      <article class="content-metric-card">
        <span>Ativos</span>
        <strong>${activeCount}</strong>
        <small>${inactiveCount} inativos</small>
      </article>
      <article class="content-metric-card">
        <span>Módulos</span>
        <strong>${moduleCount}</strong>
        <small>Em todos os cursos</small>
      </article>
      <article class="content-metric-card">
        <span>Grupos</span>
        <strong>${groupCount}</strong>
        <small>Turmas criadas</small>
      </article>
    </section>

    <form id="courseFilterForm" class="admin-filter-bar course-list-filters" aria-label="Filtros de cursos">
      <label>
        <span>Pesquisar</span>
        <input id="courseSearch" type="search" value="${escapeHtml(state.courseFilters.query)}"
          placeholder="ID, código, nome ou descrição">
      </label>
      <label>
        <span>Estado</span>
        <select id="courseStatusFilter">
          ${studentFilterOption('ALL', 'Todos', state.courseFilters.status)}
          ${studentFilterOption('ACTIVE', 'Ativos', state.courseFilters.status)}
          ${studentFilterOption('INACTIVE', 'Inativos', state.courseFilters.status)}
          ${studentFilterOption('DELETED', 'Eliminados', state.courseFilters.status)}
        </select>
      </label>
      <label>
        <span>Conteúdo</span>
        <select id="courseContentFilter">
          ${studentFilterOption('ALL', 'Todos', state.courseFilters.content)}
          ${studentFilterOption('WITH_MODULES', 'Com módulos', state.courseFilters.content)}
          ${studentFilterOption('WITHOUT_MODULES', 'Sem módulos', state.courseFilters.content)}
          ${studentFilterOption('WITH_GROUPS', 'Com grupos', state.courseFilters.content)}
          ${studentFilterOption('WITHOUT_GROUPS', 'Sem grupos', state.courseFilters.content)}
        </select>
      </label>
      <button class="button button-secondary" type="submit">Aplicar filtros</button>
    </form>

    <section class="admin-course-list" aria-label="Lista de cursos">
      ${visibleCourses.length
        ? visibleCourses.map(courseListCardTemplate).join('')
        : '<div class="student-empty-state">Nenhum curso encontrado para os filtros atuais.</div>'}
    </section>
  `;

  document.querySelector('#newCourse').addEventListener('click', () => showCourseDialog());
  document.querySelector('#courseFilterForm').addEventListener('submit', (event) => {
    event.preventDefault();
    state.courseFilters.query = document.querySelector('#courseSearch').value;
    state.courseFilters.status = document.querySelector('#courseStatusFilter').value;
    state.courseFilters.content = document.querySelector('#courseContentFilter').value;
    loadCourses();
  });
  document.querySelector('#courseSearch').addEventListener('input', (event) => {
    state.courseFilters.query = event.currentTarget.value;
    renderPreservingFocus(renderCourseList);
    scheduleCourseRefresh();
  });
  document.querySelector('#courseStatusFilter').addEventListener('change', (event) => {
    state.courseFilters.query = document.querySelector('#courseSearch').value;
    state.courseFilters.status = event.currentTarget.value;
    state.courseFilters.content = document.querySelector('#courseContentFilter').value;
    renderPreservingFocus(renderCourseList);
    scheduleCourseRefresh(0);
  });
  document.querySelector('#courseContentFilter').addEventListener('change', (event) => {
    state.courseFilters.query = document.querySelector('#courseSearch').value;
    state.courseFilters.status = document.querySelector('#courseStatusFilter').value;
    state.courseFilters.content = event.currentTarget.value;
    renderPreservingFocus(renderCourseList);
    scheduleCourseRefresh(0);
  });
  root.querySelectorAll('[data-open-course-detail]').forEach((button) => {
    button.addEventListener('click', () => openCourseDetail(button.dataset.openCourseDetail));
  });
  root.querySelectorAll('[data-restore-course]').forEach((button) => {
    button.addEventListener('click', () => restoreCourse(button.dataset.restoreCourse));
  });

  reportHeight();
}

function scheduleCourseRefresh(delay = 450) {
  clearTimeout(courseSearchTimer);
  const expectedFilters = JSON.stringify(state.courseFilters);
  courseSearchTimer = setTimeout(() => {
    loadCourses({ silent: true }).then(() => {
      if (expectedFilters === JSON.stringify(state.courseFilters) && document.querySelector('#courseSearch')) {
        renderPreservingFocus(renderCourseList);
      }
    });
  }, delay);
}

function filteredAdminCourses() {
  const query = state.courseFilters.query.trim().toLowerCase();
  const status = state.courseFilters.status;
  const content = state.courseFilters.content;

  return state.courses.filter((item) => {
    const course = item.course || {};
    if (status !== 'ALL' && course.status !== status) return false;
    if (content === 'WITH_MODULES' && !Number(item.lessonCount || 0)) return false;
    if (content === 'WITHOUT_MODULES' && Number(item.lessonCount || 0)) return false;
    if (content === 'WITH_GROUPS' && !Number(item.groupCount || 0)) return false;
    if (content === 'WITHOUT_GROUPS' && Number(item.groupCount || 0)) return false;
    if (!query) return true;
    return [
      course.courseId,
      course.courseCode,
      course.title,
      course.description,
      course.status
    ].join(' ').toLowerCase().includes(query);
  });
}

function courseListCardTemplate(item) {
  const course = item.course || {};
  const status = course.status || 'ACTIVE';
  const isDeleted = status === 'DELETED';

  return `
    <article class="admin-course-card">
      <div>
        <div class="admin-course-card-topline">
          <span class="status-pill ${statusClass(status)}">${statusLabel(status)}</span>
          <small>${escapeHtml(course.courseCode || course.courseId || '')}</small>
        </div>
        <h2>${escapeHtml(course.title || 'Curso sem nome')}</h2>
        <p>${escapeHtml(course.description || 'Sem descrição registada.')}</p>
      </div>
      <dl>
        <div>
          <dt>ID</dt>
          <dd>${escapeHtml(course.courseId || '-')}</dd>
        </div>
        <div>
          <dt>Módulos</dt>
          <dd>${item.lessonCount || 0}</dd>
        </div>
        <div>
          <dt>Grupos</dt>
          <dd>${item.groupCount || 0}</dd>
        </div>
      </dl>
      <div class="admin-course-card-actions">
        ${isDeleted ? `
          <button class="button button-primary" type="button"
            data-restore-course="${escapeHtml(course.courseId || '')}">
            Restaurar curso
          </button>
        ` : `
          <button class="button button-primary" type="button"
            data-open-course-detail="${escapeHtml(course.courseId || '')}">
            Abrir detalhes
          </button>
        `}
      </div>
    </article>
  `;
}

async function openCourseDetail(courseId) {
  state.selectedCourseId = courseId;
  state.courseMode = 'detail';
  state.courseView = 'overview';
  await loadCourses();
}

function renderCourses() {
  const main = document.querySelector('#adminMain');
  const course = state.courseStructure?.course || {};
  if (!course.courseId) {
    main.innerHTML = `
      <div class="admin-page-heading">
        <div>
          <p class="eyebrow">Conteúdo académico</p>
          <h1>Cursos e módulos</h1>
        </div>
        <div class="admin-heading-actions">
          <button class="button button-primary" id="newCourse" type="button">Novo curso</button>
        </div>
      </div>
      <section class="student-empty-state">
        Nenhum curso ativo encontrado. Crie um curso para iniciar a gestão de conteúdos.
      </section>
    `;
    document.querySelector('#newCourse').addEventListener('click', () => showCourseDialog());
    return;
  }
  const lessons = (state.courseStructure?.lessons || []).filter(({ lesson }) => lesson?.status !== 'DELETED');
  const groups = (state.groups || []).filter(({ group }) => group?.status !== 'DELETED');
  const visibleLessons = state.courseFilters.showDeletedItems ? (state.courseStructure?.lessons || []) : lessons;
  const visibleGroups = state.courseFilters.showDeletedItems ? (state.groups || []) : groups;
  const deletedLessons = (state.courseStructure?.lessons || []).filter(({ lesson }) => lesson?.status === 'DELETED').length;
  const deletedGroups = (state.groups || []).filter(({ group }) => group?.status === 'DELETED').length;
  const totalContent = lessons.reduce((sum, item) => sum + (item.content?.length || 0), 0);
  const totalQuestions = lessons.reduce((sum, item) => sum + (item.questions?.length || 0), 0);

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Conteúdo académico</p>
        <h1>${escapeHtml(course.title || 'Cursos e módulos')}</h1>
      </div>
      <div class="admin-heading-actions">
        <button class="button button-secondary" id="backToCourseList" type="button">Todos os cursos</button>
        <button class="button button-secondary" id="newCourse" type="button">Novo curso</button>
      </div>
    </div>

    <section class="admin-content-overview">
      <article class="content-metric-card">
        <span>Módulos ativos</span>
        <strong>${lessons.length}</strong>
        <small>${deletedLessons} eliminados</small>
      </article>
      <article class="content-metric-card">
        <span>Conteúdos</span>
        <strong>${totalContent}</strong>
        <small>Secções registadas</small>
      </article>
      <article class="content-metric-card">
        <span>Questões</span>
        <strong>${totalQuestions}</strong>
        <small>Avaliação</small>
      </article>
      <article class="content-metric-card">
        <span>Grupos ativos</span>
        <strong>${groups.length}</strong>
        <small>${deletedGroups} eliminados</small>
      </article>
    </section>

    <section class="admin-content-tabs" aria-label="Organização do conteúdo">
      <button type="button" class="${state.courseView === 'overview' ? 'is-active' : ''}" data-course-view="overview">Visão geral</button>
      <button type="button" class="${state.courseView === 'modules' ? 'is-active' : ''}" data-course-view="modules">Módulos</button>
      <button type="button" class="${state.courseView === 'groups' ? 'is-active' : ''}" data-course-view="groups">Grupos</button>
    </section>

    ${courseManagementPanel(course, visibleLessons, visibleGroups, { deletedLessons, deletedGroups })}
  `;

  document.querySelector('#backToCourseList').addEventListener('click', () => {
    state.courseMode = 'list';
    renderCourseList();
  });
  document.querySelector('#newCourse').addEventListener('click', () => showCourseDialog());
  document.querySelector('#courseForm')?.addEventListener('submit', saveCourse);
  document.querySelector('#deleteCourse')?.addEventListener('click', deleteCurrentCourse);
  document.querySelector('#newGroup')?.addEventListener('click', () => showGroupDialog());
  document.querySelector('#newLesson')?.addEventListener('click', () => showLessonDialog());
  root.querySelectorAll('[data-course-view]').forEach((button) => {
    button.addEventListener('click', () => {
      state.courseView = button.dataset.courseView;
      renderCourses();
    });
  });
  root.querySelectorAll('[data-edit-lesson]').forEach((button) => {
    button.addEventListener('click', () => showLessonDialog(button.dataset.editLesson));
  });
  root.querySelectorAll('[data-manage-lesson-access]').forEach((button) => {
    button.addEventListener('click', () => showLessonAccessDialog(button.dataset.manageLessonAccess));
  });
  root.querySelectorAll('[data-delete-lesson]').forEach((button) => {
    button.addEventListener('click', () => deleteLesson(button.dataset.deleteLesson));
  });
  root.querySelectorAll('[data-restore-lesson]').forEach((button) => {
    button.addEventListener('click', () => restoreLesson(button.dataset.restoreLesson));
  });
  root.querySelectorAll('[data-edit-group]').forEach((button) => {
    button.addEventListener('click', () => showGroupDialog(button.dataset.editGroup));
  });
  root.querySelectorAll('[data-delete-group]').forEach((button) => {
    button.addEventListener('click', () => deleteGroup(button.dataset.deleteGroup));
  });
  root.querySelectorAll('[data-restore-group]').forEach((button) => {
    button.addEventListener('click', () => restoreGroup(button.dataset.restoreGroup));
  });
  document.querySelector('#toggleDeletedItems')?.addEventListener('click', () => {
    state.courseFilters.showDeletedItems = !state.courseFilters.showDeletedItems;
    renderCourses();
  });

  reportHeight();
}

function courseManagementPanel(course, lessons, groups, meta = {}) {
  const deletedTotal = Number(meta.deletedLessons || 0) + Number(meta.deletedGroups || 0);
  const deletedToggle = deletedTotal ? `
    <button class="button button-secondary" id="toggleDeletedItems" type="button">
      ${state.courseFilters.showDeletedItems ? 'Ocultar eliminados' : `Mostrar eliminados (${deletedTotal})`}
    </button>
  ` : '';

  if (state.courseView === 'modules') {
    return `
      <section class="admin-content-panel">
        <div class="course-section-heading">
          <div>
            <p class="eyebrow">Nível 2</p>
            <h2>Módulos do curso</h2>
          </div>
          <div class="admin-heading-actions">
            ${deletedToggle}
            <button class="button button-primary" id="newLesson" type="button">Novo módulo</button>
          </div>
        </div>
        <div class="course-module-list course-module-list-clean">
          ${lessons.length ? lessons.map(moduleCardTemplate).join('') : `
            <div class="student-empty-state">Nenhum módulo registado.</div>
          `}
        </div>
      </section>
    `;
  }

  if (state.courseView === 'groups') {
    return `
      <section class="admin-content-panel">
        <div class="course-section-heading">
          <div>
            <p class="eyebrow">Nível 3</p>
            <h2>Grupos e estudantes</h2>
          </div>
          <div class="admin-heading-actions">
            ${deletedToggle}
            <button class="button button-primary" id="newGroup" type="button">Nova turma</button>
          </div>
        </div>
        <div class="course-module-list course-module-list-clean">
          ${groups.length ? groups.map(groupCardTemplate).join('') : `
            <div class="student-empty-state">Nenhuma turma registada para este curso.</div>
          `}
        </div>
      </section>
    `;
  }

  return `
    <section class="admin-content-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Nível 1</p>
          <h2>Configuração do curso</h2>
        </div>
      </div>

      <form id="courseForm" class="course-overview-form form-stack">
        <input type="hidden" name="courseId" value="${escapeHtml(course.courseId || config.courseId || '')}">
        <div class="course-form-grid">
          <label>
            <span>Código</span>
            <input name="courseCode" value="${escapeHtml(course.courseCode || '')}" required>
          </label>
          <label>
            <span>Título</span>
            <input name="title" value="${escapeHtml(course.title || '')}" required>
          </label>
          <label>
            <span>Estado</span>
            <select name="status">
              ${studentFilterOption('ACTIVE', 'Ativo', course.status || 'ACTIVE')}
              ${studentFilterOption('INACTIVE', 'Inativo', course.status || 'ACTIVE')}
            </select>
          </label>
        </div>
        <label>
          <span>Descrição</span>
          <textarea name="description" rows="5">${escapeHtml(course.description || '')}</textarea>
        </label>
        <div class="course-form-grid">
          <label>
            <span>Total de horas</span>
            <input type="number" name="totalHours" min="0" value="${escapeHtml(course.totalHours || 0)}">
          </label>
          <label>
            <span>Nota minima</span>
            <input type="number" name="passingScore" min="0" max="100" value="${escapeHtml(course.passingScore || 60)}">
          </label>
        </div>
        <div class="dialog-actions">
          ${course.courseId ? '<button class="button button-danger" id="deleteCourse" type="button">Eliminar curso</button>' : ''}
          <button class="button button-secondary" type="reset">Cancelar alterações</button>
          <button class="button button-primary" type="submit">Guardar curso</button>
        </div>
      </form>
    </section>
  `;
}

function moduleCardTemplate(item) {
  const lesson = item.lesson || item;
  const contentCount = item.content?.length || 0;
  const questionCount = item.questions?.length || 0;
  const isDeleted = lesson.status === 'DELETED';

  return `
    <article class="course-module-card">
      <div>
        <span class="status-pill ${statusClass(lesson.status)}">${statusLabel(lesson.status)}</span>
        <h3>Aula ${escapeHtml(lesson.lessonNumber)} - ${escapeHtml(lesson.title)}</h3>
        <p>${escapeHtml(lesson.summary || 'Sem resumo registado.')}</p>
      </div>
      <dl>
        <div><dt>Teoria</dt><dd>${escapeHtml(lesson.theoryMinutes || 0)} min</dd></div>
        <div><dt>Exercicios</dt><dd>${escapeHtml(lesson.exerciseMinutes || 0)} min</dd></div>
        <div><dt>Individual</dt><dd>${escapeHtml(lesson.individualMinutes || 0)} min</dd></div>
        <div><dt>Submissão</dt><dd>${escapeHtml(lesson.submissionDurationMinutes || 180)} min</dd></div>
        <div><dt>Conteúdos</dt><dd>${contentCount}</dd></div>
        <div><dt>Questões</dt><dd>${questionCount}</dd></div>
      </dl>
      <div class="admin-row-actions">
        ${isDeleted ? `
          <button class="button button-primary button-small" type="button"
            data-restore-lesson="${escapeHtml(lesson.lessonId)}">
            Restaurar
          </button>
          <button class="button button-secondary button-small" type="button"
            data-edit-lesson="${escapeHtml(lesson.lessonId)}">
            Rever dados
          </button>
        ` : `
          <button class="button button-secondary button-small" type="button"
            data-manage-lesson-access="${escapeHtml(lesson.lessonId)}">
            Gerir estados
          </button>
          <button class="button button-secondary button-small" type="button"
            data-edit-lesson="${escapeHtml(lesson.lessonId)}">
            Editar módulo
          </button>
          <button class="button button-danger button-small" type="button"
            data-delete-lesson="${escapeHtml(lesson.lessonId)}">
            Eliminar
          </button>
        `}
      </div>
    </article>
  `;
}

function groupCardTemplate(item) {
  const group = item.group || item;
  const isDeleted = group.status === 'DELETED';
  return `
    <article class="course-module-card">
      <div>
        <span class="status-pill ${statusClass(group.status)}">${statusLabel(group.status)}</span>
        <h3>${escapeHtml(group.name)}</h3>
        <p>${escapeHtml(group.groupCode || group.groupId)} · ${escapeHtml(formatDate(group.startDate))} até ${escapeHtml(formatDate(group.endDate))}</p>
      </div>
      <dl>
        <div><dt>Membros</dt><dd>${item.memberCount || 0}</dd></div>
        <div><dt>Curso</dt><dd>${escapeHtml(group.courseId)}</dd></div>
        <div><dt>Início</dt><dd>${escapeHtml(formatDate(group.startDate))}</dd></div>
        <div><dt>Fim</dt><dd>${escapeHtml(formatDate(group.endDate))}</dd></div>
        <div><dt>Estado</dt><dd>${escapeHtml(statusLabel(group.status))}</dd></div>
      </dl>
      <div class="admin-row-actions">
        ${isDeleted ? `
          <button class="button button-primary button-small" type="button"
            data-restore-group="${escapeHtml(group.groupId)}">
            Restaurar
          </button>
          <button class="button button-secondary button-small" type="button"
            data-edit-group="${escapeHtml(group.groupId)}">
            Rever dados
          </button>
        ` : `
          <button class="button button-secondary button-small" type="button"
            data-edit-group="${escapeHtml(group.groupId)}">
            Gerir turma
          </button>
          <button class="button button-danger button-small" type="button"
            data-delete-group="${escapeHtml(group.groupId)}">
            Eliminar
          </button>
        `}
      </div>
    </article>
  `;
}

async function showLessonAccessDialog(lessonId) {
  const lessonItem = (state.courseStructure?.lessons || []).find((item) => item.lesson?.lessonId === lessonId);
  const lesson = lessonItem?.lesson;
  const courseId = lesson?.courseId || state.courseStructure?.course?.courseId || state.selectedCourseId;
  if (!lesson || !courseId) return;

  let students = state.students || [];
  try {
    const result = await api.adminStudents({ limit: 500 }, { force: true });
    students = result.students || [];
  } catch {
    students = state.students || [];
  }

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>Gestão do módulo</h2>
      <p class="dialog-helper-text">
        Aula ${escapeHtml(lesson.lessonNumber)} - ${escapeHtml(lesson.title)}
      </p>
      <form id="lessonAccessDialogForm" class="form-stack">
        <input type="hidden" name="courseId" value="${escapeHtml(courseId)}">
        <input type="hidden" name="lessonId" value="${escapeHtml(lesson.lessonId)}">
        <div class="assessment-management-fields">
          <label>
            <span>Acesso ao conteúdo</span>
            <select name="contentAccessStatus">
              <option value="UNCHANGED">Não alterar</option>
              <option value="AVAILABLE">Disponível para leitura</option>
              <option value="LOCKED">Conteúdo bloqueado</option>
            </select>
          </label>
          <label>
            <span>Estado da avaliação</span>
            <select name="evaluationStatus">
              <option value="UNCHANGED">Não alterar</option>
              <option value="NOT_STARTED">Não iniciada</option>
              <option value="IN_PROGRESS">Em curso</option>
              <option value="UNDER_REVIEW">Em avaliação</option>
              <option value="CORRECTION_REQUIRED">Correção solicitada</option>
              <option value="APPROVED">Aprovada</option>
              <option value="FAILED">Não aprovada</option>
              <option value="TIME_EXCEEDED">Tempo excedido</option>
            </select>
          </label>
          <label>
            <span>Tempo de submissão (min)</span>
            <input type="number" name="submissionDurationMinutes" min="1" max="43200"
              value="${escapeHtml(lesson.submissionDurationMinutes || 180)}">
          </label>
        </div>
        <p class="field-hint">A leitura e a avaliação são controladas separadamente.</p>
        <fieldset class="group-student-picker">
          <legend>Estudantes</legend>
          ${selectAllToolbar('studentIds')}
          <div class="video-student-list">
            ${moduleAccessStudentCheckboxes(courseId, students)}
          </div>
        </fieldset>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Aplicar alterações</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  bindDialogClose(overlay);
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  bindSelectAllControls(overlay);
  overlay.querySelector('#lessonAccessDialogForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const studentIds = values.getAll('studentIds');
    const changesProgress = values.get('contentAccessStatus') !== 'UNCHANGED'
      || values.get('evaluationStatus') !== 'UNCHANGED';
    const changesDuration = Boolean(values.get('submissionDurationMinutes'));

    if (changesProgress && !studentIds.length) {
      showToast('Selecione pelo menos um estudante.', 'warning');
      return;
    }
    if (!changesProgress && !changesDuration) {
      showToast('Escolha pelo menos uma alteração.', 'warning');
      return;
    }

    if (!confirmAdminAction('Deseja aplicar estas alterações ao módulo e aos estudantes selecionados?')) {
      return;
    }

    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, 'A aplicar...');
    try {
      const result = await api.adminManageLessonProgress({
        courseId: values.get('courseId'),
        contentAccessStatus: values.get('contentAccessStatus'),
        evaluationStatus: values.get('evaluationStatus'),
        submissionDurationMinutes: values.get('submissionDurationMinutes'),
        lessonIds: [values.get('lessonId')],
        studentIds,
        groupIds: []
      });
      showToast(`Gestão atualizada para ${result.studentCount || studentIds.length} estudante(s).`, 'success');
      overlay.remove();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

function moduleAccessStudentCheckboxes(courseId, students) {
  const courseStudents = (students || []).filter(({ enrollments }) => {
    return (enrollments || []).some((enrollment) => enrollment.courseId === courseId);
  });

  if (!courseStudents.length) {
    return '<p class="empty-note">Sem estudantes inscritos neste curso.</p>';
  }

  return courseStudents.map(({ student }) => `
    <label class="video-student-option">
      <input type="checkbox" name="studentIds" value="${escapeHtml(student.studentId)}">
      <span>
        <strong>${escapeHtml(studentPublicIdLabel(student.publicStudentId))} - ${escapeHtml(student.fullName)}</strong>
        <small>${escapeHtml(student.email)}</small>
      </span>
    </label>
  `).join('');
}

async function saveCourse(event) {
  event.preventDefault();

  if (!confirmAdminAction('Deseja guardar as alterações deste curso?')) return;

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = Object.fromEntries(new FormData(form));
  values.totalHours = Number(values.totalHours || 0);
  values.passingScore = Number(values.passingScore || 0);

  setBusy(button, true, 'A guardar...');

  try {
    const result = await api.adminSaveCourse(values);
    state.selectedCourseId = result.course?.courseId || values.courseId || state.selectedCourseId;
    state.courseMode = 'detail';
    showToast('Curso guardado.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteCurrentCourse() {
  const course = state.courseStructure?.course;
  if (!course?.courseId) return;
  if (!confirmAdminAction('Tem a certeza de que deseja eliminar este curso? O histórico fica preservado, mas o curso deixa de estar ativo.')) return;

  try {
    await api.adminSaveCourse({
      ...course,
      status: 'DELETED'
    });
    showToast('Curso eliminado.', 'success');
    state.selectedCourseId = '';
    state.courseMode = 'list';
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

async function restoreCourse(courseId) {
  const found = (state.courses || []).find((item) => item.course?.courseId === courseId);
  const course = found?.course;
  if (!course) return;
  if (!confirmAdminAction(`Restaurar o curso "${course.title || course.courseCode || course.courseId}"?`)) return;

  try {
    const result = await api.adminSaveCourse({
      ...course,
      status: 'ACTIVE'
    });
    state.selectedCourseId = result.course?.courseId || course.courseId;
    state.courseMode = 'detail';
    showToast('Curso restaurado.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

async function deleteLesson(lessonId) {
  const found = (state.courseStructure?.lessons || []).find((item) => item.lesson?.lessonId === lessonId);
  const lesson = found?.lesson;
  if (!lesson) return;
  if (!confirmAdminAction(`Eliminar o módulo "${lesson.title}"?`)) return;

  try {
    await api.adminSaveLesson({
      ...lesson,
      status: 'DELETED'
    });
    showToast('Módulo eliminado.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

async function restoreLesson(lessonId) {
  const found = (state.courseStructure?.lessons || []).find((item) => item.lesson?.lessonId === lessonId);
  const lesson = found?.lesson;
  if (!lesson) return;
  if (!confirmAdminAction(`Restaurar o módulo "${lesson.title}"?`)) return;

  try {
    await api.adminSaveLesson({
      ...lesson,
      status: 'ACTIVE'
    });
    showToast('Módulo restaurado.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

async function deleteGroup(groupId) {
  const found = (state.groups || []).find((item) => item.group?.groupId === groupId);
  const group = found?.group;
  if (!group) return;
  if (!confirmAdminAction(`Eliminar a turma "${group.name}"?`)) return;

  try {
    await api.adminSaveGroup({
      ...group,
      status: 'DELETED',
      studentIds: []
    });
    showToast('Turma eliminada.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

async function restoreGroup(groupId) {
  const found = (state.groups || []).find((item) => item.group?.groupId === groupId);
  const group = found?.group;
  if (!group) return;
  if (!confirmAdminAction(`Restaurar a turma "${group.name}"?`)) return;

  try {
    await api.adminSaveGroup({
      ...group,
      status: 'ACTIVE'
    });
    showToast('Turma restaurada.', 'success');
    await loadCourses();
  } catch (error) {
    handleAdminError(error);
  }
}

function showCourseDialog() {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>Novo curso</h2>
      <form id="newCourseForm" class="form-stack">
        <label>
          <span>Código</span>
          <input name="courseCode" required>
        </label>
        <label>
          <span>Título</span>
          <input name="title" required>
        </label>
        <label>
          <span>Descrição</span>
          <textarea name="description" rows="4"></textarea>
        </label>
        <div class="course-form-grid">
          <label>
            <span>Total de horas</span>
            <input type="number" name="totalHours" min="0" value="0">
          </label>
          <label>
            <span>Nota minima</span>
            <input type="number" name="passingScore" min="0" max="100" value="60">
          </label>
          <label>
            <span>Estado</span>
            <select name="status">
              ${studentFilterOption('ACTIVE', 'Ativo', 'ACTIVE')}
              ${studentFilterOption('INACTIVE', 'Inativo', 'ACTIVE')}
            </select>
          </label>
        </div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Criar curso</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#newCourseForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!confirmAdminAction('Deseja criar este curso?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    values.totalHours = Number(values.totalHours || 0);
    values.passingScore = Number(values.passingScore || 0);
    setBusy(button, true, 'A criar...');
    try {
      const result = await api.adminSaveCourse(values);
      state.selectedCourseId = result.course.courseId;
      state.courseMode = 'detail';
      state.courseView = 'overview';
      showToast('Curso criado.', 'success');
      overlay.remove();
      await loadCourses();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

function showGroupDialog(groupId = '') {
  const found = (state.groups || []).find((item) => item.group.groupId === groupId);
  const group = found?.group || {
    courseId: state.courseStructure?.course?.courseId || state.selectedCourseId || config.courseId,
    groupCode: '',
    name: '',
    startDate: '',
    endDate: '',
    status: 'ACTIVE'
  };
  const activeStudentIds = groupId ? activeStudentIdsForGroup(groupId) : [];

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>${groupId ? 'Gerir turma' : 'Nova turma'}</h2>
      <form id="groupForm" class="form-stack">
        <input type="hidden" name="groupId" value="${escapeHtml(group.groupId || '')}">
        <input type="hidden" name="courseId" value="${escapeHtml(group.courseId)}">
        <label>
          <span>Nome da turma</span>
          <input name="name" value="${escapeHtml(group.name || '')}" required>
        </label>
        <label>
          <span>Código</span>
          <input name="groupCode" value="${escapeHtml(group.groupCode || '')}" placeholder="opcional">
        </label>
        <div class="course-form-grid">
          <label>
            <span>Início</span>
            <input type="date" name="startDate" value="${escapeHtml(dateInputValue(group.startDate))}">
          </label>
          <label>
            <span>Fim</span>
            <input type="date" name="endDate" value="${escapeHtml(dateInputValue(group.endDate))}">
          </label>
          <label>
            <span>Estado</span>
            <select name="status">
              ${studentFilterOption('ACTIVE', 'Ativa', group.status || 'ACTIVE')}
              ${studentFilterOption('INACTIVE', 'Inativa', group.status || 'ACTIVE')}
            </select>
          </label>
        </div>
        <fieldset class="group-student-picker">
          <legend>Estudantes da turma</legend>
          ${selectAllToolbar('studentIds')}
          <div class="video-student-list">
            ${state.students.length ? state.students.map(({ student }) => `
              <label class="video-student-option">
                <input type="checkbox" name="studentIds" value="${escapeHtml(student.studentId)}"
                  ${activeStudentIds.includes(student.studentId) ? 'checked' : ''}>
                <span>
                  <strong>${escapeHtml(studentPublicIdLabel(student.publicStudentId))} · ${escapeHtml(student.fullName)}</strong>
                  <small>${escapeHtml(student.email)}</small>
                </span>
              </label>
            `).join('') : '<p class="empty-note">Carregue a secção Estudantes antes de gerir membros.</p>'}
          </div>
        </fieldset>
        <div class="dialog-actions">
          ${groupId ? '<button class="button button-danger" type="button" data-delete-dialog-group>Eliminar turma</button>' : ''}
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar turma</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-delete-dialog-group]')?.addEventListener('click', async () => {
    overlay.remove();
    await deleteGroup(group.groupId);
  });
  bindSelectAllControls(overlay);
  overlay.querySelector('#groupForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!confirmAdminAction('Deseja guardar esta turma e os seus estudantes?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    values.studentIds = new FormData(form).getAll('studentIds');
    setBusy(button, true, 'A guardar...');
    try {
      await api.adminSaveGroup(values);
      showToast('Turma guardada.', 'success');
      overlay.remove();
      await loadCourses();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

function activeStudentIdsForGroup(groupId) {
  return state.students
    .filter(({ memberships }) => (memberships || []).some((member) => member.groupId === groupId && member.status === 'ACTIVE'))
    .map(({ student }) => student.studentId);
}

function dateInputValue(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0, 10);
}

function showLessonDialog(lessonId = '') {
  const lessons = state.courseStructure?.lessons || [];
  const found = lessons.find((item) => item.lesson?.lessonId === lessonId);
  const lesson = found?.lesson || {
    courseId: state.courseStructure?.course?.courseId || config.courseId,
    lessonNumber: lessons.length + 1,
    title: '',
    slug: '',
    summary: '',
    theoryMinutes: 0,
    exerciseMinutes: 0,
    individualMinutes: 0,
    submissionDurationMinutes: 180,
    passingScore: state.courseStructure?.course?.passingScore || 60,
    prerequisiteLessonId: '',
    status: 'ACTIVE'
  };

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>${lessonId ? 'Editar módulo' : 'Novo módulo'}</h2>
      <form id="lessonForm" class="form-stack">
        <input type="hidden" name="lessonId" value="${escapeHtml(lesson.lessonId || '')}">
        <input type="hidden" name="courseId" value="${escapeHtml(lesson.courseId || state.courseStructure?.course?.courseId || config.courseId)}">
        <div class="course-form-grid">
          <label>
            <span>Número</span>
            <input type="number" name="lessonNumber" min="1" value="${escapeHtml(lesson.lessonNumber || 1)}" required>
          </label>
          <label>
            <span>Nota minima</span>
            <input type="number" name="passingScore" min="0" max="100" value="${escapeHtml(lesson.passingScore || 60)}">
          </label>
          <label>
            <span>Estado</span>
            <select name="status">
              ${studentFilterOption('ACTIVE', 'Ativo', lesson.status || 'ACTIVE')}
              ${studentFilterOption('INACTIVE', 'Inativo', lesson.status || 'ACTIVE')}
            </select>
          </label>
        </div>
        <label>
          <span>Título</span>
          <input name="title" value="${escapeHtml(lesson.title || '')}" required>
        </label>
        <label>
          <span>Slug</span>
          <input name="slug" value="${escapeHtml(lesson.slug || '')}" placeholder="gerado automaticamente se vazio">
        </label>
        <label>
          <span>Resumo</span>
          <textarea name="summary" rows="4">${escapeHtml(lesson.summary || '')}</textarea>
        </label>
        <div class="course-form-grid">
          <label>
            <span>Teoria (min)</span>
            <input type="number" name="theoryMinutes" min="0" value="${escapeHtml(lesson.theoryMinutes || 0)}">
          </label>
          <label>
            <span>Exercicios (min)</span>
            <input type="number" name="exerciseMinutes" min="0" value="${escapeHtml(lesson.exerciseMinutes || 0)}">
          </label>
          <label>
            <span>Individual (min)</span>
            <input type="number" name="individualMinutes" min="0" value="${escapeHtml(lesson.individualMinutes || 0)}">
          </label>
          <label>
            <span>Tempo de submissão (min)</span>
            <input type="number" name="submissionDurationMinutes" min="1" max="43200"
              value="${escapeHtml(lesson.submissionDurationMinutes || 180)}" required>
          </label>
        </div>
        <label>
          <span>Módulo pre-requisito</span>
          <select name="prerequisiteLessonId">
            ${studentFilterOption('', 'Sem pre-requisito', lesson.prerequisiteLessonId || '')}
            ${lessons
              .filter((item) => item.lesson?.lessonId !== lesson.lessonId)
              .map((item) => studentFilterOption(item.lesson.lessonId, `Aula ${item.lesson.lessonNumber} - ${item.lesson.title}`, lesson.prerequisiteLessonId || ''))
              .join('')}
          </select>
        </label>
        <div class="dialog-actions">
          ${lessonId ? '<button class="button button-danger" type="button" data-delete-dialog-lesson>Eliminar módulo</button>' : ''}
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar módulo</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('[data-cancel-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-delete-dialog-lesson]')?.addEventListener('click', async () => {
    overlay.remove();
    await deleteLesson(lesson.lessonId);
  });
  overlay.querySelector('#lessonForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!confirmAdminAction('Deseja guardar este módulo?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    ['lessonNumber', 'passingScore', 'theoryMinutes', 'exerciseMinutes', 'individualMinutes', 'submissionDurationMinutes'].forEach((field) => {
      values[field] = Number(values[field] || 0);
    });

    setBusy(button, true, 'A guardar...');
    try {
      await api.adminSaveLesson(values);
      showToast('Módulo guardado.', 'success');
      overlay.remove();
      await loadCourses();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

async function renderVideos(options = {}) {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar vídeos…');
  await loadAdminMediaConfig(options);
  await ensureStudentsForMedia(options);
  const videos = videoGallery();

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Galeria</p>
        <h1>Vídeos</h1>
      </div>
    </div>

    <section class="admin-video-panel">
      <form id="adminVideoForm" class="admin-video-form">
        <label>
          <span>Título</span>
          <input name="title" required placeholder="Ex.: Aula inaugural">
        </label>
        <label>
          <span>Link YouTube ou Vimeo</span>
          <input type="url" name="url" required placeholder="https://www.youtube.com/watch?v=...">
        </label>
        <label class="admin-video-description">
          <span>Descrição opcional</span>
          <textarea name="description" rows="3" placeholder="Breve contexto para os estudantes"></textarea>
        </label>
        <label>
          <span>Visibilidade</span>
          <select name="visibility" id="videoVisibility">
            <option value="PUBLIC">Todos os estudantes</option>
            <option value="SELECTED">Apenas emails selecionados</option>
          </select>
        </label>
        <fieldset class="video-student-access" id="videoStudentAccess" disabled>
          <legend>Estudantes autorizados</legend>
          ${selectAllToolbar('allowedStudents')}
          <div class="video-student-list">
            ${studentVideoCheckboxes()}
          </div>
        </fieldset>
        <button class="button button-primary" type="submit">Publicar video</button>
      </form>
    </section>

    <section class="admin-video-list ${videos.length ? '' : 'is-empty'}">
      ${videos.length
        ? videos.map((video) => `
          <article class="admin-video-card">
            <div>
              <h3>${escapeHtml(video.title)}</h3>
              <p>${escapeHtml(video.description || 'Sem descrição.')}</p>
              <small>${escapeHtml(videoAccessLabel(video))}</small>
              <a href="${escapeHtml(video.url)}" target="_blank" rel="noopener">Abrir link original</a>
            </div>
            <button type="button" data-delete-video="${escapeHtml(video.id)}">Remover</button>
          </article>
        `).join('')
        : '<div class="video-empty">Nenhum video publicado.</div>'}
    </section>
  `;

  document.querySelector('#adminVideoForm').addEventListener('submit', saveVideo);
  document.querySelector('#videoVisibility').addEventListener('change', updateVideoAccessState);
  bindSelectAllControls(root);
  updateVideoAccessState();
  root.querySelectorAll('[data-delete-video]').forEach((button) => {
    button.addEventListener('click', () => deleteVideo(button.dataset.deleteVideo));
  });

  reportHeight();
}

async function renderBrandSettings() {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar marca…');
  await loadAdminMediaConfig();

  const rawLogoUrl = state.media.logoUrl || '';
  const displayLogo = brandLogoUrl();

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Identidade visual</p>
        <h1>Marca</h1>
      </div>
    </div>

    <section class="brand-settings-panel">
      <div class="brand-preview-card">
        <div class="brand-preview-symbol${displayLogo ? ' has-brand-logo' : ''}">
          ${displayLogo ? `<img src="${escapeHtml(displayLogo)}" alt="Logotipo">` : 'LSS'}
        </div>
        <div>
          <h2>Logotipo da plataforma</h2>
          <p>Este logotipo substitui o monograma LSS no cabeçalho, nos cartões de início de sessão, no painel administrativo e nos certificados.</p>
        </div>
      </div>

      <form id="brandLogoForm" class="brand-logo-form">
        <label>
          <span>Link da imagem</span>
          <input type="url" name="logoUrl" value="${escapeHtml(rawLogoUrl)}"
            placeholder="https://drive.google.com/file/d/.../view ou https://.../logo.png">
        </label>
        <div class="brand-logo-actions">
          <button class="button button-primary" type="submit">Guardar logotipo</button>
          <button class="button button-secondary" type="button" id="removeBrandLogo"
            ${rawLogoUrl ? '' : 'disabled'}>Remover</button>
        </div>
      </form>
    </section>
  `;

  document.querySelector('#brandLogoForm').addEventListener('submit', saveBrandLogo);
  document.querySelector('#removeBrandLogo').addEventListener('click', removeBrandLogo);
  reportHeight();
}

async function saveBrandLogo(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const rawUrl = String(new FormData(form).get('logoUrl') || '').trim();

  if (!imageDisplayUrl(rawUrl)) {
    showToast('Adicione um link válido para a imagem do logotipo.', 'warning');
    form.elements.logoUrl.focus();
    return;
  }

  setBusy(button, true, 'A guardar…');
  try {
    state.media.logoUrl = rawUrl;
    await saveMediaConfig();
    applyBrandLogo();
    showToast('Logotipo atualizado.', 'success');
    await renderBrandSettings();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function removeBrandLogo() {
  try {
    state.media.logoUrl = '';
    await saveMediaConfig();
    applyBrandLogo();
    showToast('Logotipo removido.', 'success');
    await renderBrandSettings();
  } catch (error) {
    handleAdminError(error);
  }
}

async function ensureStudentsForMedia(options = {}) {
  if (state.students.length && !options.force) return;

  try {
    const result = await api.adminStudents({ limit: 500 }, options);
    state.students = result.students || [];
  } catch {
    state.students = [];
  }
}

function studentVideoCheckboxes() {
  if (!state.students.length) {
    return '<p class="empty-note">Nenhum estudante disponível para seleção.</p>';
  }

  return state.students.map(({ student }) => `
    <label class="video-student-option">
      <input type="checkbox" name="allowedStudents" value="${escapeHtml(student.email)}">
      <span>
        <strong>${escapeHtml(student.fullName)}</strong>
        <small>${escapeHtml(student.email)}</small>
      </span>
    </label>
  `).join('');
}

function updateVideoAccessState() {
  const visibility = document.querySelector('#videoVisibility');
  const access = document.querySelector('#videoStudentAccess');
  if (!visibility || !access) return;
  access.disabled = visibility.value !== 'SELECTED';
  access.classList.toggle('is-disabled', access.disabled);
}

async function saveVideo(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const url = String(values.get('url') || '').trim();
  const visibility = String(values.get('visibility') || 'PUBLIC');
  const allowedEmails = visibility === 'SELECTED'
    ? normalizeEmailList(values.getAll('allowedStudents'))
    : [];

  if (!videoEmbedUrl(url)) {
    showToast('Adicione um link válido do YouTube ou Vimeo.', 'warning');
    form.elements.url.focus();
    return;
  }

  if (visibility === 'SELECTED' && !allowedEmails.length) {
    showToast('Informe pelo menos um email autorizado.', 'warning');
    form.querySelector('[name="allowedStudents"]')?.focus();
    return;
  }

  setBusy(button, true, 'A publicar…');
  const videos = videoGallery();
  videos.unshift({
    id: String(Date.now()),
    title: String(values.get('title') || '').trim(),
    url,
    description: String(values.get('description') || '').trim(),
    visibility,
    allowedEmails,
    status: 'ACTIVE'
  });

  try {
    state.media.videos = videos;
    await saveMediaConfig();
    showToast('Video publicado na galeria.', 'success');
    await renderVideos();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteVideo(videoId) {
  if (!window.confirm('Remover este video da galeria?')) return;

  try {
    state.media.videos = videoGallery().filter((video) => video.id !== videoId);
    await saveMediaConfig();
    showToast('Video removido.', 'success');
    await renderVideos();
  } catch (error) {
    handleAdminError(error);
  }
}

function videoGallery() {
  return state.media.videos.filter((video) => video?.id && videoEmbedUrl(video.url));
}

function videoAccessLabel(video) {
  if (video.visibility === 'SELECTED') {
    const count = normalizeEmailList(video.allowedEmails).length;
    return `Visível para ${count} estudante${count === 1 ? '' : 's'}`;
  }

  return 'Visível para todos os estudantes';
}

function videoEmbedUrl(rawUrl) {
  if (!rawUrl) return '';

  try {
    const url = new URL(rawUrl);
    const host = url.hostname.replace(/^www\./, '');

    if (host === 'youtu.be') {
      const id = url.pathname.split('/').filter(Boolean)[0];
      return id ? `https://www.youtube.com/embed/${encodeURIComponent(id)}` : '';
    }

    if (host.endsWith('youtube.com')) {
      const watchId = url.searchParams.get('v');
      if (watchId) return `https://www.youtube.com/embed/${encodeURIComponent(watchId)}`;

      const parts = url.pathname.split('/').filter(Boolean);
      const marker = parts.findIndex((part) => ['embed', 'shorts', 'live'].includes(part));
      const id = marker >= 0 ? parts[marker + 1] : '';
      return id ? `https://www.youtube.com/embed/${encodeURIComponent(id)}` : '';
    }

    if (host.endsWith('vimeo.com')) {
      const id = url.pathname.split('/').filter(Boolean).find((part) => /^\d+$/.test(part));
      return id ? `https://player.vimeo.com/video/${encodeURIComponent(id)}` : '';
    }
  } catch {
    return '';
  }

  return '';
}

function showStudentDialog() {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card">
      <button class="dialog-close" type="button">x</button>
      <h2>Adicionar estudante</h2>

      <form id="newStudentForm" class="form-stack">
        <label>
          <span>Nome completo</span>
          <input name="fullName" required>
        </label>
        <label>
          <span>Email</span>
          <input type="email" name="email" required>
        </label>
        <label>
          <span>País</span>
          <input name="country" value="Moçambique">
        </label>
        <label>
          <span>Organização</span>
          <input name="organization">
        </label>
        <button class="button button-primary button-block" type="submit">
          Criar estudante
        </button>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.querySelector('.dialog-close').addEventListener('click', () => {
    overlay.remove();
  });

  overlay.querySelector('#newStudentForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const form = event.currentTarget;
    const button = form.querySelector('button');
    const values = Object.fromEntries(new FormData(form));

    setBusy(button, true, 'A criar…');

    try {
      const result = await api.adminCreateStudent(values);
      window.alert(
        `Estudante criado.\n\nPalavra-passe temporária: ${result.accessCode}\n\nGuarde a palavra-passe antes de fechar.`
      );
      overlay.remove();
      await loadStudents();
    } catch (error) {
      handleAdminError(error);
    } finally {
      setBusy(button, false);
    }
  });
}

async function resetAccess(studentId) {
  if (!window.confirm('Gerar um novo código e encerrar as sessões atuais?')) return;

  try {
    const result = await api.adminResetAccess(studentId);
    window.alert(
      `Nova palavra-passe temporária: ${result.accessCode}\n\nGuarde-a antes de fechar.`
    );
  } catch (error) {
    handleAdminError(error);
  }
}

async function toggleStudent(studentId, currentStatus) {
  const next = currentStatus === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE';

  if (!window.confirm(`Alterar o estado para ${statusLabel(next)}?`)) return;

  try {
    await api.adminSetStudentStatus(studentId, next);
    await loadStudents();
  } catch (error) {
    handleAdminError(error);
  }
}

function loadingTemplate(message) {
  return `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function initializeThemeToggle() {
  if (!themeToggle) return;

  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('lssTheme', theme);
    const icon = themeToggle.querySelector('.theme-toggle-icon img');
    if (icon) {
      icon.dataset.iconColor = blueIcon;
      icon.src = iconUrl(theme === 'dark' ? 'sun' : 'moon', blueIcon);
    }
    updateThemeIcons(theme);
    themeToggle.title = theme === 'dark' ? 'Usar modo claro' : 'Usar modo noturno';
    themeToggle.setAttribute('aria-label', themeToggle.title);
  };

  applyTheme(document.documentElement.dataset.theme || 'light');

  themeToggle.addEventListener('click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(nextTheme);
  });
}

function iconUrl(name, color) {
  const resolvedColor = document.documentElement.dataset.theme === 'dark' ? 'ffffff' : color;
  const iconName = lucideIconAliases[name] || name;
  return `${lucideIconsBase}/${encodeURIComponent(iconName)}.svg?color=%23${resolvedColor}&width=20&height=20`;
}

function updateThemeIcons(theme) {
  document.querySelectorAll(`img[src^="${lucideIconsBase}/"]`).forEach((image) => {
    const url = new URL(image.src);
    const currentColor = (url.searchParams.get('color') || '').replace('#', '').toLowerCase();
    const originalColor = image.dataset.iconColor || (currentColor === 'ffffff' ? goldIcon : currentColor);
    image.dataset.iconColor = originalColor;
    url.searchParams.set('color', `#${theme === 'dark' ? 'ffffff' : originalColor}`);
    image.src = url.toString();
  });
}

function brandSymbolTemplate(className) {
  const logo = brandLogoUrl();
  return `
    <div class="${className}${logo ? ' has-brand-logo' : ''}">
      ${logo ? `<img src="${escapeHtml(logo)}" alt="LMTWEBNAIRS">` : 'LSS'}
    </div>
  `;
}

function applyBrandLogo() {
  document.querySelectorAll('.site-brand-symbol, .brand-mark, .admin-sidebar-symbol').forEach((symbol) => {
    const logo = brandLogoUrl();
    symbol.classList.toggle('has-brand-logo', Boolean(logo));
    symbol.innerHTML = logo ? `<img src="${escapeHtml(logo)}" alt="LMTWEBNAIRS">` : 'LSS';
  });
}

function brandLogoUrl() {
  const rawUrl = state.media.logoUrl || localStorage.getItem('lssLogoUrl') || '';
  return imageDisplayUrl(rawUrl);
}

async function loadPublicMediaConfig() {
  try {
    const result = await api.publicMediaConfig();
    setMediaConfig(result.mediaConfig || result);
  } catch {
    setMediaConfig(localMediaConfig());
  }
}

async function loadAdminMediaConfig(options = {}) {
  try {
    const result = await api.adminMediaConfig(options);
    setMediaConfig(result.mediaConfig || result);
  } catch {
    setMediaConfig(localMediaConfig());
    showToast('Conteúdo multimédia carregado localmente. Confirme a ligação à API Python para sincronizar com o Supabase.', 'warning');
  }
}

async function saveMediaConfig() {
  const mediaConfig = {
    logoUrl: state.media.logoUrl,
    videos: state.media.videos
  };

  const result = await api.adminSaveMediaConfig(mediaConfig);
  setMediaConfig(result.mediaConfig || mediaConfig);
  localStorage.setItem('lssLogoUrl', state.media.logoUrl || '');
  localStorage.setItem('lssVideoGallery', JSON.stringify(state.media.videos));
}

function setMediaConfig(mediaConfig = {}) {
  state.media.logoUrl = mediaConfig.logoUrl || '';
  state.media.videos = Array.isArray(mediaConfig.videos) ? mediaConfig.videos : [];
}

function localMediaConfig() {
  return {
    logoUrl: localStorage.getItem('lssLogoUrl') || '',
    videos: localVideoGallery()
  };
}

function localVideoGallery() {
  try {
    const parsed = JSON.parse(localStorage.getItem('lssVideoGallery') || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function normalizeEmailList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
  }

  return String(value || '')
    .split(/[\n,;]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function imageDisplayUrl(rawUrl) {
  if (!rawUrl) return '';

  try {
    const url = new URL(rawUrl);
    const host = url.hostname.replace(/^www\./, '');

    if (host === 'drive.google.com') {
      const queryId = url.searchParams.get('id');
      const pathId = url.pathname.match(/\/file\/d\/([^/]+)/)?.[1];
      const id = queryId || pathId;
      return id ? `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w400` : rawUrl;
    }

    return rawUrl;
  } catch {
    return '';
  }
}

function handleAdminError(error) {
  console.error(error);

  if (
    error instanceof ApiError &&
    ['INVALID_SESSION', 'SESSION_EXPIRED', 'ADMIN_SESSION_REQUIRED'].includes(error.code)
  ) {
    sessionStorage.removeItem('courseAdminToken');
    renderAdminLogin();
  }

  showToast(error.message || 'Ocorreu um erro.', 'error');
}
