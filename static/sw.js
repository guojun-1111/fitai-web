// FitAI Service Worker — Offline caching + V11 API cache
const CACHE_VERSION = 'fitai-v24';
const STATIC_CACHE = CACHE_VERSION + '-static';
const CDN_CACHE = CACHE_VERSION + '-cdn';
const API_CACHE = CACHE_VERSION + '-api';

const CDN_HOSTS = ['cdn.jsdelivr.net'];

// API endpoints to cache with network-first strategy
const API_CACHE_PATHS = ['/api/dashboard/', '/api/insights/', '/api/health/', '/api/stats'];

// Install: pre-cache critical static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll([
        '/js/boot.js', '/js/state.js', '/js/utils.js', '/js/ws.js',
        '/js/chat.js', '/js/voice.js', '/js/call.js', '/js/nav.js',
        '/js/home.js', '/js/dashboard.js', '/js/sidebar.js', '/js/history.js',
        '/js/chart-utils.js', '/js/health.js', '/js/exercises.js', '/js/videos.js', '/js/insights.js', '/js/profile.js',
        '/js/settings.js', '/js/import.js', '/js/auth.js', '/js/analysis-worker.js',
        '/style.css', '/style-mobile.css', '/manifest.json',
        '/icons/icon-192.png', '/icons/icon-512.png',
        '/img/shot-dashboard.webp', '/img/shot-health.webp', '/img/shot-insights.webp',
        '/img/shot-chat.webp', '/img/shot-m-home.webp', '/img/shot-m-chat.webp',
      ]);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter(key => key !== STATIC_CACHE && key !== CDN_CACHE && key !== API_CACHE)
            .map(key => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Fetch: route by type
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: network-first with short cache, only GET
  if (url.pathname.startsWith('/api/') && event.request.method === 'GET') {
    const shouldCache = API_CACHE_PATHS.some(p => url.pathname.startsWith(p));
    if (shouldCache) {
      event.respondWith(apiNetworkFirst(event.request));
      return;
    }
    return; // Other API calls: pass through
  }

  // CDN scripts: Cache-first
  if (CDN_HOSTS.some(h => url.hostname.includes(h))) {
    event.respondWith(cacheFirst(event.request, CDN_CACHE));
    return;
  }

  // HTML: Network-first (mode==='navigate' more reliable than destination in Safari SW)
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // Static assets: Cache-first
  event.respondWith(cacheFirst(event.request, STATIC_CACHE));
});

// API network-first with 5-min TTL via Date header check
async function apiNetworkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      // Store with timestamp for TTL check
      const cloned = response.clone();
      const headers = new Headers(cloned.headers);
      headers.set('sw-cached-at', Date.now().toString());
      // Create a new response with the timestamp header
      const cacheResponse = new Response(cloned.body, {
        status: cloned.status,
        statusText: cloned.statusText,
        headers: headers,
      });
      cache.put(request, cacheResponse);
    }
    return response;
  } catch (e) {
    // Network failed — try cache
    const cached = await caches.match(request);
    if (cached) {
      const cachedAt = parseInt(cached.headers.get('sw-cached-at') || '0');
      const maxAge = request.url.includes('/insights/') ? 600000 : 300000; // 10min for insights, 5min for others
      if (Date.now() - cachedAt < maxAge) {
        return cached;
      }
    }
    return new Response(JSON.stringify({ error: 'offline', message: '网络不可用且缓存已过期' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    // cache:'reload' bypasses browser HTTP cache, forces network
    const response = await fetch(request, { cache: 'reload' });
    return response;
  } catch (e) {
    // Network failed — try cache
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'You are offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// Periodic cache cleanup (remove expired API entries)
setInterval(async () => {
  const cache = await caches.open(API_CACHE);
  const keys = await cache.keys();
  const now = Date.now();
  for (const req of keys) {
    const resp = await cache.match(req);
    if (resp) {
      const cachedAt = parseInt(resp.headers.get('sw-cached-at') || '0');
      if (now - cachedAt > 900000) { // 15 min max
        cache.delete(req);
      }
    }
  }
}, 300000); // Every 5 minutes
