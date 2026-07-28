import { CoursePlatformApi, ApiError } from './api.js';
import {
  escapeHtml,
  formatBytes,
  formatDate,
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
const icons8Base = 'https://img.icons8.com/ios-filled/50';
const blueIcon = '00365b';
const goldIcon = 'c9a55b';

let api;
let submissionSearchTimer;
let studentSearchTimer;
let courseSearchTimer;
const state = {
  admin: null,
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
    content: 'ALL'
  },
  selectedSubmission: null,
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
  staff: []
};

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
      loadPending();
    } catch (error) {
      handleAdminError(error);
    }
  } else {
    renderAdminLogin();
  }
}

function renderAdminLogin() {
  logoutButton.hidden = true;
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
            <span>Senha administrativa</span>
            <input type="password" name="adminKey" required>
          </label>
          <button class="button button-primary button-block" type="submit">
            Entrar
          </button>
        </form>

        <div id="adminLoginError" class="form-message form-message-error" hidden></div>
      </div>
    </section>
  `;

  document.querySelector('#adminLoginForm').addEventListener('submit', login);
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
    await loadPending();
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    setBusy(button, false);
    reportHeight();
  }
}

async function logout() {
  try {
    await api.adminLogout();
  } catch {
    sessionStorage.removeItem('courseAdminToken');
  }
  state.admin = null;
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
      canManageStaff() ? (typeof api.adminStaff === 'function' ? api.adminStaff() : api.adminstaff()) : Promise.resolve()
    ]);
  }, 1200);
}

function renderAdminShell() {
  logoutButton.hidden = false;
  adminIdentity.hidden = false;
  if (state.admin) {
    adminIdentity.textContent = `${state.admin.fullName} · ${state.admin.role}`;
  }

  root.innerHTML = `
    <div class="admin-layout">
      <aside class="admin-sidebar">
        <div class="admin-sidebar-heading">
          ${brandSymbolTemplate('admin-sidebar-symbol')}
          <h2>Gestão da Summer School</h2>
        </div>
        <button class="admin-nav is-active" data-admin-view="pending">
          <img src="${iconUrl('inbox', blueIcon)}" alt="">
          <span>Submissões</span>
        </button>
        <button class="admin-nav" data-admin-view="students">
          <img src="${iconUrl('student-male', blueIcon)}" alt="">
          <span>Estudantes</span>
        </button>
        <button class="admin-nav" data-admin-view="courses">
          <img src="${iconUrl('book-shelf', blueIcon)}" alt="">
          <span>Cursos</span>
        </button>
        <button class="admin-nav" data-admin-view="videos">
          <img src="${iconUrl('video-playlist', blueIcon)}" alt="">
          <span>Vídeos</span>
        </button>
        <button class="admin-nav" data-admin-view="brand">
          <img src="${iconUrl('picture', blueIcon)}" alt="">
          <span>Marca</span>
        </button>
        ${canManageStaff() ? `
          <button class="admin-nav" data-admin-view="staff">
            <img src="${iconUrl('conference-call', blueIcon)}" alt="">
            <span>Staff</span>
          </button>
        ` : ''}
        ${canManageCredentials() ? `
          <button class="admin-nav" data-admin-view="credentials">
            <img src="${iconUrl('key', blueIcon)}" alt="">
            <span>Credenciais</span>
          </button>
        ` : ''}
        <button class="admin-nav" data-admin-view="profile">
          <img src="${iconUrl('user-male-circle', blueIcon)}" alt="">
          <span>Perfil</span>
        </button>
      </aside>

      <main class="admin-main" id="adminMain"></main>
    </div>
  `;

  root.querySelectorAll('[data-admin-view]').forEach((button) => {
    button.addEventListener('click', () => {
      setActiveAdminView(button.dataset.adminView);

      if (button.dataset.adminView === 'students') {
        loadStudents();
      } else if (button.dataset.adminView === 'courses') {
        state.courseMode = 'list';
        loadCourses();
      } else if (button.dataset.adminView === 'videos') {
        renderVideos();
      } else if (button.dataset.adminView === 'brand') {
        renderBrandSettings();
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
}

function setActiveAdminView(view) {
  root.querySelectorAll('[data-admin-view]').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.adminView === view);
  });
}

function confirmAdminAction(message) {
  return window.confirm(message);
}

function bindDialogClose(overlay) {
  overlay.querySelector('.dialog-close')?.addEventListener('click', () => overlay.remove());
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
        <p class="eyebrow">Seguranca de acesso</p>
        <h1>Credenciais</h1>
      </div>
    </div>

    <section class="credential-management-grid">
      <article class="credential-management-card">
        <img src="${iconUrl('student-male', goldIcon)}" alt="">
        <div>
          <span>Estudantes</span>
          <h2>Restaurar acesso dos participantes</h2>
          <p>Cria senhas temporarias para contas importadas ou selecionadas.</p>
        </div>
        <button class="button button-primary" type="button" data-open-credential-target="STUDENTS">
          Abrir restauracao
        </button>
      </article>

      ${canRestoreStaff ? `
        <article class="credential-management-card">
          <img src="${iconUrl('conference-call', goldIcon)}" alt="">
          <div>
            <span>Staff</span>
            <h2>Restaurar acesso administrativo</h2>
            <p>Disponivel apenas para owner e com invalidacao de sessoes antigas.</p>
          </div>
          <button class="button button-primary" type="button" data-open-credential-target="ADMINS">
            Abrir restauracao
          </button>
        </article>

        <article class="credential-management-card">
          <img src="${iconUrl('key', goldIcon)}" alt="">
          <div>
            <span>Lote completo</span>
            <h2>Tratar estudantes e staff</h2>
            <p>Usar em migracoes ou correcao geral de contas sem senha.</p>
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
        <p class="eyebrow">Gestao de Staff</p>
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
            <th>Permissao</th>
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
          ` : '<span class="empty-note">Sem permissao para editar</span>'}
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
            <span>Permissao</span>
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
    if (!confirmAdminAction('Deseja guardar estas permissoes de staff?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    setBusy(button, true, 'A guardar...');
    try {
      const result = await api.adminSaveStaff(values);
      if (result.adminPassword) {
        alert(`Staff guardado.\n\nSenha temporaria: ${result.adminPassword}\n\nGuarde a senha antes de fechar.`);
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
  const verb = status === 'DELETED' ? 'remover permissoes deste membro' : 'alterar o estado deste membro';
  if (!confirmAdminAction(`Tem certeza que deseja ${verb}?`)) return;

  try {
    await api.adminSetStaffStatus(adminId, status);
    showToast('Permissoes atualizadas.', 'success');
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
        Gere novas senhas temporarias para contas ja existentes no Supabase. O progresso,
        inscricoes, grupos e submissoes nao sao alterados.
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
              <option value="missing" selected>Apenas contas sem senha</option>
              <option value="rotate">Substituir senhas selecionadas</option>
            </select>
          </label>
        </div>

        <label class="credential-checkbox-line">
          <input type="checkbox" name="includeInactive">
          <span>Incluir contas inativas ou bloqueadas</span>
        </label>

        <div class="select-all-toolbar">
          <button class="button button-small button-secondary" type="button" data-select-credentials="all">Selecionar todos</button>
          <button class="button button-small button-secondary" type="button" data-select-credentials="none">Limpar selecao</button>
        </div>

        <div id="credentialCandidateList" class="credential-candidate-list">
          ${credentialCandidateListTemplate(defaultTarget)}
        </div>

        <div id="credentialRecoveryResult" class="credential-result" hidden></div>

        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Gerar senhas</button>
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
      ? 'Isto vai substituir as senhas atuais das contas selecionadas e encerrar sessoes abertas. Continuar?'
      : 'Gerar senha temporaria apenas para contas selecionadas que ainda nao possuem senha?';
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
    meta: `${student.publicStudentId || student.studentId} - ${student.email}`,
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
    return '<p class="empty-note">Nenhuma conta disponivel para este filtro.</p>';
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
        <strong>${Number(summary.total || credentials.length)} senha(s) temporaria(s) criada(s)</strong>
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
              <th>Senha temporaria</th>
            </tr>
          </thead>
          <tbody>
            ${credentials.map((item) => `
              <tr>
                <td>${item.type === 'ADMIN' ? 'Staff' : 'Estudante'}</td>
                <td>${escapeHtml(item.fullName || '')}</td>
                <td>${escapeHtml(item.email || '')}</td>
                <td>${escapeHtml(item.publicId || item.id || '')}</td>
                <td><code>${escapeHtml(item.temporaryPassword || '')}</code></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : '<p class="empty-note">Nenhuma conta precisava de nova senha neste modo.</p>'}
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
      item.publicId || item.id || '',
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
          <div><dt>Permissao</dt><dd>${escapeHtml(admin.role || '-')}</dd></div>
          <div><dt>Criado em</dt><dd>${escapeHtml(formatDate(admin.createdAt))}</dd></div>
          <div><dt>Atualizado em</dt><dd>${escapeHtml(formatDate(admin.updatedAt))}</dd></div>
        </dl>
      </article>

      <article class="profile-card">
        <div class="profile-section-heading">
          <div>
            <p class="eyebrow">Sessao</p>
            <h2>Acesso atual</h2>
          </div>
        </div>
        <p class="profile-security-note">Use sair quando terminar a gestao administrativa neste dispositivo.</p>
        <button class="button button-secondary" id="adminProfileLogout" type="button">Sair da conta</button>
      </article>
    </section>
  `;

  document.querySelector('#adminProfileLogout').addEventListener('click', logout);
  reportHeight();
}

async function loadPending(options = {}) {
  const main = document.querySelector('#adminMain');
  if (!options.silent) {
    main.innerHTML = loadingTemplate('A carregar submissoes...');
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
      console.warn('Falha ao atualizar submissoes em segundo plano:', error);
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
        <p class="eyebrow">Avaliacao</p>
        <h1>Submissoes</h1>
      </div>
      <button class="button button-secondary" id="refreshPending">Atualizar</button>
    </div>

    <section class="admin-summary-grid" aria-label="Resumo de avaliacao">
      <article class="insight-card">
        <img src="${iconUrl('inbox', goldIcon)}" alt="">
        <div>
          <span>Visiveis</span>
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

    <section class="admin-filter-bar" aria-label="Filtros de submissoes">
      <label>
        <span>Estado</span>
        <select id="submissionStatusFilter">
          ${submissionStatusOption('ALL', 'Todas', state.submissionFilters.status)}
          ${submissionStatusOption('UNDER_REVIEW', 'Pendentes', state.submissionFilters.status)}
          ${submissionStatusOption('REVIEWED', 'Ja avaliadas', state.submissionFilters.status)}
          ${submissionStatusOption('APPROVED', 'Aprovadas', state.submissionFilters.status)}
          ${submissionStatusOption('CORRECTION_REQUIRED', 'Correcao solicitada', state.submissionFilters.status)}
          ${submissionStatusOption('FAILED', 'Nao aprovadas', state.submissionFilters.status)}
          ${submissionStatusOption('TIME_EXCEEDED', 'Tempo excedido', state.submissionFilters.status)}
        </select>
      </label>
      <label class="admin-filter-search">
        <span>Pesquisar</span>
        <input id="submissionSearch" type="search" value="${escapeHtml(state.submissionFilters.query)}"
          placeholder="Estudante, email, aula ou comentario">
      </label>
    </section>

    <section class="access-control-panel">
      <div class="course-section-heading">
        <div>
          <p class="eyebrow">Acesso aos modulos</p>
          <h2>Liberar ou restringir conteudos</h2>
        </div>
      </div>
      <form id="lessonAccessForm" class="access-control-form">
        <label>
          <span>Curso</span>
          <select name="courseId" id="accessCourse">
            ${accessCourseOptions()}
          </select>
        </label>
        <label>
          <span>Acao</span>
          <select name="status">
            <option value="AVAILABLE">Disponibilizar novamente</option>
            <option value="LOCKED">Restringir acesso</option>
          </select>
        </label>
        <fieldset>
          <legend>Modulos</legend>
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
        <button class="button button-primary" type="submit">Aplicar acesso</button>
      </form>
    </section>

    <div class="admin-table-wrap">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Estudante</th>
            <th>Aula</th>
            <th>Estado</th>
            <th>Nota</th>
            <th>Ultima decisao</th>
            <th>Ficheiros</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${visibleSubmissions.length
            ? visibleSubmissions.map(submissionRowTemplate).join('')
            : '<tr><td colspan="7" class="empty-table">Nao existem submissoes para os filtros atuais.</td></tr>'}
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
      </td>
      <td>
        <span class="status-pill submission-status-pill ${statusClass(item.attempt.status)}">
          ${statusLabel(item.attempt.status)}
        </span>
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
  if (!lessons.length) return '<p class="empty-note">Sem modulos neste curso.</p>';
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
      <span>${escapeHtml(student.publicStudentId || student.studentId)} - ${escapeHtml(student.fullName)}</span>
    </label>
  `).join('');
}

function selectAllToolbar(inputName) {
  return `
    <div class="select-all-toolbar">
      <button class="button button-secondary button-small" type="button"
        data-select-all="${escapeHtml(inputName)}">Selecionar todos</button>
      <button class="button button-secondary button-small" type="button"
        data-clear-all="${escapeHtml(inputName)}">Limpar selecao</button>
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
    status: values.get('status'),
    lessonIds: values.getAll('lessonIds'),
    groupIds: values.getAll('groupIds'),
    studentIds: values.getAll('studentIds')
  };

  if (!payload.groupIds.length && !payload.studentIds.length) {
    showToast('Selecione pelo menos uma turma ou estudante.', 'warning');
    return;
  }

  if (!confirmAdminAction('Deseja aplicar esta alteracao de acesso aos estudantes selecionados?')) return;

  setBusy(button, true, 'A aplicar...');
  try {
    const result = await api.adminSetLessonAccess(payload);
    showToast(`Acesso atualizado para ${result.studentCount} estudante(s).`, 'success');
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

  main.innerHTML = `
    <button class="text-button" id="backPending">Voltar para submissoes</button>

    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Tentativa ${data.attempt.attemptNumber}</p>
        <h1>${escapeHtml(data.student.fullName)}</h1>
        <p>${escapeHtml(data.lesson.title)}</p>
      </div>

      <span class="status-pill ${statusClass(data.attempt.status)}">
        ${statusLabel(data.attempt.status)}
      </span>
    </div>

    <div class="submission-columns">
      <section>
        <h2>Respostas</h2>
        ${answers || '<p class="empty-note">Nenhuma resposta registada.</p>'}
      </section>

      <aside>
        <div class="review-form-card">
          <h2>Avaliação</h2>
          ${latestReview ? `
            <p class="review-history-note">
              Ultima decisao: ${escapeHtml(statusLabel(latestReview.decision))}
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
              <span>Comentários</span>
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
          ${files || '<p class="empty-note">Nenhum ficheiro.</p>'}
        </div>

        <div class="review-files">
          <h2>Acesso deste estudante</h2>
          <div class="student-detail-actions">
            <button class="button button-secondary" type="button" data-student-access="AVAILABLE">
              Disponibilizar modulo
            </button>
            <button class="button button-secondary" type="button" data-student-access="LOCKED">
              Restringir modulo
            </button>
          </div>
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
  root.querySelectorAll('[data-student-access]').forEach((button) => {
    button.addEventListener('click', () => applySingleStudentAccess(button.dataset.studentAccess));
  });
  reportHeight();
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

async function applySingleStudentAccess(status) {
  const data = state.selectedSubmission;
  if (!data) return;

  const label = status === 'AVAILABLE' ? 'disponibilizar' : 'restringir';
  if (!window.confirm(`Deseja ${label} este modulo para ${data.student.fullName}?`)) return;

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

  if (!confirmAdminAction('Deseja guardar esta avaliacao? Esta decisao pode alterar o progresso do estudante.')) return;

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
          <span>Progresso médio</span>
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
          placeholder="Nome, email, pais ou organizacao">
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
          ${studentFilterOption('recentLogin', 'Ultimo acesso', state.studentFilters.sort)}
        </select>
      </label>
      <button class="button button-secondary" id="exportStudents" type="button">
        Exportar CSV
      </button>
    </section>

    <div class="student-list-meta">
      <strong>${visibleStudents.length}</strong>
      <span>de ${state.students.length} estudantes visiveis</span>
    </div>

    <div class="student-admin-grid">
      ${visibleStudents.length ? visibleStudents.map(studentCardTemplate).join('') : `
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
    button.addEventListener('click', () => showStudentDetails(button.dataset.viewStudent));
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
  const organization = student.organization || 'Sem organizacao';
  const country = student.country || 'Sem pais';

  return `
    <article class="student-admin-card">
      <div class="student-card-header">
        <span class="student-avatar">${escapeHtml(studentInitials(student.fullName))}</span>
        <div>
          <span class="status-pill ${statusClass(student.status)}">
            ${statusLabel(student.status)}
          </span>
          <h3>${escapeHtml(student.fullName)}</h3>
          <p>${escapeHtml(student.publicStudentId || student.studentId)} · ${escapeHtml(student.email)}</p>
        </div>
      </div>

      <dl class="student-meta-grid">
        <div>
          <dt>Organizacao</dt>
          <dd>${escapeHtml(organization)}</dd>
        </div>
        <div>
          <dt>Pais</dt>
          <dd>${escapeHtml(country)}</dd>
        </div>
        <div>
          <dt>Ultimo acesso</dt>
          <dd>${escapeHtml(lastLogin)}</dd>
        </div>
        <div>
          <dt>Curso</dt>
          <dd>${escapeHtml(primary?.courseId || 'Sem inscricao')}</dd>
        </div>
      </dl>

      <div class="student-progress-line">
        <span>Progresso</span>
        <strong>${progress}%</strong>
      </div>
      <div class="student-progress-track">
        <span style="width:${progress}%"></span>
      </div>

      <div class="student-admin-actions">
        <button type="button" data-view-student="${escapeHtml(student.studentId)}">Detalhes</button>
        <button type="button" data-copy-email="${escapeHtml(student.email)}">Copiar email</button>
        <button type="button" data-reset-access="${escapeHtml(student.studentId)}">Nova senha</button>
        <button type="button"
          data-toggle-student="${escapeHtml(student.studentId)}"
          data-current-status="${escapeHtml(student.status)}">
          ${student.status === 'ACTIVE' ? 'Bloquear' : 'Ativar'}
        </button>
      </div>
    </article>
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
        <div><dt>ID publico</dt><dd>${escapeHtml(student.publicStudentId || student.studentId)}</dd></div>
        <div><dt>Pais</dt><dd>${escapeHtml(student.country || 'Sem registo')}</dd></div>
        <div><dt>Organizacao</dt><dd>${escapeHtml(student.organization || 'Sem registo')}</dd></div>
        <div><dt>Criado em</dt><dd>${escapeHtml(formatDate(student.createdAt))}</dd></div>
        <div><dt>Atualizado em</dt><dd>${escapeHtml(formatDate(student.updatedAt))}</dd></div>
        <div><dt>Ultimo acesso</dt><dd>${escapeHtml(formatDate(student.lastLoginAt))}</dd></div>
      </dl>

      <section class="student-detail-section">
        <div class="student-detail-section-heading">
          <h3>Percurso academico</h3>
          <strong>${progress}%</strong>
        </div>
        <div class="student-progress-track">
          <span style="width:${progress}%"></span>
        </div>
        <div class="student-enrollment-list">
          ${enrollments.length ? enrollments.map(enrollmentTemplate).join('') : `
            <div class="student-empty-state">Sem inscricoes registadas.</div>
          `}
        </div>
      </section>

      <div class="student-detail-actions">
        <button class="button button-secondary" type="button" data-copy-email="${escapeHtml(student.email)}">
          Copiar email
        </button>
        <button class="button button-secondary" type="button" data-reset-access="${escapeHtml(student.studentId)}">
          Nova senha
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
    ['ID publico', 'Nome', 'Email', 'Estado', 'Pais', 'Organizacao', 'Progresso', 'Ultimo acesso']
  ];

  records.forEach(({ student, enrollments }) => {
    rows.push([
      student.publicStudentId || student.studentId || '',
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
        <p class="eyebrow">Catalogo academico</p>
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
        <span>Modulos</span>
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
          placeholder="ID, codigo, nome ou descricao">
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
        <span>Conteudo</span>
        <select id="courseContentFilter">
          ${studentFilterOption('ALL', 'Todos', state.courseFilters.content)}
          ${studentFilterOption('WITH_MODULES', 'Com modulos', state.courseFilters.content)}
          ${studentFilterOption('WITHOUT_MODULES', 'Sem modulos', state.courseFilters.content)}
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

  return `
    <article class="admin-course-card">
      <div>
        <div class="admin-course-card-topline">
          <span class="status-pill ${statusClass(status)}">${statusLabel(status)}</span>
          <small>${escapeHtml(course.courseCode || course.courseId || '')}</small>
        </div>
        <h2>${escapeHtml(course.title || 'Curso sem nome')}</h2>
        <p>${escapeHtml(course.description || 'Sem descricao registada.')}</p>
      </div>
      <dl>
        <div>
          <dt>ID</dt>
          <dd>${escapeHtml(course.courseId || '-')}</dd>
        </div>
        <div>
          <dt>Modulos</dt>
          <dd>${item.lessonCount || 0}</dd>
        </div>
        <div>
          <dt>Grupos</dt>
          <dd>${item.groupCount || 0}</dd>
        </div>
      </dl>
      <div class="admin-course-card-actions">
        <button class="button button-primary" type="button"
          data-open-course-detail="${escapeHtml(course.courseId || '')}">
          Abrir detalhes
        </button>
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
          <p class="eyebrow">Conteudo academico</p>
          <h1>Cursos e modulos</h1>
        </div>
        <div class="admin-heading-actions">
          <button class="button button-primary" id="newCourse" type="button">Novo curso</button>
        </div>
      </div>
      <section class="student-empty-state">
        Nenhum curso ativo encontrado. Crie um curso para iniciar a gestao de conteudos.
      </section>
    `;
    document.querySelector('#newCourse').addEventListener('click', () => showCourseDialog());
    return;
  }
  const lessons = (state.courseStructure?.lessons || []).filter(({ lesson }) => lesson?.status !== 'DELETED');
  const groups = (state.groups || []).filter(({ group }) => group?.status !== 'DELETED');
  const deletedLessons = (state.courseStructure?.lessons || []).filter(({ lesson }) => lesson?.status === 'DELETED').length;
  const deletedGroups = (state.groups || []).filter(({ group }) => group?.status === 'DELETED').length;
  const totalContent = lessons.reduce((sum, item) => sum + (item.content?.length || 0), 0);
  const totalQuestions = lessons.reduce((sum, item) => sum + (item.questions?.length || 0), 0);

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Conteudo academico</p>
        <h1>${escapeHtml(course.title || 'Cursos e modulos')}</h1>
      </div>
      <div class="admin-heading-actions">
        <button class="button button-secondary" id="backToCourseList" type="button">Todos os cursos</button>
        <button class="button button-secondary" id="newCourse" type="button">Novo curso</button>
      </div>
    </div>

    <section class="admin-content-overview">
      <article class="content-metric-card">
        <span>Modulos ativos</span>
        <strong>${lessons.length}</strong>
        <small>${deletedLessons} eliminados</small>
      </article>
      <article class="content-metric-card">
        <span>Conteudos</span>
        <strong>${totalContent}</strong>
        <small>Seccoes cadastradas</small>
      </article>
      <article class="content-metric-card">
        <span>Questoes</span>
        <strong>${totalQuestions}</strong>
        <small>Avaliacao</small>
      </article>
      <article class="content-metric-card">
        <span>Grupos ativos</span>
        <strong>${groups.length}</strong>
        <small>${deletedGroups} eliminados</small>
      </article>
    </section>

    <section class="admin-content-tabs" aria-label="Organizacao do conteudo">
      <button type="button" class="${state.courseView === 'overview' ? 'is-active' : ''}" data-course-view="overview">Visao geral</button>
      <button type="button" class="${state.courseView === 'modules' ? 'is-active' : ''}" data-course-view="modules">Modulos</button>
      <button type="button" class="${state.courseView === 'groups' ? 'is-active' : ''}" data-course-view="groups">Grupos</button>
    </section>

    ${courseManagementPanel(course, lessons, groups)}
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
  root.querySelectorAll('[data-edit-group]').forEach((button) => {
    button.addEventListener('click', () => showGroupDialog(button.dataset.editGroup));
  });
  root.querySelectorAll('[data-delete-group]').forEach((button) => {
    button.addEventListener('click', () => deleteGroup(button.dataset.deleteGroup));
  });

  reportHeight();
}

function courseManagementPanel(course, lessons, groups) {
  if (state.courseView === 'modules') {
    return `
      <section class="admin-content-panel">
        <div class="course-section-heading">
          <div>
            <p class="eyebrow">Nivel 2</p>
            <h2>Modulos do curso</h2>
          </div>
          <button class="button button-primary" id="newLesson" type="button">Novo modulo</button>
        </div>
        <div class="course-module-list course-module-list-clean">
          ${lessons.length ? lessons.map(moduleCardTemplate).join('') : `
            <div class="student-empty-state">Nenhum modulo registado.</div>
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
            <p class="eyebrow">Nivel 3</p>
            <h2>Grupos e estudantes</h2>
          </div>
          <button class="button button-primary" id="newGroup" type="button">Nova turma</button>
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
          <p class="eyebrow">Nivel 1</p>
          <h2>Configuracao do curso</h2>
        </div>
      </div>

      <form id="courseForm" class="course-overview-form form-stack">
        <input type="hidden" name="courseId" value="${escapeHtml(course.courseId || config.courseId || '')}">
        <div class="course-form-grid">
          <label>
            <span>Codigo</span>
            <input name="courseCode" value="${escapeHtml(course.courseCode || '')}" required>
          </label>
          <label>
            <span>Titulo</span>
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
          <span>Descricao</span>
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
          <button class="button button-secondary" type="reset">Cancelar alteracoes</button>
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
        <div><dt>Conteudos</dt><dd>${contentCount}</dd></div>
        <div><dt>Questoes</dt><dd>${questionCount}</dd></div>
      </dl>
      <div class="admin-row-actions">
        <button class="button button-secondary button-small" type="button"
          data-manage-lesson-access="${escapeHtml(lesson.lessonId)}">
          Gerir acesso
        </button>
        <button class="button button-secondary button-small" type="button"
          data-edit-lesson="${escapeHtml(lesson.lessonId)}">
          Editar modulo
        </button>
        <button class="button button-danger button-small" type="button"
          data-delete-lesson="${escapeHtml(lesson.lessonId)}">
          Eliminar
        </button>
      </div>
    </article>
  `;
}

function groupCardTemplate(item) {
  const group = item.group || item;
  return `
    <article class="course-module-card">
      <div>
        <span class="status-pill ${statusClass(group.status)}">${statusLabel(group.status)}</span>
        <h3>${escapeHtml(group.name)}</h3>
        <p>${escapeHtml(group.groupCode || group.groupId)} · ${escapeHtml(formatDate(group.startDate))} ate ${escapeHtml(formatDate(group.endDate))}</p>
      </div>
      <dl>
        <div><dt>Membros</dt><dd>${item.memberCount || 0}</dd></div>
        <div><dt>Curso</dt><dd>${escapeHtml(group.courseId)}</dd></div>
        <div><dt>Inicio</dt><dd>${escapeHtml(formatDate(group.startDate))}</dd></div>
        <div><dt>Fim</dt><dd>${escapeHtml(formatDate(group.endDate))}</dd></div>
        <div><dt>Estado</dt><dd>${escapeHtml(statusLabel(group.status))}</dd></div>
      </dl>
      <div class="admin-row-actions">
        <button class="button button-secondary button-small" type="button"
          data-edit-group="${escapeHtml(group.groupId)}">
          Gerir turma
        </button>
        <button class="button button-danger button-small" type="button"
          data-delete-group="${escapeHtml(group.groupId)}">
          Eliminar
        </button>
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
      <h2>Acesso do modulo</h2>
      <p class="dialog-helper-text">
        Aula ${escapeHtml(lesson.lessonNumber)} - ${escapeHtml(lesson.title)}
      </p>
      <form id="lessonAccessDialogForm" class="form-stack">
        <input type="hidden" name="courseId" value="${escapeHtml(courseId)}">
        <input type="hidden" name="lessonId" value="${escapeHtml(lesson.lessonId)}">
        <label>
          <span>Acao</span>
          <select name="status">
            <option value="AVAILABLE">Disponibilizar este modulo</option>
            <option value="LOCKED">Restringir este modulo</option>
          </select>
        </label>
        <fieldset class="group-student-picker">
          <legend>Estudantes</legend>
          ${selectAllToolbar('studentIds')}
          <div class="video-student-list">
            ${moduleAccessStudentCheckboxes(courseId, students)}
          </div>
        </fieldset>
        <div class="dialog-actions">
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Aplicar acesso</button>
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

    if (!studentIds.length) {
      showToast('Selecione pelo menos um estudante.', 'warning');
      return;
    }

    if (!confirmAdminAction('Deseja aplicar esta alteracao de acesso ao modulo para os estudantes selecionados?')) {
      return;
    }

    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, 'A aplicar...');
    try {
      const result = await api.adminSetLessonAccess({
        courseId: values.get('courseId'),
        status: values.get('status'),
        lessonIds: [values.get('lessonId')],
        studentIds,
        groupIds: []
      });
      showToast(`Acesso atualizado para ${result.studentCount || studentIds.length} estudante(s).`, 'success');
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
        <strong>${escapeHtml(student.publicStudentId || student.studentId)} - ${escapeHtml(student.fullName)}</strong>
        <small>${escapeHtml(student.email)}</small>
      </span>
    </label>
  `).join('');
}

async function saveCourse(event) {
  event.preventDefault();

  if (!confirmAdminAction('Deseja guardar as alteracoes deste curso?')) return;

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
  if (!confirmAdminAction('Tem certeza que deseja eliminar este curso? O historico fica preservado, mas o curso deixa de ficar ativo.')) return;

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

async function deleteLesson(lessonId) {
  const found = (state.courseStructure?.lessons || []).find((item) => item.lesson?.lessonId === lessonId);
  const lesson = found?.lesson;
  if (!lesson) return;
  if (!confirmAdminAction(`Eliminar o modulo "${lesson.title}"?`)) return;

  try {
    await api.adminSaveLesson({
      ...lesson,
      status: 'DELETED'
    });
    showToast('Modulo eliminado.', 'success');
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

function showCourseDialog() {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>Novo curso</h2>
      <form id="newCourseForm" class="form-stack">
        <label>
          <span>Codigo</span>
          <input name="courseCode" required>
        </label>
        <label>
          <span>Titulo</span>
          <input name="title" required>
        </label>
        <label>
          <span>Descricao</span>
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
          <span>Codigo</span>
          <input name="groupCode" value="${escapeHtml(group.groupCode || '')}" placeholder="opcional">
        </label>
        <div class="course-form-grid">
          <label>
            <span>Inicio</span>
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
                  <strong>${escapeHtml(student.publicStudentId || student.studentId)} · ${escapeHtml(student.fullName)}</strong>
                  <small>${escapeHtml(student.email)}</small>
                </span>
              </label>
            `).join('') : '<p class="empty-note">Carregue a seccao Estudantes antes de gerir membros.</p>'}
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
    passingScore: state.courseStructure?.course?.passingScore || 60,
    prerequisiteLessonId: '',
    status: 'ACTIVE'
  };

  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card course-lesson-dialog">
      <button class="dialog-close" type="button">x</button>
      <h2>${lessonId ? 'Editar modulo' : 'Novo modulo'}</h2>
      <form id="lessonForm" class="form-stack">
        <input type="hidden" name="lessonId" value="${escapeHtml(lesson.lessonId || '')}">
        <input type="hidden" name="courseId" value="${escapeHtml(lesson.courseId || state.courseStructure?.course?.courseId || config.courseId)}">
        <div class="course-form-grid">
          <label>
            <span>Numero</span>
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
          <span>Titulo</span>
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
        </div>
        <label>
          <span>Modulo pre-requisito</span>
          <select name="prerequisiteLessonId">
            ${studentFilterOption('', 'Sem pre-requisito', lesson.prerequisiteLessonId || '')}
            ${lessons
              .filter((item) => item.lesson?.lessonId !== lesson.lessonId)
              .map((item) => studentFilterOption(item.lesson.lessonId, `Aula ${item.lesson.lessonNumber} - ${item.lesson.title}`, lesson.prerequisiteLessonId || ''))
              .join('')}
          </select>
        </label>
        <div class="dialog-actions">
          ${lessonId ? '<button class="button button-danger" type="button" data-delete-dialog-lesson>Eliminar modulo</button>' : ''}
          <button class="button button-secondary" type="button" data-cancel-dialog>Cancelar</button>
          <button class="button button-primary" type="submit">Guardar modulo</button>
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
    if (!confirmAdminAction('Deseja guardar este modulo?')) return;
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const values = Object.fromEntries(new FormData(form));
    ['lessonNumber', 'passingScore', 'theoryMinutes', 'exerciseMinutes', 'individualMinutes'].forEach((field) => {
      values[field] = Number(values[field] || 0);
    });

    setBusy(button, true, 'A guardar...');
    try {
      await api.adminSaveLesson(values);
      showToast('Modulo guardado.', 'success');
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
        <button class="button button-primary" type="submit">Publicar vídeo</button>
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
        : '<div class="video-empty">Nenhum vídeo publicado.</div>'}
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
          <p>Este logotipo substitui o texto LSS no cabeçalho, nos cartões de login e no painel administrativo.</p>
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
    return '<p class="empty-note">Nenhum estudante disponivel para selecao.</p>';
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
    showToast('Vídeo publicado na galeria.', 'success');
    await renderVideos();
  } catch (error) {
    handleAdminError(error);
  } finally {
    setBusy(button, false);
  }
}

async function deleteVideo(videoId) {
  if (!window.confirm('Remover este vídeo da galeria?')) return;

  try {
    state.media.videos = videoGallery().filter((video) => video.id !== videoId);
    await saveMediaConfig();
    showToast('Vídeo removido.', 'success');
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
      <button class="dialog-close" type="button">×</button>
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
        `Estudante criado.\n\nSenha temporaria: ${result.accessCode}\n\nGuarde a senha antes de fechar.`
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
      `Nova senha temporaria: ${result.accessCode}\n\nGuarde-a antes de fechar.`
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
    const icon = themeToggle.querySelector('.theme-toggle-icon');
    if (icon) icon.textContent = theme === 'dark' ? '☾' : '☀';
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
  return `${icons8Base}/${resolvedColor}/${name}.png`;
}

function updateThemeIcons(theme) {
  document.querySelectorAll('img[src^="https://img.icons8.com/ios-filled/50/"]').forEach((image) => {
    const url = new URL(image.src);
    const parts = url.pathname.split('/');
    if (parts.length < 4) return;
    const currentColor = parts[3];
    const originalColor = image.dataset.iconColor || (currentColor === 'ffffff' ? goldIcon : currentColor);
    image.dataset.iconColor = originalColor;
    parts[3] = theme === 'dark' ? 'ffffff' : originalColor;
    url.pathname = parts.join('/');
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
    showToast('Media carregada localmente. Confirme a conexao com a API Python para sincronizar com Supabase.', 'warning');
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
