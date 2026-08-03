import { escapeHtml, showToast } from './utils.js';

const ICONS = 'https://api.iconify.design/lucide';
const CHAT_EMOJIS = [
  '😀', '😃', '😂', '😊', '😍', '🤝', '👏', '👍',
  '🙏', '🎉', '✅', '📚', '💡', '✍️', '🚀', '🔥',
  '💬', '❤️', '🙌', '🤔', '👀', '⭐', '📌', '🎓'
];

function icon(name, color = '00365b') {
  return `${ICONS}/${encodeURIComponent(name)}.svg?color=%23${color}`;
}

function initials(name = '') {
  return String(name || 'U')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || '')
    .join('')
    .toUpperCase() || 'U';
}

function safeImageUrl(value) {
  const url = String(value || '').trim();
  return /^(https?:|data:image\/(?:png|jpe?g|webp);base64,)/i.test(url) ? url : '';
}

function compactText(value, limit = 74) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function chatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return new Intl.DateTimeFormat('pt-PT', { hour: '2-digit', minute: '2-digit' }).format(date);
  }
  return new Intl.DateTimeFormat('pt-PT', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function chatDay(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Hoje';
  if (date.toDateString() === yesterday.toDateString()) return 'Ontem';
  return new Intl.DateTimeFormat('pt-PT', { dateStyle: 'long' }).format(date);
}

function roomTypeLabel(type) {
  return {
    COMMUNITY: 'Comunidade',
    COURSE: 'Curso',
    GROUP: 'Grupo',
    SUPPORT: 'Apoio privado',
    DIRECT: 'Conversa privada'
  }[type] || 'Conversa';
}

function roomIcon(type) {
  return {
    COMMUNITY: 'messages-square',
    COURSE: 'book-open',
    GROUP: 'users-round',
    SUPPORT: 'headset',
    DIRECT: 'user-round'
  }[type] || 'message-square';
}

export class ChatWorkspace {
  constructor({ api, mount, mode = 'student', initialRoomId = '', onUnreadChange = null }) {
    this.api = api;
    this.mount = mount;
    this.mode = mode;
    this.initialRoomId = initialRoomId;
    this.onUnreadChange = onUnreadChange;
    this.rooms = [];
    this.contacts = [];
    this.messages = [];
    this.activeRoom = null;
    this.filter = 'ALL';
    this.panelMode = 'rooms';
    this.search = '';
    this.replyingTo = null;
    this.editingMessage = null;
    this.pollTimer = null;
    this.pollCount = 0;
    this.polling = false;
    this.destroyed = false;
  }

  async start() {
    this.renderFrame();
    this.bindEvents();
    await Promise.all([
      this.loadRooms(),
      this.mode === 'student' ? this.loadContacts({ quiet: true }) : Promise.resolve()
    ]);
    if (this.destroyed || !this.rooms.length) return;
    const preferred = this.rooms.find((room) => room.roomId === this.initialRoomId);
    if (preferred || window.matchMedia('(min-width: 761px)').matches) {
      await this.selectRoom((preferred || this.rooms[0]).roomId, { updateAddress: false });
    }
    this.pollTimer = window.setInterval(() => this.poll(), 4000);
  }

  destroy() {
    this.destroyed = true;
    window.clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  request(name, ...args) {
    const methods = this.mode === 'admin'
      ? {
          rooms: 'adminChatRooms',
          messages: 'adminChatMessages',
          send: 'adminSendChatMessage',
          edit: 'adminEditChatMessage',
          delete: 'adminDeleteChatMessage',
          read: 'adminMarkChatRoomRead'
        }
      : {
          rooms: 'chatRooms',
          messages: 'chatMessages',
          send: 'sendChatMessage',
          edit: 'editChatMessage',
          delete: 'deleteChatMessage',
          read: 'markChatRoomRead',
          report: 'reportChatMessage',
          contacts: 'chatContacts',
          startDirect: 'startDirectChat'
        };
    const method = this.api[methods[name]];
    if (typeof method !== 'function') throw new Error('O módulo de mensagens não está disponível nesta versão.');
    return method.apply(this.api, args);
  }

  renderFrame() {
    this.mount.innerHTML = `
      <section class="chat-workspace ${this.mode === 'admin' ? 'chat-workspace-admin' : ''}" aria-label="Mensagens internas">
        <aside class="chat-room-panel">
          <div class="chat-room-heading">
            <div>
              <p class="eyebrow">Comunicação</p>
              <h2>Mensagens</h2>
            </div>
            <span class="chat-live-indicator"><i></i> Atualização automática</span>
          </div>
          ${this.mode === 'student' ? `
            <div class="chat-panel-tabs" role="tablist" aria-label="Conteúdo da coluna lateral">
              <button type="button" class="is-active" role="tab" aria-selected="true" data-chat-panel="rooms">
                <img src="${icon('messages-square')}" alt=""><span>Conversas</span>
              </button>
              <button type="button" role="tab" aria-selected="false" data-chat-panel="contacts">
                <img src="${icon('users-round')}" alt=""><span>Colegas</span>
              </button>
            </div>
          ` : ''}
          <label class="chat-search">
            <img src="${icon('search')}" alt="">
            <input type="search" placeholder="Pesquisar conversas" aria-label="Pesquisar conversas">
          </label>
          <div class="chat-room-filters" role="tablist" aria-label="Filtrar conversas">
            ${[
              ['ALL', 'Todas'],
              ['SUPPORT', 'Apoio'],
              ['DIRECT', 'Privadas'],
              ['COURSE', 'Cursos'],
              ['GROUP', 'Grupos']
            ].map(([value, label]) => `
              <button type="button" class="${value === 'ALL' ? 'is-active' : ''}" data-chat-filter="${value}">${label}</button>
            `).join('')}
          </div>
          <div class="chat-room-list" role="listbox" aria-label="Conversas">
            <div class="chat-list-loading"><span class="loading-spinner"></span><span>A carregar conversas…</span></div>
          </div>
        </aside>

        <section class="chat-conversation-panel">
          <div class="chat-empty-state">
            <span class="chat-empty-icon"><img src="${icon('message-square', 'c9a55b')}" alt=""></span>
            <h3>Escolha uma conversa</h3>
            <p>Partilhe dúvidas, acompanhe o seu grupo e comunique com a equipa de formação.</p>
          </div>
        </section>

        <dialog class="chat-report-dialog">
          <form method="dialog" class="chat-report-card">
            <div class="chat-report-heading">
              <span><img src="${icon('flag')}" alt=""></span>
              <div><h3>Denunciar mensagem</h3><p>A equipa administrativa analisará o conteúdo.</p></div>
            </div>
            <label><span>Motivo da denúncia</span><textarea name="reason" rows="4" minlength="5" maxlength="500" required placeholder="Explique brevemente o problema"></textarea></label>
            <input type="hidden" name="messageId">
            <div class="chat-report-actions">
              <button class="button button-secondary button-small" value="cancel" formnovalidate>Cancelar</button>
              <button class="button button-primary button-small" value="submit">Enviar denúncia</button>
            </div>
          </form>
        </dialog>
      </section>
    `;
  }

  bindEvents() {
    this.mount.querySelector('.chat-search input')?.addEventListener('input', (event) => {
      this.search = event.currentTarget.value.trim().toLowerCase();
      this.renderSidebarContent();
    });
    this.mount.querySelector('.chat-panel-tabs')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-chat-panel]');
      if (!button) return;
      this.panelMode = button.dataset.chatPanel;
      this.search = '';
      const searchInput = this.mount.querySelector('.chat-search input');
      if (searchInput) {
        searchInput.value = '';
        searchInput.placeholder = this.panelMode === 'contacts' ? 'Pesquisar colegas' : 'Pesquisar conversas';
        searchInput.setAttribute('aria-label', searchInput.placeholder);
      }
      this.mount.querySelectorAll('[data-chat-panel]').forEach((item) => {
        const active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-selected', String(active));
      });
      this.mount.querySelector('.chat-room-filters')?.toggleAttribute('hidden', this.panelMode === 'contacts');
      this.renderSidebarContent();
    });
    this.mount.querySelector('.chat-room-filters')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-chat-filter]');
      if (!button) return;
      this.filter = button.dataset.chatFilter;
      this.mount.querySelectorAll('[data-chat-filter]').forEach((item) => item.classList.toggle('is-active', item === button));
      this.renderSidebarContent();
    });
    this.mount.querySelector('.chat-room-list')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-chat-room]');
      if (button) this.selectRoom(button.dataset.chatRoom);
      const contact = event.target.closest('[data-chat-contact]');
      if (contact) this.startDirectConversation(contact.dataset.chatContact);
    });
    this.mount.addEventListener('error', (event) => {
      const image = event.target.closest?.('img[data-chat-avatar-fallback]');
      if (!image) return;
      const fallback = document.createElement('span');
      fallback.textContent = image.dataset.chatAvatarFallback || 'U';
      image.replaceWith(fallback);
    }, true);
    const dialog = this.mount.querySelector('.chat-report-dialog');
    dialog?.addEventListener('close', async () => {
      if (dialog.returnValue !== 'submit') return;
      const form = dialog.querySelector('form');
      const values = Object.fromEntries(new FormData(form));
      try {
        await this.request('report', values.messageId, values.reason);
        showToast('Denúncia enviada para análise.', 'success');
        form.reset();
      } catch (error) {
        showToast(error.message || 'Não foi possível enviar a denúncia.', 'error');
      }
    });
  }

  async loadRooms({ quiet = false } = {}) {
    try {
      const result = await this.request('rooms');
      if (this.destroyed) return;
      this.rooms = Array.isArray(result.rooms) ? result.rooms : [];
      if (this.activeRoom) {
        this.activeRoom = this.rooms.find((room) => room.roomId === this.activeRoom.roomId) || this.activeRoom;
      }
      this.renderSidebarContent();
      this.onUnreadChange?.(Number(result.unreadCount || 0));
      if (!this.rooms.length && this.panelMode === 'rooms') this.renderNoRooms();
    } catch (error) {
      if (!quiet) this.renderRoomError(error);
    }
  }

  async loadContacts({ quiet = false } = {}) {
    if (this.mode !== 'student') return;
    try {
      const result = await this.request('contacts');
      if (this.destroyed) return;
      this.contacts = Array.isArray(result.contacts) ? result.contacts : [];
      if (this.panelMode === 'contacts') this.renderContacts();
    } catch (error) {
      if (!quiet && this.panelMode === 'contacts') this.renderContactError(error);
    }
  }

  renderSidebarContent() {
    if (this.panelMode === 'contacts' && this.mode === 'student') this.renderContacts();
    else this.renderRooms();
  }

  renderRooms() {
    const list = this.mount.querySelector('.chat-room-list');
    if (!list) return;
    const rooms = this.rooms.filter((room) => {
      const matchesType = this.filter === 'ALL' || room.roomType === this.filter;
      const haystack = `${room.name} ${room.description} ${room.lastMessage?.body || ''}`.toLowerCase();
      return matchesType && (!this.search || haystack.includes(this.search));
    });
    list.innerHTML = rooms.length ? rooms.map((room) => {
      const lastMessage = room.lastMessage;
      const preview = lastMessage
        ? `${lastMessage.isMine ? 'Você: ' : ''}${lastMessage.isDeleted ? 'Mensagem removida' : compactText(lastMessage.body)}`
        : room.description;
      const peerPhoto = room.roomType === 'DIRECT' ? safeImageUrl(room.peer?.profilePhotoUrl) : '';
      const roomAvatar = peerPhoto
        ? `<img src="${escapeHtml(peerPhoto)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(room.name))}">`
        : `<img src="${icon(roomIcon(room.roomType), room.roomId === this.activeRoom?.roomId ? 'ffffff' : '00365b')}" alt="">`;
      return `
        <button type="button" role="option" aria-selected="${String(room.roomId === this.activeRoom?.roomId)}"
          class="chat-room-item ${room.roomId === this.activeRoom?.roomId ? 'is-active' : ''}"
          data-chat-room="${escapeHtml(room.roomId)}">
          <span class="chat-room-avatar">${roomAvatar}</span>
          <span class="chat-room-copy">
            <span class="chat-room-title-row"><strong>${escapeHtml(room.name)}</strong><time>${escapeHtml(chatTime(lastMessage?.createdAt))}</time></span>
            <span class="chat-room-preview">${escapeHtml(preview || 'Sem mensagens')}</span>
            <span class="chat-room-meta">${escapeHtml(roomTypeLabel(room.roomType))} · ${Number(room.participantCount || 0)} participantes</span>
          </span>
          ${room.unreadCount ? `<span class="chat-unread-count" aria-label="${room.unreadCount} mensagens não lidas">${Math.min(room.unreadCount, 99)}</span>` : ''}
        </button>
      `;
    }).join('') : `
      <div class="chat-list-empty">
        <img src="${icon('search-x')}" alt="">
        <strong>Nenhuma conversa encontrada</strong>
        <span>Altere a pesquisa ou o filtro selecionado.</span>
      </div>
    `;
  }

  renderContacts() {
    const list = this.mount.querySelector('.chat-room-list');
    if (!list) return;
    const contacts = this.contacts.filter((contact) => {
      const courses = (contact.sharedCourses || []).map((course) => course.title).join(' ');
      return !this.search || `${contact.fullName} ${contact.publicStudentId} ${contact.organization} ${courses}`.toLowerCase().includes(this.search);
    });
    list.innerHTML = contacts.length ? contacts.map((contact) => {
      const photo = safeImageUrl(contact.profilePhotoUrl);
      const avatar = photo
        ? `<img src="${escapeHtml(photo)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(contact.fullName))}">`
        : `<span>${escapeHtml(initials(contact.fullName))}</span>`;
      const courses = (contact.sharedCourses || []).map((course) => course.title).join(', ');
      return `
        <button type="button" class="chat-contact-item" data-chat-contact="${escapeHtml(contact.publicStudentId)}">
          <span class="chat-contact-avatar">${avatar}</span>
          <span class="chat-contact-copy">
            <strong>${escapeHtml(contact.fullName)}</strong>
            <span>${escapeHtml(compactText(courses || 'Colega do seu curso', 64))}</span>
            <small>${escapeHtml(contact.publicStudentId || '')}</small>
          </span>
          <span class="chat-contact-action" aria-hidden="true"><img src="${icon(contact.roomId ? 'message-circle' : 'message-circle-plus')}" alt=""></span>
        </button>
      `;
    }).join('') : `
      <div class="chat-list-empty">
        <img src="${icon(this.search ? 'search-x' : 'users-round')}" alt="">
        <strong>${this.search ? 'Nenhum colega encontrado' : 'Sem colegas disponíveis'}</strong>
        <span>${this.search ? 'Altere os termos da pesquisa.' : 'Os estudantes dos seus cursos aparecerão aqui.'}</span>
      </div>
    `;
  }

  renderContactError(error) {
    const list = this.mount.querySelector('.chat-room-list');
    if (!list) return;
    list.innerHTML = `<div class="chat-list-empty is-error"><strong>Não foi possível carregar os colegas</strong><span>${escapeHtml(error.message || 'Tente novamente.')}</span><button class="button button-secondary button-small" type="button">Repetir</button></div>`;
    list.querySelector('button')?.addEventListener('click', () => this.loadContacts());
  }

  async startDirectConversation(publicStudentId) {
    const contact = this.contacts.find((item) => item.publicStudentId === publicStudentId);
    if (!contact) return;
    try {
      let roomId = contact.roomId;
      if (!roomId) {
        const result = await this.request('startDirect', publicStudentId);
        roomId = result.room?.roomId;
        contact.roomId = roomId || '';
        await this.loadRooms({ quiet: true });
      }
      if (!roomId) throw new Error('Não foi possível abrir a conversa privada.');
      this.panelMode = 'rooms';
      const roomsTab = this.mount.querySelector('[data-chat-panel="rooms"]');
      roomsTab?.click();
      await this.selectRoom(roomId);
    } catch (error) {
      showToast(error.message || 'Não foi possível iniciar a conversa.', 'error');
    }
  }

  renderNoRooms() {
    const list = this.mount.querySelector('.chat-room-list');
    if (list) list.innerHTML = '<div class="chat-list-empty"><strong>Sem conversas disponíveis</strong><span>Os canais surgirão quando estiver associado a um curso ou grupo.</span></div>';
  }

  renderRoomError(error) {
    const list = this.mount.querySelector('.chat-room-list');
    if (list) list.innerHTML = `<div class="chat-list-empty is-error"><strong>Não foi possível carregar</strong><span>${escapeHtml(error.message || 'Tente novamente.')}</span><button class="button button-secondary button-small" type="button">Repetir</button></div>`;
    list?.querySelector('button')?.addEventListener('click', () => this.loadRooms());
  }

  async selectRoom(roomId, { updateAddress = true } = {}) {
    const room = this.rooms.find((item) => item.roomId === roomId);
    if (!room || this.destroyed) return;
    this.activeRoom = room;
    this.messages = [];
    this.replyingTo = null;
    this.editingMessage = null;
    this.mount.querySelector('.chat-workspace')?.classList.add('has-active-room');
    this.renderRooms();
    this.renderConversationLoading();
    if (updateAddress && this.mode === 'student') {
      history.replaceState(null, '', `#/chat/${encodeURIComponent(roomId)}`);
    }
    try {
      const result = await this.request('messages', roomId, { limit: 80 });
      if (this.destroyed || this.activeRoom?.roomId !== roomId) return;
      this.activeRoom = result.room || room;
      this.messages = Array.isArray(result.messages) ? result.messages : [];
      this.activeRoom.unreadCount = 0;
      this.renderRooms();
      this.renderConversation();
      this.scrollToBottom(false);
      this.updateTotalUnread();
    } catch (error) {
      this.renderConversationError(error);
    }
  }

  renderConversationLoading() {
    const panel = this.mount.querySelector('.chat-conversation-panel');
    if (!panel) return;
    panel.innerHTML = '<div class="chat-conversation-loading"><span class="loading-spinner"></span><span>A carregar mensagens…</span></div>';
  }

  renderConversationError(error) {
    const panel = this.mount.querySelector('.chat-conversation-panel');
    if (!panel) return;
    panel.innerHTML = `<div class="chat-empty-state"><span class="chat-empty-icon"><img src="${icon('message-circle-warning', 'c9a55b')}" alt=""></span><h3>Conversa indisponível</h3><p>${escapeHtml(error.message || 'Tente novamente.')}</p><button class="button button-secondary button-small" type="button">Repetir</button></div>`;
    panel.querySelector('button')?.addEventListener('click', () => this.selectRoom(this.activeRoom.roomId, { updateAddress: false }));
  }

  renderConversation() {
    const panel = this.mount.querySelector('.chat-conversation-panel');
    const room = this.activeRoom;
    if (!panel || !room) return;
    const peerPhoto = room.roomType === 'DIRECT' ? safeImageUrl(room.peer?.profilePhotoUrl) : '';
    const activeAvatar = peerPhoto
      ? `<img src="${escapeHtml(peerPhoto)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(room.name))}">`
      : `<img src="${icon(roomIcon(room.roomType), 'ffffff')}" alt="">`;
    panel.innerHTML = `
      <header class="chat-conversation-header">
        <button class="chat-mobile-back" type="button" aria-label="Voltar às conversas"><img src="${icon('arrow-left')}" alt=""></button>
        <span class="chat-active-avatar">${activeAvatar}</span>
        <div class="chat-active-copy">
          <h2>${escapeHtml(room.name)}</h2>
          <p><span class="chat-presence-dot"></span>${escapeHtml(roomTypeLabel(room.roomType))} · ${Number(room.participantCount || 0)} participantes</p>
        </div>
        <button class="chat-info-button" type="button" aria-label="Informações da conversa" title="${escapeHtml(room.description || roomTypeLabel(room.roomType))}"><img src="${icon('info')}" alt=""></button>
      </header>
      <div class="chat-safety-note"><img src="${icon('shield-check')}" alt=""><span>Canal protegido. Partilhe apenas informações relacionadas com a formação.</span></div>
      <div class="chat-message-list" aria-live="polite">${this.messagesTemplate()}</div>
      <form class="chat-composer">
        <div class="chat-draft-context" hidden></div>
        <div class="chat-composer-row">
          <div class="chat-emoji-control">
            <button class="chat-emoji-button" type="button" aria-label="Adicionar emoji" title="Adicionar emoji" aria-expanded="false">
              <img src="${icon('smile')}" alt="">
            </button>
            <div class="chat-emoji-picker" role="dialog" aria-label="Escolher emoji" hidden>
              <strong>Escolha um emoji</strong>
              <div class="chat-emoji-grid">
                ${CHAT_EMOJIS.map((emoji) => `<button type="button" data-chat-emoji="${emoji}" aria-label="Adicionar ${emoji}">${emoji}</button>`).join('')}
              </div>
            </div>
          </div>
          <textarea name="message" rows="1" maxlength="2000" placeholder="Escreva uma mensagem" aria-label="Mensagem" required></textarea>
          <button class="chat-send-button" type="submit" aria-label="Enviar mensagem" title="Enviar mensagem"><img src="${icon('send', 'ffffff')}" alt=""></button>
        </div>
        <div class="chat-composer-meta"><span>Enter para enviar · Shift + Enter para nova linha</span><span data-chat-character-count>0/2000</span></div>
      </form>
    `;
    this.bindConversationEvents();
  }

  messagesTemplate() {
    if (!this.messages.length) {
      return `<div class="chat-welcome-message"><span><img src="${icon(roomIcon(this.activeRoom.roomType), 'c9a55b')}" alt=""></span><h3>Início da conversa</h3><p>${escapeHtml(this.activeRoom.description || 'Envie a primeira mensagem deste canal.')}</p></div>`;
    }
    let previousDay = '';
    return this.messages.map((message) => {
      const day = chatDay(message.createdAt);
      const separator = day !== previousDay ? `<div class="chat-date-separator"><span>${escapeHtml(day)}</span></div>` : '';
      previousDay = day;
      return separator + this.messageTemplate(message);
    }).join('');
  }

  messageTemplate(message) {
    const photo = safeImageUrl(message.sender?.profilePhotoUrl);
    const avatar = photo
      ? `<img src="${escapeHtml(photo)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(message.sender?.name))}">`
      : `<span>${escapeHtml(initials(message.sender?.name))}</span>`;
    const canEdit = message.isMine && !message.isDeleted;
    const canDelete = !message.isDeleted && (message.isMine || this.mode === 'admin');
    const canReport = !message.isDeleted && !message.isMine && this.mode === 'student';
    return `
      <article class="chat-message ${message.isMine ? 'is-mine' : ''} ${message.isDeleted ? 'is-deleted' : ''}" data-message-id="${escapeHtml(message.messageId)}">
        <div class="chat-message-avatar">${avatar}</div>
        <div class="chat-message-content">
          <div class="chat-message-author">
            <strong>${escapeHtml(message.isMine ? 'Você' : message.sender?.name || 'Participante')}</strong>
            ${message.sender?.type === 'ADMIN' ? '<span class="chat-trainer-badge">Formador</span>' : ''}
            <time>${escapeHtml(chatTime(message.createdAt))}</time>
            ${message.editedAt && !message.isDeleted ? '<small>Editada</small>' : ''}
            ${this.mode === 'admin' && message.reportCount ? `<span class="chat-report-badge"><img src="${icon('flag', 'b42318')}" alt="">${message.reportCount}</span>` : ''}
          </div>
          <div class="chat-message-bubble">
            ${message.replyTo ? `<blockquote><strong>${escapeHtml(message.replyTo.senderName)}</strong><span>${escapeHtml(compactText(message.replyTo.body, 120))}</span></blockquote>` : ''}
            ${message.isDeleted ? '<p class="chat-deleted-copy"><img src="' + icon('ban') + '" alt="">Mensagem removida</p>' : `<p>${escapeHtml(message.body)}</p>`}
          </div>
        </div>
        ${!message.isDeleted ? `
          <div class="chat-message-actions">
            <button type="button" data-chat-action="reply" aria-label="Responder" title="Responder"><img src="${icon('reply')}" alt=""></button>
            ${canEdit ? `<button type="button" data-chat-action="edit" aria-label="Editar" title="Editar"><img src="${icon('pencil')}" alt=""></button>` : ''}
            ${canReport ? `<button type="button" data-chat-action="report" aria-label="Denunciar" title="Denunciar"><img src="${icon('flag')}" alt=""></button>` : ''}
            ${canDelete ? `<button type="button" data-chat-action="delete" aria-label="Remover" title="Remover"><img src="${icon('trash-2')}" alt=""></button>` : ''}
          </div>
        ` : ''}
      </article>
    `;
  }

  bindConversationEvents() {
    const panel = this.mount.querySelector('.chat-conversation-panel');
    const form = panel?.querySelector('.chat-composer');
    const textarea = form?.elements.message;
    const emojiButton = form?.querySelector('.chat-emoji-button');
    const emojiPicker = form?.querySelector('.chat-emoji-picker');
    panel?.querySelector('.chat-mobile-back')?.addEventListener('click', () => {
      this.mount.querySelector('.chat-workspace')?.classList.remove('has-active-room');
      if (this.mode === 'student') history.replaceState(null, '', '#/chat');
    });
    panel?.querySelector('.chat-message-list')?.addEventListener('click', (event) => this.handleMessageAction(event));
    form?.addEventListener('submit', (event) => this.submitMessage(event));
    emojiButton?.addEventListener('click', () => {
      const willOpen = emojiPicker.hasAttribute('hidden');
      emojiPicker.toggleAttribute('hidden', !willOpen);
      emojiButton.setAttribute('aria-expanded', String(willOpen));
    });
    emojiPicker?.addEventListener('click', (event) => {
      const option = event.target.closest('[data-chat-emoji]');
      if (!option || !textarea) return;
      const emoji = option.dataset.chatEmoji;
      const start = textarea.selectionStart ?? textarea.value.length;
      const end = textarea.selectionEnd ?? textarea.value.length;
      if (textarea.value.length - (end - start) + emoji.length > 2000) {
        showToast('A mensagem não pode exceder 2 000 caracteres.', 'error');
        return;
      }
      textarea.setRangeText(emoji, start, end, 'end');
      textarea.dispatchEvent(new Event('input'));
      emojiPicker.hidden = true;
      emojiButton.setAttribute('aria-expanded', 'false');
      textarea.focus();
    });
    panel?.addEventListener('click', (event) => {
      if (!emojiPicker || emojiPicker.hidden || event.target.closest('.chat-emoji-control')) return;
      emojiPicker.hidden = true;
      emojiButton?.setAttribute('aria-expanded', 'false');
    });
    textarea?.addEventListener('input', () => {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
      const counter = form.querySelector('[data-chat-character-count]');
      if (counter) counter.textContent = `${textarea.value.length}/2000`;
    });
    textarea?.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && emojiPicker && !emojiPicker.hidden) {
        emojiPicker.hidden = true;
        emojiButton?.setAttribute('aria-expanded', 'false');
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  }

  handleMessageAction(event) {
    const button = event.target.closest('[data-chat-action]');
    const article = button?.closest('[data-message-id]');
    if (!button || !article) return;
    const message = this.messages.find((item) => item.messageId === article.dataset.messageId);
    if (!message) return;
    const action = button.dataset.chatAction;
    if (action === 'reply') {
      this.replyingTo = message;
      this.editingMessage = null;
      this.renderDraftContext();
    } else if (action === 'edit') {
      this.editingMessage = message;
      this.replyingTo = null;
      const textarea = this.mount.querySelector('.chat-composer textarea');
      textarea.value = message.body;
      textarea.dispatchEvent(new Event('input'));
      this.renderDraftContext();
    } else if (action === 'delete') {
      this.deleteMessage(message);
    } else if (action === 'report') {
      this.openReportDialog(message);
    }
  }

  renderDraftContext() {
    const box = this.mount.querySelector('.chat-draft-context');
    const textarea = this.mount.querySelector('.chat-composer textarea');
    if (!box) return;
    const message = this.editingMessage || this.replyingTo;
    if (!message) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }
    box.hidden = false;
    box.innerHTML = `
      <span><img src="${icon(this.editingMessage ? 'pencil' : 'reply')}" alt=""></span>
      <div><strong>${this.editingMessage ? 'A editar mensagem' : `A responder a ${escapeHtml(message.sender?.name || 'Participante')}`}</strong><small>${escapeHtml(compactText(message.body, 110))}</small></div>
      <button type="button" aria-label="Cancelar"><img src="${icon('x')}" alt=""></button>
    `;
    box.querySelector('button')?.addEventListener('click', () => {
      this.editingMessage = null;
      this.replyingTo = null;
      box.hidden = true;
      if (textarea) {
        textarea.value = '';
        textarea.dispatchEvent(new Event('input'));
        textarea.focus();
      }
    });
    textarea?.focus();
  }

  async submitMessage(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const textarea = form.elements.message;
    const button = form.querySelector('.chat-send-button');
    const body = textarea.value.trim();
    if (!body || !this.activeRoom) return;
    button.disabled = true;
    button.classList.add('is-busy');
    try {
      const result = this.editingMessage
        ? await this.request('edit', this.editingMessage.messageId, body)
        : await this.request('send', this.activeRoom.roomId, body, this.replyingTo?.messageId || '');
      const message = result.message;
      const existingIndex = this.messages.findIndex((item) => item.messageId === message.messageId);
      if (existingIndex >= 0) this.messages[existingIndex] = message;
      else this.messages.push(message);
      textarea.value = '';
      textarea.dispatchEvent(new Event('input'));
      this.editingMessage = null;
      this.replyingTo = null;
      this.renderConversation();
      this.scrollToBottom();
      this.loadRooms({ quiet: true });
    } catch (error) {
      showToast(error.message || 'Não foi possível enviar a mensagem.', 'error');
    } finally {
      button.disabled = false;
      button.classList.remove('is-busy');
      this.mount.querySelector('.chat-composer textarea')?.focus();
    }
  }

  async deleteMessage(message) {
    if (!window.confirm(this.mode === 'admin' && !message.isMine
      ? 'Remover esta mensagem por moderação?'
      : 'Remover esta mensagem?')) return;
    try {
      const result = await this.request('delete', message.messageId);
      const index = this.messages.findIndex((item) => item.messageId === message.messageId);
      if (index >= 0) this.messages[index] = result.message;
      this.renderConversation();
      showToast('Mensagem removida.', 'success');
    } catch (error) {
      showToast(error.message || 'Não foi possível remover a mensagem.', 'error');
    }
  }

  openReportDialog(message) {
    const dialog = this.mount.querySelector('.chat-report-dialog');
    if (!dialog) return;
    dialog.querySelector('[name="messageId"]').value = message.messageId;
    dialog.querySelector('[name="reason"]').value = '';
    if (typeof dialog.showModal === 'function') dialog.showModal();
  }

  async poll() {
    if (this.polling || this.destroyed) return;
    this.polling = true;
    try {
      if (this.activeRoom) {
        const latest = this.messages.reduce((value, message) => {
          const candidate = message.updatedAt || message.createdAt || '';
          return !value || candidate > value ? candidate : value;
        }, '');
        const result = await this.request('messages', this.activeRoom.roomId, { limit: 80, since: latest });
        if (!this.destroyed && this.activeRoom?.roomId === result.room?.roomId) {
          const incoming = Array.isArray(result.messages) ? result.messages : [];
          if (incoming.length) {
            const wasNearBottom = this.isNearBottom();
            incoming.forEach((message) => {
              const index = this.messages.findIndex((item) => item.messageId === message.messageId);
              if (index >= 0) this.messages[index] = message;
              else this.messages.push(message);
            });
            this.messages.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
            this.activeRoom = result.room;
            const list = this.mount.querySelector('.chat-message-list');
            if (list) list.innerHTML = this.messagesTemplate();
            if (wasNearBottom) this.scrollToBottom();
          }
        }
      }
      this.pollCount += 1;
      if (this.pollCount % 3 === 0) await this.loadRooms({ quiet: true });
    } catch {
      // Uma falha temporária não interrompe a conversa; o ciclo seguinte tenta novamente.
    } finally {
      this.polling = false;
    }
  }

  isNearBottom() {
    const list = this.mount.querySelector('.chat-message-list');
    if (!list) return true;
    return list.scrollHeight - list.scrollTop - list.clientHeight < 120;
  }

  scrollToBottom(smooth = true) {
    window.requestAnimationFrame(() => {
      const list = this.mount.querySelector('.chat-message-list');
      list?.scrollTo({ top: list.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    });
  }

  updateTotalUnread() {
    this.onUnreadChange?.(this.rooms.reduce((sum, room) => sum + Number(room.unreadCount || 0), 0));
  }
}
