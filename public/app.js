import { CoursePlatformApi, ApiError } from './api.js';
import {
  debounce,
  escapeHtml,
  formatBytes,
  formatDate,
  formatDuration,
  parseSelectedOptions,
  renderMath,
  reportHeight,
  safeHtml,
  setBusy,
  showToast,
  statusClass,
  statusLabel
} from './utils.js';

const config = window.COURSE_PLATFORM_CONFIG;
const root = document.querySelector('#app');
const headerUser = document.querySelector('#headerUser');
const logoutButton = document.querySelector('#logoutButton');
const themeToggle = document.querySelector('#themeToggle');
const mobileMenuButton = document.querySelector('#mobileMenuButton');
const mobileMenu = document.querySelector('#mobileMenu');
const mobileThemeButton = document.querySelector('#mobileThemeButton');
const mobileLogoutButton = document.querySelector('#mobileLogoutButton');
const platformName = config.appName || 'LMTWEBNAIRS Summer School 2026';
const platformYear = 'Summer School 2026';
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
const state = {
  dashboard: null,
  myCourses: [],
  selectedCourseId: localStorage.getItem('courseSelectedCourseId') || config.courseId || '',
  lesson: null,
  attempt: null,
  attemptData: null,
  media: {
    logoUrl: '',
    videos: []
  },
  certifications: null,
  notifications: {
    items: [],
    unreadCount: 0,
    total: 0
  },
  notificationChannelInfo: null,
  push: {
    configuration: null,
    subscriptionCount: 0,
    subscribedOnDevice: false
  },
  telegramLinkToken: '',
  telegramLinkUrl: '',
  timerId: null,
  pollId: null,
  notificationPollId: null
};

let deferredInstallPrompt = null;
window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
});
window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  localStorage.setItem('coursePlatformAppInstalled', 'true');
  document.querySelector('#pushRecommendation')?.remove();
});

initialize().catch((error) => {
  console.error(error);
  renderConfigurationError(error);
});

async function initialize() {
  initializeThemeToggle();

  try {
    api = new CoursePlatformApi(config);
  } catch (error) {
    renderConfigurationError(error);
    return;
  }

  await initializePwa();

  setMediaConfig(localMediaConfig());
  applyBrandLogo();

  headerUser.addEventListener('click', openProfileFromHeader);
  document.addEventListener('error', handleProfilePhotoError, true);
  initializeMobileMenu();
  document.body.classList.toggle('sidebar-collapsed', localStorage.getItem('lssSidebarCollapsed') === 'true');
  root.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-sidebar-toggle]');
    if (!toggle) return;
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('lssSidebarCollapsed', String(collapsed));
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.setAttribute('aria-label', collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral');
    toggle.title = collapsed ? 'Expandir menu lateral' : 'Recolher menu lateral';
    const label = toggle.querySelector('span');
    if (label) label.textContent = collapsed ? 'Expandir menu' : 'Recolher menu';
  });
  logoutButton.addEventListener('click', logout);
  mobileLogoutButton?.addEventListener('click', logout);
  window.addEventListener('hashchange', route);
  window.addEventListener('message', (event) => {
    if (event.data?.source === 'tilda-parent' && event.data?.type === 'request-resize') {
      reportHeight();
    }
  });
  if (window.ResizeObserver) {
    new ResizeObserver(reportHeight).observe(document.body);
  }

  if (!api.hasStudentSession()) {
    renderLogin();
    loadPublicMediaConfig().then(applyBrandLogo);
    return;
  }

  route();
}

function isStandaloneApp() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

function isIosDevice() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) || (
    navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  );
}

function supportsWebPush() {
  return window.isSecureContext
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window;
}

async function initializePwa() {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return null;
  try {
    return await navigator.serviceWorker.register('./sw.js', { scope: './' });
  } catch (error) {
    console.warn('Não foi possível registar o service worker.', error);
    return null;
  }
}

function urlBase64ToUint8Array(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

async function refreshPushState(serverState = null) {
  if (!api?.hasStudentSession()) return state.push;
  const result = serverState || await api.pushConfiguration();
  state.push.configuration = result.pushConfiguration || {};
  state.push.subscriptionCount = Number(result.subscriptionCount || 0);
  state.push.subscribedOnDevice = false;
  if (supportsWebPush()) {
    try {
      const registration = await navigator.serviceWorker.ready;
      state.push.subscribedOnDevice = Boolean(await registration.pushManager.getSubscription());
    } catch {
      state.push.subscribedOnDevice = false;
    }
  }
  return state.push;
}

function pushDeviceLabel() {
  const platform = navigator.userAgentData?.platform || navigator.platform || 'Dispositivo';
  return `${platform} · navegador web`.slice(0, 120);
}

async function enablePushNotifications(button = null) {
  if (!supportsWebPush()) {
    showToast('Este navegador não suporta notificações Push ou a página não utiliza HTTPS.', 'error');
    return false;
  }
  if (isIosDevice() && !isStandaloneApp()) {
    showToast('No iPhone ou iPad, guarde primeiro a aplicação no ecrã principal e abra-a pelo novo ícone.', 'error');
    maybeShowPushRecommendation(true);
    return false;
  }
  const configuration = state.push.configuration || (await refreshPushState()).configuration || {};
  if (!configuration.configured || !configuration.publicKey) {
    showToast('As notificações Push ainda não estão configuradas pela administração.', 'error');
    return false;
  }
  if (Notification.permission === 'denied') {
    showToast('As notificações estão bloqueadas nas definições do navegador deste dispositivo.', 'error');
    return false;
  }
  setBusy(button, true, 'A ativar...');
  try {
    const permission = Notification.permission === 'granted'
      ? 'granted'
      : await Notification.requestPermission();
    if (permission !== 'granted') {
      showToast('A autorização para notificações não foi concedida.', 'error');
      return false;
    }
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(configuration.publicKey)
      });
    }
    await api.subscribePush(subscription.toJSON(), pushDeviceLabel());
    state.push.subscribedOnDevice = true;
    state.push.subscriptionCount = Math.max(1, state.push.subscriptionCount + 1);
    localStorage.setItem('coursePlatformPushEnabled', 'true');
    document.querySelector('#pushRecommendation')?.remove();
    showToast('Notificações Push ativadas neste dispositivo.', 'success');
    return true;
  } catch (error) {
    handleError(error);
    return false;
  } finally {
    setBusy(button, false);
  }
}

async function disablePushNotifications(button = null) {
  if (!supportsWebPush()) return false;
  setBusy(button, true, 'A desativar...');
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api.unsubscribePush(subscription.endpoint);
      await subscription.unsubscribe();
    }
    state.push.subscribedOnDevice = false;
    state.push.subscriptionCount = Math.max(0, state.push.subscriptionCount - 1);
    localStorage.removeItem('coursePlatformPushEnabled');
    showToast('Notificações Push desativadas neste dispositivo.', 'success');
    return true;
  } catch (error) {
    handleError(error);
    return false;
  } finally {
    setBusy(button, false);
  }
}

async function installWebApp(button = null) {
  if (isStandaloneApp()) {
    showToast('A aplicação já está aberta a partir do ecrã principal.', 'success');
    return true;
  }
  if (deferredInstallPrompt) {
    setBusy(button, true, 'A abrir...');
    try {
      await deferredInstallPrompt.prompt();
      const choice = await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      if (choice.outcome === 'accepted') {
        localStorage.setItem('coursePlatformAppInstalled', 'true');
        showToast('Aplicação guardada no dispositivo.', 'success');
        return true;
      }
      return false;
    } finally {
      setBusy(button, false);
    }
  }
  const guidance = isIosDevice()
    ? 'No Safari, toque em Partilhar e depois em “Adicionar ao ecrã principal”. Abra a aplicação pelo novo ícone para ativar notificações.'
    : 'Abra o menu do navegador e escolha “Instalar aplicação” ou “Adicionar ao ecrã principal”.';
  showToast(guidance, 'success');
  return false;
}

function maybeShowPushRecommendation(force = false) {
  document.querySelector('#pushRecommendation')?.remove();
  const configuration = state.push.configuration || {};
  const permissionDenied = supportsWebPush() && Notification.permission === 'denied';
  if (!configuration.configured || state.push.subscribedOnDevice || permissionDenied) return;
  const mobile = window.matchMedia('(max-width: 1024px)').matches || isIosDevice();
  if (!mobile && !force) return;
  const dismissedAt = Number(localStorage.getItem('pushRecommendationDismissedAt') || 0);
  if (!force && dismissedAt && Date.now() - dismissedAt < 7 * 24 * 60 * 60 * 1000) return;
  const installed = isStandaloneApp();
  const panel = document.createElement('aside');
  panel.id = 'pushRecommendation';
  panel.className = 'push-recommendation';
  panel.setAttribute('aria-label', 'Recomendação de notificações');
  panel.innerHTML = `
    <button class="push-recommendation-close" type="button" aria-label="Fechar recomendação">×</button>
    <div class="push-recommendation-icon"><img src="${iconUrl('bell-ring', goldIcon)}" alt=""></div>
    <div class="push-recommendation-copy">
      <strong>${installed ? 'Ative as notificações' : 'Guarde a aplicação no ecrã principal'}</strong>
      <p>${installed
        ? 'Receba avisos de novos módulos, prazos e avaliações mesmo com a plataforma fechada.'
        : 'Tenha acesso rápido e, depois de abrir pelo novo ícone, ative avisos de módulos, prazos e avaliações.'}</p>
    </div>
    <button class="button button-primary button-small" type="button" data-push-recommendation-action>${installed ? 'Ativar' : 'Guardar aplicação'}</button>
  `;
  document.body.appendChild(panel);
  panel.querySelector('.push-recommendation-close')?.addEventListener('click', () => {
    localStorage.setItem('pushRecommendationDismissedAt', String(Date.now()));
    panel.remove();
  });
  panel.querySelector('[data-push-recommendation-action]')?.addEventListener('click', async (event) => {
    if (installed) {
      await enablePushNotifications(event.currentTarget);
    } else {
      await installWebApp(event.currentTarget);
    }
  });
}

async function route() {
  closeMobileMenu();
  const hash = location.hash.replace(/^#\/?/, '');
  const [routeName, routeValue] = hash.split('/');

  if (!api.hasStudentSession()) {
    renderLogin();
    return;
  }

  try {
    if (routeName === 'lesson' && routeValue) {
      await openLesson(routeValue);
      return;
    }

    if (routeName === 'certificate' || routeName === 'certifications') {
      await renderCertifications();
      return;
    }

    if (routeName === 'profile') {
      await renderProfile();
      return;
    }

    if (routeName === 'notifications') {
      await renderNotifications();
      return;
    }

    if (['courses', 'lessons', 'submissions', 'grades'].includes(routeName)) {
      await renderDashboard(routeName);
      return;
    }

    await renderDashboard('overview');
  } catch (error) {
    handleError(error);
  }
}

function renderLogin() {
  clearTimers();
  document.querySelector('#pushRecommendation')?.remove();
  headerUser.innerHTML = '';
  headerUser.title = '';
  headerUser.removeAttribute('aria-label');
  headerUser.hidden = true;
  if (mobileMenuButton) mobileMenuButton.hidden = true;
  closeMobileMenu();
  logoutButton.hidden = true;

  root.innerHTML = `
    <section class="auth-shell">
      <div class="auth-card auth-card-modern">
        <div class="auth-card-accent">
          <img src="${iconUrl('graduation-cap', goldIcon)}" alt="">
          <span>Portal académico</span>
        </div>

        <div class="auth-brand-row">
          ${brandSymbolTemplate('brand-mark')}
          <div>
            <p class="eyebrow">LMTWEBNAIRS Summer School</p>
            <h1>Área do estudante</h1>
          </div>
        </div>

        <p class="auth-description">
          Entre na área do participante para acompanhar aulas, exercícios e avaliações num ambiente simples e bem organizado.
        </p>

        <div class="auth-feature-list" aria-label="Recursos da plataforma">
          <span><img src="${iconUrl('open-book', blueIcon)}" alt=""> Aulas</span>
          <span><img src="${iconUrl('task-completed', blueIcon)}" alt=""> Atividades</span>
          <span><img src="${iconUrl('certificate', blueIcon)}" alt=""> Certificado</span>
        </div>

        <form id="loginForm" class="form-stack">
          <label>
            <span>Email</span>
            <input type="email" name="email" autocomplete="email" required
              placeholder="estudante@email.com">
          </label>
          <label>
            <span>Palavra-passe de acesso</span>
            <input type="password" name="accessCode" autocomplete="current-password"
              required placeholder="Palavra-passe fornecida pelo administrador">
          </label>
          <button class="button button-primary button-block" type="submit">
            Entrar na plataforma
          </button>
          <button class="text-button login-recovery-link" type="button" id="recoverAccessButton">
            Esqueci a palavra-passe de acesso
          </button>
        </form>

        <div id="loginError" class="form-message form-message-error" hidden></div>
      </div>
    </section>
  `;

  document.querySelector('#loginForm').addEventListener('submit', login);
  document.querySelector('#recoverAccessButton').addEventListener('click', () => {
    const email = document.querySelector('#loginForm [name="email"]')?.value || '';
    showStudentRecoveryDialog(email);
  });
  reportHeight();
}

async function openProfileFromHeader() {
  if (!api?.hasStudentSession()) return;

  try {
    if (location.hash === '#/profile') {
      await renderProfile();
      return;
    }

    location.hash = '#/profile';
  } catch (error) {
    handleError(error);
  }
}

function initializeMobileMenu() {
  if (!mobileMenuButton || !mobileMenu) return;
  const compactNavigation = window.matchMedia('(max-width: 1024px)');

  mobileMenuButton.addEventListener('click', (event) => {
    event.stopPropagation();
    const willOpen = mobileMenu.hidden;
    mobileMenu.hidden = !willOpen;
    document.body.classList.toggle('student-menu-open', willOpen);
    mobileMenuButton.setAttribute('aria-expanded', String(willOpen));
  });

  mobileMenu.addEventListener('click', (event) => {
    const routeButton = event.target.closest('[data-mobile-route]');
    if (routeButton) {
      location.hash = routeButton.dataset.mobileRoute;
      closeMobileMenu();
      return;
    }

    if (event.target.closest('#mobileThemeButton')) {
      themeToggle?.click();
      closeMobileMenu();
    }
  });

  document.addEventListener('click', (event) => {
    if (
      mobileMenu.hidden ||
      mobileMenu.contains(event.target) ||
      mobileMenuButton.contains(event.target)
    ) {
      return;
    }

    closeMobileMenu();
  });

  compactNavigation.addEventListener('change', (event) => {
    if (!event.matches) closeMobileMenu();
  });
}

function closeMobileMenu() {
  if (!mobileMenu || !mobileMenuButton) return;
  mobileMenu.hidden = true;
  document.body.classList.remove('student-menu-open');
  mobileMenuButton.setAttribute('aria-expanded', 'false');
}

async function login(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const data = new FormData(form);
  const button = form.querySelector('button');
  const errorBox = document.querySelector('#loginError');

  errorBox.hidden = true;
  setBusy(button, true, 'A autenticar...');

  try {
    await api.login(data.get('email'), data.get('accessCode'));
    location.hash = '#/';
    await renderDashboard();
  } catch (error) {
    if (error instanceof ApiError && error.code === 'INVALID_CREDENTIALS') {
      errorBox.innerHTML = `
        <span>${escapeHtml(error.message)}</span>
        <button class="text-button" type="button" id="recoverAfterLoginError">
          Recuperar palavra-passe
        </button>
      `;
      errorBox.querySelector('#recoverAfterLoginError').addEventListener('click', () => {
        showStudentRecoveryDialog(data.get('email'));
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

function showStudentRecoveryDialog(prefilledEmail = '') {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card recovery-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <h2>Recuperar palavra-passe de acesso</h2>
      <p class="recovery-note">
        Informe o email e o ID público do estudante para gerar uma nova palavra-passe temporária.
      </p>

      <form id="studentRecoveryForm" class="form-stack">
        <label>
          <span>Email</span>
          <input type="email" name="email" autocomplete="email" required
            value="${escapeHtml(prefilledEmail || '')}" placeholder="estudante@email.com">
        </label>
        <label>
          <span>ID do estudante</span>
          <input name="publicStudentId" required placeholder="STU-00000"
            autocomplete="off" autocapitalize="characters">
        </label>

        <div id="studentRecoveryResult" class="recovery-result" hidden></div>

        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-recovery>Cancelar</button>
          <button class="button button-primary" type="submit">Gerar palavra-passe temporária</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-cancel-recovery]').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('#studentRecoveryForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    setBusy(button, true, 'A gerar...');

    try {
      const result = await api.recoverStudentAccess(values.email, values.publicStudentId);
      renderStudentRecoveryResult(overlay, result, values.email);
    } catch (error) {
      const resultBox = overlay.querySelector('#studentRecoveryResult');
      resultBox.hidden = false;
      resultBox.classList.add('is-error');
      resultBox.textContent = error.message || 'Não foi possível recuperar o acesso.';
    } finally {
      setBusy(button, false);
      reportHeight();
    }
  });
  overlay.querySelector('[name="publicStudentId"]').focus();
  reportHeight();
}

function renderStudentRecoveryResult(overlay, result, email) {
  const resultBox = overlay.querySelector('#studentRecoveryResult');
  resultBox.hidden = false;
  resultBox.classList.remove('is-error');
  resultBox.innerHTML = `
    <span>Palavra-passe temporária criada para ${escapeHtml(result.email || email)}</span>
    <strong>${escapeHtml(result.temporaryPassword || '')}</strong>
    <div class="recovery-result-actions">
      <button class="button button-secondary button-small" type="button" data-copy-temporary-password>
        Copiar palavra-passe
      </button>
      <button class="button button-primary button-small" type="button" data-use-temporary-password>
        Usar no login
      </button>
    </div>
  `;
  resultBox.querySelector('[data-copy-temporary-password]').addEventListener('click', () => {
    copyText(result.temporaryPassword || '', 'Palavra-passe temporária copiada.');
  });
  resultBox.querySelector('[data-use-temporary-password]').addEventListener('click', () => {
    const loginForm = document.querySelector('#loginForm');
    if (loginForm) {
      loginForm.elements.email.value = email || '';
      loginForm.elements.accessCode.value = result.temporaryPassword || '';
    }
    overlay.remove();
    showToast('Palavra-passe temporária preenchida no início de sessão.', 'success');
  });
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage, 'success');
  } catch {
    window.prompt('Copie o texto:', text);
  }
}

async function logout() {
  try {
    await api.logout();
  } catch {
    localStorage.removeItem('courseSessionToken');
  }

  state.dashboard = null;
  state.lesson = null;
  state.attempt = null;
  state.push.configuration = null;
  state.push.subscriptionCount = 0;
  state.push.subscribedOnDevice = false;
  location.hash = '';
  renderLogin();
}

function studentAppShell(activeView, content, page = {}) {
  const student = state.dashboard?.student || {};
  const course = state.dashboard?.course || {};
  const currentCourse = state.myCourses.find((item) => item.course?.courseId === state.selectedCourseId)?.course || course;
  const navItems = [
    { id: 'overview', label: 'Visão geral', href: '#/', icon: 'classroom' },
    { id: 'courses', label: 'Meus cursos', href: '#/courses', icon: 'book-shelf' },
    { id: 'lessons', label: 'Aulas e módulos', href: '#/lessons', icon: 'reading' },
    { id: 'submissions', label: 'Submissões', href: '#/submissions', icon: 'upload-to-cloud' },
    { id: 'grades', label: 'Notas e feedback', href: '#/grades', icon: 'checked-checkbox' },
    { id: 'notifications', label: 'Notificações', href: '#/notifications', icon: 'bell' },
    { id: 'certifications', label: 'Certificados', href: '#/certifications', icon: 'diploma' },
    { id: 'support', label: 'Suporte', href: config.institutionalUrl || '#/', icon: 'help' },
    { id: 'profile', label: 'Perfil', href: '#/profile', icon: 'user-male-circle' }
  ];
  const title = page.title || 'Painel do estudante';
  const topbarTitle = page.topbarTitle || 'Área do estudante';
  const eyebrow = page.eyebrow || 'Área do estudante';
  const description = page.description || currentCourse?.title || 'Acompanhe cursos, atividades, progresso e certificados.';
  const sidebarCollapsed = document.body.classList.contains('sidebar-collapsed');
  return `
    <div class="student-app-shell student-view-${escapeHtml(activeView)}">
      <aside class="student-sidebar" aria-label="Navegação do estudante">
        <div class="student-sidebar-heading">
          ${brandSymbolTemplate('student-sidebar-symbol')}
          <div>
            <strong>LMTWEBNAIRS</strong>
            <small>Área do estudante</small>
          </div>
        </div>
        <nav class="student-nav">
          <p>Estudos</p>
          ${navItems.map((item) => `
            <a class="${item.id === activeView ? 'is-active' : ''}" href="${escapeHtml(item.href)}"
              aria-label="${escapeHtml(item.label)}" title="${escapeHtml(item.label)}"
              ${item.id === 'support' && config.institutionalUrl ? 'target="_blank" rel="noopener"' : ''}>
              <img src="${iconUrl(item.icon, goldIcon)}" alt="">
              <span>${escapeHtml(item.label)}</span>
            </a>
          `).join('')}
        </nav>
        <button class="sidebar-collapse-button" type="button" data-sidebar-toggle
          aria-label="${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu lateral"
          aria-expanded="${String(!sidebarCollapsed)}"
          title="${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu lateral">
          <img src="${iconUrl('panel-left-close', goldIcon)}" alt="">
          <span>${sidebarCollapsed ? 'Expandir' : 'Recolher'} menu</span>
        </button>
        <a class="student-sidebar-profile" href="#/profile">
          ${profileAvatarTemplate(student, 'student-sidebar-avatar')}
          <span>
            <strong>${escapeHtml(student.fullName || 'Estudante')}</strong>
            <small>${escapeHtml(student.publicStudentId || student.email || '')}</small>
          </span>
        </a>
      </aside>
      <section class="student-main-frame">
        <div class="student-topbar">
          <div>
            <p class="breadcrumb-line">${escapeHtml(config.organizationName || 'Summer School')} / ${escapeHtml(eyebrow)}</p>
            <h1>${escapeHtml(topbarTitle)}</h1>
          </div>
          <div class="student-topbar-actions">
            <label class="global-search">
              <span class="sr-only">Pesquisar</span>
              <input type="search" placeholder="Pesquisar cursos, aulas ou certificados">
            </label>
            <a class="icon-button" href="#/certifications" aria-label="Certificados">
              <img src="${iconUrl('diploma', blueIcon)}" alt="">
            </a>
            <a class="icon-button notification-button" href="#/notifications"
              aria-label="Notificações${state.notifications.unreadCount ? `: ${state.notifications.unreadCount} não lidas` : ''}">
              <img src="${iconUrl('bell', blueIcon)}" alt="">
              ${state.notifications.unreadCount ? `<span class="notification-badge">${Math.min(state.notifications.unreadCount, 99)}</span>` : ''}
            </a>
          </div>
        </div>
        <div class="student-page-heading" ${page.compactHeading ? 'hidden' : ''}>
          <div>
            <p class="eyebrow">${escapeHtml(eyebrow)}</p>
            <h2>${escapeHtml(title)}</h2>
            <p>${escapeHtml(description)}</p>
          </div>
        </div>
        <div class="student-content-area">
          ${content}
        </div>
      </section>
    </div>
  `;
}

function normalizeStudentDashboard(home = {}) {
  const dashboard = home.dashboard || {};
  const currentCourse = (home.courses || []).find((item) => item.course?.courseId === home.selectedCourseId) || {};
  const course = dashboard.course || currentCourse.course || {};
  const enrollment = dashboard.enrollment || currentCourse.enrollment || {};
  const student = dashboard.student || home.student || {};
  const lessons = Array.isArray(dashboard.lessons) ? dashboard.lessons : [];
  const totalHours = Number(course.totalHours || course.workloadHours || 0);
  const progressPercent = Math.max(0, Math.min(100, Number(enrollment.progressPercent || 0)));

  return {
    student,
    course: {
      courseId: course.courseId || state.selectedCourseId || config.courseId || '',
      title: course.title || 'Curso',
      description: course.description || 'Curso associado ao seu perfil.',
      courseCode: course.courseCode || course.courseId || '',
      totalHours,
      status: course.status || 'ACTIVE'
    },
    enrollment: {
      ...enrollment,
      status: enrollment.status || 'ACTIVE',
      progressPercent
    },
    lessons: lessons.map((item) => {
      const progress = item.progress || { status: 'LOCKED' };
      return {
        lesson: item.lesson || {},
        progress: {
          ...progress,
          contentAccessStatus: moduleContentAccessStatus(progress),
          evaluationStatus: moduleEvaluationStatus(progress, item.activeAttempt)
        },
        activeAttempt: item.activeAttempt || null
      };
    })
  };
}

function moduleContentAccessStatus(progress = {}) {
  if (['AVAILABLE', 'LOCKED'].includes(progress.contentAccessStatus)) {
    return progress.contentAccessStatus;
  }

  return progress.status === 'LOCKED' ? 'LOCKED' : 'AVAILABLE';
}

function moduleEvaluationStatus(progress = {}, attempt = null) {
  const supported = [
    'NOT_STARTED',
    'IN_PROGRESS',
    'UNDER_REVIEW',
    'CORRECTION_REQUIRED',
    'APPROVED',
    'FAILED',
    'TIME_EXCEEDED'
  ];
  if (supported.includes(progress.evaluationStatus)) return progress.evaluationStatus;
  if (supported.includes(attempt?.status)) return attempt.status;
  return supported.includes(progress.status) ? progress.status : 'NOT_STARTED';
}

function moduleStatusPairTemplate(progress = {}, attempt = null) {
  const accessStatus = moduleContentAccessStatus(progress);
  const evaluationStatus = moduleEvaluationStatus(progress, attempt);
  return `
    <div class="module-status-pair" aria-label="Estados do módulo">
      <span class="module-status-item">
        <small>Conteúdo</small>
        <span class="status-pill ${statusClass(accessStatus)}">${escapeHtml(statusLabel(accessStatus))}</span>
      </span>
      <span class="module-status-item">
        <small>Avaliação</small>
        <span class="status-pill ${statusClass(evaluationStatus)}">${escapeHtml(statusLabel(evaluationStatus))}</span>
      </span>
    </div>
  `;
}

async function renderDashboard(view = 'overview') {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar o curso...');

  const [home, notificationData, pushData] = await Promise.all([
    api.studentHome(state.selectedCourseId),
    api.notifications({ limit: 6 }),
    api.pushConfiguration()
  ]);
  await refreshPushState(pushData);
  setNotificationState(notificationData);
  state.myCourses = Array.isArray(home.courses) ? home.courses : [];
  state.selectedCourseId = home.selectedCourseId || state.selectedCourseId || config.courseId || '';
  localStorage.setItem('courseSelectedCourseId', state.selectedCourseId);
  setMediaConfig(home.mediaConfig || {});
  applyBrandLogo();

  const dashboard = normalizeStudentDashboard(home);
  state.dashboard = dashboard;

  const greeting = studentGreeting(dashboard.student.fullName || 'Estudante');
  headerUser.innerHTML = profileAvatarTemplate(dashboard.student, 'header-avatar');
  headerUser.title = 'Editar perfil pessoal';
  headerUser.setAttribute('aria-label', 'Editar perfil pessoal');
  headerUser.hidden = false;
  if (mobileMenuButton) mobileMenuButton.hidden = false;
  logoutButton.hidden = false;

  const totalLessons = dashboard.lessons.length;
  const approvedLessons = dashboard.lessons.filter((item) => moduleEvaluationStatus(item.progress, item.activeAttempt) === 'APPROVED').length;
  const activeLessons = dashboard.lessons.filter((item) => moduleContentAccessStatus(item.progress) === 'AVAILABLE').length;
  const videos = videoGallery();
  const totalHoursLabel = dashboard.course.totalHours ? `${dashboard.course.totalHours} horas` : 'Carga horária por definir';
  const nextLessonItem = dashboard.lessons.find((item) => (
    moduleContentAccessStatus(item.progress) === 'AVAILABLE'
    && moduleEvaluationStatus(item.progress, item.activeAttempt) !== 'APPROVED'
  ))
    || dashboard.lessons.find((item) => moduleContentAccessStatus(item.progress) === 'AVAILABLE')
    || null;
  const pendingActivities = dashboard.lessons.filter((item) => (
    moduleContentAccessStatus(item.progress) === 'AVAILABLE'
    && moduleEvaluationStatus(item.progress, item.activeAttempt) !== 'APPROVED'
  )).length;
  const latestFeedbackItem = dashboard.lessons
    .filter((item) => item.activeAttempt?.reviewComments)
    .sort((left, right) => new Date(right.activeAttempt?.reviewedAt || 0) - new Date(left.activeAttempt?.reviewedAt || 0))[0] || null;
  const selectedCourseEntry = state.myCourses.find((item) => item.course?.courseId === state.selectedCourseId);
  const nextDeadlineValue = nextLessonItem?.activeAttempt?.deadlineAt || selectedCourseEntry?.group?.endDate || '';
  const nextDeadlineLabel = nextDeadlineValue ? formatDate(nextDeadlineValue) : 'Sem prazo definido';

  const certificateButton = dashboard.enrollment.status === 'COMPLETED'
    ? '<a class="button button-secondary" href="#/certifications">Minhas certificações</a>'
    : '';
  const pageMeta = {
    overview: {
      eyebrow: 'Visão geral',
      title: 'Painel do estudante',
      description: dashboard.course?.title || 'Acompanhe o seu percurso académico.',
      compactHeading: true
    },
    courses: {
      eyebrow: 'Meus cursos',
      title: 'Cursos disponíveis',
      description: 'Consulte os cursos associados ao seu perfil e escolha o percurso que pretende abrir.'
    },
    lessons: {
      eyebrow: 'Aulas e módulos',
      title: 'Conteúdos do curso',
      description: 'Acompanhe aulas, vídeos, materiais e o estado de cada módulo.'
    },
    submissions: {
      eyebrow: 'Submissões',
      title: 'Trabalhos e atividades',
      description: 'Veja o estado das atividades, submissões e revisões pendentes.'
    },
    grades: {
      eyebrow: 'Notas e feedback',
      title: 'Desempenho académico',
      description: 'Acompanhe pontuações, aprovações e feedback das atividades.'
    }
  };

  root.innerHTML = studentAppShell(view, `
    <section class="dashboard-hero">
      <div class="hero-copy">
        <p class="eyebrow">${escapeHtml(platformYear)}</p>
        <h1 class="hero-greeting">${escapeHtml(greeting)}</h1>
        <p>
          Ambiente digital para acompanhar conteúdos, exercícios e avaliações do programa.
        </p>
        <div class="hero-meta">
          <span>Programa: ${escapeHtml(dashboard.course.title)}</span>
          <span>${escapeHtml(dashboard.course.courseCode)}</span>
          <span>${dashboard.course.totalHours} horas</span>
        </div>
        <div class="hero-actions">
          <a class="button button-light" href="${escapeHtml(config.institutionalUrl)}" target="_blank" rel="noopener">
            Página do evento
          </a>
          <a class="button button-secondary" href="#/certifications">
            Minhas certificações
          </a>
        </div>
      </div>

      <div class="progress-summary">
        <strong>${dashboard.enrollment.progressPercent}%</strong>
        <span>Progresso</span>
        <div class="progress-track">
          <span style="width:${dashboard.enrollment.progressPercent}%"></span>
        </div>
        ${certificateButton}
      </div>
    </section>

    <section class="student-courses-panel" aria-label="Cursos disponíveis">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Meus cursos</p>
          <h2>Cursos disponíveis para si</h2>
        </div>
      </div>
      <div class="student-course-list">
        ${state.myCourses.length ? state.myCourses.map(studentCourseCardTemplate).join('') : `
          <div class="video-empty">Ainda não existem cursos associados ao seu perfil.</div>
        `}
      </div>
    </section>

    <section class="dashboard-insights" aria-label="Resumo do percurso">
      <article class="insight-card">
        <img src="${iconUrl('checked-checkbox', goldIcon)}" alt="">
        <div>
          <span>Aulas aprovadas</span>
          <strong>${approvedLessons}/${totalLessons}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('classroom', goldIcon)}" alt="">
        <div>
          <span>Aulas disponíveis</span>
          <strong>${activeLessons}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('time', goldIcon)}" alt="">
        <div>
          <span>Carga horária</span>
          <strong>${dashboard.course.totalHours}h</strong>
        </div>
      </article>
    </section>

    <section class="student-submission-panel" aria-label="Submissões do estudante">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Submissões</p>
          <h2>Trabalhos e atividades</h2>
        </div>
      </div>
      <div class="student-status-list">
        ${dashboard.lessons.length ? dashboard.lessons.map(studentSubmissionRowTemplate).join('') : `
          <div class="video-empty">Ainda não existem atividades associadas ao curso.</div>
        `}
      </div>
    </section>

    <section class="student-grade-panel" aria-label="Notas e feedback">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Notas e feedback</p>
          <h2>Desempenho por módulo</h2>
        </div>
      </div>
      <div class="student-status-list">
        ${dashboard.lessons.length ? dashboard.lessons.map(studentGradeRowTemplate).join('') : `
          <div class="video-empty">Ainda não existem notas para apresentar.</div>
        `}
      </div>
    </section>

    <section class="video-panel" aria-label="Galeria de vídeos">
      <div class="video-panel-copy">
        <p class="eyebrow">Galeria</p>
        <h2>Vídeos da Summer School</h2>
        <p>Assista aos vídeos de apoio adicionados pela administração.</p>
      </div>

      <div class="video-gallery ${videos.length ? '' : 'is-empty'}">
        ${videos.length
          ? videos.map(videoCardTemplate).join('')
          : '<div class="video-empty">Ainda não existem vídeos publicados.</div>'}
      </div>
    </section>

    <section class="section-heading lesson-section-heading">
      <div>
        <p class="eyebrow">Percurso formativo</p>
        <h2>Aulas da Summer School</h2>
      </div>
      <span class="course-hours">${dashboard.course.totalHours} horas</span>
    </section>

    <div class="lesson-grid">
      ${dashboard.lessons.map(lessonCardTemplate).join('')}
    </div>

    <section class="information-panel">
      <h3>Como funciona a plataforma</h3>
      <div class="information-grid">
        <div><strong>1.</strong><span>Consulte os materiais da aula.</span></div>
        <div><strong>2.</strong><span>Inicie a atividade prática.</span></div>
        <div><strong>3.</strong><span>Responda e carregue evidencias.</span></div>
        <div><strong>4.</strong><span>Acompanhe a avaliação.</span></div>
      </div>
    </section>
  `, pageMeta[view] || pageMeta.overview);

  const overviewContent = `
    <section class="dashboard-hero">
      <div class="hero-copy">
        <p class="eyebrow">${escapeHtml(platformYear)}</p>
        <h1 class="hero-greeting">${escapeHtml(greeting)}</h1>
        <p>Ambiente digital para acompanhar conteúdos, exercícios e avaliações do programa.</p>
        <div class="hero-meta">
          <span>Programa: ${escapeHtml(dashboard.course.title)}</span>
          <span>${escapeHtml(dashboard.course.courseCode)}</span>
          <span>${escapeHtml(totalHoursLabel)}</span>
        </div>
        <div class="hero-actions">
          ${nextLessonItem ? `
            <button class="button button-primary" type="button"
              data-open-lesson="${escapeHtml(nextLessonItem.lesson?.lessonId || '')}">
              Continuar a estudar
            </button>
          ` : ''}
          <a class="button button-secondary" href="${escapeHtml(config.institutionalUrl)}" target="_blank" rel="noopener">Página do evento</a>
        </div>
      </div>
      <div class="progress-summary">
        <strong>${dashboard.enrollment.progressPercent}%</strong>
        <span>Progresso</span>
        <div class="progress-track">
          <span style="width:${dashboard.enrollment.progressPercent}%"></span>
        </div>
        ${certificateButton}
      </div>
    </section>
    <section class="dashboard-insights student-priority-grid" aria-label="Próximos passos do percurso">
      <article class="insight-card priority-card">
        <img src="${iconUrl('play-circle', goldIcon)}" alt="">
        <div>
          <span>Próxima aula</span>
          <strong>${escapeHtml(nextLessonItem?.lesson?.title || 'Percurso concluido')}</strong>
        </div>
      </article>
      <article class="insight-card priority-card">
        <img src="${iconUrl('calendar-days', goldIcon)}" alt="">
        <div><span>Próximo prazo</span><strong>${escapeHtml(nextDeadlineLabel)}</strong></div>
      </article>
      <article class="insight-card priority-card">
        <img src="${iconUrl('clipboard-list', goldIcon)}" alt="">
        <div><span>Atividades pendentes</span><strong>${pendingActivities}</strong></div>
      </article>
      <article class="insight-card priority-card">
        <img src="${iconUrl('message-square', goldIcon)}" alt="">
        <div>
          <span>Último feedback</span>
          <strong>${escapeHtml(latestFeedbackItem?.activeAttempt?.reviewComments || 'Sem feedback novo')}</strong>
        </div>
      </article>
    </section>
    <section class="video-panel" aria-label="Galeria de vídeos">
      <div class="video-panel-copy">
        <p class="eyebrow">Galeria</p>
        <h2>Vídeos da Summer School</h2>
        <p>Assista aos vídeos de apoio adicionados pela administração.</p>
      </div>
      <div class="video-gallery ${videos.length ? '' : 'is-empty'}">
        ${videos.length ? videos.map(videoCardTemplate).join('') : '<div class="video-empty">Ainda não existem vídeos publicados.</div>'}
      </div>
    </section>
    <section class="information-panel">
      <h3>Como funciona a plataforma</h3>
      <div class="information-grid">
        <div><strong>1.</strong><span>Consulte os materiais da aula.</span></div>
        <div><strong>2.</strong><span>Inicie a atividade prática.</span></div>
        <div><strong>3.</strong><span>Responda e carregue evidencias.</span></div>
        <div><strong>4.</strong><span>Acompanhe a avaliação.</span></div>
      </div>
    </section>
  `;
  const coursesContent = `
    <section class="student-courses-panel" aria-label="Cursos disponíveis">
      <div class="student-course-list">
        ${state.myCourses.length ? state.myCourses.map(studentCourseCardTemplate).join('') : `
          <div class="video-empty">Ainda não existem cursos associados ao seu perfil.</div>
        `}
      </div>
    </section>
  `;
  const lessonsContent = `
    <section class="section-heading lesson-section-heading">
      <div>
        <p class="eyebrow">Percurso formativo</p>
        <h2>Aulas da Summer School</h2>
      </div>
      <span class="course-hours">${escapeHtml(totalHoursLabel)}</span>
    </section>
    <div class="lesson-grid">
      ${dashboard.lessons.length ? dashboard.lessons.map(lessonCardTemplate).join('') : '<div class="video-empty">Ainda não existem módulos publicados para este curso.</div>'}
    </div>
  `;
  const submissionsContent = `
    <section class="student-submission-panel" aria-label="Submissões do estudante">
      <div class="student-status-list">
        ${dashboard.lessons.length ? dashboard.lessons.map(studentSubmissionRowTemplate).join('') : `
          <div class="video-empty">Ainda não existem atividades associadas ao curso.</div>
        `}
      </div>
    </section>
  `;
  const gradesContent = `
    <section class="dashboard-insights" aria-label="Resumo do desempenho">
      <article class="insight-card">
        <img src="${iconUrl('checked-checkbox', goldIcon)}" alt="">
        <div><span>Aprovadas</span><strong>${approvedLessons}/${totalLessons}</strong></div>
      </article>
      <article class="insight-card">
        <img src="${iconUrl('bar-chart', goldIcon)}" alt="">
        <div><span>Progresso geral</span><strong>${dashboard.enrollment.progressPercent}%</strong></div>
      </article>
    </section>
    <section class="student-grade-panel" aria-label="Notas e feedback">
      <div class="student-status-list">
        ${dashboard.lessons.length ? dashboard.lessons.map(studentGradeRowTemplate).join('') : `
          <div class="video-empty">Ainda não existem notas para apresentar.</div>
        `}
      </div>
    </section>
  `;
  const contentByView = {
    overview: overviewContent,
    courses: coursesContent,
    lessons: lessonsContent,
    submissions: submissionsContent,
    grades: gradesContent
  };

  root.innerHTML = studentAppShell(view, contentByView[view] || overviewContent, pageMeta[view] || pageMeta.overview);

  root.querySelectorAll('[data-open-lesson]').forEach((button) => {
    button.addEventListener('click', () => {
      location.hash = `#/lesson/${button.dataset.openLesson}`;
    });
  });

  root.querySelectorAll('[data-select-student-course]').forEach((button) => {
    button.addEventListener('click', async () => {
      state.selectedCourseId = button.dataset.selectStudentCourse;
      localStorage.setItem('courseSelectedCourseId', state.selectedCourseId);
      await renderDashboard(view);
    });
  });

  root.querySelectorAll('[data-check-attempt]').forEach((button) => {
    button.addEventListener('click', async () => {
      setBusy(button, true);
      try {
        const attemptData = await api.attemptStatus(button.dataset.checkAttempt);
        showReviewDialog(attemptData);
      } catch (error) {
        handleError(error);
      } finally {
        setBusy(button, false);
      }
    });
  });

  bindVideoSoundEvents();
  startNotificationPolling();
  maybeShowPushRecommendation();
  renderMath();
}

function studentCourseCardTemplate(item) {
  const course = item.course || {};
  const enrollment = item.enrollment || {};
  const group = item.group || null;
  const active = course.courseId === state.selectedCourseId;
  const remainingDays = courseRemainingDaysLabel(group?.endDate);

  return `
    <article class="student-course-card ${active ? 'is-active' : ''}">
      <div>
        <span class="status-pill ${statusClass(enrollment.status)}">
          ${escapeHtml(statusLabel(enrollment.status))}
        </span>
        <h3>${escapeHtml(course.title || 'Curso')}</h3>
        <p>${escapeHtml(course.description || 'Curso associado ao seu perfil.')}</p>
      </div>
      <dl>
        <div><dt>Progresso</dt><dd>${Number(enrollment.progressPercent || 0)}%</dd></div>
        <div><dt>Módulos</dt><dd>${item.lessonCount || 0}</dd></div>
        <div><dt>Dias restantes</dt><dd>${escapeHtml(remainingDays)}</dd></div>
      </dl>
      <button class="button ${active ? 'button-disabled' : 'button-secondary'}" type="button"
        data-select-student-course="${escapeHtml(course.courseId)}"
        ${active ? 'disabled' : ''}>
        ${active ? 'Curso aberto' : 'Abrir curso'}
      </button>
    </article>
  `;
}

function studentSubmissionRowTemplate(item) {
  const lesson = item.lesson || {};
  const progress = item.progress || { status: 'LOCKED' };
  const activeAttempt = item.activeAttempt || null;
  const evaluationStatus = moduleEvaluationStatus(progress, activeAttempt);
  const locked = moduleContentAccessStatus(progress) === 'LOCKED';
  const reviewable = locked && activeAttempt && ['UNDER_REVIEW', 'CORRECTION_REQUIRED', 'FAILED', 'TIME_EXCEEDED'].includes(evaluationStatus);
  const lessonId = lesson.lessonId || '';
  const action = reviewable
    ? `<button class="button button-secondary button-small" type="button" data-check-attempt="${escapeHtml(activeAttempt.attemptId)}">Abrir revisão</button>`
    : `<button class="button ${locked || !lessonId ? 'button-disabled' : 'button-primary'} button-small" type="button" ${locked || !lessonId ? 'disabled' : `data-open-lesson="${escapeHtml(lessonId)}"`}>${locked ? 'Bloqueada' : 'Abrir atividade'}</button>`;
  return `
    <article class="student-status-row">
      <div class="student-status-index">${escapeHtml(String(lesson.lessonNumber || '').padStart(2, '0'))}</div>
      <div>
        <h3>${escapeHtml(lesson.title || 'Módulo')}</h3>
        <p>${escapeHtml(lesson.summary || 'Atividade associada ao módulo.')}</p>
      </div>
      ${moduleStatusPairTemplate(progress, activeAttempt)}
      <div class="student-status-actions">${action}</div>
    </article>
  `;
}

function studentGradeRowTemplate(item) {
  const lesson = item.lesson || {};
  const progress = item.progress || { status: 'LOCKED' };
  const evaluationStatus = moduleEvaluationStatus(progress, item.activeAttempt);
  const score = progress.score === null || progress.score === undefined ? '-' : `${progress.score}%`;
  return `
    <article class="student-status-row student-grade-row">
      <div class="student-status-index">${escapeHtml(String(lesson.lessonNumber || '').padStart(2, '0'))}</div>
      <div>
        <h3>${escapeHtml(lesson.title || 'Módulo')}</h3>
        <p>${escapeHtml(evaluationStatus === 'APPROVED' ? 'Módulo aprovado.' : 'A aguardar conclusão ou avaliação.')}</p>
      </div>
      <strong class="student-score-value">${escapeHtml(score)}</strong>
      <span class="status-pill ${statusClass(evaluationStatus)}">${escapeHtml(statusLabel(evaluationStatus))}</span>
    </article>
  `;
}

function courseRemainingDaysLabel(endDate) {
  if (!endDate) return 'Sem prazo';

  const end = new Date(endDate);
  if (Number.isNaN(end.getTime())) return 'Sem prazo';

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const finalDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  const days = Math.ceil((finalDay - today) / 86400000);

  if (days < 0) return 'Terminado';
  if (days === 0) return 'Termina hoje';
  if (days === 1) return '1 dia';
  return `${days} dias`;
}

function setNotificationState(data = {}) {
  state.notifications = {
    items: Array.isArray(data.notifications) ? data.notifications : [],
    unreadCount: Number(data.unreadCount || 0),
    total: Number(data.total || 0)
  };
}

function notificationCategoryMeta(category) {
  const categories = {
    MODULE_AVAILABLE: { label: 'Módulos e exercícios', icon: 'book-open' },
    SUBMISSION_STATUS: { label: 'Estado da submissão', icon: 'clipboard-list' },
    REVIEW_FEEDBACK: { label: 'Avaliação e feedback', icon: 'message-square' },
    GENERAL: { label: 'Atualização', icon: 'bell' }
  };
  return categories[category] || categories.GENERAL;
}

function notificationItemTemplate(notification) {
  const meta = notificationCategoryMeta(notification.category);
  const actionUrl = notification.actionUrl || '#/notifications';
  return `
    <article class="notification-item ${notification.readAt ? '' : 'is-unread'}"
      data-notification-id="${escapeHtml(notification.notificationId)}">
      <div class="notification-item-icon" aria-hidden="true">
        <img src="${iconUrl(meta.icon, notification.readAt ? blueIcon : goldIcon)}" alt="">
      </div>
      <div class="notification-item-copy">
        <div class="notification-item-meta">
          <span>${escapeHtml(meta.label)}</span>
          <time>${escapeHtml(formatDate(notification.createdAt))}</time>
        </div>
        <h2>${escapeHtml(notification.title || 'Atualização')}</h2>
        <p>${escapeHtml(notification.message || '')}</p>
        <div class="notification-item-actions">
          ${actionUrl ? `<a class="button button-primary button-small" href="${escapeHtml(actionUrl)}" data-open-notification>Abrir</a>` : ''}
          ${notification.readAt ? '' : '<button class="button button-secondary button-small" type="button" data-mark-notification>Lida</button>'}
        </div>
      </div>
    </article>
  `;
}

async function renderNotifications() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar notificações...');

  const [home, notificationData, pushData] = await Promise.all([
    api.studentHome(state.selectedCourseId),
    api.notifications({ limit: 100 }),
    api.pushConfiguration()
  ]);
  await refreshPushState(pushData);
  state.myCourses = Array.isArray(home.courses) ? home.courses : [];
  state.selectedCourseId = home.selectedCourseId || state.selectedCourseId || config.courseId || '';
  state.dashboard = normalizeStudentDashboard(home);
  setNotificationState(notificationData);
  setMediaConfig(home.mediaConfig || {});
  applyBrandLogo();

  const student = state.dashboard.student || {};
  headerUser.innerHTML = profileAvatarTemplate(student, 'header-avatar');
  headerUser.title = 'Editar perfil pessoal';
  headerUser.setAttribute('aria-label', 'Editar perfil pessoal');
  headerUser.hidden = false;
  if (mobileMenuButton) mobileMenuButton.hidden = false;
  logoutButton.hidden = false;

  root.innerHTML = studentAppShell('notifications', `
    <section class="notifications-page" aria-label="Central de notificações">
      <div class="notifications-toolbar">
        <div>
          <p class="eyebrow">Atualizações da plataforma</p>
          <h2>Central de notificações</h2>
          <p>${state.notifications.unreadCount
            ? `${state.notifications.unreadCount} notificação${state.notifications.unreadCount === 1 ? '' : 'ões'} por ler.`
            : 'Não existem notificações por ler.'}</p>
        </div>
        ${state.notifications.unreadCount
          ? '<button class="button button-secondary" id="markAllNotifications" type="button">Marcar todas como lidas</button>'
          : ''}
      </div>
      <div class="notification-list">
        ${state.notifications.items.length
          ? state.notifications.items.map(notificationItemTemplate).join('')
          : '<div class="empty-note">Ainda não recebeu atualizações.</div>'}
      </div>
    </section>
  `, {
    eyebrow: 'Notificações',
    topbarTitle: 'Notificações',
    title: 'Atualizações importantes',
    description: 'Acompanhe módulos, exercícios, submissões e comentários de avaliação.',
    compactHeading: true
  });

  document.querySelector('#markAllNotifications')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, 'A atualizar...');
    try {
      await api.markNotificationRead('', true);
      await renderNotifications();
    } catch (error) {
      handleError(error);
      setBusy(button, false);
    }
  });
  root.querySelectorAll('[data-mark-notification]').forEach((button) => {
    button.addEventListener('click', async () => {
      const item = button.closest('[data-notification-id]');
      try {
        await api.markNotificationRead(item?.dataset.notificationId || '');
        await renderNotifications();
      } catch (error) {
        handleError(error);
      }
    });
  });
  root.querySelectorAll('[data-open-notification]').forEach((link) => {
    link.addEventListener('click', () => {
      const item = link.closest('[data-notification-id]');
      if (item?.classList.contains('is-unread')) {
        api.markNotificationRead(item.dataset.notificationId).catch(() => {});
      }
    });
  });
  startNotificationPolling();
  maybeShowPushRecommendation();
  reportHeight();
}

async function renderProfile() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar perfil...');

  const [courseBundle, notificationData, pushData] = await Promise.all([
    api.myCourses(),
    api.notifications({ limit: 6 }),
    api.pushConfiguration()
  ]);
  state.myCourses = courseBundle.courses || [];
  state.notificationChannelInfo = courseBundle.notificationChannelInfo || null;
  setNotificationState(notificationData);
  await refreshPushState(pushData);
  const student = courseBundle?.student || state.dashboard?.student || {};
  const channelInfo = state.notificationChannelInfo || {};
  const telegramInfo = channelInfo.telegram || {};
  const telegramLinked = Boolean(student.telegramLinked);
  const whatsappActive = Boolean(student.whatsappOptIn && channelInfo.whatsapp?.configured);
  const emailActive = Boolean(student.emailOptIn && channelInfo.email?.configured);
  const telegramActive = Boolean(student.telegramOptIn && telegramLinked && telegramInfo.configured);
  const pushInfo = state.push.configuration || channelInfo.push || {};
  const pushSupported = supportsWebPush();
  const pushActive = Boolean(pushSupported && pushInfo.configured && state.push.subscribedOnDevice);
  const pushBlocked = pushSupported && Notification.permission === 'denied';
  headerUser.innerHTML = profileAvatarTemplate(student, 'header-avatar');
  headerUser.title = 'Editar perfil pessoal';
  headerUser.setAttribute('aria-label', 'Editar perfil pessoal');
  headerUser.hidden = false;
  if (mobileMenuButton) mobileMenuButton.hidden = false;
  logoutButton.hidden = false;

  root.innerHTML = studentAppShell('profile', `
    <section class="profile-shell profile-shell-modern">
      <div class="profile-header-card">
        <div class="profile-identity">
          <div class="profile-photo-frame profile-photo-frame-large">
            ${profilePhotoTemplate(student)}
          </div>
          <div>
            <p class="eyebrow">Perfil pessoal</p>
            <h1>${escapeHtml(student.fullName || 'Estudante')}</h1>
            <p>${escapeHtml(student.publicStudentId || '')}  -  ${escapeHtml(student.email || '')}</p>
          </div>
        </div>
        <div class="profile-status-grid" aria-label="Resumo do perfil">
          <div>
            <span>ID público</span>
            <strong>${escapeHtml(student.publicStudentId || '-')}</strong>
          </div>
          <div>
            <span>Cursos</span>
            <strong>${state.myCourses.length}</strong>
          </div>
          <div>
            <span>Estado</span>
            <strong>${escapeHtml(statusLabel(student.status || 'ACTIVE'))}</strong>
          </div>
        </div>
      </div>

      <div class="profile-workspace">
        <form id="profileForm" class="profile-card profile-form form-stack">
          <div class="profile-section-heading">
            <div>
              <p class="eyebrow">Dados gerais</p>
              <h2>Informações pessoais</h2>
            </div>
          </div>

          <div class="profile-photo-editor">
            <div class="profile-photo-preview" id="profilePhotoPreview">
              ${profilePhotoTemplate(student)}
            </div>
            <label class="file-control">
              <span>Fotografia de perfil</span>
              <input name="profilePhotoFile" id="profilePhotoFile" type="file" accept="image/jpeg,image/png,image/webp">
              <span class="button button-secondary profile-photo-button">Selecionar fotografia</span>
              <small id="profilePhotoFileName">Nenhum ficheiro selecionado.</small>
              <small>Use uma imagem clara em JPG, PNG ou WebP.</small>
            </label>
            ${student.profilePhotoUrl ? `
              <label class="checkbox-line">
                <input type="checkbox" name="removeProfilePhoto" value="true">
                Remover fotografia atual
              </label>
            ` : ''}
          </div>

          <div class="profile-form-grid">
            <label>
              <span>Nome completo</span>
              <input name="fullName" value="${escapeHtml(student.fullName || '')}" required>
            </label>
            <div class="profile-email-control">
              <label>
                <span>Email de acesso</span>
                <input value="${escapeHtml(student.email || '')}" readonly aria-describedby="profileEmailHint">
              </label>
              <button class="button button-secondary button-small" id="changeProfileEmailButton" type="button">Alterar email</button>
              <small id="profileEmailHint">A alteração exige a palavra-passe atual e encerra todas as sessões.</small>
            </div>
            <label>
              <span>País</span>
              <input name="country" value="${escapeHtml(student.country || '')}">
            </label>
            <label>
              <span>Telefone</span>
              <input name="phone" value="${escapeHtml(student.phone || '')}" placeholder="+258 84 000 0000">
            </label>
            <label>
              <span>Organização</span>
              <input name="organization" value="${escapeHtml(student.organization || '')}">
            </label>
            <label>
              <span>Função profissional</span>
              <input name="jobTitle" value="${escapeHtml(student.jobTitle || '')}">
            </label>
          </div>

          <label>
            <span>Interesses académicos ou profissionais</span>
            <textarea name="interests" rows="5">${escapeHtml(student.interests || '')}</textarea>
          </label>

          <fieldset class="profile-notification-settings">
            <legend>Preferências de notificações</legend>
            <p class="profile-notification-intro">Escolha livremente um ou vários canais. A central de notificações da plataforma permanece sempre ativa.</p>
            <div class="profile-notification-channels">
              <label class="checkbox-line notification-consent-option notification-channel-option">
                <input type="checkbox" name="whatsappOptIn" value="true" ${student.whatsappOptIn ? 'checked' : ''}>
                <span>
                  <strong>WhatsApp</strong>
                  <small>Atualizações académicas enviadas para o telefone indicado no perfil.</small>
                  <span class="notification-channel-state ${whatsappActive ? 'is-active' : ''}">${whatsappActive ? 'Ativo' : student.whatsappOptIn ? 'Autorizado' : 'Opcional'}</span>
                </span>
              </label>
              <label class="checkbox-line notification-consent-option notification-channel-option">
                <input type="checkbox" name="emailOptIn" value="true" ${student.emailOptIn ? 'checked' : ''}>
                <span>
                  <strong>Email</strong>
                  <small>Mensagens enviadas para ${escapeHtml(student.email || 'o email da conta')}.</small>
                  <span class="notification-channel-state ${emailActive ? 'is-active' : ''}">${emailActive ? 'Ativo' : student.emailOptIn ? 'Autorizado' : 'Opcional'}</span>
                </span>
              </label>
              <div class="notification-consent-option notification-channel-option notification-telegram-option">
                <input type="checkbox" name="telegramOptIn" value="true" ${student.telegramOptIn ? 'checked' : ''} ${telegramLinked ? '' : 'disabled'} aria-label="Receber atualizações pelo Telegram">
                <span>
                  <strong>Telegram</strong>
                  <small>${telegramLinked
                    ? 'Conta associada ao bot oficial. Pode suspender as mensagens sem remover a associação.'
                    : telegramInfo.linkingAvailable
                      ? `Associe a sua conta através do bot @${escapeHtml(telegramInfo.botUsername || '')}.`
                      : 'A associação ainda não foi disponibilizada pela administração.'}</small>
                  <span class="notification-channel-state ${telegramActive ? 'is-active' : ''}">${telegramLinked ? (telegramActive ? 'Ativo' : student.telegramOptIn ? 'Autorizado' : 'Associado') : 'Não associado'}</span>
                  <span class="notification-telegram-actions" id="telegramLinkActions">
                    ${telegramLinked ? `
                      <button class="button button-secondary" id="telegramUnlinkButton" type="button">Remover associação</button>
                    ` : `
                      <button class="button button-secondary" id="telegramLinkButton" type="button" ${telegramInfo.linkingAvailable ? '' : 'disabled'}>Associar Telegram</button>
                      <a class="button button-secondary" id="telegramOpenLink" href="${escapeHtml(state.telegramLinkUrl || '#')}" target="_blank" rel="noopener noreferrer" ${state.telegramLinkUrl ? '' : 'hidden'}>Abrir bot</a>
                      <button class="button button-primary" id="telegramConfirmButton" type="button" ${state.telegramLinkToken ? '' : 'hidden'}>Confirmar associação</button>
                    `}
                  </span>
                </span>
              </div>
              <div class="notification-consent-option notification-channel-option notification-push-option">
                <span class="notification-channel-icon" aria-hidden="true"><img src="${iconUrl('bell-ring', blueIcon)}" alt=""></span>
                <span>
                  <strong>Notificações Push</strong>
                  <small>${!pushSupported
                    ? 'Este navegador não suporta Web Push ou a plataforma não está aberta por HTTPS.'
                    : pushBlocked
                      ? 'As notificações estão bloqueadas nas definições deste navegador.'
                    : !pushInfo.configured
                      ? 'O canal Push ainda precisa de ser ativado pela administração.'
                      : pushActive
                        ? 'Este dispositivo recebe avisos mesmo quando a plataforma está fechada.'
                        : isIosDevice() && !isStandaloneApp()
                          ? 'No iPhone ou iPad, guarde a aplicação no ecrã principal antes de ativar.'
                          : 'Ative avisos de módulos, prazos e avaliações neste dispositivo.'}</small>
                  <span class="notification-channel-state ${pushActive ? 'is-active' : ''}">${pushActive ? 'Ativo neste dispositivo' : pushBlocked ? 'Bloqueado no navegador' : state.push.subscriptionCount ? `${state.push.subscriptionCount} dispositivo(s) associado(s)` : 'Opcional'}</span>
                  <span class="notification-push-actions">
                    ${!isStandaloneApp() ? '<button class="button button-secondary" id="installWebAppButton" type="button">Guardar aplicação</button>' : ''}
                    ${pushActive
                      ? '<button class="button button-secondary" id="disablePushButton" type="button">Desativar neste dispositivo</button>'
                      : `<button class="button button-primary" id="enablePushButton" type="button" ${pushSupported && pushInfo.configured && !pushBlocked ? '' : 'disabled'}>Ativar notificações</button>`}
                  </span>
                </span>
              </div>
            </div>
            <div class="notification-preference-grid">
              <label class="checkbox-line">
                <input type="checkbox" name="notifyModuleAvailable" value="true" ${student.notificationPreferences?.MODULE_AVAILABLE !== false ? 'checked' : ''}>
                Módulos e exercícios disponíveis
              </label>
              <label class="checkbox-line">
                <input type="checkbox" name="notifySubmissionStatus" value="true" ${student.notificationPreferences?.SUBMISSION_STATUS !== false ? 'checked' : ''}>
                Mudanças no estado das submissões
              </label>
              <label class="checkbox-line">
                <input type="checkbox" name="notifyReviewFeedback" value="true" ${student.notificationPreferences?.REVIEW_FEEDBACK !== false ? 'checked' : ''}>
                Comentários e resultados de avaliação
              </label>
              <label class="checkbox-line">
                <input type="checkbox" name="notifyGeneral" value="true" ${student.notificationPreferences?.GENERAL !== false ? 'checked' : ''}>
                Comunicados gerais
              </label>
            </div>
            <small>Ao ativar um canal, autoriza apenas notificações académicas e pode retirar a autorização a qualquer momento.</small>
          </fieldset>

          <div class="profile-actions">
            <a class="button button-secondary" href="#/">Voltar ao curso</a>
            <button class="button button-primary" type="submit">Guardar perfil</button>
          </div>
        </form>

        <div class="profile-side-column">
          <form id="passwordForm" class="profile-card profile-security form-stack">
            <div class="profile-section-heading">
              <div>
                <p class="eyebrow">Segurança</p>
                <h2>Alterar palavra-passe de acesso</h2>
              </div>
            </div>
            <label>
              <span>Palavra-passe atual</span>
              <input type="password" name="currentAccessCode" autocomplete="current-password" required>
            </label>
            <label>
              <span>Nova palavra-passe</span>
              <input type="password" name="newAccessCode" autocomplete="new-password" minlength="8" required>
            </label>
            <label>
              <span>Confirmar a nova palavra-passe</span>
              <input type="password" name="confirmAccessCode" autocomplete="new-password" minlength="8" required>
            </label>
            <div class="profile-security-note">
              Ao alterar a palavra-passe, será necessário iniciar sessão novamente.
            </div>
            <div class="profile-actions">
              <button class="button button-primary" type="submit">Alterar palavra-passe</button>
            </div>
          </form>

          <section class="profile-card profile-exit">
            <div class="profile-section-heading">
              <div>
                <p class="eyebrow">Sessão</p>
                <h2>Terminar acesso</h2>
              </div>
            </div>
            <p>Saia da plataforma quando terminar de usar este dispositivo.</p>
            <button class="button button-secondary" id="profileLogoutButton" type="button">Sair da conta</button>
          </section>
        </div>
      </div>
    </section>
  `, {
    eyebrow: 'Perfil e configurações',
    title: 'Perfil pessoal',
    description: 'Atualize os seus dados, fotografia e palavra-passe de acesso.'
  });

  document.querySelector('#profileForm').addEventListener('submit', saveProfile);
  document.querySelector('#passwordForm').addEventListener('submit', changePassword);
  document.querySelector('#profileLogoutButton').addEventListener('click', logout);
  document.querySelector('#changeProfileEmailButton')?.addEventListener('click', () => showEmailChangeDialog(student));
  document.querySelector('#telegramLinkButton')?.addEventListener('click', startTelegramLink);
  document.querySelector('#telegramConfirmButton')?.addEventListener('click', confirmTelegramLink);
  document.querySelector('#telegramUnlinkButton')?.addEventListener('click', unlinkTelegram);
  document.querySelector('#installWebAppButton')?.addEventListener('click', async (event) => {
    await installWebApp(event.currentTarget);
  });
  document.querySelector('#enablePushButton')?.addEventListener('click', async (event) => {
    if (await enablePushNotifications(event.currentTarget)) await renderProfile();
  });
  document.querySelector('#disablePushButton')?.addEventListener('click', async (event) => {
    if (await disablePushNotifications(event.currentTarget)) await renderProfile();
  });
  bindProfilePhotoPreview(student);
  startNotificationPolling();
  maybeShowPushRecommendation();
  reportHeight();
}

async function saveProfile(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const formData = new FormData(form);
  const values = Object.fromEntries(formData.entries());
  const profilePhotoFile = form.querySelector('[name="profilePhotoFile"]')?.files?.[0] || null;

  values.profilePhotoFile = profilePhotoFile && profilePhotoFile.size ? profilePhotoFile : null;
  values.removeProfilePhoto = formData.get('removeProfilePhoto') === 'true' ? 'true' : '';
  values.whatsappOptIn = formData.get('whatsappOptIn') === 'true';
  values.emailOptIn = formData.get('emailOptIn') === 'true';
  values.telegramOptIn = formData.get('telegramOptIn') === 'true';
  values.notificationPreferences = {
    MODULE_AVAILABLE: formData.get('notifyModuleAvailable') === 'true',
    SUBMISSION_STATUS: formData.get('notifySubmissionStatus') === 'true',
    REVIEW_FEEDBACK: formData.get('notifyReviewFeedback') === 'true',
    GENERAL: formData.get('notifyGeneral') === 'true'
  };
  delete values.notifyModuleAvailable;
  delete values.notifySubmissionStatus;
  delete values.notifyReviewFeedback;
  delete values.notifyGeneral;
  setBusy(button, true, 'A guardar...');

  try {
    const result = await api.updateMyProfile(values);
    if (state.dashboard) state.dashboard.student = result.student;
    showToast('Perfil atualizado.', 'success');
    await renderProfile();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

async function changePassword(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const formData = new FormData(form);
  const currentAccessCode = String(formData.get('currentAccessCode') || '');
  const newAccessCode = String(formData.get('newAccessCode') || '');
  const confirmAccessCode = String(formData.get('confirmAccessCode') || '');

  if (newAccessCode !== confirmAccessCode) {
    showToast('A confirmação da nova palavra-passe não corresponde.', 'error');
    return;
  }

  setBusy(button, true, 'A alterar...');

  try {
    await api.changeMyAccessCode(currentAccessCode, newAccessCode);
    state.dashboard = null;
    state.myCourses = [];
    location.hash = '';
    showToast('Palavra-passe alterada. Inicie sessão novamente.', 'success');
    renderLogin();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

function showEmailChangeDialog(student) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card email-change-dialog" role="dialog" aria-modal="true" aria-labelledby="emailChangeTitle">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <p class="eyebrow">Segurança da conta</p>
      <h2 id="emailChangeTitle">Alterar email de acesso</h2>
      <p class="recovery-note">Confirme cuidadosamente o novo endereço. Depois da alteração terá de iniciar sessão novamente.</p>
      <form id="studentEmailChangeForm" class="form-stack">
        <label>
          <span>Email atual</span>
          <input type="email" value="${escapeHtml(student.email || '')}" readonly>
        </label>
        <label>
          <span>Novo email</span>
          <input type="email" name="newEmail" autocomplete="email" maxlength="254" required>
        </label>
        <label>
          <span>Confirmar novo email</span>
          <input type="email" name="confirmEmail" autocomplete="off" maxlength="254" required>
        </label>
        <label>
          <span>Palavra-passe atual</span>
          <input type="password" name="currentAccessCode" autocomplete="current-password" required>
        </label>
        <label class="checkbox-line email-change-confirmation">
          <input type="checkbox" name="acknowledge" value="true" required>
          <span>Compreendo que todas as sessões serão encerradas e que as notificações por email terão de ser novamente autorizadas.</span>
        </label>
        <div class="form-message form-message-error" id="studentEmailChangeError" role="alert" hidden></div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-email-change>Cancelar</button>
          <button class="button button-primary" type="submit">Alterar email</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('.dialog-close')?.addEventListener('click', close);
  overlay.querySelector('[data-cancel-email-change]')?.addEventListener('click', close);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) close();
  });
  overlay.querySelector('#studentEmailChangeForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const errorBox = form.querySelector('#studentEmailChangeError');
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
    setBusy(button, true, 'A alterar...');
    try {
      const result = await api.changeMyEmail(
        values.currentAccessCode,
        newEmail,
        confirmEmail,
        values.acknowledge === 'true'
      );
      close();
      state.dashboard = null;
      state.myCourses = [];
      state.notificationChannelInfo = null;
      location.hash = '';
      renderLogin();
      const loginEmail = document.querySelector('#loginForm [name="email"]');
      if (loginEmail) loginEmail.value = result.email || newEmail;
      showToast('Email alterado com segurança. Inicie sessão com o novo endereço.', 'success');
    } catch (error) {
      errorBox.textContent = error.message || 'Não foi possível alterar o email.';
      errorBox.hidden = false;
      form.elements.currentAccessCode.value = '';
      form.elements.currentAccessCode.focus();
    } finally {
      setBusy(button, false);
      reportHeight();
    }
  });
  overlay.querySelector('[name="newEmail"]')?.focus();
  reportHeight();
}

function bindProfilePhotoPreview(student) {
  const input = document.querySelector('[name="profilePhotoFile"]');
  const preview = document.querySelector('#profilePhotoPreview');
  const fileName = document.querySelector('#profilePhotoFileName');
  if (!input || !preview) return;

  input.addEventListener('change', () => {
    const file = input.files?.[0];
    if (!file) {
      if (fileName) fileName.textContent = 'Nenhum ficheiro selecionado.';
      preview.innerHTML = profilePhotoTemplate(student);
      return;
    }

    if (!file.type.startsWith('image/')) {
      showToast('Selecione uma imagem válida.', 'error');
      input.value = '';
      if (fileName) fileName.textContent = 'Nenhum ficheiro selecionado.';
      preview.innerHTML = profilePhotoTemplate(student);
      return;
    }

    if (fileName) fileName.textContent = file.name;
    const objectUrl = URL.createObjectURL(file);
    preview.innerHTML = profileAvatarTemplate({
      ...student,
      profilePhotoUrl: objectUrl
    }, 'profile-photo-image');
  });
}

function profileInitials(fullName) {
  const parts = String(fullName || '').trim().split(/\s+/).filter(Boolean);
  return `${parts[0]?.[0] || 'E'}${parts.length > 1 ? parts.at(-1)[0] : ''}`.toUpperCase();
}

function profilePhotoTemplate(student) {
  return profileAvatarTemplate(student, 'profile-photo-image');
}

function profileAvatarTemplate(student, className = '') {
  const initials = profileInitials(student?.fullName || student?.email);
  const photoUrl = safeImageUrl(student?.profilePhotoUrl);
  const classes = className ? ` class="${escapeHtml(className)}"` : '';

  if (photoUrl) {
    return `<img${classes} src="${escapeHtml(photoUrl)}" alt="Fotografia de ${escapeHtml(student?.fullName || 'estudante')}" data-profile-photo="true" data-profile-initials="${escapeHtml(initials)}" referrerpolicy="no-referrer">`;
  }

  return `<span${classes}>${escapeHtml(initials)}</span>`;
}

function safeImageUrl(url) {
  const value = String(url || '').trim();
  if (!value) return '';

  try {
    const parsed = new URL(value, window.location.href);
    if (!['http:', 'https:', 'blob:', 'data:'].includes(parsed.protocol)) return '';
    return imageDisplayUrl(parsed.href) || parsed.href;
  } catch {
    return '';
  }
}

function handleProfilePhotoError(event) {
  const image = event.target;
  if (!(image instanceof HTMLImageElement) || !image.dataset.profilePhoto) return;

  const fallback = document.createElement('span');
  fallback.className = image.className;
  fallback.textContent = image.dataset.profileInitials || 'E';
  image.replaceWith(fallback);
}

function lessonCardTemplate(item) {
  const { lesson, progress, activeAttempt } = item;
  const locked = moduleContentAccessStatus(progress) === 'LOCKED';
  const evaluationStatus = moduleEvaluationStatus(progress, activeAttempt);
  const reviewState = [
    'UNDER_REVIEW',
    'CORRECTION_REQUIRED',
    'FAILED',
    'TIME_EXCEEDED'
  ].includes(evaluationStatus);

  let action;

  if (locked && reviewState && activeAttempt) {
    action = `
      <button class="button button-secondary" type="button"
        data-check-attempt="${escapeHtml(activeAttempt.attemptId)}">
        Consultar avaliação
      </button>
    `;
  } else if (!locked) {
    action = `
      <button class="button button-primary" type="button"
        data-open-lesson="${escapeHtml(lesson.lessonId)}">
        ${evaluationStatus === 'APPROVED' ? 'Rever aula' : reviewState ? 'Ver conteúdo e avaliação' : 'Abrir aula'}
      </button>
    `;
  } else {
    action = '<button class="button button-disabled" type="button" disabled>Aula bloqueada</button>';
  }

  return `
    <article class="lesson-card ${locked ? 'is-locked' : ''}">
      <div class="lesson-number">${lesson.lessonNumber}</div>
      <div class="lesson-card-body">
        <div class="lesson-card-topline">
          ${moduleStatusPairTemplate(progress, activeAttempt)}
          <span>${lesson.theoryMinutes + lesson.exerciseMinutes + lesson.individualMinutes} min</span>
        </div>
        <h3>${escapeHtml(lesson.title)}</h3>
        <p>${escapeHtml(lesson.summary)}</p>
        <div class="lesson-meta">
          <span>Teoria: ${lesson.theoryMinutes} min</span>
          <span>Prática: ${lesson.exerciseMinutes + lesson.individualMinutes} min</span>
        </div>
        ${progress.score !== null
          ? `<p class="score-line">Classificação: <strong>${progress.score}%</strong></p>`
          : ''}
        <div class="lesson-card-actions">${action}</div>
      </div>
    </article>
  `;
}

async function openLesson(lessonId) {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar a aula...');

  const lessonData = await api.getLesson(lessonId);
  state.lesson = lessonData;

  let activeAttempt = state.dashboard?.lessons?.find(
    (item) => item.lesson.lessonId === lessonId
  )?.activeAttempt || null;

  if (moduleEvaluationStatus(lessonData.progress, activeAttempt) === 'NOT_STARTED') {
    activeAttempt = null;
  }

  let attemptData = null;
  if (activeAttempt) {
    attemptData = await api.attemptStatus(activeAttempt.attemptId);
    activeAttempt = attemptData.attempt;
  }

  state.attempt = activeAttempt;
  state.attemptData = attemptData;

  root.innerHTML = `
    <div class="lesson-layout">
      <aside class="lesson-sidebar">
        <button class="text-button lesson-back-button" id="backDashboard">
          <img src="${iconUrl('arrow-left', blueIcon)}" alt="">
          Voltar ao curso
        </button>
        <p class="eyebrow">Aula ${lessonData.lesson.lessonNumber}</p>
        <h2>${escapeHtml(lessonData.lesson.title)}</h2>
        <div class="lesson-time-summary">
          <span>Teoria<strong>${lessonData.lesson.theoryMinutes} min</strong></span>
          <span>Exercicios<strong>${lessonData.lesson.exerciseMinutes} min</strong></span>
          <span>Individual<strong>${lessonData.lesson.individualMinutes} min</strong></span>
          <span>Submissão<strong>${lessonData.lesson.submissionDurationMinutes} min</strong></span>
        </div>
        <nav id="lessonNavigation" class="lesson-navigation"></nav>
      </aside>

      <main class="lesson-main">
        <header class="lesson-header">
          ${moduleStatusPairTemplate(lessonData.progress, activeAttempt)}
          <h1>${escapeHtml(lessonData.lesson.title)}</h1>
          <p>${escapeHtml(lessonData.lesson.summary)}</p>
        </header>

        <div id="lessonContent">
          ${lessonData.content.map(contentSectionTemplate).join('')}
        </div>

        <section id="assessmentArea" class="assessment-area">
          ${assessmentTemplate(lessonData, activeAttempt, attemptData)}
        </section>
      </main>
    </div>
  `;

  document.querySelector('#backDashboard').addEventListener('click', () => {
    location.hash = '#/';
  });

  buildLessonNavigation();
  bindAssessmentEvents();

  if (activeAttempt?.status === 'IN_PROGRESS') {
    startTimer(activeAttempt.deadlineAt);
    startStatusPoll(activeAttempt.attemptId);
  }

  renderMath();
}

function contentSectionTemplate(section) {
  return `
    <article class="content-section" id="section-${escapeHtml(section.contentId)}">
      <div class="content-section-label">${escapeHtml(section.sectionType)}</div>
      <h2>${escapeHtml(section.title)}</h2>
      <div class="rich-content">${safeHtml(section.bodyHtml)}</div>
    </article>
  `;
}

function assessmentTemplate(lessonData, attempt, attemptData) {
  const evaluationStatus = moduleEvaluationStatus(lessonData.progress, attempt);
  const effectiveAttempt = evaluationStatus === 'NOT_STARTED' ? null : attempt;
  const status = effectiveAttempt?.status || evaluationStatus;

  if (evaluationStatus === 'APPROVED') {
    return `
      <div class="completion-card">
        <div class="completion-icon"><img src="${iconUrl('circle-check', goldIcon)}" alt=""></div>
        <h2>Aula aprovada</h2>
        <p>Obteve ${lessonData.progress.score}% e pode rever todo o conteúdo.</p>
        <button class="button button-secondary" id="backApproved">Voltar ao curso</button>
      </div>
    `;
  }

  if (['UNDER_REVIEW', 'CORRECTION_REQUIRED', 'FAILED', 'TIME_EXCEEDED'].includes(status)) {
    return reviewStateTemplate(effectiveAttempt, attemptData?.latestReview);
  }

  if (!effectiveAttempt) {
    const minutes = lessonData.lesson.submissionDurationMinutes
      || lessonData.lesson.exerciseMinutes + lessonData.lesson.individualMinutes
      || 180;
    return `
      <div class="start-assessment-card">
        <p class="eyebrow">Avaliação prática</p>
        <h2>Preparado para iniciar?</h2>
        <p>
          Ao iniciar, o temporizador de ${minutes} minutos comecara no servidor
          e continuará mesmo que feche a página.
        </p>
        <button class="button button-primary" id="startAttempt">Iniciar exercicios</button>
      </div>
    `;
  }

  return attemptFormTemplate(lessonData, effectiveAttempt, attemptData);
}

function attemptFormTemplate(lessonData, attempt, attemptData) {
  const answerMap = new Map(
    (attemptData?.answers || []).map((answer) => [answer.questionId, answer])
  );

  return `
    <div class="attempt-header">
      <div>
        <p class="eyebrow">Tentativa ${attempt.attemptNumber}</p>
        <h2>Respostas e submissão</h2>
      </div>
      <div class="timer-card">
        <span>Tempo restante</span>
        <strong id="attemptTimer">${formatDuration(attempt.remainingSeconds)}</strong>
      </div>
    </div>

    <div class="question-list">
      ${lessonData.questions.map((question) => {
        return questionTemplate(question, answerMap.get(question.questionId));
      }).join('')}
    </div>

    <section class="upload-panel">
      <div>
        <p class="eyebrow">Documentos obrigatorios</p>
        <h3>Carregue fotografias ou ficheiros</h3>
        <p>As imagens serão otimizadas antes do envio. Confirme que todos os cálculos estão legíveis.</p>
      </div>

      <div class="upload-methods">
        <label class="upload-dropzone" for="exerciseFiles">
          <input id="exerciseFiles" type="file" multiple
            accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx">
          <span class="upload-icon"><img src="${iconUrl('upload', blueIcon)}" alt=""></span>
          <strong>Selecionar ficheiros</strong>
          <small>JPG, PNG, WebP, PDF, Word ou Excel</small>
        </label>

        <form id="driveUploadForm" class="drive-upload-form">
          <label>
            <span>Imagem por link do Google Drive</span>
            <input id="driveImageUrl" type="url" name="driveImageUrl"
              placeholder="https://drive.google.com/file/d/.../view">
          </label>
          <button class="button button-secondary" type="submit">Carregar imagem</button>
          <p class="field-hint">
            Use um link público para uma imagem. A plataforma lê a imagem e envia-a pela mesma submissão.
          </p>
        </form>
      </div>

      <div id="uploadProgress" class="upload-progress" hidden></div>
      <div id="uploadedFiles" class="uploaded-files">
        ${(attemptData?.files || []).length
          ? attemptData.files.map(fileTemplate).join('')
          : '<p class="empty-note">Nenhum ficheiro carregado.</p>'}
      </div>
    </section>

    <div class="submission-box">
      <label class="authorship-check">
        <input type="checkbox" id="authorshipConfirmation">
        <span>Confirmo que resolvi pessoalmente os exercicios apresentados.</span>
      </label>
      <button class="button button-primary" id="submitAttempt">Submeter atividade</button>
      <p class="submission-warning">
        Depois da submissão, as respostas e os ficheiros deixam de poder ser alterados.
      </p>
    </div>
  `;
}

function questionTemplate(question, answer = null) {
  const selected = parseSelectedOptions(answer?.selectedOptionId);
  let field;

  if (['SINGLE_CHOICE', 'TRUE_FALSE'].includes(question.questionType)) {
    field = optionListTemplate(question, selected, 'radio');
  } else if (question.questionType === 'MULTIPLE_CHOICE') {
    field = optionListTemplate(question, selected, 'checkbox');
  } else {
    field = `
      <textarea rows="${question.questionType === 'LONG_TEXT' ? 6 : 3}"
        data-answer-text="${escapeHtml(question.questionId)}"
        placeholder="Escreva a sua resposta...">${escapeHtml(answer?.answerText || '')}</textarea>
    `;
  }

  return `
    <article class="question-card" data-question="${escapeHtml(question.questionId)}">
      <div class="question-number">Questão ${question.questionOrder}</div>
      <h3>${escapeHtml(question.prompt)}</h3>
      <p class="question-points">${question.points} pontos ${question.isRequired ? ' -  obrigatoria' : ''}</p>
      ${field}
      <div class="save-indicator" data-save-indicator="${escapeHtml(question.questionId)}"></div>
    </article>
  `;
}

function optionListTemplate(question, selected, inputType) {
  return `
    <div class="option-list">
      ${question.options.map((option) => `
        <label class="option-item">
          <input type="${inputType}"
            name="question-${escapeHtml(question.questionId)}"
            value="${escapeHtml(option.optionId)}"
            ${selected.includes(option.optionId) ? 'checked' : ''}>
          <span class="option-label">${escapeHtml(option.optionLabel)}</span>
          <span>${escapeHtml(option.optionText)}</span>
        </label>
      `).join('')}
    </div>
  `;
}

function fileTemplate(file) {
  return `
    <div class="uploaded-file" data-file="${escapeHtml(file.fileId)}">
      <div>
        <strong>${escapeHtml(file.fileName)}</strong>
        <span>${escapeHtml(formatBytes(file.sizeBytes))}</span>
      </div>
      <div class="file-actions">
        <a href="${escapeHtml(file.driveUrl)}" target="_blank" rel="noopener">Abrir</a>
        <button type="button" data-delete-file="${escapeHtml(file.fileId)}">Eliminar</button>
      </div>
    </div>
  `;
}

function reviewStateTemplate(attempt, review) {
  if (!attempt) {
    return `
      <div class="completion-card">
        <h2>Estado da atividade</h2>
        <p>Volte ao painel para consultar a tentativa.</p>
        <button class="button button-secondary" id="backReview">Voltar ao curso</button>
      </div>
    `;
  }

  const retry = attempt.retryAuthorized
    ? '<div class="review-retry-action"><p class="success-note">Uma nova tentativa foi autorizada.</p><button class="button button-primary" id="startAttempt" type="button">Iniciar nova tentativa</button></div>'
    : '';

  return `
    <div class="review-card">
      <span class="status-pill ${statusClass(attempt.status)}">
        ${escapeHtml(statusLabel(attempt.status))}
      </span>
      <h2>${attempt.status === 'UNDER_REVIEW' ? 'Atividade em avaliação' : 'Resultado da avaliação'}</h2>
      ${attempt.score !== null ? `<p class="review-score">${attempt.score}%</p>` : ''}
      <p>${escapeHtml(review?.comments || attempt.reviewComments || reviewStatusMessage(attempt.status))}</p>
      ${review?.correctionDeadline
        ? `<p>Prazo para correção: <strong>${formatDate(review.correctionDeadline)}</strong></p>`
        : ''}
      ${retry}
      <button class="button button-secondary" id="backReview">Voltar ao curso</button>
    </div>
  `;
}

function reviewStatusMessage(status) {
  const messages = {
    UNDER_REVIEW: 'A submissão foi recebida e aguarda análise do avaliador.',
    CORRECTION_REQUIRED: 'Leia os comentários e aguarde ou use a autorização de nova tentativa.',
    FAILED: 'A atividade não atingiu os critérios de aprovação.',
    TIME_EXCEEDED: 'O prazo da tentativa terminou antes da submissão.'
  };
  return messages[status] || 'Consulte o estado da atividade.';
}

function bindAssessmentEvents() {
  document.querySelector('#backApproved')?.addEventListener('click', () => {
    location.hash = '#/';
  });
  document.querySelector('#backReview')?.addEventListener('click', () => {
    location.hash = '#/';
  });
  document.querySelector('#startAttempt')?.addEventListener('click', startAttempt);

  if (!state.attempt || state.attempt.status !== 'IN_PROGRESS') {
    return;
  }

  const delayedSave = debounce(saveTextAnswer, 750);

  root.querySelectorAll('[data-answer-text]').forEach((field) => {
    field.addEventListener('input', () => delayedSave(field));
    field.addEventListener('blur', () => saveTextAnswer(field));
  });

  root.querySelectorAll('.option-item input').forEach((input) => {
    input.addEventListener('change', () => saveOptionAnswer(input));
  });

  document.querySelector('#exerciseFiles')?.addEventListener('change', uploadFiles);
  document.querySelector('#driveUploadForm')?.addEventListener('submit', uploadDriveImage);
  document.querySelector('#submitAttempt')?.addEventListener('click', submitAttempt);
  bindDeleteFileEvents();
}

async function startAttempt(event) {
  const button = event.currentTarget;
  setBusy(button, true, 'A iniciar...');

  try {
    const result = await api.startAttempt(state.lesson.lesson.lessonId);
    state.attempt = result.attempt;
    state.attemptData = await api.attemptStatus(result.attempt.attemptId);

    document.querySelector('#assessmentArea').innerHTML = attemptFormTemplate(
      state.lesson,
      state.attempt,
      state.attemptData
    );

    bindAssessmentEvents();
    startTimer(state.attempt.deadlineAt);
    startStatusPoll(state.attempt.attemptId);
    showToast('Tentativa iniciada. O temporizador está em curso.', 'success');
    reportHeight();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

async function saveTextAnswer(field) {
  const questionId = field.dataset.answerText;
  const indicator = document.querySelector(
    `[data-save-indicator="${CSS.escape(questionId)}"]`
  );

  indicator.textContent = 'A guardar...';

  try {
    await api.saveAnswer(state.attempt.attemptId, questionId, {
      answerText: field.value
    });
    indicator.textContent = 'Guardado';
  } catch (error) {
    indicator.textContent = 'Erro ao guardar';
    handleError(error, false);
  }
}

async function saveOptionAnswer(input) {
  const card = input.closest('[data-question]');
  const questionId = card.dataset.question;
  const inputs = [...card.querySelectorAll('input')];
  const selected = inputs.filter((item) => item.checked).map((item) => item.value);
  const value = inputs[0]?.type === 'checkbox' ? selected : (selected[0] || '');
  const indicator = card.querySelector('[data-save-indicator]');

  indicator.textContent = 'A guardar...';

  try {
    await api.saveAnswer(state.attempt.attemptId, questionId, {
      selectedOptionId: value
    });
    indicator.textContent = 'Guardado';
  } catch (error) {
    indicator.textContent = 'Erro ao guardar';
    handleError(error, false);
  }
}

async function uploadFiles(event) {
  const files = [...event.target.files];
  if (!files.length) return;

  const progress = document.querySelector('#uploadProgress');
  progress.hidden = false;

  for (let index = 0; index < files.length; index += 1) {
    progress.textContent = `A enviar ${index + 1} de ${files.length}: ${files[index].name}`;

    try {
      await api.uploadFile(state.attempt.attemptId, files[index]);
      showToast(`${files[index].name} carregado.`, 'success');
    } catch (error) {
      handleError(error);
    }
  }

  progress.hidden = true;
  event.target.value = '';
  await refreshAttemptData();
}

async function uploadDriveImage(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const input = form.querySelector('#driveImageUrl');
  const button = form.querySelector('button');
  const progress = document.querySelector('#uploadProgress');
  const rawUrl = input.value.trim();

  if (!rawUrl) {
    input.focus();
    return;
  }

  progress.hidden = false;
  progress.textContent = 'A preparar imagem do Google Drive...';
  setBusy(button, true, 'A carregar...');

  try {
    const file = await fileFromDriveImageUrl(rawUrl);
    progress.textContent = `A enviar ${file.name}`;
    await api.uploadFile(state.attempt.attemptId, file);
    input.value = '';
    showToast(`${file.name} carregado.`, 'success');
    await refreshAttemptData();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
    progress.hidden = true;
    reportHeight();
  }
}

async function fileFromDriveImageUrl(rawUrl) {
  const sourceUrl = googleDriveDownloadUrl(rawUrl);
  let response;

  try {
    response = await fetch(sourceUrl, {
      method: 'GET',
      cache: 'no-store'
    });
  } catch {
    throw new Error('Não foi possível ler o link. Confirme que a imagem do Google Drive está pública.');
  }

  if (!response.ok) {
    throw new Error('Não foi possível descarregar a imagem do Google Drive.');
  }

  const blob = await response.blob();

  if (!blob.type.startsWith('image/')) {
    throw new Error('O link indicado precisa apontar para uma imagem pública do Google Drive.');
  }

  return new File([blob], driveImageFileName(rawUrl, blob.type), { type: blob.type });
}

function googleDriveDownloadUrl(rawUrl) {
  const fileId = googleDriveFileId(rawUrl);
  if (!fileId) return rawUrl;
  return `https://drive.google.com/uc?export=download&id=${encodeURIComponent(fileId)}`;
}

function googleDriveFileId(rawUrl) {
  try {
    const url = new URL(rawUrl);
    const queryId = url.searchParams.get('id');
    if (queryId) return queryId;

    const match = url.pathname.match(/\/file\/d\/([^/]+)/);
    return match?.[1] || '';
  } catch {
    return '';
  }
}

function driveImageFileName(rawUrl, mimeType) {
  const extensionByMime = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif'
  };
  const extension = extensionByMime[mimeType] || 'jpg';
  const fileId = googleDriveFileId(rawUrl);
  return `google-drive-${fileId || Date.now()}.${extension}`;
}

async function refreshAttemptData() {
  state.attemptData = await api.attemptStatus(state.attempt.attemptId);
  state.attempt = state.attemptData.attempt;

  const container = document.querySelector('#uploadedFiles');
  if (container) {
    container.innerHTML = state.attemptData.files.length
      ? state.attemptData.files.map(fileTemplate).join('')
      : '<p class="empty-note">Nenhum ficheiro carregado.</p>';
    bindDeleteFileEvents();
  }

  reportHeight();
}

function bindDeleteFileEvents() {
  root.querySelectorAll('[data-delete-file]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('Eliminar este ficheiro da tentativa?')) return;

      setBusy(button, true, '...');
      try {
        await api.deleteUploadedFile(button.dataset.deleteFile);
        await refreshAttemptData();
        showToast('Ficheiro eliminado.', 'success');
      } catch (error) {
        handleError(error);
      }
    });
  });
}

async function submitAttempt(event) {
  const checkbox = document.querySelector('#authorshipConfirmation');

  if (!checkbox.checked) {
    showToast('Confirme a declaração de autoria antes de submeter.', 'warning');
    checkbox.focus();
    return;
  }

  if (!window.confirm('Confirmar a submissão final da atividade?')) return;

  const button = event.currentTarget;
  setBusy(button, true, 'A submeter...');

  try {
    const result = await api.submitAttempt(state.attempt.attemptId);
    clearTimers();
    state.attempt = result.attempt;
    state.attemptData = await api.attemptStatus(result.attempt.attemptId);

    document.querySelector('#assessmentArea').innerHTML = reviewStateTemplate(
      state.attempt,
      state.attemptData.latestReview
    );
    bindAssessmentEvents();
    showToast('Atividade submetida com sucesso.', 'success');
    reportHeight();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

function startTimer(deadlineAt) {
  window.clearInterval(state.timerId);

  const update = () => {
    const timer = document.querySelector('#attemptTimer');
    if (!timer) return;

    const remaining = Math.max(
      0,
      Math.floor((new Date(deadlineAt).getTime() - Date.now()) / 1000)
    );

    timer.textContent = formatDuration(remaining);
    timer.closest('.timer-card')?.classList.toggle('is-critical', remaining <= 600);

    if (remaining <= 0) {
      window.clearInterval(state.timerId);
      showToast('O tempo da tentativa terminou.', 'warning');
      refreshExpiredAttempt();
    }
  };

  update();
  state.timerId = window.setInterval(update, 1000);
}

function startStatusPoll(attemptId) {
  window.clearInterval(state.pollId);

  state.pollId = window.setInterval(async () => {
    try {
      const data = await api.attemptStatus(attemptId);

      if (data.attempt.status !== 'IN_PROGRESS') {
        clearTimers();
        state.attempt = data.attempt;
        state.attemptData = data;

        document.querySelector('#assessmentArea').innerHTML = reviewStateTemplate(
          data.attempt,
          data.latestReview
        );
        bindAssessmentEvents();
        reportHeight();
      }
    } catch {
      // Não interromper o trabalho em caso de falha transitória do polling.
    }
  }, config.pollIntervalMs || 60000);
}

async function refreshExpiredAttempt() {
  try {
    const data = await api.attemptStatus(state.attempt.attemptId);
    state.attempt = data.attempt;
    state.attemptData = data;

    document.querySelector('#assessmentArea').innerHTML = reviewStateTemplate(
      data.attempt,
      data.latestReview
    );
    bindAssessmentEvents();
    reportHeight();
  } catch (error) {
    handleError(error);
  }
}

function clearTimers() {
  window.clearInterval(state.timerId);
  window.clearInterval(state.pollId);
  window.clearInterval(state.notificationPollId);
  state.timerId = null;
  state.pollId = null;
  state.notificationPollId = null;
}

async function startTelegramLink(event) {
  const button = event.currentTarget;
  const botWindow = window.open('', '_blank');
  if (botWindow) botWindow.opener = null;
  setBusy(button, true, 'A preparar...');
  try {
    const result = await api.startTelegramLink();
    state.telegramLinkToken = result.linkToken || '';
    state.telegramLinkUrl = result.linkUrl || '';
    const confirmButton = document.querySelector('#telegramConfirmButton');
    if (confirmButton) confirmButton.hidden = !state.telegramLinkToken;
    const directLink = document.querySelector('#telegramOpenLink');
    if (directLink) {
      directLink.href = state.telegramLinkUrl || '#';
      directLink.hidden = !state.telegramLinkUrl;
    }
    if (botWindow && state.telegramLinkUrl) {
      botWindow.location.replace(state.telegramLinkUrl);
    } else if (botWindow) {
      botWindow.close();
    }
    showToast('No Telegram, toque em “Iniciar” e depois confirme a associação aqui.', 'success');
  } catch (error) {
    if (botWindow) botWindow.close();
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

async function confirmTelegramLink(event) {
  const button = event.currentTarget;
  if (!state.telegramLinkToken) {
    showToast('Gere primeiro uma ligação ao Telegram.', 'error');
    return;
  }
  setBusy(button, true, 'A confirmar...');
  try {
    const result = await api.confirmTelegramLink(state.telegramLinkToken);
    if (!result.linked) {
      showToast(result.message || 'Ainda não foi possível confirmar. Inicie o bot e tente novamente.', 'error');
      return;
    }
    state.telegramLinkToken = '';
    state.telegramLinkUrl = '';
    if (state.dashboard) state.dashboard.student = result.student;
    showToast('Telegram associado e ativado.', 'success');
    await renderProfile();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

async function unlinkTelegram(event) {
  if (!window.confirm('Remover a associação ao Telegram e interromper as notificações neste canal?')) return;
  const button = event.currentTarget;
  setBusy(button, true, 'A remover...');
  try {
    const result = await api.unlinkTelegram();
    state.telegramLinkToken = '';
    state.telegramLinkUrl = '';
    if (state.dashboard) state.dashboard.student = result.student;
    showToast('Associação ao Telegram removida.', 'success');
    await renderProfile();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

function updateNotificationBadge() {
  const button = document.querySelector('.notification-button');
  if (!button) return;
  const unreadCount = Number(state.notifications.unreadCount || 0);
  button.setAttribute('aria-label', unreadCount ? `Notificações: ${unreadCount} não lidas` : 'Notificações');
  const currentBadge = button.querySelector('.notification-badge');
  if (!unreadCount) {
    currentBadge?.remove();
    return;
  }
  const badge = currentBadge || document.createElement('span');
  badge.className = 'notification-badge';
  badge.textContent = String(Math.min(unreadCount, 99));
  if (!currentBadge) button.appendChild(badge);
}

function startNotificationPolling() {
  window.clearInterval(state.notificationPollId);
  if (!api?.hasStudentSession()) return;
  const interval = Math.max(30000, Number(config.pollIntervalMs || 60000));
  state.notificationPollId = window.setInterval(async () => {
    if (document.hidden || !api.hasStudentSession()) return;
    try {
      setNotificationState(await api.notifications({ limit: 6 }));
      updateNotificationBadge();
    } catch {
      // A central interna permanece disponível; uma falha temporária será
      // repetida automaticamente no próximo ciclo.
    }
  }, interval);
}

function buildLessonNavigation() {
  const navigation = document.querySelector('#lessonNavigation');
  if (!navigation) return;

  navigation.innerHTML = state.lesson.content.map((section) => `
    <button type="button" data-scroll-section="${escapeHtml(section.contentId)}">
      ${escapeHtml(section.title)}
    </button>
  `).join('');

  navigation.querySelectorAll('[data-scroll-section]').forEach((button) => {
    button.addEventListener('click', () => {
      document
        .querySelector(`#section-${CSS.escape(button.dataset.scrollSection)}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function videoGallery() {
  const videos = state.media.videos.length ? state.media.videos : localVideoGallery();
  const studentEmail = String(state.dashboard?.student?.email || '').toLowerCase();

  return videos.filter((video) => {
    if (!videoEmbedUrl(video.url)) return false;
    if (video.status && video.status !== 'ACTIVE') return false;
    if (video.visibility !== 'SELECTED') return true;

    const allowed = normalizeEmailList(video.allowedEmails);
    return allowed.includes(studentEmail);
  });
}

function videoCardTemplate(video) {
  return `
    <article class="video-card" data-video-url="${escapeHtml(video.url)}">
      <div class="video-frame">
        <iframe src="${escapeHtml(videoEmbedUrl(video.url, { autoplay: true, muted: true }))}"
          title="${escapeHtml(video.title || 'Video da Summer School')}"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowfullscreen></iframe>
      </div>
      <div class="video-card-body">
        <div>
          <h3>${escapeHtml(video.title || 'Video da Summer School')}</h3>
          ${video.description ? `<p>${escapeHtml(video.description)}</p>` : ''}
        </div>
        <button class="video-sound-button" type="button" data-toggle-video-sound
          data-sound="off" aria-pressed="false" aria-label="Ativar som">
          ${soundIcon(false)}
        </button>
      </div>
    </article>
  `;
}

function bindVideoSoundEvents() {
  root.querySelectorAll('[data-toggle-video-sound]').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('[data-video-url]');
      const iframe = card?.querySelector('iframe');
      if (!card || !iframe) return;

      const soundOn = button.dataset.sound !== 'on';
      button.dataset.sound = soundOn ? 'on' : 'off';
      button.innerHTML = soundIcon(soundOn);
      button.setAttribute('aria-label', soundOn ? 'Desativar som' : 'Ativar som');
      button.setAttribute('aria-pressed', String(soundOn));
      iframe.src = videoEmbedUrl(card.dataset.videoUrl, {
        autoplay: true,
        muted: !soundOn
      });
    });
  });
}

function soundIcon(soundOn) {
  return soundOn
    ? `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 9v6h4l5 4V5L8 9H4Z"></path>
        <path d="M16 8.4a5 5 0 0 1 0 7.2"></path>
        <path d="M18.5 5.8a9 9 0 0 1 0 12.4"></path>
      </svg>`
    : `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 9v6h4l5 4V5L8 9H4Z"></path>
        <path d="m17 9 4 4"></path>
        <path d="m21 9-4 4"></path>
      </svg>`;
}

function videoEmbedUrl(rawUrl, options = {}) {
  if (!rawUrl) return '';
  const autoplay = options.autoplay !== false;
  const muted = options.muted !== false;

  try {
    const url = new URL(rawUrl);
    const host = url.hostname.replace(/^www\./, '');

    if (host === 'youtu.be') {
      const id = url.pathname.split('/').filter(Boolean)[0];
      return id ? youtubeEmbedUrl(id, autoplay, muted) : '';
    }

    if (host.endsWith('youtube.com')) {
      const watchId = url.searchParams.get('v');
      if (watchId) return youtubeEmbedUrl(watchId, autoplay, muted);

      const parts = url.pathname.split('/').filter(Boolean);
      const marker = parts.findIndex((part) => ['embed', 'shorts', 'live'].includes(part));
      const id = marker >= 0 ? parts[marker + 1] : '';
      return id ? youtubeEmbedUrl(id, autoplay, muted) : '';
    }

    if (host.endsWith('vimeo.com')) {
      const id = url.pathname.split('/').filter(Boolean).find((part) => /^\d+$/.test(part));
      return id ? vimeoEmbedUrl(id, autoplay, muted) : '';
    }
  } catch {
    return '';
  }

  return '';
}

function youtubeEmbedUrl(id, autoplay, muted) {
  const url = new URL(`https://www.youtube.com/embed/${encodeURIComponent(id)}`);
  url.searchParams.set('autoplay', autoplay ? '1' : '0');
  url.searchParams.set('mute', muted ? '1' : '0');
  url.searchParams.set('controls', '0');
  url.searchParams.set('modestbranding', '1');
  url.searchParams.set('rel', '0');
  url.searchParams.set('playsinline', '1');
  url.searchParams.set('iv_load_policy', '3');
  url.searchParams.set('fs', '0');
  url.searchParams.set('disablekb', '1');
  return url.toString();
}

function vimeoEmbedUrl(id, autoplay, muted) {
  const url = new URL(`https://player.vimeo.com/video/${encodeURIComponent(id)}`);
  url.searchParams.set('autoplay', autoplay ? '1' : '0');
  url.searchParams.set('muted', muted ? '1' : '0');
  url.searchParams.set('controls', '0');
  url.searchParams.set('title', '0');
  url.searchParams.set('byline', '0');
  url.searchParams.set('portrait', '0');
  url.searchParams.set('autopause', '0');
  url.searchParams.set('dnt', '1');
  return url.toString();
}

async function renderCertificate() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar o certificado...');

  const result = await api.certificate(state.selectedCourseId);

  if (!result.certificate) {
    root.innerHTML = `
      <div class="completion-card standalone-card">
        <h1>Certificado ainda indisponível</h1>
        <p>O certificado será disponibilizado depois da aprovação de todas as aulas.</p>
        <a class="button button-secondary" href="#/">Voltar ao curso</a>
      </div>
    `;
    return;
  }

  const certificate = result.certificate;

  root.innerHTML = `
    <section class="certificate-card">
      <p class="eyebrow">${escapeHtml(config.organizationName)}</p>
      <h1>Certificado de conclusão</h1>
      <p class="certificate-lead">Este registo confirma a conclusão do curso</p>
      <h2>${escapeHtml(config.appName)}</h2>

      <div class="certificate-data">
        <div><span>Número</span><strong>${escapeHtml(certificate.certificateNumber)}</strong></div>
        <div><span>Data</span><strong>${formatDate(certificate.issueDate)}</strong></div>
        <div><span>Classificação</span><strong>${certificate.finalScore}%</strong></div>
        <div><span>Verificação</span><strong>${escapeHtml(certificate.verificationCode)}</strong></div>
      </div>

      ${certificate.driveUrl
        ? `<a class="button button-primary" href="${escapeHtml(certificate.driveUrl)}" target="_blank">Abrir certificado</a>`
        : ''}
      <a class="button button-secondary" href="#/">Voltar ao curso</a>
    </section>
  `;

  reportHeight();
}

async function renderCertifications() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar as certificações...');

  const result = await api.certifications(state.selectedCourseId);
  const settings = result.settings || {};
  const certificates = result.certificates || [];
  const requests = result.requests || [];
  const simpleCertificate = result.simpleCertificate;
  const professionalCertificate = certificates.find((item) => item.certificateType === 'PROFESSIONAL' && item.status === 'ISSUED');
  const blockedProfessionalCertificate = certificates.find((item) => item.certificateType === 'PROFESSIONAL' && item.status === 'BLOCKED');
  const activeRequest = requests.find((item) => ['REQUESTED', 'PAYMENT_SUBMITTED'].includes(item.status));
  state.certifications = { ...result, settings, certificates, requests, activeRequest };

  if (!result.completed) {
    root.innerHTML = studentAppShell('certifications', `
      <div class="completion-card standalone-card">
        <h1>Certificações ainda indisponíveis</h1>
        <p>Conclua e obtenha aprovação em todos os módulos do curso para libertar os certificados.</p>
        <a class="button button-secondary" href="#/">Voltar ao curso</a>
      </div>
    `, {
      eyebrow: 'Certificados',
      title: 'Minhas certificações',
      description: 'Os certificados ficam disponíveis depois da conclusão do curso.'
    });
    reportHeight();
    return;
  }

  const certificateList = certificates.length
    ? certificates
    : [simpleCertificate].filter(Boolean);

  root.innerHTML = studentAppShell('certifications', `
    <section class="certifications-shell certifications-page">
      <div class="certifications-header">
        <div class="certifications-header-icon" aria-hidden="true">
          <img src="${iconUrl('award', goldIcon)}" alt="">
        </div>
        <div>
          <p class="eyebrow">Minhas certificações</p>
          <h1>Certificações</h1>
          <p>Certificados emitidos após a conclusão dos cursos elegíveis.</p>
        </div>
      </div>

      <div class="certification-list">
        ${certificateList.length ? certificateList.map(certificationListItemTemplate).join('') : `
          <div class="video-empty">Ainda não existem certificados emitidos.</div>
        `}
      </div>

      <section class="certificate-upgrade-panel">
        ${professionalCertificate
          ? professionalReadyTemplate(professionalCertificate)
          : professionalRequestFlowTemplate(settings, activeRequest, blockedProfessionalCertificate)}
      </section>
    </section>
  `, {
    eyebrow: 'Certificados',
    title: 'Minhas certificações',
    description: 'Visualize, baixe e acompanhe os seus certificados oficiais.'
  });

  root.querySelectorAll('[data-preview-certificate]').forEach((button) => {
    button.addEventListener('click', () => showCertificatePreview(button.dataset.previewCertificate));
  });
  root.querySelectorAll('[data-open-professional-survey]').forEach((button) => {
    button.addEventListener('click', () => showProfessionalSurveyDialog());
  });
  root.querySelectorAll('[data-open-payment-dialog]').forEach((button) => {
    button.addEventListener('click', () => showPaymentDialog(button.dataset.openPaymentDialog));
  });
  reportHeight();
}

function certificationListItemTemplate(certificate) {
  const isProfessional = certificate.certificateType === 'PROFESSIONAL';
  const isAvailable = certificate.status === 'ISSUED';
  const label = isProfessional ? 'CERTIFICADO PROFISSIONAL' : 'CERTIFICADO DE PARTICIPAÇÃO';
  const title = isProfessional ? 'Certificado profissional personalizado' : 'Certificado de Participação';
  const emittedAt = certificate.issueDate ? `Emitido em ${formatDate(certificate.issueDate)}` : 'Em emissão';
  const logoUrl = brandLogoUrl();
  return `
    <article class="certification-list-item ${isProfessional ? 'is-professional' : ''} ${isAvailable ? '' : 'is-blocked'}">
      <div class="certification-seal${logoUrl ? ' has-brand-logo' : ''}" aria-hidden="true">
        ${logoUrl ? `<img src="${escapeHtml(logoUrl)}" alt="">` : '<span>LSS</span>'}
      </div>
      <div class="certification-list-copy">
        <p class="eyebrow">${label}</p>
        <h2>${escapeHtml(certificate.courseTitle || state.dashboard?.course?.title || title)}</h2>
        <p>100% &middot; ${escapeHtml(isAvailable ? emittedAt : 'Acesso temporariamente removido pela administração')}</p>
        <div class="certification-list-actions">
          <code>${escapeHtml(certificateDisplayNumber(certificate) || certificate.certificateId || '')}</code>
          <button class="button button-secondary button-small" type="button"
            data-preview-certificate="${escapeHtml(certificate.certificateId)}" ${isAvailable ? '' : 'disabled'}>
            ${isAvailable ? 'Ver certificado' : 'Indisponível'}
          </button>
        </div>
      </div>
    </article>
  `;
}

function certificateDisplayNumber(certificate = {}) {
  return String(certificate.certificateNumber || '')
    .replace(/SIMPLE/gi, 'PART')
    .replace(/PARTICIPATION/gi, 'PART');
}

function professionalRequestFlowTemplate(settings, request, blockedCertificate = null) {
  const payment = certificatePaymentPolicy(settings);
  if (payment.blocked) {
    return `
      <article class="certificate-upgrade-card">
        <p class="eyebrow">Certificado profissional</p>
        <h2>Emissão temporariamente indisponível</h2>
        <p>A administração ainda não libertou novos pedidos para este certificado. Quando estiver disponível, as condições de emissão aparecerão aqui.</p>
      </article>
    `;
  }

  if (request?.status === 'PAYMENT_SUBMITTED') {
    return `
      <article class="certificate-upgrade-card">
        <p class="eyebrow">Certificado profissional</p>
        <h2>${payment.requiresPayment ? 'Comprovativo recebido' : 'Pedido recebido'}</h2>
        <p>A administração irá rever o pedido e libertar o certificado profissional se estiver tudo correto.</p>
      </article>
    `;
  }

  if (request?.status === 'REQUESTED') {
    if (!payment.requiresPayment) {
      return `
        <article class="certificate-upgrade-card">
          <p class="eyebrow">Certificado profissional</p>
          <h2>Pedido recebido</h2>
          <p>A administração irá rever o pedido e libertar o certificado profissional se estiver tudo correto.</p>
        </article>
      `;
    }
    return `
      <article class="certificate-upgrade-card">
        <p class="eyebrow">Certificado profissional</p>
        <h2>Pagamento pendente</h2>
        ${paymentConditionsTemplate(payment)}
        <button class="button button-primary" type="button"
          data-open-payment-dialog="${escapeHtml(request.requestId)}">
          Enviar comprovativo
        </button>
      </article>
    `;
  }

  return `
    <article class="certificate-upgrade-card">
      <div>
        <p class="eyebrow">Opcional</p>
        <h2>${blockedCertificate ? 'Solicitar nova libertação' : 'Certificado profissional personalizado'}</h2>
        <p>${blockedCertificate
          ? 'O acesso ao certificado profissional anterior foi removido. Pode iniciar um novo pedido para revisão administrativa.'
          : 'Um modelo institucional com descrição dos conteúdos aprendidos, verificação oficial, campos de assinatura e acabamento profissional.'}</p>
      </div>
      <div class="professional-certificate-mock">
        <strong>${escapeHtml(payment.issuerName || config.organizationName || 'Instituição emissora')}</strong>
        <span>Certificado profissional</span>
        <small>${payment.requiresPayment ? `Pagamento: ${escapeHtml(payment.amountLabel)}` : 'Sem pagamento obrigatorio'}</small>
      </div>
      ${paymentConditionsTemplate(payment)}
      <button class="button button-primary" type="button" data-open-professional-survey>
        Quero certificado profissional
      </button>
    </article>
  `;
}

function certificatePaymentPolicy(settings = {}) {
  const profile = settings.certificateProfile || {};
  const requiresPayment = (profile.printAccess || 'paid') === 'paid';
  const amount = profile.printFee || settings.professionalPrice || '';
  const currency = profile.printCurrency || 'MZN';
  return {
    requiresPayment,
    blocked: profile.printAccess === 'blocked',
    issuerName: profile.issuerName || '',
    amount,
    currency,
    amountLabel: amount ? `${amount} ${currency}` : 'Valor a confirmar',
    accountName: profile.paymentAccountName || '',
    accountNumber: profile.paymentAccountNumber || '',
    instructions: profile.paymentInstructions || settings.paymentInstructions || 'Siga as instruções de pagamento fornecidas pela administração.'
  };
}

function paymentConditionsTemplate(payment) {
  return `
    <div class="certificate-payment-conditions">
      <div><span>Condição</span><strong>${payment.requiresPayment ? 'Pagamento obrigatório' : 'Sem pagamento obrigatório'}</strong></div>
      ${payment.requiresPayment ? `
        <div><span>Valor</span><strong>${escapeHtml(payment.amountLabel)}</strong></div>
        ${payment.accountName ? `<div><span>Titular</span><strong>${escapeHtml(payment.accountName)}</strong></div>` : ''}
        ${payment.accountNumber ? `<div><span>Conta/carteira</span><strong>${escapeHtml(payment.accountNumber)}</strong></div>` : ''}
      ` : ''}
      <p>${escapeHtml(payment.instructions)}</p>
    </div>
  `;
}

function professionalReadyTemplate(certificate) {
  return `
    <article class="certificate-upgrade-card">
      <p class="eyebrow">Certificado profissional</p>
      <h2>Certificado profissional disponibilizado</h2>
      <p>O seu certificado profissional está pronto. Pode descarregá-lo até atingir o limite definido.</p>
      <button class="button button-primary" type="button"
        data-preview-certificate="${escapeHtml(certificate.certificateId)}">
        Ver certificado profissional
      </button>
    </article>
  `;
}

function showProfessionalSurveyDialog() {
  const settings = state.certifications?.settings || {};
  const questions = normalizedSurveyQuestions(settings.surveyQuestions);
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card certificate-survey-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <form id="professionalCertificateForm" class="form-stack">
        <div class="profile-section-heading">
          <div>
            <p class="eyebrow">Inquérito do curso</p>
            <h2>Antes do certificado profissional</h2>
          </div>
        </div>
        <p class="profile-security-note">Responda as perguntas abaixo para continuar para o pagamento.</p>
        <div class="survey-question-list">
          ${questions.map(surveyQuestionTemplate).join('')}
        </div>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-close-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Continuar</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-close-dialog]').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('#professionalCertificateForm').addEventListener('submit', (event) => submitProfessionalCertificateRequest(event, overlay));
  reportHeight();
}

function normalizedSurveyQuestions(value = []) {
  return Array.isArray(value) ? value.map((item, index) => {
    if (typeof item === 'string') {
      return {
        id: `q${index + 1}`,
        prompt: item,
        options: ['Excelente', 'Bom', 'Regular', 'Precisa melhorar'],
        required: true
      };
    }
    return {
      id: item.id || `q${index + 1}`,
      prompt: item.prompt || item.question || '',
      options: Array.isArray(item.options) && item.options.length ? item.options : ['Excelente', 'Bom', 'Regular', 'Precisa melhorar'],
      required: item.required !== false
    };
  }).filter((item) => item.prompt).slice(0, 10) : [];
}

function surveyQuestionTemplate(question, index) {
  return `
    <fieldset class="survey-question-card">
      <legend>${index + 1}. ${escapeHtml(question.prompt)}</legend>
      <div class="survey-option-grid">
        ${question.options.map((option, optionIndex) => `
          <label>
            <input type="radio" name="survey-${escapeHtml(question.id)}"
              value="${escapeHtml(option)}" ${question.required ? 'required' : ''}
              ${optionIndex === 0 ? 'checked' : ''}>
            <span>${escapeHtml(option)}</span>
          </label>
        `).join('')}
      </div>
    </fieldset>
  `;
}

async function submitProfessionalCertificateRequest(event, overlay = null) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const surveyAnswers = {};
  normalizedSurveyQuestions(state.certifications?.settings?.surveyQuestions || []).forEach((question) => {
    const selected = form.querySelector(`[name="survey-${CSS.escape(question.id)}"]:checked`);
    surveyAnswers[question.prompt] = selected?.value || '';
  });
  setBusy(button, true, 'A enviar...');
  try {
    const result = await api.requestProfessionalCertificate(state.selectedCourseId, surveyAnswers);
    const payment = certificatePaymentPolicy(state.certifications?.settings || {});
    showToast(payment.requiresPayment ? 'Pedido criado. Envie o comprovativo de pagamento.' : 'Pedido criado para revisão administrativa.', 'success');
    overlay?.remove();
    await renderCertifications();
    if (payment.requiresPayment) showPaymentDialog(result.request?.requestId);
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

function showPaymentDialog(requestId) {
  if (!requestId) return;
  const settings = state.certifications?.settings || {};
  const payment = certificatePaymentPolicy(settings);
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card certificate-payment-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <form id="professionalPaymentForm" class="form-stack">
        <div class="profile-section-heading">
          <div>
            <p class="eyebrow">Pagamento</p>
            <h2>Enviar comprovativo</h2>
          </div>
        </div>
        <div class="certificate-payment-box">
          ${paymentConditionsTemplate(payment)}
        </div>
        <input type="hidden" name="requestId" value="${escapeHtml(requestId)}">
        <label class="file-control">
          <input name="paymentReceipt" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" required>
          <span class="button button-secondary profile-photo-button">Selecionar comprovativo</span>
        </label>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-close-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Enviar comprovativo</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-close-dialog]').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  overlay.querySelector('#professionalPaymentForm').addEventListener('submit', (event) => submitProfessionalCertificatePayment(event, overlay));
  reportHeight();
}

async function submitProfessionalCertificatePayment(event, overlay = null) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const file = form.querySelector('[name="paymentReceipt"]')?.files?.[0];
  const requestId = new FormData(form).get('requestId');
  if (!file) {
    showToast('Selecione o comprovativo de pagamento.', 'warning');
    return;
  }
  setBusy(button, true, 'A enviar...');
  try {
    await api.submitProfessionalCertificatePayment(requestId, file);
    showToast('Comprovativo enviado para revisão.', 'success');
    overlay?.remove();
    await renderCertifications();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
}

function showCertificatePreview(certificateId) {
  const certificate = (state.certifications?.certificates || [])
    .find((item) => item.certificateId === certificateId);
  if (!certificate) return;
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card certificate-preview-dialog">
      <button class="dialog-close" type="button" aria-label="Fechar">x</button>
      <div class="certificate-preview-sheet ${certificate.certificateType === 'PROFESSIONAL' ? 'is-professional' : ''}">
        ${certificatePreviewTemplate(certificate)}
      </div>
      <div class="dialog-actions">
        <button class="button button-secondary" type="button" data-close-dialog>Fechar</button>
        <button class="button button-primary" type="button"
          data-download-certificate="${escapeHtml(certificate.certificateId)}">
          Baixar PDF
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-close-dialog]').addEventListener('click', () => overlay.remove());
  overlay.querySelector('[data-download-certificate]').addEventListener('click', () => downloadCertificate(certificate.certificateId, overlay));
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove();
  });
  reportHeight();
}

function certificatePreviewTemplate(certificate) {
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
            <strong>${escapeHtml(certificateDisplayNumber(certificate) || '')}</strong>
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
            <h2>${escapeHtml(certificate.studentName || state.dashboard?.student?.fullName || '')}</h2>
            <p>concluiu com sucesso o programa de aumento de qualificação profissional na ${escapeHtml(profile.issuerName || config.organizationName || 'Summer School')}</p>
            <span class="certificate-course-label">CURSO / PROGRAMA</span>
            <h3>${escapeHtml(certificate.courseTitle || state.dashboard?.course?.title || '')}</h3>
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
        <h2>${escapeHtml(certificate.studentName || state.dashboard?.student?.fullName || '')}</h2>
        <p>${isProfessional ? 'concluiu com êxito o programa profissional' : 'participou com sucesso do curso'}</p>
        <h3>${escapeHtml(certificate.courseTitle || state.dashboard?.course?.title || '')}</h3>
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
          <span><small>Nota final</small><strong>${certificate.finalScore == null ? '--/100' : `${escapeHtml(certificate.finalScore)}/100`}</strong></span>
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
        <span>N. do certificado: ${escapeHtml(certificateDisplayNumber(certificate) || '')}</span>
        <span>${escapeHtml(formatDate(certificate.issueDate))}</span>
        <span>Código: ${escapeHtml(certificate.verificationCode || '')}</span>
      </div>
    </div>
  `;
}

async function downloadCertificate(certificateId, overlay = null) {
  try {
    const cachedCertificate = state.certifications?.certificates?.find((item) => item.certificateId === certificateId);
    const model = cachedCertificate?.certificateType === 'PROFESSIONAL' ? 'professional' : 'participation';
    const blob = await api.certificatePdf(certificateId, model);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${certificateDisplayNumber(cachedCertificate) || certificateId}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('Certificado descarregado.', 'success');
    overlay?.remove();
    await renderCertifications();
  } catch (error) {
    handleError(error);
  }
}

function showReviewDialog(attemptData) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card">
      <button class="dialog-close" type="button" aria-label="Fechar">A—</button>
      ${reviewStateTemplate(attemptData.attempt, attemptData.latestReview)}
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('.dialog-close').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#backReview')?.addEventListener('click', () => overlay.remove());
  reportHeight();
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
    if (mobileThemeButton) {
      mobileThemeButton.textContent = theme === 'dark' ? 'Modo claro' : 'Modo noturno';
    }
  };

  applyTheme(document.documentElement.dataset.theme || 'light');

  themeToggle.addEventListener('click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(nextTheme);
  });
}

function studentGreeting(fullName) {
  const hour = new Date().getHours();
  const period = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite';
  return `${period}, ${fullName}, seja bem-vindo ao LMTWEBNAIRS Summer School 2026`;
}

function iconUrl(name, color) {
  const resolvedColor = document.documentElement.dataset.theme === 'dark' ? 'ffffff' : color;
  const iconName = lucideIconAliases[name] || name;
  return `${lucideIconsBase}/${encodeURIComponent(iconName)}.svg?color=%23${resolvedColor}&width=20&height=20`;
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

async function loadStudentMediaConfig() {
  try {
    const result = await api.mediaConfig(state.selectedCourseId);
    setMediaConfig(result.mediaConfig || result);
  } catch {
    setMediaConfig(localMediaConfig());
  }
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

function renderConfigurationError(error) {
  root.innerHTML = `
    <div class="configuration-error">
      <h1>Configuração incompleta</h1>
      <p>${escapeHtml(error.message)}</p>
      <code>public/config.js</code>
    </div>
  `;
}

function handleError(error, toast = true) {
  console.error(error);

  if (
    error instanceof ApiError &&
    ['INVALID_SESSION', 'SESSION_EXPIRED', 'SESSION_REQUIRED'].includes(error.code)
  ) {
    localStorage.removeItem('courseSessionToken');
    renderLogin();
  }

  if (toast) {
    showToast(error.message || 'Ocorreu um erro.', 'error');
  }
}

