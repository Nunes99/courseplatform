const SW_VERSION = 'courseplatform-push-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

function notificationTarget(rawUrl) {
  const value = String(rawUrl || '#/notifications');
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith('#/')) return `${self.registration.scope}${value}`;
  try {
    return new URL(value, self.registration.scope).href;
  } catch {
    return `${self.registration.scope}#/notifications`;
  }
}

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  const title = String(data.title || 'Nova atualização académica').slice(0, 120);
  const body = String(data.body || 'Consulte a plataforma para ver os detalhes.').slice(0, 300);
  const defaultIcon = new URL('assets/app-icon-192.png', self.registration.scope).href;
  const badgeIcon = new URL('assets/app-icon-192.png', self.registration.scope).href;
  event.waitUntil(self.registration.showNotification(title, {
    body,
    icon: defaultIcon,
    badge: badgeIcon,
    tag: String(data.tag || data.notificationId || SW_VERSION),
    renotify: Boolean(data.notificationId),
    requireInteraction: String(data.priority || '').toUpperCase() === 'HIGH',
    data: {
      url: notificationTarget(data.url),
      notificationId: String(data.notificationId || '')
    },
    actions: [{ action: 'open', title: 'Abrir' }]
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = notificationTarget(event.notification.data?.url);
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === new URL(target).origin) {
        await client.focus();
        if ('navigate' in client) await client.navigate(target);
        return;
      }
    }
    await self.clients.openWindow(target);
  })());
});
