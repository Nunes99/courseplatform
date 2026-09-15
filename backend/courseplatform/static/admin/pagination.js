import { escapeHtml } from '../utils.js';


export function resetCursorPagination(pagination) {
  pagination.cursor = '';
  pagination.nextCursor = '';
  pagination.hasMore = false;
  pagination.returned = 0;
  if ('total' in pagination) pagination.total = 0;
  pagination.history = [];
}


export function cursorPaginationTemplate(name, pagination) {
  const page = (pagination.history?.length || 0) + 1;
  const returned = Number(pagination.returned || 0);
  return `
    <nav class="cursor-pagination" aria-label="Navegação da lista">
      <span>Página ${page} · ${returned} ${returned === 1 ? 'registo' : 'registos'}</span>
      <div>
        <button class="button button-secondary button-compact" type="button"
          data-cursor-pagination="${escapeHtml(name)}" data-direction="previous"
          ${pagination.history?.length ? '' : 'disabled'}>Anterior</button>
        <button class="button button-secondary button-compact" type="button"
          data-cursor-pagination="${escapeHtml(name)}" data-direction="next"
          ${pagination.hasMore && pagination.nextCursor ? '' : 'disabled'}>Seguinte</button>
      </div>
    </nav>
  `;
}


export async function moveCursorPage(pagination, direction, loader) {
  const previousState = {
    cursor: pagination.cursor,
    nextCursor: pagination.nextCursor,
    hasMore: pagination.hasMore,
    returned: pagination.returned,
    history: [...(pagination.history || [])]
  };
  if (direction === 'next') {
    if (!pagination.hasMore || !pagination.nextCursor) return;
    pagination.history.push(pagination.cursor || '');
    pagination.cursor = pagination.nextCursor;
  } else if (direction === 'previous') {
    if (!pagination.history.length) return;
    pagination.cursor = pagination.history.pop() || '';
  } else {
    return;
  }
  pagination.nextCursor = '';
  pagination.hasMore = false;
  const loaded = await loader();
  if (loaded === false) Object.assign(pagination, previousState);
}
