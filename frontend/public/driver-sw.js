/**
 * Cardvert Driver service worker — deliberately minimal and auth-safe.
 *
 * - Immutable Next.js static assets: cache-first (hashed filenames).
 * - Navigations & API calls: network-only. NEVER cached — responses are
 *   authenticated and personal; caching them would leak data across
 *   sessions and serve stale trip/earnings state.
 * - Offline navigation gets a tiny inline fallback telling the driver
 *   tracking needs a connection.
 */
const STATIC_CACHE = "vantage-driver-static-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

const OFFLINE_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline · Cardvert Driver</title>
<style>body{margin:0;min-height:100dvh;display:grid;place-items:center;background:#0a0b0e;color:#eaedf2;font-family:system-ui,sans-serif;text-align:center;padding:24px}
h1{font-size:20px;margin:0 0 8px}p{color:#8a90a0;font-size:14px;max-width:280px;line-height:1.6}
b{color:#ffa62b}</style></head><body><div>
<h1><b>C</b> You're offline</h1>
<p>Cardvert Driver needs a connection to track trips and sync hourly earnings. Reconnect and pull to refresh.</p>
</div></body></html>`;

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Hashed, immutable build assets → cache-first
  if (url.origin === self.location.origin && url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const hit = await cache.match(event.request);
        if (hit) return hit;
        const res = await fetch(event.request);
        if (res.ok) cache.put(event.request, res.clone());
        return res;
      }),
    );
    return;
  }

  // Navigations → network, with offline fallback. Everything else untouched.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(
        () => new Response(OFFLINE_HTML, { headers: { "content-type": "text/html" } }),
      ),
    );
  }
});
