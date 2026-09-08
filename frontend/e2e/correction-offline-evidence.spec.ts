import { expect, test, type Page } from "@playwright/test";

test.skip(process.env.P07_SYNTHETIC !== "1", "requires the bounded local P07 fault fixture");
test.describe.configure({ mode: "default" });
test.use({ trace: "retain-on-failure" });

async function prepare(page: Page, samples = 1) {
  await page.context().addCookies([
    {
      name: "mobility_session",
      value: "w403b-driver-w403b-abuja-pilot-001",
      url: "http://localhost:3000",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await page.addInitScript(
    ({ samples }) => {
      const state = window as typeof window & {
        p07: {
          watches: number;
          callback?: PositionCallback;
          deferResume: boolean;
          resume?: () => void;
        };
      };
      state.p07 = { watches: 0, deferResume: false };
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        value: (media: string) => ({
          matches: media === "(display-mode: standalone)",
          media,
          addEventListener() {},
          removeEventListener() {},
        }),
      });
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {
          register: async () => ({}),
          getRegistration: () =>
            state.p07.deferResume
              ? new Promise((resolve) => {
                  state.p07.resume = () => resolve({});
                })
              : Promise.resolve({}),
        },
      });
      Object.defineProperty(navigator, "permissions", {
        configurable: true,
        value: {
          query: async () => ({
            state: "granted",
            addEventListener() {},
            removeEventListener() {},
          }),
        },
      });
      const position = () =>
        ({
          coords: {
            latitude: 9.0765,
            longitude: 7.3986,
            accuracy: 8,
            altitude: null,
            altitudeAccuracy: null,
            heading: 360,
            speed: 4,
          },
          timestamp: Date.now(),
        }) as GeolocationPosition;
      Object.defineProperty(navigator, "geolocation", {
        configurable: true,
        value: {
          getCurrentPosition: (success: PositionCallback) => success(position()),
          watchPosition: (success: PositionCallback) => {
            state.p07.watches += 1;
            state.p07.callback = success;
            for (let i = 0; i < samples; i++) success(position());
            return state.p07.watches;
          },
          clearWatch() {},
        },
      });
      Object.defineProperty(navigator, "wakeLock", {
        configurable: true,
        value: {
          request: async () =>
            Object.assign(new EventTarget(), { released: false, release: async () => {} }),
        },
      });
      // The real browser's Web Lock, IndexedDB, WebCrypto and network remain in use.
    },
    { samples },
  );
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/driver/track");
  await page.getByRole("button", { name: "▶ Start trip" }).click();
  await expect(page.getByTestId("tracking-health")).toHaveText("active");
}

test("lost End response drains the current deferred batch before reconciliation", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:38100/__test__/p07", { data: { scenario: "deferred_end" } });
  await prepare(page);
  await page.getByRole("button", { name: "■ End trip" }).click();
  await expect(page.getByRole("button", { name: "▶ Start trip" })).toBeVisible();
  const state = await (await request.get("http://127.0.0.1:38100/__test__/p07")).json();
  expect(state.status).toBe("sealed");
  expect(state.pingAttempts).toBe(2);
  expect(state.ends).toHaveLength(1);
  expect(state.ends[0].evidence_manifest.ping_count).toBe(1);
});

test("visibility completion and late GPS callbacks cannot cross the frozen End", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:38100/__test__/p07", { data: { scenario: "hold_end" } });
  await prepare(page);
  await page.evaluate(() => {
    const state = window as typeof window & { p07: { deferResume: boolean } };
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
    state.p07.deferResume = true;
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForFunction(() =>
    Boolean((window as unknown as { p07: { resume?: () => void } }).p07.resume),
  );
  await page.getByRole("button", { name: "■ End trip" }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get("http://127.0.0.1:38100/__test__/p07")).json()).ends.length,
    )
    .toBe(1);
  await page.evaluate(() => {
    const state = (window as unknown as { p07: { resume: () => void; callback: PositionCallback } })
      .p07;
    state.resume();
    state.callback({
      coords: { latitude: 9, longitude: 7, accuracy: 8, speed: 4, heading: 90 },
      timestamp: Date.now(),
    } as GeolocationPosition);
  });
  expect(
    await page.evaluate(() => (window as unknown as { p07: { watches: number } }).p07.watches),
  ).toBe(1);
  await request.post("http://127.0.0.1:38100/__test__/p07", { data: { release: true } });
  await expect(page.getByRole("button", { name: "▶ Start trip" })).toBeVisible();
});

test("partial acknowledgement remains encrypted and settled across reload", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:38100/__test__/p07", { data: { scenario: "partial_ack" } });
  await prepare(page, 3);
  await page.getByRole("button", { name: "■ End trip" }).click();
  await expect(page.getByRole("button", { name: "▶ Start trip" })).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "GPS samples need review" }),
  ).toContainText("GPS samples need review");
  const state = await (await request.get("http://127.0.0.1:38100/__test__/p07")).json();
  expect(state.pingAttempts).toBe(1);
  expect(state.ends[0].evidence_manifest.complete).toBe(false);
  const receipt = await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("cardvert-ping-queue");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const read = <T>(store: string) =>
      new Promise<T[]>((resolve, reject) => {
        const request = db.transaction(store, "readonly").objectStore(store).getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    const records = await read<{
      kind: string;
      ownerDriverId: string;
      storageKey: string;
      tripId: string;
      iv: Uint8Array<ArrayBuffer>;
      ciphertext: ArrayBuffer;
    }>("encrypted-records");
    const record = records.find((row) => row.kind === "receipt")!;
    if (!record || "sampleResults" in record) throw new Error("receipt is absent or plaintext");
    const key = (await read<{ id: string; key: CryptoKey }>("encryption-keys")).find(
      (row) => row.id === record.ownerDriverId,
    )!.key;
    const bytes = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: record.iv,
        additionalData: new TextEncoder().encode(
          `cardvert-driver-queue:v2:${record.ownerDriverId}:receipt:${record.tripId}:${record.storageKey}`,
        ),
      },
      key,
      record.ciphertext,
    );
    db.close();
    return JSON.parse(new TextDecoder().decode(bytes));
  });
  await page.screenshot({ path: "test-results/correction-p07-partial.png", fullPage: true });
  expect(receipt.acceptedCount).toBe(2);
  expect(receipt.rejectedCount).toBe(1);
  expect(receipt.sampleResults[2]).toMatchObject({
    status: "rejected",
    rejection_code: "INVALID_SPEED",
  });
});
