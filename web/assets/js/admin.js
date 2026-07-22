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

let api;
const state = {
  pending: [],
  students: [],
  selectedSubmission: null
};

initialize();

function initialize() {
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
      <div class="auth-card">
        <div class="brand-mark">ADM</div>
        <p class="eyebrow">Área reservada</p>
        <h1>Painel do avaliador</h1>

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
        <h2>Gestão do curso</h2>
        <button class="admin-nav is-active" data-admin-view="pending">
          Submissões
        </button>
        <button class="admin-nav" data-admin-view="students">
          Estudantes
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

  main.innerHTML = `
    <div class="admin-page-heading">
      <div>
        <p class="eyebrow">Avaliação</p>
        <h1>Submissões pendentes</h1>
      </div>
      <button class="button button-secondary" id="refreshPending">Atualizar</button>
    </div>

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
    renderStudents();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderStudents() {
  const main = document.querySelector('#adminMain');

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
