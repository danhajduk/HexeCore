const CACHE = "hexe-app-v4";
const STATE_CACHE = "hexe-app-state";
const SHELL = ["/app", "/site.webmanifest", "/favicon.svg", "/web-app-manifest-192x192.png", "/offline.html"];

self.addEventListener("install", event => event.waitUntil(
  caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()),
));

self.addEventListener("activate", event => event.waitUntil(
  caches.keys()
    .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()),
));

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put("/app", copy));
      return response;
    }).catch(() => caches.match("/app").then(value => value || caches.match("/offline.html"))));
    return;
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    if (response.ok && new URL(request.url).origin === location.origin) {
      caches.open(CACHE).then(cache => cache.put(request, response.clone()));
    }
    return response;
  })));
});

self.addEventListener("push", event => {
  let value = {};
  try { value = event.data ? event.data.json() : {}; } catch { value = {}; }
  const path = typeof value.navigation_path === "string" && value.navigation_path.startsWith("/app") ? value.navigation_path : "/app";
  event.waitUntil(self.registration.showNotification(
    typeof value.title === "string" ? value.title : "Hexe",
    {
      body: typeof value.body === "string" ? value.body : "Open Hexe to view this update.",
      icon: "/web-app-manifest-192x192.png",
      badge: "/favicon-96x96.png",
      data: { path },
      tag: typeof value.event_id === "string" ? value.event_id : undefined,
      renotify: false,
    },
  ));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const path = event.notification.data && typeof event.notification.data.path === "string" && event.notification.data.path.startsWith("/app") ? event.notification.data.path : "/app";
  event.waitUntil((async () => {
    const state = await caches.open(STATE_CACHE);
    await state.put("/__notification-open", new Response("1", { headers: { "cache-control": "no-store" } }));
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (!("focus" in client)) continue;
      client.postMessage({ type: "notification.open", path });
      if ("navigate" in client) {
        const navigated = await client.navigate(path);
        const target = navigated || client;
        target.postMessage({ type: "notification.open", path });
        return target.focus();
      }
      return client.focus();
    }
    return clients.openWindow(path);
  })());
});
