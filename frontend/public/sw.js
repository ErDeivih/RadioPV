// RadioPV · Service Worker (F1)
// Cachea la "carcasa" de la app (HTML/JS/CSS del build) para que funcione offline y cargue
// rápido, PERO nunca el audio. Los ficheros del build van con hash y cambian en cada versión,
// así que el precache se regenera con cada instalación.
const CACHE = 'radiopv-shell-v1';
const SHELL = ['/', '/index.html'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => undefined)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Nunca cachear la API ni el streaming (tokens únicos + audio grande).
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/stream') ||
      url.pathname.startsWith('/recommend') || url.pathname.startsWith('/playlists') ||
      url.pathname.startsWith('/library') || url.pathname.startsWith('/media')) {
    return; // red directa
  }

  // Navegación: red primero, y si falla la carcasa (para recargar rutas offline).
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Recursos estáticos (JS/CSS/fotos con hash): cache primero, luego red.
  if (event.request.method === 'GET') {
    event.respondWith(
      caches.match(event.request).then((hit) => hit || fetch(event.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy)).catch(() => undefined);
        return res;
      }))
    );
  }
});
