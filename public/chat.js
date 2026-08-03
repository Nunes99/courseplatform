import { escapeHtml, showToast } from './utils.js';

const ICONS = 'https://api.iconify.design/lucide';
const SUPABASE_ESM = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';
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

function presenceLabel(peer = {}) {
  if (peer.isOnline) return 'Online agora';
  const date = new Date(peer.lastSeenAt || '');
  if (Number.isNaN(date.getTime())) return 'Offline';
  return `Visto ${new Intl.DateTimeFormat('pt-PT', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
  }).format(date)}`;
}

function deliveryLabel(status, count = 0) {
  if (status === 'READ') return count > 1 ? `Lida por ${count}` : 'Lida';
  if (status === 'DELIVERED') return count > 1 ? `Entregue a ${count}` : 'Entregue';
  return 'Enviada';
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
    this.actor = null;
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
    this.pollIntervalMs = 4000;
    this.realtimePollIntervalMs = 15000;
    this.realtimeClient = null;
    this.realtimeChannels = new Map();
    this.realtimeConfiguration = null;
    this.realtimePromise = null;
    this.realtimeRefreshTimers = new Map();
    this.realtimeRefreshingRooms = new Set();
    this.realtimeDirtyRooms = new Set();
    this.realtimeConnectedRooms = new Set();
    this.destroyed = false;
    this.visibilityHandler = () => {
      if (document.visibilityState !== 'visible' || !this.activeRoom) return;
      this.request('presence', this.activeRoom.roomId).catch(() => {});
      this.markActiveRoomRead(this.activeRoom.roomId);
    };
  }

  async start() {
    this.renderFrame();
    this.bindEvents();
    this.realtimePromise = this.initializeRealtime().catch(() => false);
    await Promise.all([
      this.loadRooms(),
      this.mode === 'student' ? this.loadContacts({ quiet: true }) : Promise.resolve()
    ]);
    await this.realtimePromise;
    await this.syncRealtimeChannels();
    if (this.destroyed || !this.rooms.length) return;
    const preferred = this.rooms.find((room) => room.roomId === this.initialRoomId);
    if (preferred || window.matchMedia('(min-width: 761px)').matches) {
      await this.selectRoom((preferred || this.rooms[0]).roomId, { updateAddress: false });
    }
    this.startPolling();
  }

  destroy() {
    this.destroyed = true;
    window.clearInterval(this.pollTimer);
    this.pollTimer = null;
    this.realtimeRefreshTimers.forEach((timer) => window.clearTimeout(timer));
    this.realtimeRefreshTimers.clear();
    this.realtimeDirtyRooms.clear();
    this.realtimeChannels.forEach((channel) => this.realtimeClient?.removeChannel(channel));
    this.realtimeChannels.clear();
    this.realtimeClient?.removeAllChannels?.();
    this.realtimeClient = null;
    document.removeEventListener('visibilitychange', this.visibilityHandler);
  }

  request(name, ...args) {
    const methods = this.mode === 'admin'
      ? {
          rooms: 'adminChatRooms',
          messages: 'adminChatMessages',
          send: 'adminSendChatMessage',
          edit: 'adminEditChatMessage',
          delete: 'adminDeleteChatMessage',
          read: 'adminMarkChatRoomRead',
          presence: 'adminUpdatePresence',
          realtime: 'adminChatRealtimeConfiguration'
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
          startDirect: 'startDirectChat',
          presence: 'updatePresence',
          realtime: 'chatRealtimeConfiguration'
        };
    const method = this.api[methods[name]];
    if (typeof method !== 'function') throw new Error('O módulo de mensagens não está disponível nesta versão.');
    return method.apply(this.api, args);
  }

  async initializeRealtime({ refreshToken = false } = {}) {
    const result = await this.request('realtime');
    const configuration = result?.realtime || {};
    this.realtimeConfiguration = configuration;
    this.realtimePollIntervalMs = Math.max(4000, Number(configuration.pollIntervalMs || 15000));
    if (!configuration.enabled || !configuration.url || !configuration.publishableKey || !configuration.accessToken) {
      this.usePollingFallback();
      return false;
    }
    try {
      if (!this.realtimeClient) {
        const { createClient } = await import(SUPABASE_ESM);
        if (this.destroyed) return false;
        this.realtimeClient = createClient(configuration.url, configuration.publishableKey, {
          auth: {
            persistSession: false,
            autoRefreshToken: false,
            detectSessionInUrl: false
          },
          realtime: {
            params: { eventsPerSecond: 12 },
            heartbeatIntervalMs: 25000,
            reconnectAfterMs: (tries) => Math.min(1000 * (2 ** Math.min(tries, 5)), 30000)
          }
        });
      }
      await this.realtimeClient.realtime.setAuth(configuration.accessToken);
      if (!refreshToken) await this.syncRealtimeChannels();
      return true;
    } catch (error) {
      console.warn('Não foi possível iniciar as mensagens em tempo real.', error);
      this.usePollingFallback();
      return false;
    }
  }

  async syncRealtimeChannels() {
    if (!this.realtimeClient || this.destroyed) return;
    const desiredChannels = new Map();
    const inboxTopic = String(this.realtimeConfiguration?.inboxTopic || '').trim();
    if (inboxTopic) desiredChannels.set('inbox', { topic: inboxTopic, type: 'inbox' });
    if (this.activeRoom?.roomId) {
      desiredChannels.set(`room:${this.activeRoom.roomId}`, {
        topic: `chat:room:${this.activeRoom.roomId}:messages`,
        type: 'room',
        roomId: this.activeRoom.roomId
      });
    }

    this.realtimeChannels.forEach((channel, channelKey) => {
      const desired = desiredChannels.get(channelKey);
      if (desired && channel.topic?.endsWith(desired.topic)) return;
      this.realtimeClient.removeChannel(channel);
      this.realtimeChannels.delete(channelKey);
      this.realtimeConnectedRooms.delete(channelKey);
    });

    desiredChannels.forEach((descriptor, channelKey) => {
      if (this.realtimeChannels.has(channelKey)) return;
      let channel = this.realtimeClient.channel(descriptor.topic, { config: { private: true } });
      if (descriptor.type === 'inbox') {
        channel = channel.on('broadcast', { event: 'ROOMS_CHANGED' }, () => this.scheduleRealtimeInboxRefresh());
      } else {
        channel = channel
          .on('broadcast', { event: 'INSERT' }, () => this.scheduleRealtimeRefresh(descriptor.roomId))
          .on('broadcast', { event: 'UPDATE' }, () => this.scheduleRealtimeRefresh(descriptor.roomId))
          .on('broadcast', { event: 'DELETE' }, () => this.scheduleRealtimeRefresh(descriptor.roomId));
      }
      channel.subscribe((status, error) => {
        if (status === 'SUBSCRIBED') this.realtimeConnectedRooms.add(channelKey);
        if (['CHANNEL_ERROR', 'TIMED_OUT', 'CLOSED'].includes(status)) {
          this.realtimeConnectedRooms.delete(channelKey);
          if (error) console.warn(`Falha no canal Realtime ${channelKey}.`, error);
        }
        this.updateRealtimeTransportState();
      });
      this.realtimeChannels.set(channelKey, channel);
    });
    this.updateRealtimeTransportState();
  }

  realtimeHasFullCoverage() {
    if (!this.realtimeChannels.size) return false;
    return [...this.realtimeChannels.keys()].every((channelKey) => this.realtimeConnectedRooms.has(channelKey));
  }

  updateRealtimeTransportState() {
    const connected = this.realtimeHasFullCoverage();
    this.updateLiveIndicator(connected);
    this.setPollingInterval(connected ? this.realtimePollIntervalMs : 4000);
  }

  usePollingFallback() {
    this.updateLiveIndicator(false);
    this.setPollingInterval(4000);
  }

  setPollingInterval(intervalMs) {
    const nextInterval = Math.max(4000, Number(intervalMs || 4000));
    if (this.pollIntervalMs === nextInterval) return;
    this.pollIntervalMs = nextInterval;
    if (this.pollTimer !== null) this.startPolling();
  }

  startPolling() {
    window.clearInterval(this.pollTimer);
    if (this.destroyed) {
      this.pollTimer = null;
      return;
    }
    this.pollTimer = window.setInterval(() => this.poll(), this.pollIntervalMs);
  }

  updateLiveIndicator(connected) {
    const indicator = this.mount.querySelector('.chat-live-indicator');
    if (!indicator) return;
    indicator.classList.toggle('is-connected', Boolean(connected));
    indicator.innerHTML = `<i></i>${connected ? ' Em tempo real' : ' Atualização automática'}`;
  }

  scheduleRealtimeRefresh(roomId) {
    if (!roomId || this.destroyed) return;
    if (this.realtimeRefreshingRooms.has(roomId)) {
      this.realtimeDirtyRooms.add(roomId);
      return;
    }
    window.clearTimeout(this.realtimeRefreshTimers.get(roomId));
    const timer = window.setTimeout(() => {
      this.realtimeRefreshTimers.delete(roomId);
      this.refreshRoomFromRealtime(roomId);
    }, 90);
    this.realtimeRefreshTimers.set(roomId, timer);
  }

  scheduleRealtimeInboxRefresh() {
    if (this.destroyed) return;
    const timerKey = 'inbox';
    window.clearTimeout(this.realtimeRefreshTimers.get(timerKey));
    const timer = window.setTimeout(async () => {
      this.realtimeRefreshTimers.delete(timerKey);
      await this.loadRooms({ quiet: true });
      await this.syncRealtimeChannels();
    }, 90);
    this.realtimeRefreshTimers.set(timerKey, timer);
  }

  async refreshRoomFromRealtime(roomId) {
    if (this.destroyed) return;
    if (this.realtimeRefreshingRooms.has(roomId)) {
      this.realtimeDirtyRooms.add(roomId);
      return;
    }
    this.realtimeRefreshingRooms.add(roomId);
    this.realtimeDirtyRooms.delete(roomId);
    try {
      if (this.activeRoom?.roomId !== roomId) {
        await this.loadRooms({ quiet: true });
        return;
      }
      const wasNearBottom = this.isNearBottom();
      const result = await this.request('messages', roomId, { limit: 80 });
      if (this.destroyed || this.activeRoom?.roomId !== roomId) return;
      const pending = this.messages.filter((message) => message.isPending || message.isFailed);
      const serverMessages = Array.isArray(result.messages) ? result.messages : [];
      const serverIds = new Set(serverMessages.map((message) => message.messageId));
      this.messages = [...serverMessages, ...pending.filter((message) => !serverIds.has(message.messageId))]
        .sort((first, second) => new Date(first.createdAt) - new Date(second.createdAt));
      this.activeRoom = result.room || this.activeRoom;
      const list = this.mount.querySelector('.chat-message-list');
      if (list) list.innerHTML = this.messagesTemplate();
      if (wasNearBottom) this.scrollToBottom(false);
      this.markActiveRoomRead(roomId);
      await this.loadRooms({ quiet: true });
    } catch {
      // Polling remains active as a lossless fallback.
    } finally {
      this.realtimeRefreshingRooms.delete(roomId);
      if (this.realtimeDirtyRooms.delete(roomId)) this.scheduleRealtimeRefresh(roomId);
    }
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
    document.addEventListener('visibilitychange', this.visibilityHandler);
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
      this.actor = result.actor || this.actor;
      if (this.activeRoom) {
        this.activeRoom = this.rooms.find((room) => room.roomId === this.activeRoom.roomId) || this.activeRoom;
      }
      this.renderSidebarContent();
      this.onUnreadChange?.(Number(result.unreadCount || 0));
      if (!this.rooms.length && this.panelMode === 'rooms') this.renderNoRooms();
      this.syncRealtimeChannels().catch(() => {});
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
      const peerPhoto = room.peer ? safeImageUrl(room.peer.profilePhotoUrl) : '';
      const roomAvatar = peerPhoto
        ? `<img src="${escapeHtml(peerPhoto)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(room.name))}">`
        : `<img src="${icon(roomIcon(room.roomType), room.roomId === this.activeRoom?.roomId ? 'ffffff' : '00365b')}" alt="">`;
      const roomMeta = room.peer
        ? `<span class="chat-presence-dot ${room.peer?.isOnline ? '' : 'is-offline'}"></span>${escapeHtml(presenceLabel(room.peer))}`
        : `${escapeHtml(roomTypeLabel(room.roomType))} · ${Number(room.participantCount || 0)} participantes`;
      return `
        <button type="button" role="option" aria-selected="${String(room.roomId === this.activeRoom?.roomId)}"
          class="chat-room-item ${room.roomId === this.activeRoom?.roomId ? 'is-active' : ''}"
          data-chat-room="${escapeHtml(room.roomId)}">
          <span class="chat-room-avatar">${roomAvatar}</span>
          <span class="chat-room-copy">
            <span class="chat-room-title-row"><strong>${escapeHtml(room.name)}</strong><time>${escapeHtml(chatTime(lastMessage?.createdAt))}</time></span>
            <span class="chat-room-preview">${escapeHtml(preview || 'Sem mensagens')}</span>
            <span class="chat-room-meta">${roomMeta}</span>
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
          <span class="chat-contact-avatar">${avatar}<i class="chat-contact-presence ${contact.isOnline ? 'is-online' : ''}" aria-label="${escapeHtml(presenceLabel(contact))}"></i></span>
          <span class="chat-contact-copy">
            <strong>${escapeHtml(contact.fullName)}</strong>
            <span>${escapeHtml(compactText(courses || 'Colega do seu curso', 64))}</span>
            <small>${escapeHtml(contact.publicStudentId || '')} · ${escapeHtml(presenceLabel(contact))}</small>
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
    this.syncRealtimeChannels().catch((error) => {
      console.warn('Não foi possível acompanhar esta conversa em tempo real.', error);
      this.usePollingFallback();
    });
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
      this.markActiveRoomRead(roomId);
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
    const peerPhoto = room.peer ? safeImageUrl(room.peer.profilePhotoUrl) : '';
    const activeAvatar = peerPhoto
      ? `<img src="${escapeHtml(peerPhoto)}" alt="" data-chat-avatar-fallback="${escapeHtml(initials(room.name))}">`
      : `<img src="${icon(roomIcon(room.roomType), 'ffffff')}" alt="">`;
    const activePresence = room.peer
      ? `<span class="chat-presence-dot ${room.peer?.isOnline ? '' : 'is-offline'}"></span>${escapeHtml(presenceLabel(room.peer))}`
      : `<span class="chat-presence-dot"></span>${escapeHtml(roomTypeLabel(room.roomType))} · ${Number(room.participantCount || 0)} participantes · ${Number(room.onlineCount || 0)} online`;
    panel.innerHTML = `
      <header class="chat-conversation-header">
        <button class="chat-mobile-back" type="button" aria-label="Voltar às conversas"><img src="${icon('arrow-left')}" alt=""></button>
        <span class="chat-active-avatar">${activeAvatar}</span>
        <div class="chat-active-copy">
          <h2>${escapeHtml(room.name)}</h2>
          <p>${activePresence}</p>
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
    const isTransient = Boolean(message.isPending || message.isFailed);
    const canEdit = message.isMine && !message.isDeleted && !isTransient;
    const canDelete = !message.isDeleted && !isTransient && (message.isMine || this.mode === 'admin');
    const canReport = !message.isDeleted && !message.isMine && !isTransient && this.mode === 'student';
    const receiptStatus = ['SENT', 'DELIVERED', 'READ'].includes(message.deliveryStatus) ? message.deliveryStatus : 'SENT';
    const receiptCount = receiptStatus === 'READ' ? Number(message.readCount || 0) : Number(message.deliveredCount || 0);
    const receiptLabel = message.isFailed ? 'Não enviada' : (message.isPending ? 'A enviar' : deliveryLabel(receiptStatus, receiptCount));
    return `
      <article class="chat-message ${message.isMine ? 'is-mine' : ''} ${message.isDeleted ? 'is-deleted' : ''} ${message.isPending ? 'is-pending' : ''} ${message.isFailed ? 'is-failed' : ''}" data-message-id="${escapeHtml(message.messageId)}">
        <div class="chat-message-avatar">${avatar}</div>
        <div class="chat-message-content">
          <div class="chat-message-author">
            <strong>${escapeHtml(message.isMine ? 'Você' : message.sender?.name || 'Participante')}</strong>
            ${message.sender?.type === 'ADMIN' ? '<span class="chat-trainer-badge">Formador</span>' : ''}
            <time>${escapeHtml(chatTime(message.createdAt))}</time>
            ${message.editedAt && !message.isDeleted ? '<small>Editada</small>' : ''}
            ${message.isMine && !message.isDeleted ? `
              <span class="chat-delivery-status is-${message.isFailed ? 'failed' : (message.isPending ? 'pending' : receiptStatus.toLowerCase())}" title="${escapeHtml(receiptLabel)}" aria-label="${escapeHtml(receiptLabel)}">
                <img src="${icon(message.isFailed ? 'circle-alert' : (message.isPending ? 'clock-3' : (receiptStatus === 'SENT' ? 'check' : 'check-check')))}" alt=""><small>${escapeHtml(receiptLabel)}</small>
              </span>
            ` : ''}
            ${this.mode === 'admin' && message.reportCount ? `<span class="chat-report-badge"><img src="${icon('flag', 'b42318')}" alt="">${message.reportCount}</span>` : ''}
          </div>
          <div class="chat-message-bubble">
            ${message.replyTo ? `<blockquote><strong>${escapeHtml(message.replyTo.senderName)}</strong><span>${escapeHtml(compactText(message.replyTo.body, 120))}</span></blockquote>` : ''}
            ${message.isDeleted ? '<p class="chat-deleted-copy"><img src="' + icon('ban') + '" alt="">Mensagem removida</p>' : `<p>${escapeHtml(message.body)}</p>`}
          </div>
        </div>
        ${!message.isDeleted ? `
          <div class="chat-message-actions">
            ${!isTransient ? `<button type="button" data-chat-action="reply" aria-label="Responder" title="Responder"><img src="${icon('reply')}" alt=""></button>` : ''}
            ${canEdit ? `<button type="button" data-chat-action="edit" aria-label="Editar" title="Editar"><img src="${icon('pencil')}" alt=""></button>` : ''}
            ${canReport ? `<button type="button" data-chat-action="report" aria-label="Denunciar" title="Denunciar"><img src="${icon('flag')}" alt=""></button>` : ''}
            ${canDelete ? `<button type="button" data-chat-action="delete" aria-label="Remover" title="Remover"><img src="${icon('trash-2')}" alt=""></button>` : ''}
            ${message.isFailed ? `<button type="button" data-chat-action="retry" aria-label="Tentar novamente" title="Tentar novamente"><img src="${icon('rotate-cw')}" alt=""></button>` : ''}
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
    } else if (action === 'retry') {
      this.restoreFailedMessage(message);
    }
  }

  restoreFailedMessage(message) {
    this.messages = this.messages.filter((item) => item.messageId !== message.messageId);
    const list = this.mount.querySelector('.chat-message-list');
    if (list) list.innerHTML = this.messagesTemplate();
    const textarea = this.mount.querySelector('.chat-composer textarea');
    if (!textarea) return;
    textarea.value = message.body || '';
    textarea.dispatchEvent(new Event('input'));
    textarea.focus();
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
    const editingMessage = this.editingMessage;
    const replyTo = this.replyingTo;
    const temporaryId = editingMessage ? '' : `pending-${crypto.randomUUID?.() || Date.now().toString(36)}`;
    if (!editingMessage) {
      this.messages.push({
        messageId: temporaryId,
        roomId: this.activeRoom.roomId,
        body,
        isMine: true,
        isDeleted: false,
        isPending: true,
        sender: {
          type: this.actor?.type || (this.mode === 'admin' ? 'ADMIN' : 'STUDENT'),
          name: this.actor?.name || 'Você',
          profilePhotoUrl: ''
        },
        replyTo: replyTo ? {
          messageId: replyTo.messageId,
          senderName: replyTo.sender?.name || 'Participante',
          body: replyTo.body || ''
        } : null,
        deliveryStatus: 'SENT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      });
      textarea.value = '';
      textarea.dispatchEvent(new Event('input'));
      this.replyingTo = null;
      this.editingMessage = null;
      this.renderDraftContext();
      const list = this.mount.querySelector('.chat-message-list');
      if (list) list.innerHTML = this.messagesTemplate();
      this.scrollToBottom();
    } else {
      button.disabled = true;
      button.classList.add('is-busy');
    }
    try {
      const result = editingMessage
        ? await this.request('edit', editingMessage.messageId, body)
        : await this.request('send', this.activeRoom.roomId, body, replyTo?.messageId || '');
      const message = result.message;
      const temporaryIndex = temporaryId ? this.messages.findIndex((item) => item.messageId === temporaryId) : -1;
      const existingIndex = this.messages.findIndex((item) => item.messageId === message.messageId);
      if (existingIndex >= 0) {
        this.messages[existingIndex] = message;
        if (temporaryIndex >= 0 && temporaryIndex !== existingIndex) this.messages.splice(temporaryIndex, 1);
      } else if (temporaryIndex >= 0) this.messages[temporaryIndex] = message;
      else this.messages.push(message);
      textarea.value = '';
      textarea.dispatchEvent(new Event('input'));
      this.editingMessage = null;
      this.replyingTo = null;
      if (editingMessage) this.renderConversation();
      else {
        const list = this.mount.querySelector('.chat-message-list');
        if (list) list.innerHTML = this.messagesTemplate();
      }
      this.scrollToBottom();
      this.loadRooms({ quiet: true });
    } catch (error) {
      if (temporaryId) {
        const temporary = this.messages.find((item) => item.messageId === temporaryId);
        if (temporary) {
          temporary.isPending = false;
          temporary.isFailed = true;
          const list = this.mount.querySelector('.chat-message-list');
          if (list) list.innerHTML = this.messagesTemplate();
        }
      }
      showToast(error.message || 'Não foi possível enviar a mensagem.', 'error');
    } finally {
      if (editingMessage) {
        button.disabled = false;
        button.classList.remove('is-busy');
      }
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
      const realtimeExpiry = new Date(this.realtimeConfiguration?.expiresAt || '').getTime();
      if (this.realtimeClient && Number.isFinite(realtimeExpiry) && realtimeExpiry - Date.now() < 120000) {
        await this.initializeRealtime({ refreshToken: true });
      }
      await this.request('presence', this.activeRoom?.roomId || '');
      if (this.activeRoom) {
        const latest = this.messages.filter((message) => !message.isPending && !message.isFailed).reduce((value, message) => {
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
            this.markActiveRoomRead(this.activeRoom.roomId);
          }
        }
      }
      this.pollCount += 1;
      if (this.pollCount % 3 === 0) await this.loadRooms({ quiet: true });
      if (this.mode === 'student' && this.pollCount % 6 === 0) await this.loadContacts({ quiet: true });
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

  async markActiveRoomRead(roomId) {
    if (!roomId || document.visibilityState !== 'visible') return;
    try {
      await this.request('read', roomId);
      const room = this.rooms.find((item) => item.roomId === roomId);
      if (room) room.unreadCount = 0;
      this.updateTotalUnread();
    } catch {
      // A próxima atualização volta a tentar sem interromper a conversa.
    }
  }
}
