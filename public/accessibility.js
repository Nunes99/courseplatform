const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

const managedDialogs = new WeakMap();
const managedScrollRegions = new WeakSet();
let dialogLabelSequence = 0;
let validationMessageSequence = 0;
let accessibilityInstalled = false;
let lastExternalFocus = null;

const SCROLL_REGION_SELECTOR = [
  '.admin-table-wrap',
  '.credential-table-wrap',
  '.certificate-record-table',
  '.student-admin-list',
  '.rich-content'
].join(',');

function visibleFocusableElements(container) {
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter((element) => {
    if (element.hidden || element.getAttribute('aria-hidden') === 'true') return false;
    return element.getClientRects().length > 0;
  });
}

function activeDialogOverlay() {
  const overlays = Array.from(document.querySelectorAll('.dialog-overlay'))
    .filter((overlay) => overlay.isConnected && getComputedStyle(overlay).display !== 'none');
  return overlays.at(-1) || null;
}

function closeControl(overlay) {
  return overlay.querySelector('.dialog-close, [data-close-dialog], [data-cancel-recovery]');
}

function inferredDialogLabel(dialog) {
  const labels = [
    ['certificate-preview-dialog', 'Pré-visualização do certificado'],
    ['student-detail-dialog', 'Detalhes do estudante'],
    ['certificate-payment-dialog', 'Pagamento do certificado'],
    ['certificate-survey-dialog', 'Inquérito do curso'],
    ['survey-editor-dialog', 'Editor de inquérito'],
    ['credential-dialog', 'Gestão de credenciais'],
    ['question-bank-dialog', 'Banco de questões'],
    ['question-bank-picker', 'Selecionar questão'],
    ['course-version-editor-dialog', 'Editor da versão do curso'],
    ['course-version-preview-dialog', 'Pré-visualização da versão do curso'],
    ['course-lesson-dialog', 'Gestão académica'],
    ['email-change-dialog', 'Alterar email'],
    ['recovery-dialog', 'Recuperar acesso']
  ];
  return labels.find(([className]) => dialog.classList.contains(className))?.[1]
    || 'Janela de diálogo';
}

function prepareDialog(overlay) {
  if (!(overlay instanceof HTMLElement) || managedDialogs.has(overlay)) return;
  if (overlay.matches('.install-app-dialog-overlay, .push-activation-dialog-overlay')) return;

  const dialog = overlay.querySelector('[role="dialog"], .dialog-card');
  if (!dialog) return;

  const activeElement = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null;
  const previouslyFocused = activeElement && !overlay.contains(activeElement)
    ? activeElement
    : lastExternalFocus;
  managedDialogs.set(overlay, { previouslyFocused });

  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  const closer = closeControl(overlay);
  if (closer?.classList.contains('dialog-close') && !closer.hasAttribute('aria-label')) {
    closer.setAttribute('aria-label', 'Fechar');
  }

  if (!dialog.hasAttribute('aria-label') && !dialog.hasAttribute('aria-labelledby')) {
    const heading = dialog.querySelector('h1, h2, h3');
    if (heading) {
      if (!heading.id) {
        dialogLabelSequence += 1;
        heading.id = `dialog-title-${dialogLabelSequence}`;
      }
      dialog.setAttribute('aria-labelledby', heading.id);
    } else {
      dialog.setAttribute('aria-label', inferredDialogLabel(dialog));
    }
  }

  window.requestAnimationFrame(() => {
    if (!overlay.isConnected || overlay.contains(document.activeElement)) return;
    const target = dialog.querySelector('[autofocus]')
      || visibleFocusableElements(dialog)[0]
      || dialog;
    if (target === dialog && !dialog.hasAttribute('tabindex')) dialog.tabIndex = -1;
    target.focus({ preventScroll: true });
  });
}

function restoreDialogFocus(overlay) {
  const state = managedDialogs.get(overlay);
  if (!state) return;
  managedDialogs.delete(overlay);
  const target = state.previouslyFocused;
  if (target?.isConnected) {
    window.requestAnimationFrame(() => target.focus({ preventScroll: true }));
  }
}

function prepareScrollableRegion(region) {
  if (!(region instanceof HTMLElement) || managedScrollRegions.has(region)) return;
  const table = region.matches('table') ? region : region.querySelector('table');
  if (!table && !region.matches('.certificate-record-table')) return;
  managedScrollRegions.add(region);

  table?.querySelectorAll('thead th:not([scope])').forEach((heading) => {
    heading.setAttribute('scope', 'col');
  });

  const pageTitle = region.closest('main, section')?.querySelector('h1, h2')?.textContent?.trim()
    || document.querySelector('main h1')?.textContent?.trim()
    || 'dados';
  if (!region.hasAttribute('aria-label') && !region.hasAttribute('aria-labelledby')) {
    region.setAttribute('aria-label', `Tabela de ${pageTitle}`);
  }
  region.setAttribute('role', 'region');
  region.tabIndex = 0;
  region.dataset.scrollRegion = 'true';
}

function prepareScrollRegions(container = document) {
  if (container instanceof HTMLElement && container.matches(SCROLL_REGION_SELECTOR)) {
    prepareScrollableRegion(container);
  }
  container.querySelectorAll?.(SCROLL_REGION_SELECTOR).forEach(prepareScrollableRegion);
}

function showFieldValidation(control) {
  if (!(control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement)) return;
  if (control.matches('[type="checkbox"], [type="radio"], [type="hidden"]')) return;

  control.setAttribute('aria-invalid', 'true');
  let message = control.parentElement?.querySelector('.field-validation-message');
  if (!message) {
    message = document.createElement('span');
    validationMessageSequence += 1;
    message.id = `field-validation-${validationMessageSequence}`;
    message.className = 'field-validation-message';
    message.dataset.for = control.name || control.id || String(validationMessageSequence);
    message.setAttribute('role', 'alert');
    control.insertAdjacentElement('afterend', message);
  }
  message.textContent = control.validationMessage || 'Verifique este campo.';
  control.setAttribute('aria-describedby', [
    control.getAttribute('aria-describedby'),
    message.id
  ].filter(Boolean).join(' '));
}

function clearFieldValidation(control) {
  if (!(control instanceof HTMLElement) || control.getAttribute('aria-invalid') !== 'true') return;
  if (!control.matches(':valid')) return;
  control.removeAttribute('aria-invalid');
  const message = control.parentElement?.querySelector('.field-validation-message');
  if (!message) return;
  const describedBy = String(control.getAttribute('aria-describedby') || '')
    .split(/\s+/)
    .filter((id) => id && id !== message.id);
  if (describedBy.length) control.setAttribute('aria-describedby', describedBy.join(' '));
  else control.removeAttribute('aria-describedby');
  message.remove();
}

function inspectAddedNode(node) {
  if (!(node instanceof HTMLElement)) return;
  if (node.matches('.dialog-overlay')) prepareDialog(node);
  node.querySelectorAll?.('.dialog-overlay').forEach(prepareDialog);
  prepareScrollRegions(node);
}

function inspectRemovedNode(node) {
  if (!(node instanceof HTMLElement)) return;
  if (node.matches('.dialog-overlay')) restoreDialogFocus(node);
  node.querySelectorAll?.('.dialog-overlay').forEach(restoreDialogFocus);
}

function handleDialogKeyboard(event) {
  const overlay = activeDialogOverlay();
  if (!overlay || !managedDialogs.has(overlay)) return;
  const dialog = overlay.querySelector('[role="dialog"], .dialog-card');
  if (!dialog) return;

  if (event.key === 'Escape') {
    const closer = closeControl(overlay);
    if (!closer) return;
    event.preventDefault();
    event.stopPropagation();
    closer.click();
    return;
  }

  if (event.key !== 'Tab') return;
  const focusable = visibleFocusableElements(dialog);
  if (!focusable.length) {
    event.preventDefault();
    dialog.focus();
    return;
  }

  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function installAccessibility() {
  if (accessibilityInstalled) return;
  accessibilityInstalled = true;

  document.querySelectorAll('.dialog-overlay').forEach(prepareDialog);
  prepareScrollRegions();
  document.addEventListener('focusin', (event) => {
    if (event.target instanceof HTMLElement && !event.target.closest('.dialog-overlay')) {
      lastExternalFocus = event.target;
    }
  });
  new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach(inspectAddedNode);
      mutation.removedNodes.forEach(inspectRemovedNode);
    });
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('keydown', handleDialogKeyboard, true);
  document.addEventListener('invalid', (event) => showFieldValidation(event.target), true);
  document.addEventListener('input', (event) => clearFieldValidation(event.target), true);
  document.addEventListener('change', (event) => clearFieldValidation(event.target), true);
}

export function focusPageHeading(container, options = {}) {
  const heading = container?.querySelector('h1, .student-page-heading h2');
  if (!heading) return;
  heading.tabIndex = -1;
  window.requestAnimationFrame(() => {
    if (heading.isConnected) heading.focus({ preventScroll: options.preventScroll !== false });
  });
}
