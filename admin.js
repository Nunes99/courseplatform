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
const state = {
  pending: [],
  students: [],
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
  }
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
  new ResizeObserver(reportHeight).observe(document.body);

  if (api.hasAdminSession()) {
    renderAdminShell();
    loadPending();
  } else {
    renderAdminLogin();
  }
}

function renderAdminLogin() {
  logoutButton.hidden = true;
  adminIdentity.textContent = '';

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
            <span>Chave administrativa</span>
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
    adminIdentity.textContent = `${result.admin.fullName} · ${result.admin.role}`;
    renderAdminShell();
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
  renderAdminLogin();
}

function renderAdminShell() {
  logoutButton.hidden = false;

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
        <button class="admin-nav" data-admin-view="videos">
          <img src="${iconUrl('video-playlist', blueIcon)}" alt="">
          <span>Vídeos</span>
        </button>
        <button class="admin-nav" data-admin-view="brand">
          <img src="${iconUrl('picture', blueIcon)}" alt="">
          <span>Marca</span>
        </button>
      </aside>

      <main class="admin-main" id="adminMain"></main>
    </div>
  `;

  root.querySelectorAll('[data-admin-view]').forEach((button) => {
    button.addEventListener('click', () => {
      root.querySelectorAll('[data-admin-view]').forEach((item) => {
        item.classList.remove('is-active');
      });

      button.classList.add('is-active');

      if (button.dataset.adminView === 'students') {
        loadStudents();
      } else if (button.dataset.adminView === 'videos') {
        renderVideos();
      } else if (button.dataset.adminView === 'brand') {
        renderBrandSettings();
      } else {
        loadPending();
      }
    });
  });
}

async function loadPending() {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar submissões…');

  try {
    const result = await api.adminPending();
    state.pending = result.submissions;
    renderPending();
  } catch (error) {
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

  document.querySelector('#refreshPending').addEventListener('click', loadPending);

  root.querySelectorAll('[data-open-submission]').forEach((button) => {
    button.addEventListener('click', () => {
      openSubmission(button.dataset.openSubmission);
    });
  });

  reportHeight();
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
    <button class="text-button" id="backPending">← Submissões pendentes</button>

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
      </aside>
    </div>
  `;

  document.querySelector('#backPending').addEventListener('click', loadPending);
  document.querySelector('#reviewForm').addEventListener('submit', submitReview);
  reportHeight();
}

async function submitReview(event) {
  event.preventDefault();

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

async function loadStudents() {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar estudantes…');

  try {
    const result = await api.adminStudents();
    state.students = result.students;
    renderStudentsV2();
  } catch (error) {
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
  document.querySelector('#studentSearch').addEventListener('input', (event) => {
    state.studentFilters.query = event.currentTarget.value;
    renderStudentsV2();
  });
  document.querySelector('#studentStatusFilter').addEventListener('change', (event) => {
    state.studentFilters.status = event.currentTarget.value;
    renderStudentsV2();
  });
  document.querySelector('#studentProgressFilter').addEventListener('change', (event) => {
    state.studentFilters.progress = event.currentTarget.value;
    renderStudentsV2();
  });
  document.querySelector('#studentSort').addEventListener('change', (event) => {
    state.studentFilters.sort = event.currentTarget.value;
    renderStudentsV2();
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
          <p>${escapeHtml(student.email)}</p>
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
        <button type="button" data-reset-access="${escapeHtml(student.studentId)}">Novo codigo</button>
        <button type="button"
          data-toggle-student="${escapeHtml(student.studentId)}"
          data-current-status="${escapeHtml(student.status)}">
          ${student.status === 'ACTIVE' ? 'Bloquear' : 'Ativar'}
        </button>
      </div>
    </article>
  `;
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
        <div><dt>ID</dt><dd>${escapeHtml(student.studentId)}</dd></div>
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
          Novo codigo
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
    ['Nome', 'Email', 'Estado', 'Pais', 'Organizacao', 'Progresso', 'Ultimo acesso']
  ];

  records.forEach(({ student, enrollments }) => {
    rows.push([
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

async function renderVideos() {
  const main = document.querySelector('#adminMain');
  main.innerHTML = loadingTemplate('A carregar vídeos…');
  await loadAdminMediaConfig();
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
          <select name="visibility">
            <option value="PUBLIC">Todos os estudantes</option>
            <option value="SELECTED">Apenas emails selecionados</option>
          </select>
        </label>
        <label class="admin-video-description">
          <span>Emails autorizados</span>
          <textarea name="allowedEmails" rows="3"
            placeholder="um email por linha, vírgula ou ponto e vírgula"></textarea>
        </label>
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

async function saveVideo(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const url = String(values.get('url') || '').trim();
  const visibility = String(values.get('visibility') || 'PUBLIC');
  const allowedEmails = normalizeEmailList(values.get('allowedEmails'));

  if (!videoEmbedUrl(url)) {
    showToast('Adicione um link válido do YouTube ou Vimeo.', 'warning');
    form.elements.url.focus();
    return;
  }

  if (visibility === 'SELECTED' && !allowedEmails.length) {
    showToast('Informe pelo menos um email autorizado.', 'warning');
    form.elements.allowedEmails.focus();
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
        `Estudante criado.\n\nCódigo de acesso: ${result.accessCode}\n\nGuarde o código antes de fechar.`
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
      `Novo código de acesso: ${result.accessCode}\n\nGuarde-o antes de fechar.`
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

async function loadAdminMediaConfig() {
  try {
    const result = await api.adminMediaConfig();
    setMediaConfig(result.mediaConfig || result);
  } catch {
    setMediaConfig(localMediaConfig());
    showToast('Media carregada localmente. Publique as funções do Apps Script para sincronizar com Google Sheets.', 'warning');
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
