/**
 * WM Driver App — Service Worker (sw.js)
 *
 * Strategy:
 *   - Shell assets (HTML, CSS, JS, fonts): Network-first (revalidated, bypassing the
 *     browser's HTTP cache), falling back to the cache when offline
 *   - API calls (/driver/api/...): Network-only (the app handles IndexedDB
 *     queueing for offline submissions — the SW doesn't need to intercept them)
 */

const CACHE_NAME = 'wm-driver-app-v12';
const SHELL_ASSETS = [
  '/driver/app',
  '/wm_driver_app/static/src/css/app.css',
  '/wm_driver_app/static/src/js/app.js?v=6',
];

// ----- Install: pre-cache shell assets ---------------------------------
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_ASSETS).catch((err) => {
        console.warn('[SW] Pre-cache failed:', err);
      });
    })
  );
});

// ----- Activate: clean up old caches -----------------------------------
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => {
            return caches.delete(key);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// ----- Fetch: network-first with cache fallback when offline ------------
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Let API requests pass straight through — app JS handles offline queueing
  if (url.pathname.startsWith('/driver/api/')) {
    return; // network-only
  }

  // For shell assets / same-origin GET requests, try network first, fallback to cache
  if (event.request.method === 'GET') {
    // 'no-cache' revalidates with the server: Odoo serves static files with a
    // 7-day max-age, which would otherwise keep serving a fixed file's old copy
    event.respondWith(
      fetch(event.request, { cache: 'no-cache' })
        .then((response) => {
          if (response && response.ok) {
            const toCache = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, toCache));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  }
});

// ----- Background Sync (where supported) --------------------------------
self.addEventListener('sync', (event) => {
  if (event.tag === 'wm-sync-queue') {
    // The app's JS sync logic is triggered via postMessage; this fires it
    // again after connectivity returns, as a belt-and-braces approach.
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'SYNC_QUEUE' }));
      })
    );
  }
});
