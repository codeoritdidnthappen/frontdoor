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
 *     The name carries the deployed commit: the server rewrites the __COMMIT__
 *     placeholder below when it serves this file. It used to be a fixed
 *     "entrymap-v1", so the comment above described a behaviour the code did
 *     not have -- after a deploy, a phone that had opened the app before was
 *     served the previous release from its own cache, and only picked up the
 *     new page on the launch after that. A design port shipped that way and
 *     the old artwork was still on screen while the server was answering
 *     correctly.
 *
 * WHY CACHE-FIRST STAYS, AND WHAT WAS ADDED INSTEAD (#483)
 * -------------------------------------------------------
 * Cache-first has one defect and it is not small: the navigation for /app is
 * answered from the cache before the browser has even asked whether a new
 * worker exists, so the load immediately after a deploy renders the previous
 * build. Watched in Chromium across a simulated deploy (see the ticket), it was
 * worse than one load -- the new worker refilled its new cache from the
 * browser's five-minute HTTP cache of /app, so loads two, three and four all
 * served the old page. That second half is fixed in the /app route, which now
 * revalidates instead of holding a window.
 *
 * Three ways to fix the first half were on the table. This file takes the third:
 *
 *   1. Network-first for the /app navigation, cache as fallback. Rejected. This
 *      page is 1.6 MB and it opens in an atrium on a stranger's wifi, which is
 *      the entire reason the worker exists. Network-first makes every launch
 *      wait on that transfer, and a timeout short enough not to hurt is too
 *      short to be reliably won on cellular. It trades a once-per-deploy defect
 *      for a once-per-launch one.
 *   2. Nothing in code, a written pre-demo step: open the app twice, check
 *      /version. Rejected. It is free and it depends on somebody remembering,
 *      which is precisely what already failed.
 *   3. Keep cache-first, and let the page correct itself. The stale document
 *      renders instantly, the browser fetches this file (served no-cache), a
 *      new worker installs, takes over, and the page reloads exactly once. The
 *      user sees the right build without knowing to ask for it, and every
 *      launch that is NOT the one after a deploy is untouched and still fast.
 *
 * The reload is in the page (tools/app_wiring/service-worker.html), guarded so
 * it can only fire for a client that already had a controller and only once per
 * document. What this file contributes is speed: skipWaiting() is called
 * immediately below rather than after the precache, so the takeover waits on
 * the browser starting this worker (~1.7 s on localhost) instead of on that
 * plus a 1.6 MB download. Whole correction, measured: about 2.9 s.
 */

const CACHE = "entrymap-__COMMIT__";
const SHELL = ["/app", "/app-icon.png", "/app-manifest.json",
  // Self-hosted since the type moved off the CDN. Without these the installed app
  // launches offline in the system font, which is the failure this all exists to stop.
  "/app-fonts/AtkinsonHyperlegibleNext-Variable.woff2",
  "/app-fonts/AtkinsonHyperlegibleNext-Italic-Variable.woff2",
  "/app-fonts/NunitoSans-ExtraBold.ttf"];

// Held so activate can wait for it without delaying the takeover. Same worker
// global as the install that assigns it; if the worker is torn down between the
// two events this stays resolved, which only means the old cache is dropped as
// promptly as it always was.
let precached = Promise.resolve();

self.addEventListener("install", (event) => {
  precached = caches
    .open(CACHE)
    .then((cache) => cache.addAll(SHELL))
    // A failed precache must not wedge the worker: the app still works online,
    // and the next launch tries again.
    .catch(() => {});
  // Before the precache, not after it (#483). Waiting for 1.6 MB to land put
  // seconds between the stale page appearing and the new worker taking over --
  // long enough for someone to start using the old build, and long enough on
  // stage to read as "it did not update". Nothing downstream needs a full
  // cache: a request that misses falls through to the network below.
  self.skipWaiting();
  event.waitUntil(precached);
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    // Claim first, delete second. Claiming is what tells the open page a new
    // build has arrived, so it happens immediately. Dropping the previous
    // shell waits for this one to be in place: between the two there would
    // otherwise be a window with the old cache gone and the new one still
    // filling, and a phone that lost signal inside it would have no app to
    // open -- which is the one thing this worker exists to prevent.
    self.clients
      .claim()
      .then(() => precached)
      .then(() => caches.keys())
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      ),
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
