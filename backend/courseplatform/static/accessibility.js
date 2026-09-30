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
let dialogLabelSequence = 0;
let accessibilityInstalled = false;
let lastExternalFocus = null;

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

  if (!dialog.hasAttribute('aria-label') && !dialog.hasAttribute('aria-labelledby')) {
    const heading = dialog.querySelector('h1, h2, h3');
    if (heading) {
      if (!heading.id) {
        dialogLabelSequence += 1;
        heading.id = `dialog-title-${dialogLabelSequence}`;
      }
      dialog.setAttribute('aria-labelledby', heading.id);
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

function inspectAddedNode(node) {
  if (!(node instanceof HTMLElement)) return;
  if (node.matches('.dialog-overlay')) prepareDialog(node);
  node.querySelectorAll?.('.dialog-overlay').forEach(prepareDialog);
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
}

export function focusPageHeading(container, options = {}) {
  const heading = container?.querySelector('h1, .student-page-heading h2');
  if (!heading) return;
  heading.tabIndex = -1;
  window.requestAnimationFrame(() => {
    if (heading.isConnected) heading.focus({ preventScroll: options.preventScroll !== false });
  });
}
