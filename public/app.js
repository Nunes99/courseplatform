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
const platformName = config.appName || 'LMTWEBNAIRS Summer School 2026';
const platformYear = 'Summer School 2026';
const icons8Base = 'https://img.icons8.com/ios-filled/50';
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
  timerId: null,
  pollId: null
};

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

  await loadPublicMediaConfig();
  applyBrandLogo();

  headerUser.addEventListener('click', openProfileFromHeader);
  document.addEventListener('error', handleProfilePhotoError, true);
  initializeMobileMenu();
  logoutButton.addEventListener('click', logout);
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
    return;
  }

  route();
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

    if (routeName === 'certificate') {
      await renderCertificate();
      return;
    }

    if (routeName === 'profile') {
      await renderProfile();
      return;
    }

    await renderDashboard();
  } catch (error) {
    handleError(error);
  }
}

function renderLogin() {
  clearTimers();
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
            <span>Senha de acesso</span>
            <input type="password" name="accessCode" autocomplete="current-password"
              required placeholder="Senha fornecida pelo administrador">
          </label>
          <button class="button button-primary button-block" type="submit">
            Entrar na plataforma
          </button>
          <button class="text-button login-recovery-link" type="button" id="recoverAccessButton">
            Esqueci a senha de acesso
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

  mobileMenuButton.addEventListener('click', (event) => {
    event.stopPropagation();
    const willOpen = mobileMenu.hidden;
    mobileMenu.hidden = !willOpen;
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
}

function closeMobileMenu() {
  if (!mobileMenu || !mobileMenuButton) return;
  mobileMenu.hidden = true;
  mobileMenuButton.setAttribute('aria-expanded', 'false');
}

async function login(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const data = new FormData(form);
  const button = form.querySelector('button');
  const errorBox = document.querySelector('#loginError');

  errorBox.hidden = true;
  setBusy(button, true, 'A autenticar…');

  try {
    await api.login(data.get('email'), data.get('accessCode'));
    location.hash = '#/';
    await renderDashboard();
  } catch (error) {
    if (error instanceof ApiError && error.code === 'INVALID_CREDENTIALS') {
      errorBox.innerHTML = `
        <span>${escapeHtml(error.message)}</span>
        <button class="text-button" type="button" id="recoverAfterLoginError">
          Recuperar senha
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
      <h2>Recuperar senha de acesso</h2>
      <p class="recovery-note">
        Informe o email e o ID publico do estudante para gerar uma nova senha temporaria.
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
          <button class="button button-primary" type="submit">Gerar senha temporaria</button>
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
      resultBox.textContent = error.message || 'Nao foi possivel recuperar o acesso.';
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
    <span>Senha temporaria criada para ${escapeHtml(result.email || email)}</span>
    <strong>${escapeHtml(result.temporaryPassword || '')}</strong>
    <div class="recovery-result-actions">
      <button class="button button-secondary button-small" type="button" data-copy-temporary-password>
        Copiar senha
      </button>
      <button class="button button-primary button-small" type="button" data-use-temporary-password>
        Usar no login
      </button>
    </div>
  `;
  resultBox.querySelector('[data-copy-temporary-password]').addEventListener('click', () => {
    copyText(result.temporaryPassword || '', 'Senha temporaria copiada.');
  });
  resultBox.querySelector('[data-use-temporary-password]').addEventListener('click', () => {
    const loginForm = document.querySelector('#loginForm');
    if (loginForm) {
      loginForm.elements.email.value = email || '';
      loginForm.elements.accessCode.value = result.temporaryPassword || '';
    }
    overlay.remove();
    showToast('Senha temporaria preenchida no login.', 'success');
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
  location.hash = '';
  renderLogin();
}

async function renderDashboard() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar o curso…');

  const courseBundle = await api.myCourses();
  state.myCourses = courseBundle.courses || [];
  if (!state.selectedCourseId || !state.myCourses.some((item) => item.course.courseId === state.selectedCourseId)) {
    state.selectedCourseId = state.myCourses[0]?.course?.courseId || config.courseId || '';
    localStorage.setItem('courseSelectedCourseId', state.selectedCourseId);
  }

  const dashboard = await api.dashboard(state.selectedCourseId);
  state.dashboard = dashboard;
  await loadStudentMediaConfig();
  applyBrandLogo();

  const greeting = studentGreeting(dashboard.student.fullName);
  headerUser.innerHTML = profileAvatarTemplate(dashboard.student, 'header-avatar');
  headerUser.title = 'Editar perfil pessoal';
  headerUser.setAttribute('aria-label', 'Editar perfil pessoal');
  headerUser.hidden = false;
  if (mobileMenuButton) mobileMenuButton.hidden = false;
  logoutButton.hidden = true;

  const totalLessons = dashboard.lessons.length;
  const approvedLessons = dashboard.lessons.filter((item) => item.progress.status === 'APPROVED').length;
  const activeLessons = dashboard.lessons.filter((item) => ['AVAILABLE', 'IN_PROGRESS', 'UNDER_REVIEW'].includes(item.progress.status)).length;
  const videos = videoGallery();

  const certificateButton = dashboard.enrollment.status === 'COMPLETED'
    ? '<a class="button button-secondary" href="#/certificate">Ver certificado</a>'
    : '';

  root.innerHTML = `
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

    <section class="student-courses-panel" aria-label="Cursos disponiveis">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Meus cursos</p>
          <h2>Cursos disponiveis para si</h2>
        </div>
      </div>
      <div class="student-course-list">
        ${state.myCourses.length ? state.myCourses.map(studentCourseCardTemplate).join('') : `
          <div class="video-empty">Ainda nao existem cursos associados ao seu perfil.</div>
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

    <section class="section-heading">
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
        <div><strong>3.</strong><span>Responda e carregue evidências.</span></div>
        <div><strong>4.</strong><span>Acompanhe a avaliação.</span></div>
      </div>
    </section>
  `;

  root.querySelectorAll('[data-open-lesson]').forEach((button) => {
    button.addEventListener('click', () => {
      location.hash = `#/lesson/${button.dataset.openLesson}`;
    });
  });

  root.querySelectorAll('[data-select-student-course]').forEach((button) => {
    button.addEventListener('click', async () => {
      state.selectedCourseId = button.dataset.selectStudentCourse;
      localStorage.setItem('courseSelectedCourseId', state.selectedCourseId);
      await renderDashboard();
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
  renderMath();
}

function studentCourseCardTemplate(item) {
  const course = item.course;
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
        <h3>${escapeHtml(course.title)}</h3>
        <p>${escapeHtml(course.description || 'Curso associado ao seu perfil.')}</p>
      </div>
      <dl>
        <div><dt>Progresso</dt><dd>${Number(enrollment.progressPercent || 0)}%</dd></div>
        <div><dt>Modulos</dt><dd>${item.lessonCount || 0}</dd></div>
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

async function renderProfile() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar perfil...');

  const courseBundle = await api.myCourses();
  state.myCourses = courseBundle.courses || [];
  const student = courseBundle.student || state.dashboard?.student || {};
  headerUser.innerHTML = profileAvatarTemplate(student, 'header-avatar');
  headerUser.title = 'Editar perfil pessoal';
  headerUser.setAttribute('aria-label', 'Editar perfil pessoal');
  headerUser.hidden = false;
  if (mobileMenuButton) mobileMenuButton.hidden = false;
  logoutButton.hidden = true;

  root.innerHTML = `
    <section class="profile-shell profile-shell-modern">
      <div class="profile-header-card">
        <div class="profile-identity">
          <div class="profile-photo-frame profile-photo-frame-large">
            ${profilePhotoTemplate(student)}
          </div>
          <div>
            <p class="eyebrow">Perfil pessoal</p>
            <h1>${escapeHtml(student.fullName || 'Estudante')}</h1>
            <p>${escapeHtml(student.publicStudentId || '')} · ${escapeHtml(student.email || '')}</p>
          </div>
        </div>
        <div class="profile-status-grid" aria-label="Resumo do perfil">
          <div>
            <span>ID publico</span>
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
              <h2>Informacoes pessoais</h2>
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
            <label>
              <span>Email</span>
              <input value="${escapeHtml(student.email || '')}" disabled>
            </label>
            <label>
              <span>Pais</span>
              <input name="country" value="${escapeHtml(student.country || '')}">
            </label>
            <label>
              <span>Telefone</span>
              <input name="phone" value="${escapeHtml(student.phone || '')}">
            </label>
            <label>
              <span>Organizacao</span>
              <input name="organization" value="${escapeHtml(student.organization || '')}">
            </label>
            <label>
              <span>Funcao profissional</span>
              <input name="jobTitle" value="${escapeHtml(student.jobTitle || '')}">
            </label>
          </div>

          <label>
            <span>Interesses academicos ou profissionais</span>
            <textarea name="interests" rows="5">${escapeHtml(student.interests || '')}</textarea>
          </label>

          <div class="profile-actions">
            <a class="button button-secondary" href="#/">Voltar ao curso</a>
            <button class="button button-primary" type="submit">Guardar perfil</button>
          </div>
        </form>

        <form id="passwordForm" class="profile-card profile-security form-stack">
          <div class="profile-section-heading">
            <div>
              <p class="eyebrow">Seguranca</p>
              <h2>Alterar senha de acesso</h2>
            </div>
          </div>
          <label>
            <span>Senha atual</span>
            <input type="password" name="currentAccessCode" autocomplete="current-password" required>
          </label>
          <label>
            <span>Nova senha</span>
            <input type="password" name="newAccessCode" autocomplete="new-password" minlength="8" required>
          </label>
          <label>
            <span>Confirmar nova senha</span>
            <input type="password" name="confirmAccessCode" autocomplete="new-password" minlength="8" required>
          </label>
          <div class="profile-security-note">
            Ao alterar a senha, sera necessario iniciar sessao novamente.
          </div>
          <div class="profile-actions">
            <button class="button button-primary" type="submit">Alterar senha</button>
          </div>
        </form>

        <section class="profile-card profile-exit">
          <div class="profile-section-heading">
            <div>
              <p class="eyebrow">Sessao</p>
              <h2>Terminar acesso</h2>
            </div>
          </div>
          <p>Saia da plataforma quando terminar de usar este dispositivo.</p>
          <button class="button button-secondary" id="profileLogoutButton" type="button">Sair da conta</button>
        </section>
      </div>
    </section>
  `;

  document.querySelector('#profileForm').addEventListener('submit', saveProfile);
  document.querySelector('#passwordForm').addEventListener('submit', changePassword);
  document.querySelector('#profileLogoutButton').addEventListener('click', logout);
  bindProfilePhotoPreview(student);
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
    showToast('A confirmacao da nova senha nao corresponde.', 'error');
    return;
  }

  setBusy(button, true, 'A alterar...');

  try {
    await api.changeMyAccessCode(currentAccessCode, newAccessCode);
    state.dashboard = null;
    state.myCourses = [];
    location.hash = '';
    showToast('Senha alterada. Inicie sessao novamente.', 'success');
    renderLogin();
  } catch (error) {
    handleError(error);
  } finally {
    setBusy(button, false);
  }
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
      showToast('Selecione uma imagem valida.', 'error');
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
  const locked = progress.status === 'LOCKED';
  const reviewState = [
    'UNDER_REVIEW',
    'CORRECTION_REQUIRED',
    'FAILED',
    'TIME_EXCEEDED'
  ].includes(progress.status);

  let action;

  if (reviewState && activeAttempt) {
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
        ${progress.status === 'APPROVED' ? 'Rever aula' : 'Abrir aula'}
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
          <span class="status-pill ${statusClass(progress.status)}">
            ${escapeHtml(statusLabel(progress.status))}
          </span>
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
  root.innerHTML = loadingTemplate('A carregar a aula…');

  const lessonData = await api.getLesson(lessonId);
  state.lesson = lessonData;

  let activeAttempt = state.dashboard?.lessons?.find(
    (item) => item.lesson.lessonId === lessonId
  )?.activeAttempt || null;

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
        <button class="text-button" id="backDashboard">← Voltar ao curso</button>
        <p class="eyebrow">Aula ${lessonData.lesson.lessonNumber}</p>
        <h2>${escapeHtml(lessonData.lesson.title)}</h2>
        <div class="lesson-time-summary">
          <span>Teoria<strong>${lessonData.lesson.theoryMinutes} min</strong></span>
          <span>Exercícios<strong>${lessonData.lesson.exerciseMinutes} min</strong></span>
          <span>Individual<strong>${lessonData.lesson.individualMinutes} min</strong></span>
        </div>
        <nav id="lessonNavigation" class="lesson-navigation"></nav>
      </aside>

      <main class="lesson-main">
        <header class="lesson-header">
          <span class="status-pill ${statusClass(lessonData.progress.status)}">
            ${escapeHtml(statusLabel(lessonData.progress.status))}
          </span>
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
  const status = attempt?.status || lessonData.progress.status;

  if (lessonData.progress.status === 'APPROVED') {
    return `
      <div class="completion-card">
        <div class="completion-icon">✓</div>
        <h2>Aula aprovada</h2>
        <p>Obteve ${lessonData.progress.score}% e pode rever todo o conteúdo.</p>
        <button class="button button-secondary" id="backApproved">Voltar ao curso</button>
      </div>
    `;
  }

  if (['UNDER_REVIEW', 'CORRECTION_REQUIRED', 'FAILED', 'TIME_EXCEEDED'].includes(status)) {
    return reviewStateTemplate(attempt, attemptData?.latestReview);
  }

  if (!attempt) {
    const minutes = lessonData.lesson.exerciseMinutes + lessonData.lesson.individualMinutes;
    return `
      <div class="start-assessment-card">
        <p class="eyebrow">Avaliação prática</p>
        <h2>Preparado para iniciar?</h2>
        <p>
          Ao iniciar, o temporizador de ${minutes} minutos começará no servidor
          e continuará mesmo que feche a página.
        </p>
        <button class="button button-primary" id="startAttempt">Iniciar exercícios</button>
      </div>
    `;
  }

  return attemptFormTemplate(lessonData, attempt, attemptData);
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
        <p class="eyebrow">Documentos obrigatórios</p>
        <h3>Carregue fotografias ou ficheiros</h3>
        <p>As imagens serão otimizadas antes do envio. Confirme que todos os cálculos estão legíveis.</p>
      </div>

      <div class="upload-methods">
        <label class="upload-dropzone" for="exerciseFiles">
          <input id="exerciseFiles" type="file" multiple
            accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx">
          <span class="upload-icon">↑</span>
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
        <span>Confirmo que resolvi pessoalmente os exercícios apresentados.</span>
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
        placeholder="Escreva a sua resposta…">${escapeHtml(answer?.answerText || '')}</textarea>
    `;
  }

  return `
    <article class="question-card" data-question="${escapeHtml(question.questionId)}">
      <div class="question-number">Questão ${question.questionOrder}</div>
      <h3>${escapeHtml(question.prompt)}</h3>
      <p class="question-points">${question.points} pontos ${question.isRequired ? '· obrigatória' : ''}</p>
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
    ? '<p class="success-note">Uma nova tentativa foi autorizada. Volte ao curso e abra novamente esta aula.</p>'
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
  setBusy(button, true, 'A iniciar…');

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

  indicator.textContent = 'A guardar…';

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

  indicator.textContent = 'A guardar…';

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

      setBusy(button, true, '…');
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
  setBusy(button, true, 'A submeter…');

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
  state.timerId = null;
  state.pollId = null;
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
          title="${escapeHtml(video.title || 'Vídeo da Summer School')}"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowfullscreen></iframe>
      </div>
      <div class="video-card-body">
        <div>
          <h3>${escapeHtml(video.title || 'Vídeo da Summer School')}</h3>
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
  root.innerHTML = loadingTemplate('A carregar o certificado…');

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

function showReviewDialog(attemptData) {
  const overlay = document.createElement('div');
  overlay.className = 'dialog-overlay';
  overlay.innerHTML = `
    <div class="dialog-card">
      <button class="dialog-close" type="button" aria-label="Fechar">×</button>
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
    const icon = themeToggle.querySelector('.theme-toggle-icon');
    if (icon) icon.textContent = theme === 'dark' ? '☾' : '☀';
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
  return `${icons8Base}/${resolvedColor}/${name}.png`;
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
