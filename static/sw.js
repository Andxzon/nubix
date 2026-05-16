const CACHE_NAME = 'meteo-iot-v1';
const OFFLINE_URL = '/';

self.addEventListener('install', (event) => {
  console.log('[SW] Instalando Service Worker...');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('[SW] Service Worker activado');
  event.waitUntil(clients.claim());
});

self.addEventListener('push', (event) => {
  console.log('[SW] Push recibido:', event);
  
  let data = {
    title: 'Estación Meteorológica',
    body: 'Nueva notificación',
    icon: '/static/images/logo_noti.png',
    badge: '/static/images/icon.png',
    tag: 'meteo-notification',
    data: {}
  };
  
  if (event.data) {
    try {
      const payload = event.data.json();
      data = { ...data, ...payload };
    } catch (e) {
      data.body = event.data.text();
    }
  }
  
  const options = {
    body: data.body,
    icon: data.icon || '/static/images/logo_noti.png',
    badge: data.badge || '/static/images/icon.png',
    tag: data.tag || 'meteo-notification',
    vibrate: [200, 100, 200],
    requireInteraction: data.requireInteraction || false,
    data: data.data || {},
    actions: data.actions || []
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Click en notificación:', event);
  event.notification.close();
  
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        for (const client of windowClients) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            return client.focus();
          }
        }
        return clients.openWindow(urlToOpen);
      })
  );
});
