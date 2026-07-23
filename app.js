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
const platformName = config.appName || 'LMTWEBNAIRS Summer School 2026';
const platformYear = 'Summer School 2026';
const icons8Base = 'https://img.icons8.com/ios-filled/50';

let api;
const state = {
  dashboard: null,
  lesson: null,
  attempt: null,
  attemptData: null,
  timerId: null,
  pollId: null
};

initialize();

function initialize() {
  initializeThemeToggle();

  try {
    api = new CoursePlatformApi(config);
  } catch (error) {
    renderConfigurationError(error);
    return;
  }

  logoutButton.addEventListener('click', logout);
  window.addEventListener('hashchange', route);
  window.addEventListener('message', (event) => {
    if (event.data?.source === 'tilda-parent' && event.data?.type === 'request-resize') {
      reportHeight();
    }
  });
  new ResizeObserver(reportHeight).observe(document.body);

  if (!api.hasStudentSession()) {
    renderLogin();
    return;
  }

  route();
}

async function route() {
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

    await renderDashboard();
  } catch (error) {
    handleError(error);
  }
}

function renderLogin() {
  clearTimers();
  headerUser.innerHTML = '';
  headerUser.title = '';
  logoutButton.hidden = true;

  root.innerHTML = `
    <section class="auth-shell">
      <div class="auth-card auth-card-modern">
        <div class="auth-card-accent">
          <img src="${icons8Base}/c9a55b/graduation-cap.png" alt="">
          <span>Portal académico</span>
        </div>

        <div class="auth-brand-row">
          <div class="brand-mark">LSS</div>
          <div>
            <p class="eyebrow">LMTWEBNAIRS Summer School</p>
            <h1>${escapeHtml(platformName)}</h1>
          </div>
        </div>

        <p class="auth-description">
          Entre na área do participante para acompanhar aulas, exercícios e avaliações num ambiente simples e bem organizado.
        </p>

        <div class="auth-feature-list" aria-label="Recursos da plataforma">
          <span><img src="${icons8Base}/00365b/open-book.png" alt=""> Aulas</span>
          <span><img src="${icons8Base}/00365b/task-completed.png" alt=""> Atividades</span>
          <span><img src="${icons8Base}/00365b/certificate.png" alt=""> Certificado</span>
        </div>

        <form id="loginForm" class="form-stack">
          <label>
            <span>Email</span>
            <input type="email" name="email" autocomplete="email" required
              placeholder="estudante@email.com">
          </label>
          <label>
            <span>Código de acesso</span>
            <input type="password" name="accessCode" autocomplete="current-password"
              required placeholder="Código fornecido pelo administrador">
          </label>
          <button class="button button-primary button-block" type="submit">
            Entrar na plataforma
          </button>
        </form>

        <div id="loginError" class="form-message form-message-error" hidden></div>
      </div>
    </section>
  `;

  document.querySelector('#loginForm').addEventListener('submit', login);
  reportHeight();
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
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    setBusy(button, false);
    reportHeight();
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

  const dashboard = await api.dashboard();
  state.dashboard = dashboard;

  const greeting = studentGreeting(dashboard.student.fullName);
  headerUser.innerHTML = `<span class="header-greeting">${escapeHtml(greeting)}</span>`;
  headerUser.title = greeting;
  logoutButton.hidden = false;

  const totalLessons = dashboard.lessons.length;
  const approvedLessons = dashboard.lessons.filter((item) => item.progress.status === 'APPROVED').length;
  const activeLessons = dashboard.lessons.filter((item) => ['AVAILABLE', 'IN_PROGRESS', 'UNDER_REVIEW'].includes(item.progress.status)).length;

  const certificateButton = dashboard.enrollment.status === 'COMPLETED'
    ? '<a class="button button-secondary" href="#/certificate">Ver certificado</a>'
    : '';

  root.innerHTML = `
    <section class="dashboard-hero">
      <div class="hero-copy">
        <p class="eyebrow">${escapeHtml(platformYear)}</p>
        <h1>${escapeHtml(platformName)}</h1>
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

    <section class="dashboard-insights" aria-label="Resumo do percurso">
      <article class="insight-card">
        <img src="${icons8Base}/c9a55b/checked-checkbox.png" alt="">
        <div>
          <span>Aulas aprovadas</span>
          <strong>${approvedLessons}/${totalLessons}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${icons8Base}/c9a55b/classroom.png" alt="">
        <div>
          <span>Aulas disponíveis</span>
          <strong>${activeLessons}</strong>
        </div>
      </article>
      <article class="insight-card">
        <img src="${icons8Base}/c9a55b/time.png" alt="">
        <div>
          <span>Carga horária</span>
          <strong>${dashboard.course.totalHours}h</strong>
        </div>
      </article>
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

  renderMath();
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
    <a href="#section-${escapeHtml(section.contentId)}">
      ${escapeHtml(section.title)}
    </a>
  `).join('');
}

async function renderCertificate() {
  clearTimers();
  root.innerHTML = loadingTemplate('A carregar o certificado…');

  const result = await api.certificate();

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
    themeToggle.title = theme === 'dark' ? 'Usar modo claro' : 'Usar modo noturno';
    themeToggle.setAttribute('aria-label', themeToggle.title);
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

function renderConfigurationError(error) {
  root.innerHTML = `
    <div class="configuration-error">
      <h1>Configuração incompleta</h1>
      <p>${escapeHtml(error.message)}</p>
      <code>web/assets/js/config.js</code>
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
