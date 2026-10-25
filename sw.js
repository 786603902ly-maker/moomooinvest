// Service worker for the installed dashboard.
//
// Its job is installability and a usable offline fallback -- NOT speed via
// caching. This dashboard's whole point is showing current prices, so a
// cache that could serve yesterday's numbers as if they were today's would
// be worse than no service worker at all. The rules below are built around
// that:
//
//   /api/*       never cached, ever. Live quotes, ticks and notes always go
//                to the network, and a failure surfaces as a failure so the
//                page can say so rather than showing stale data silently.
//   navigation   network first. The cached copy is only reached when the
//                network actually fails, and the page then shows whatever
//                "Prices as of" date it was built with, so staleness is
//                visible rather than disguised.
//   icons etc.   cache first. They never change within a release.
//
// Bump CACHE whenever the precache list changes; activate deletes every
// cache that isn't the current one.
const CACHE = "moomooinvest-v1";
const PRECACHE = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      // addAll is all-or-nothing; one 404 would leave the worker uninstalled,
      // so each entry is allowed to fail on its own.
      .then((cache) => Promise.allSettled(PRECACHE.map((url) => cache.add(url))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // live data: straight to network

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put("/", copy));
          return res;
        })
        .catch(() => caches.match("/").then((hit) => hit || Response.error()))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
    )
  );
});
