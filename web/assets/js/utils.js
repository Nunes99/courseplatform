export const STATUS_LABELS = Object.freeze({
  LOCKED: 'Bloqueada',
  AVAILABLE: 'Disponível',
  IN_PROGRESS: 'Em curso',
  UNDER_REVIEW: 'Em avaliação',
  CORRECTION_REQUIRED: 'Correção solicitada',
  APPROVED: 'Aprovada',
  FAILED: 'Não aprovada',
  TIME_EXCEEDED: 'Tempo excedido',
  COMPLETED: 'Concluído',
  ACTIVE: 'Ativo',
  INACTIVE: 'Inativo',
  BLOCKED: 'Bloqueado'
});

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || 'Sem estado';
}

export function statusClass(status) {
  return `status-${String(status || 'unknown').toLowerCase().replaceAll('_', '-')}`;
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
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
