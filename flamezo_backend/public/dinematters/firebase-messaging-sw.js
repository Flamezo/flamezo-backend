// Flamezo Merchant Dashboard — Firebase Cloud Messaging Service Worker
// Handles push notifications when the dashboard tab is in background.
// Cost: ZERO — FCM web push is completely free.

importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.8.0/firebase-messaging-compat.js');

let messaging = null;

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'FIREBASE_CONFIG') {
    try {
      firebase.initializeApp(event.data.config);
      messaging = firebase.messaging();

      messaging.onBackgroundMessage((payload) => {
        const { title, body, icon } = payload.notification || {};
        const data = payload.data || {};

        self.registration.showNotification(title || '🔔 New Order', {
          body: body || 'A new order has been placed.',
          icon: icon || '/logo-192.png',
          badge: '/badge-72.png',
          tag: `new-order-${data.order_number || Date.now()}`,
          renotify: true,
          requireInteraction: true, // Keep notification visible until dismissed
          actions: [
            { action: 'view', title: 'View Order' },
            { action: 'dismiss', title: 'Dismiss' }
          ],
          data: {
            url: '/flamezo_backend/orders',
            ...data,
          },
        });
      });
    } catch (e) {
      console.warn('[SW Merchant] Firebase init failed:', e);
    }
  }
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url || '/flamezo_backend/orders';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes('flamezo_backend') && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
