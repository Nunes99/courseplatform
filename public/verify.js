import { CoursePlatformApi } from './api.js';
import { escapeHtml, formatDate, reportHeight, setBusy } from './utils.js';

const config = window.COURSE_PLATFORM_CONFIG;
const api = new CoursePlatformApi(config);
const root = document.querySelector('#verificationResult');
const form = document.querySelector('#verificationForm');

form.addEventListener('submit', verify);

const codeFromUrl = new URLSearchParams(location.search).get('code');
if (codeFromUrl) {
  form.elements.code.value = codeFromUrl;
  form.requestSubmit();
}

async function verify(event) {
  event.preventDefault();

  const button = form.querySelector('button');
  const code = form.elements.code.value.trim();
  if (!code) return;

  setBusy(button, true, 'A verificar…');

  try {
    const result = await api.verifyCertificate(code);

    if (!result.valid) {
      root.innerHTML = `
        <div class="verification-card verification-invalid">
          <span>Não confirmado</span>
          <h2>Certificado não encontrado</h2>
          <p>Confirme o número ou o código de verificação e tente novamente.</p>
        </div>
      `;
      return;
    }

    const certificate = result.certificate;

    root.innerHTML = `
      <div class="verification-card verification-valid">
        <span>Certificado válido</span>
        <h2>${escapeHtml(certificate.studentName)}</h2>
        <p>${escapeHtml(certificate.courseTitle)}</p>
        <dl>
          <div>
            <dt>Número</dt>
            <dd>${escapeHtml(certificate.certificateNumber)}</dd>
          </div>
          <div>
            <dt>Data</dt>
            <dd>${formatDate(certificate.issueDate)}</dd>
          </div>
          <div>
            <dt>Classificação</dt>
            <dd>${certificate.finalScore}%</dd>
          </div>
        </dl>
      </div>
    `;
  } catch (error) {
    root.innerHTML = `
      <div class="verification-card verification-invalid">
        <span>Erro</span>
        <h2>Não foi possível verificar</h2>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  } finally {
    setBusy(button, false);
    reportHeight();
  }
}
