const CACHE_NAME = "scalper-shell-v1";
const SHELL = ["/", "/static/styles.css", "/static/app.js", "/manifest.webmanifest"];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
  )));
  self.clients.claim();
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
    if (response.ok && (url.pathname === "/" || url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest")) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
    }
    return response;
  })));
});
