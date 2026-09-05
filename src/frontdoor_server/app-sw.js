/* EntryMap service worker (TICK-327).
 *
 * The demo happens in an atrium on someone else's wifi, and the people this
 * product is for are often standing outside a door with one bar of signal.
 * So the app has to open even when the network does not answer.
 *
 * Strategy, deliberately narrow:
 *   - The app page and its icon are cached on install and served cache-first.
 *     They are large and they change only on deploy, so a phone pays the
 *     download once per release instead of once per launch.
 *   - Everything else - /screen, /screen/publish, /map/data, /scan/photo -
 *     is never cached. A scan verdict or a map row served from a stale cache
 *     would be a wrong answer about a real doorway, which is worse than no
 *     answer. Those requests go to the network and fail honestly.
 *   - A new deploy changes CACHE, which drops the old entries on activate.
 */

const CACHE = "entrymap-v1";
const SHELL = ["/app", "/app-icon.png", "/app-manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
      // A failed precache must not wedge the worker: the app still works
      // online, and the next launch tries again.
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!SHELL.includes(url.pathname)) return;

  event.respondWith(
    caches.match(request).then((hit) => {
      // Cache-first, but still refresh in the background so the next launch
      // after a deploy gets the new page without waiting for a cache bust.
      const network = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => hit);
      return hit || network;
    }),
  );
});
