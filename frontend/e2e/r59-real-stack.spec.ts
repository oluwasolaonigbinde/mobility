import { chromium, expect, test as base, type BrowserContext, type Page } from "@playwright/test";
import {
  latestR59Trip,
  r59DriverTripCount,
  redisQueueDepth,
  startService,
  stopService,
  tripSnapshot,
  waitForService,
  writeReceipt,
} from "./support/r59-stack";

const test = base.extend<{ context: BrowserContext; page: Page }>({
  context: async ({}, provide, testInfo) => {
    const baseURL = process.env.PLAYWRIGHT_BASE_URL;
    if (!baseURL) throw new Error("PLAYWRIGHT_BASE_URL is required");
    const context = await chromium.launchPersistentContext(testInfo.outputPath("profile"), {
      headless: false,
      args: [`--app=${baseURL}/driver/track`],
      geolocation: { latitude: 9.03, longitude: 7.48, accuracy: 8 },
      permissions: ["geolocation"],
    });
    await provide(context);
    await context.close();
  },
  page: async ({ context }, provide) => {
    const page = context.pages()[0] ?? (await context.newPage());
    await provide(page);
  },
});

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

test("R59 real-stack release journey survives outages and converges exactly once", async ({
  context,
  page,
}) => {
  if (process.env.R59_REAL_STACK !== "1") throw new Error("R59_REAL_STACK=1 is required");

  await context.grantPermissions(["geolocation"], { origin: process.env.PLAYWRIGHT_BASE_URL });
  // Drive within the demo assignment's frozen Abuja target area; its daily
  // rate credits no distance outside that area.
  await context.setGeolocation({ latitude: 9.03, longitude: 7.48, accuracy: 8 });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: {
        request: async () => ({
          released: false,
          addEventListener: () => undefined,
          release: async () => undefined,
        }),
      },
    });
  });
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto("/login");
  await page.getByLabel("Email").fill("driver@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoDriver12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/driver");
  await page.goto("/driver/track");

  await expect
    .poll(
      () =>
        page.evaluate(async () => ({
          displayMode: window.matchMedia("(display-mode: standalone)").matches,
          serviceWorker: Boolean(await navigator.serviceWorker.getRegistration("/driver")),
          webLocks: typeof navigator.locks?.request === "function",
          indexedDb: typeof indexedDB?.open === "function",
          secureContext: window.isSecureContext,
        })),
      { timeout: 30_000 },
    )
    .toEqual({
      displayMode: true,
      serviceWorker: true,
      webLocks: true,
      indexedDb: true,
      secureContext: true,
    });

  const start = page.getByRole("button", { name: "Start trip" });
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await start.click();
  await expect(page.getByRole("button", { name: "End trip" })).toBeEnabled();

  const started = latestR59Trip();
  expect(started.status).toBe("active");
  const tripId = started.tripId;

  for (let index = 1; index <= 12; index += 1) {
    await context.setGeolocation({
      latitude: 9.03 + index * 0.00001,
      longitude: 7.48 + index * 0.00001,
      accuracy: 8,
    });
    await page.waitForTimeout(500);
  }

  await page.reload();
  await expect(page.getByRole("button", { name: "End trip" })).toBeEnabled();
  expect(latestR59Trip().tripId).toBe(tripId);

  stopService("worker");
  await waitForService("worker", "stopped");
  stopService("api");
  await waitForService("api", "stopped");
  await page.getByRole("button", { name: "End trip" }).click();
  await expect(page.getByRole("button", { name: "Check trip status" })).toBeVisible({
    timeout: 30_000,
  });
  const uncertain = tripSnapshot(tripId);
  expect(uncertain.status).toBe("active");
  expect(uncertain.manifestRoot).toBeNull();
  expect(uncertain.counts.payout).toBe(0);

  startService("api");
  await waitForService("api", "ready");
  await page.reload();
  // The outage-time End froze a durable boundary in IndexedDB, and that survives
  // the reload. The tracker deliberately keeps capture fenced and offers the
  // reconciliation affordance instead of a fresh End, so that pressing it
  // re-submits the identical frozen manifest rather than minting a new one.
  const end = page.getByRole("button", { name: "Check trip status" });
  await expect(end).toBeEnabled({ timeout: 30_000 });
  await end.click();
  await expect.poll(() => tripSnapshot(tripId).status, { timeout: 30_000 }).toBe("sealed");

  const sealed = tripSnapshot(tripId);
  expect(sealed.status).toBe("sealed");
  expect(sealed.manifestRoot).toMatch(/^[0-9a-f]{64}$/);
  expect(sealed.manifestCount).toBeGreaterThan(0);
  expect(sealed.manifestPingCount).toBeGreaterThan(0);
  expect(sealed.counts.analytics).toBe(0);
  expect(sealed.counts.payout).toBe(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "End trip" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Check trip status" })).toHaveCount(0);

  if (process.env.R59_WITHHOLD_WORKER !== "1") {
    startService("worker");
    await waitForService("worker", "ready");
  }

  await expect
    .poll(
      () => {
        const current = tripSnapshot(tripId);
        return { ...current.counts, queue: redisQueueDepth() };
      },
      { timeout: 120_000, intervals: [500, 1_000, 2_000] },
    )
    .toEqual({
      analytics: 1,
      fraud: 1,
      impression: 1,
      payout: 1,
      ledger: 1,
      workerAudit: 1,
      queue: 0,
    });

  const complete = tripSnapshot(tripId);
  expect(complete.amount).not.toBeNull();
  expect(Number(complete.amount)).toBeGreaterThan(0);
  expect(complete.currency).not.toBeNull();
  await page.goto(`/driver/earnings/trips/${tripId}`);
  await expect(page.getByRole("heading", { name: "Trip earnings" })).toBeVisible();
  const formatted = new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: complete.currency ?? "NGN",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(complete.amount));
  const earnedAmount = page
    .getByText("This trip earned", { exact: true })
    .locator("..")
    .getByText(formatted, { exact: true });
  await expect(earnedAmount).toBeVisible();
  await page.reload();
  await expect(earnedAmount).toBeVisible();

  const receiptPath = writeReceipt(complete);
  console.log(`R59_BROWSER_RECEIPT=${receiptPath}`);
});

// Read the app's real encrypted records without modifying or returning GPS data.
async function queuedEvidence(page: Page, tripId: string) {
  return page.evaluate(async (id) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("cardvert-ping-queue");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error("R59 could not read the evidence database"));
    });
    try {
      const read = <T>(store: string) =>
        new Promise<T[]>((resolve, reject) => {
          const request = db.transaction(store, "readonly").objectStore(store).getAll();
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(new Error("R59 could not read encrypted evidence"));
        });
      const [allRecords, keys] = await Promise.all([
        read<{
          storageKey: string;
          ownerDriverId: string;
          tripId: string;
          kind: string;
          iv: Uint8Array<ArrayBuffer>;
          ciphertext: ArrayBuffer;
        }>("encrypted-records"),
        read<{ id: string; key: CryptoKey }>("encryption-keys"),
      ]);
      const records = allRecords.filter((record) => record.tripId === id);
      let queuedSamples = 0;
      let recordedSamples = 0;
      const fingerprints = [];
      for (const record of records) {
        const key = keys.find((value) => value.id === record.ownerDriverId)?.key;
        if (
          !key ||
          key.extractable ||
          !record.ownerDriverId ||
          record.iv.byteLength !== 12 ||
          Object.keys(record).some(
            (name) =>
              !["storageKey", "ownerDriverId", "tripId", "kind", "iv", "ciphertext"].includes(name),
          )
        )
          throw new Error("R59 evidence is not bound encrypted storage");
        const plaintext = await crypto.subtle.decrypt(
          {
            name: "AES-GCM",
            iv: record.iv,
            additionalData: new TextEncoder().encode(
              `cardvert-driver-queue:v2:${record.ownerDriverId}:${record.kind}:${record.tripId}:${record.storageKey}`,
            ),
          },
          key,
          record.ciphertext,
        );
        const payload = JSON.parse(new TextDecoder().decode(plaintext));
        if (record.kind === "pending") queuedSamples += 1;
        if (record.kind === "batch") queuedSamples += payload.pings.length;
        if (record.kind === "meta") recordedSamples = payload.pingsRecorded;
        const digest = await crypto.subtle.digest("SHA-256", record.ciphertext);
        fingerprints.push(
          Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""),
        );
      }
      return {
        queuedSamples,
        recordedSamples,
        encryptedRecords: records.length,
        fingerprint: fingerprints.sort().join(":"),
      };
    } finally {
      db.close();
    }
  }, tripId);
}

test("R59 uncertain Start preserves offline evidence across bounded cache releases", async ({
  context,
  page,
}) => {
  if (process.env.R59_REAL_STACK !== "1") throw new Error("R59_REAL_STACK=1 is required");
  await context.addInitScript(() => {
    const state = window as typeof window & { r59Capture: { watches: number; fixes: number } };
    state.r59Capture = { watches: 0, fixes: 0 };
    const nativeWatch = navigator.geolocation.watchPosition.bind(navigator.geolocation);
    Object.defineProperty(navigator.geolocation, "watchPosition", {
      configurable: true,
      value: (
        success: PositionCallback,
        failure?: PositionErrorCallback,
        options?: PositionOptions,
      ) => {
        state.r59Capture.watches += 1;
        return nativeWatch(
          (position) => {
            state.r59Capture.fixes += 1;
            success(position);
          },
          failure,
          options,
        );
      },
    });
    // Same disclosed wake-lock stand-in as the original R59 journey; GPS is native.
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: {
        request: async () =>
          Object.assign(new EventTarget(), {
            released: false,
            release: async () => undefined,
          }),
      },
    });
  });
  const captureCounts = () =>
    page.evaluate(
      () =>
        (window as typeof window & { r59Capture: { watches: number; fixes: number } }).r59Capture,
    );
  page.on("dialog", (dialog) => void dialog.accept());
  await page.goto("/login");
  await page.getByLabel("Email").fill("driver@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoDriver12345!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/driver");
  await page.goto("/driver/track");
  const start = page.getByRole("button", { name: "Start trip", exact: true });
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await expect
    .poll(() =>
      page.evaluate(
        async () => (await navigator.serviceWorker.getRegistration("/driver"))?.active?.state,
      ),
    )
    .toBe("activated");
  const installedWorker = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration("/driver");
    return {
      secureContext: window.isSecureContext,
      scope: registration?.scope,
      scriptURL: registration?.active?.scriptURL,
      controlledBeforeNavigation: Boolean(navigator.serviceWorker.controller),
    };
  });
  // Public worker metadata only; no session, response headers or position data.
  console.log(`R59_INSTALLED_WORKER=${JSON.stringify(installedWorker)}`);
  expect(installedWorker.secureContext).toBe(true);
  expect(installedWorker.scope).toBe(new URL("/driver", page.url()).href);
  expect(installedWorker.scriptURL).toBe(
    new URL(`/driver-sw.js?release=${process.env.R59_GIT_SHA}`, page.url()).href,
  );
  // The CI profile had an active worker but this first-login document was
  // uncontrolled. Navigate with that active registration before testing fetches.
  await page.reload();
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  expect(
    await page.evaluate(() => ({
      scriptURL: navigator.serviceWorker.controller?.scriptURL,
      state: navigator.serviceWorker.controller?.state,
    })),
  ).toEqual({ scriptURL: installedWorker.scriptURL, state: "activated" });
  const beforeTrips = r59DriverTripCount();
  let startAction = "";
  let startRequests = 0;
  let tripId = "";
  let lossStage = "fetch";
  let failedLossStage = "";
  let outageFinished = false;
  await page.route("**/driver/track", async (route) => {
    const action = route.request().headers()["next-action"];
    if (route.request().method() !== "POST" || !action || (startAction && action !== startAction)) {
      await route.continue();
      return;
    }
    startRequests += 1;
    if (startAction) {
      await route.continue();
      return;
    }
    startAction = action;
    try {
      // Complete the real action and verify its committed trip before losing
      // only the browser response. No fabricated action or backend response.
      const response = await route.fetch();
      await response.body();
      if (outageFinished) {
        await route.abort("failed");
        return;
      }
      expect(response.status()).toBe(200);
      lossStage = "committed-trip";
      expect(r59DriverTripCount()).toBe(beforeTrips + 1);
      const created = latestR59Trip();
      expect(created.status).toBe("active");
      tripId = created.tripId;
      lossStage = "api-outage";
      stopService("api");
      await waitForService("api", "stopped");
      await route.abort("failed");
    } catch {
      // Do not print route.fetch errors: their call logs can contain cookies.
      failedLossStage = lossStage;
      await route.abort("failed").catch(() => undefined);
    }
  });
  const check = page.getByRole("button", { name: "Check trip status", exact: true });
  try {
    await start.click();
    await expect(check).toBeEnabled({ timeout: 30_000 });
    expect(failedLossStage, "the real Start-loss proof must complete every phase").toBe("");
    expect(tripId).toMatch(/^[0-9a-f-]{36}$/);
    for (let retry = 0; retry < 2; retry += 1) {
      // A real stopped-API lookup can take longer than the UI assertion's 5s.
      // Await its response and complete body before checking the settled UI.
      const [checked] = await Promise.all([
        page.waitForResponse((response) => {
          const request = response.request();
          const action = request.headers()["next-action"];
          const url = new URL(response.url());
          return (
            url.origin === new URL(page.url()).origin &&
            url.pathname === "/driver/track" &&
            request.method() === "POST" &&
            Boolean(action) &&
            action !== startAction
          );
        }),
        check.click(),
      ]);
      expect(checked.status()).toBe(200);
      const responseFinished = await checked.finished().then(
        (error) => error === null,
        () => false,
      );
      expect(responseFinished, "the real status response must finish").toBe(true);
      await expect(check).toBeEnabled();
      expect(startRequests).toBe(1);
      expect(r59DriverTripCount()).toBe(beforeTrips + 1);
      expect(await captureCounts()).toEqual({ watches: 0, fixes: 0 });
      expect((await queuedEvidence(page, tripId)).recordedSamples).toBe(0);
      await expect(start).toHaveCount(0);
    }
  } finally {
    outageFinished = true;
    startService("api");
    await waitForService("api", "ready");
    await page.unroute("**/driver/track");
  }
  await check.click();
  const end = page.getByRole("button", { name: "End trip", exact: true });
  await expect(end).toBeEnabled();
  await expect.poll(async () => (await captureCounts()).watches).toBe(1);
  expect(startRequests).toBe(1);
  expect(latestR59Trip().tripId).toBe(tripId);
  expect(r59DriverTripCount()).toBe(beforeTrips + 1);

  const bounded = await page.evaluate(async () => {
    const assets = performance
      .getEntriesByType("resource")
      .map((entry) => new URL(entry.name))
      .filter((url) => url.origin === location.origin && url.pathname.startsWith("/_next/static/"));
    const asset = assets.find((url) => url.pathname.endsWith(".css")) ?? assets[0];
    if (!asset) throw new Error("R59 has no real production static asset");
    const urls: string[] = [];
    // Distinct requests for an existing real immutable asset, not fake routes.
    for (let index = 0; index < 70; index += 1) {
      const url = new URL(asset);
      url.searchParams.set("r59-bound", String(index));
      urls.push(url.href);
      const response = await fetch(url);
      if (!response.ok) throw new Error("R59 real static asset fetch failed");
      await response.arrayBuffer();
    }
    const names = (await caches.keys()).filter((name) => name.startsWith("cardvert-driver-"));
    if (names.length !== 1 || !names[0]) throw new Error("R59 static release cache is ambiguous");
    const cache = await caches.open(names[0]);
    const oldest = urls[0],
      newest = urls[69];
    if (!oldest || !newest) throw new Error("R59 cache requests were incomplete");
    return {
      name: names[0],
      entries: (await cache.keys()).length,
      oldestRetained: Boolean(await cache.match(oldest)),
      newestRetained: Boolean(await cache.match(newest)),
      asset: asset.href,
      newest,
    };
  });
  expect(bounded.entries).toBe(64);
  expect(bounded.oldestRetained).toBe(false);
  expect(bounded.newestRetained).toBe(true);

  try {
    const beforeOffline = (await queuedEvidence(page, tripId)).recordedSamples;
    await context.setOffline(true);
    expect(await page.evaluate(async (url) => (await fetch(url)).ok, bounded.newest)).toBe(true);
    for (let index = 1; index <= 4; index += 1) {
      await context.setGeolocation({
        latitude: 9.03 + index * 0.00001,
        longitude: 7.48 + index * 0.00001,
        accuracy: 8,
      });
      await expect
        .poll(async () => (await queuedEvidence(page, tripId)).recordedSamples)
        .toBeGreaterThanOrEqual(beforeOffline + index);
    }
    await expect(page.getByTestId("tracking-health")).toHaveText("Saved on this phone");
    const offlineNavigation = await page.goto("/driver/earnings");
    expect(offlineNavigation?.status()).toBe(503);
    expect(offlineNavigation?.headers()["cache-control"]).toBe("no-store");
    await expect(page.getByText(/This offline page is not tracking your location/)).toBeVisible();
    const preserved = await queuedEvidence(page, tripId);
    expect(preserved.queuedSamples).toBeGreaterThanOrEqual(4);
    expect(preserved.encryptedRecords).toBeGreaterThan(0);
    await context.setOffline(false);

    const nextRelease = "r59-browser-next";
    await page.evaluate(async (release) => {
      const unrelated = await caches.open("r59-unrelated");
      await unrelated.put("/r59-unrelated-marker", new Response("preserve"));
      await navigator.serviceWorker.register(`/driver-sw.js?release=${release}`, {
        scope: "/driver",
        updateViaCache: "none",
      });
    }, nextRelease);
    await expect
      .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL))
      .toContain(`release=${nextRelease}`);
    const otherOrigin = new URL(bounded.asset);
    otherOrigin.hostname = otherOrigin.hostname === "127.0.0.1" ? "localhost" : "127.0.0.1";
    expect((await page.request.get(otherOrigin.href)).status()).toBe(200);
    const boundary = await page.evaluate(
      async ({ asset, other }) => {
        const staticRead = await fetch(asset);
        const auth = await fetch("/login", { credentials: "omit" });
        const keepalive = await fetch("/driver/keepalive");
        const api = await fetch("/api/notifications");
        const crossOrigin = await fetch(other, { mode: "no-cors" });
        const post = new URL(asset);
        post.searchParams.set("r59-non-get", "1");
        const nonGet = await fetch(post, { method: "POST" });
        return {
          static: staticRead.status,
          auth: auth.status,
          keepalive: keepalive.status,
          api: api.status,
          other: crossOrigin.type,
          nonGet: nonGet.status,
        };
      },
      { asset: bounded.asset, other: otherOrigin.href },
    );
    expect(boundary).toMatchObject({
      static: 200,
      auth: 200,
      keepalive: 200,
      api: 200,
      other: "opaque",
    });
    expect([404, 405]).toContain(boundary.nonGet);
    const navigation = await context.newPage();
    try {
      expect((await navigation.goto("/driver/manifest.webmanifest"))?.status()).toBe(200);
    } finally {
      await navigation.close();
    }
    const afterRelease = await page.evaluate(async () => {
      const names = await caches.keys();
      const driverNames = names.filter((name) => name.startsWith("cardvert-driver-"));
      const requests = (
        await Promise.all(driverNames.map(async (name) => (await caches.open(name)).keys()))
      ).flat();
      return {
        driverNames,
        onlySameOriginStatic: requests.every((request) => {
          const url = new URL(request.url);
          return (
            request.method === "GET" &&
            url.origin === location.origin &&
            url.pathname.startsWith("/_next/static/") &&
            !url.searchParams.has("r59-non-get")
          );
        }),
        entries: requests.length,
        unrelated: await (
          await (await caches.open("r59-unrelated")).match("/r59-unrelated-marker")
        )?.text(),
      };
    });
    expect(afterRelease.driverNames).toEqual([`cardvert-driver-static-v4-${nextRelease}`]);
    expect(afterRelease.driverNames).not.toContain(bounded.name);
    expect(afterRelease.entries).toBe(1);
    expect(afterRelease.onlySameOriginStatic).toBe(true);
    expect(afterRelease.unrelated).toBe("preserve");
    expect(await queuedEvidence(page, tripId)).toEqual(preserved);

    await page.goto("/driver/track");
    await expect(end).toBeEnabled();
    expect(latestR59Trip().tripId).toBe(tripId);
    await end.click();
    await expect.poll(() => tripSnapshot(tripId).status, { timeout: 30_000 }).toBe("sealed");
    const sealed = tripSnapshot(tripId);
    expect(sealed.manifestRoot).toMatch(/^[0-9a-f]{64}$/);
    expect(sealed.manifestPingCount).toBeGreaterThanOrEqual(preserved.recordedSamples);
    await expect
      .poll(() => tripSnapshot(tripId).counts, { timeout: 30_000 })
      .toEqual({
        analytics: 1,
        fraud: 1,
        impression: 1,
        payout: 1,
        ledger: 1,
        workerAudit: 1,
      });
    expect(r59DriverTripCount()).toBe(beforeTrips + 1);
    await expect.poll(async () => (await queuedEvidence(page, tripId)).queuedSamples).toBe(0);
  } finally {
    await context.setOffline(false);
  }
});
