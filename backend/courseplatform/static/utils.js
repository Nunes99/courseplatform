export const STATUS_LABELS = Object.freeze({
  NOT_STARTED: 'Não iniciada',
  LOCKED: 'Bloqueada',
  AVAILABLE: 'Disponível',
  IN_PROGRESS: 'Em curso',
  UNDER_REVIEW: 'Em avaliação',
  CORRECTION_REQUIRED: 'Correção solicitada',
  APPROVED: 'Aprovada',
  APPROVED_WITH_NOTES: 'Aprovada com observações',
  FAILED: 'Não aprovada',
  TIME_EXCEEDED: 'Tempo excedido',
  COMPLETED: 'Concluído',
  REQUESTED: 'Solicitado',
  PAYMENT_SUBMITTED: 'Comprovativo submetido',
  REJECTED: 'Rejeitado',
  ISSUED: 'Emitido',
  SIMPLE: 'Simples',
  PROFESSIONAL: 'Profissional',
  ACTIVE: 'Ativo',
  INACTIVE: 'Inativo',
  BLOCKED: 'Bloqueado',
  DELETED: 'Eliminado'
});

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || 'Sem estado';
}

export function statusClass(status) {
  return `status-${String(status || 'unknown').toLowerCase().replaceAll('_', '-')}`;
}

export function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return new Intl.DateTimeFormat('pt-PT', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

export function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = Math.floor(seconds % 60);

  return [hours, minutes, remaining]
    .map((value) => String(value).padStart(2, '0'))
    .join(':');
}

export function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  );
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function safeHtml(value) {
  if (window.DOMPurify) {
    return window.DOMPurify.sanitize(String(value || ''), {
      USE_PROFILES: { html: true },
      ADD_ATTR: ['target']
    });
  }
  return escapeHtml(value);
}

const DEFAULT_FAVICON_URL = './assets/app-icon.svg';
const DEFAULT_TOUCH_ICON_URL = './assets/app-icon-180.png';
const BRAND_FAVICON_BACKGROUND = '#00365B';
const BRAND_FAVICON_SIZE = 256;

export function applyBrandFavicon(rawLogoUrl = '') {
  if (!document?.head) return;

  let favicon = document.head.querySelector('link[rel="icon"]');
  if (!favicon) {
    favicon = document.createElement('link');
    favicon.rel = 'icon';
    document.head.appendChild(favicon);
  }

  const touchIcon = document.head.querySelector('link[rel="apple-touch-icon"]');
  const logoUrl = normalizeFaviconUrl(rawLogoUrl);

  const applyFallback = () => {
    favicon.href = DEFAULT_FAVICON_URL;
    favicon.type = 'image/svg+xml';
    favicon.dataset.brandFavicon = '';
    if (touchIcon) touchIcon.href = DEFAULT_TOUCH_ICON_URL;
  };

  if (!logoUrl) {
    applyFallback();
    return;
  }

  favicon.dataset.brandFavicon = logoUrl;
  const probe = new Image();
  probe.decoding = 'async';
  if (/^https?:/i.test(logoUrl)) probe.crossOrigin = 'anonymous';
  probe.addEventListener('load', () => {
    if (favicon.dataset.brandFavicon !== logoUrl) return;
    try {
      const generatedFavicon = renderBrandFavicon(probe);
      applyGeneratedFavicon(favicon, touchIcon, logoUrl, generatedFavicon);
    } catch {
      applyFallback();
    }
  }, { once: true });
  probe.addEventListener('error', () => {
    if (favicon.dataset.brandFavicon !== logoUrl) return;
    applyFallback();
  }, { once: true });
  probe.src = logoUrl;
}

function applyGeneratedFavicon(favicon, touchIcon, logoUrl, generatedFavicon) {
  if (favicon.dataset.brandFavicon !== logoUrl) return;
  favicon.type = 'image/png';
  favicon.href = generatedFavicon;
  if (touchIcon) touchIcon.href = generatedFavicon;
}

function renderBrandFavicon(image) {
  const canvas = document.createElement('canvas');
  canvas.width = BRAND_FAVICON_SIZE;
  canvas.height = BRAND_FAVICON_SIZE;

  const context = canvas.getContext('2d');
  if (!context || !image.naturalWidth || !image.naturalHeight) {
    throw new Error('Não foi possível preparar o favicon.');
  }

  const cornerRadius = 44;
  context.beginPath();
  context.moveTo(cornerRadius, 0);
  context.lineTo(BRAND_FAVICON_SIZE - cornerRadius, 0);
  context.quadraticCurveTo(BRAND_FAVICON_SIZE, 0, BRAND_FAVICON_SIZE, cornerRadius);
  context.lineTo(BRAND_FAVICON_SIZE, BRAND_FAVICON_SIZE - cornerRadius);
  context.quadraticCurveTo(
    BRAND_FAVICON_SIZE,
    BRAND_FAVICON_SIZE,
    BRAND_FAVICON_SIZE - cornerRadius,
    BRAND_FAVICON_SIZE
  );
  context.lineTo(cornerRadius, BRAND_FAVICON_SIZE);
  context.quadraticCurveTo(0, BRAND_FAVICON_SIZE, 0, BRAND_FAVICON_SIZE - cornerRadius);
  context.lineTo(0, cornerRadius);
  context.quadraticCurveTo(0, 0, cornerRadius, 0);
  context.closePath();
  context.fillStyle = BRAND_FAVICON_BACKGROUND;
  context.fill();

  const availableSize = BRAND_FAVICON_SIZE - 64;
  const scale = Math.min(availableSize / image.naturalWidth, availableSize / image.naturalHeight);
  const width = Math.max(1, image.naturalWidth * scale);
  const height = Math.max(1, image.naturalHeight * scale);
  const x = (BRAND_FAVICON_SIZE - width) / 2;
  const y = (BRAND_FAVICON_SIZE - height) / 2;

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  context.shadowColor = 'rgba(255, 248, 228, 0.35)';
  context.shadowBlur = 8;
  context.drawImage(image, x, y, width, height);
  context.shadowColor = 'transparent';
  context.shadowBlur = 0;
  context.drawImage(image, x, y, width, height);

  return canvas.toDataURL('image/png');
}

function normalizeFaviconUrl(rawLogoUrl) {
  const value = String(rawLogoUrl || '').trim();
  if (!value) return '';

  try {
    const url = new URL(value, document.baseURI);
    const protocol = url.protocol.toLowerCase();
    if (!['http:', 'https:', 'blob:', 'data:'].includes(protocol)) return '';
    if (protocol === 'data:' && !value.toLowerCase().startsWith('data:image/')) return '';

    const host = url.hostname.replace(/^www\./, '');
    if (host === 'drive.google.com') {
      const queryId = url.searchParams.get('id');
      const pathId = url.pathname.match(/\/file\/d\/([^/]+)/)?.[1];
      const id = queryId || pathId;
      return id ? `https://drive.google.com/thumbnail?id=${encodeURIComponent(id)}&sz=w256` : '';
    }

    return url.href;
  } catch {
    return '';
  }
}

export function debounce(callback, wait = 600) {
  let timer;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => callback(...args), wait);
  };
}

export function showToast(message, type = 'info') {
  const container = document.querySelector('#toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(() => toast.classList.add('is-visible'), 20);
  window.setTimeout(() => {
    toast.classList.remove('is-visible');
    window.setTimeout(() => toast.remove(), 250);
  }, 4500);
}

export function setBusy(button, busy, busyText = 'A processar…') {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = busyText;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText || button.textContent;
  }
}

export function reportHeight() {
  const height = Math.max(
    document.documentElement.scrollHeight,
    document.body.scrollHeight
  );

  window.parent.postMessage({
    source: 'course-platform',
    type: 'resize',
    height
  }, '*');
}

export function renderMath() {
  if (window.MathJax?.typesetPromise) {
    window.MathJax.typesetClear?.();
    window.MathJax.typesetPromise().finally(reportHeight);
  } else {
    reportHeight();
  }
}

export function parseSelectedOptions(value) {
  if (Array.isArray(value)) return value.map(String);
  if (!value) return [];

  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [String(value)];
  } catch {
    return [String(value)];
  }
}
