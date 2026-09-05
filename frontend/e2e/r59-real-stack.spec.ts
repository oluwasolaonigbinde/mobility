import { chromium, expect, test as base, type BrowserContext, type Page } from "@playwright/test";
import {
  latestR59Trip,
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
      geolocation: { latitude: 6.5244, longitude: 3.3792, accuracy: 8 },
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
  await context.setGeolocation({ latitude: 6.5244, longitude: 3.3792, accuracy: 8 });
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
  await page.getByRole("button", { name: "Enter the network" }).click();
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

  const start = page.getByRole("button", { name: "▶ Start trip" });
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await start.click();
  await expect(page.getByRole("button", { name: "■ End trip" })).toBeEnabled();

  const started = latestR59Trip();
  expect(started.status).toBe("active");
  const tripId = started.tripId;

  for (let index = 1; index <= 12; index += 1) {
    await context.setGeolocation({
      latitude: 6.5244 + index * 0.00001,
      longitude: 3.3792 + index * 0.00001,
      accuracy: 8,
    });
    await page.waitForTimeout(500);
  }

  await page.reload();
  await expect(page.getByRole("button", { name: "■ End trip" })).toBeEnabled();
  expect(latestR59Trip().tripId).toBe(tripId);

  stopService("worker");
  await waitForService("worker", "stopped");
  stopService("api");
  await waitForService("api", "stopped");
  await page.getByRole("button", { name: "■ End trip" }).click();
  await expect(page.getByRole("button", { name: "Reconcile trip" })).toBeVisible({
    timeout: 30_000,
  });
  const uncertain = tripSnapshot(tripId);
  expect(uncertain.status).toBe("active");
  expect(uncertain.manifestRoot).toBeNull();
  expect(uncertain.counts.payout).toBe(0);

  startService("api");
  await waitForService("api", "ready");
  await page.reload();
  const end = page.getByRole("button", { name: "■ End trip" });
  await expect(end).toBeEnabled({ timeout: 30_000 });
  await end.click();
  await expect
    .poll(() => tripSnapshot(tripId).status, { timeout: 30_000 })
    .toBe("sealed");

  const sealed = tripSnapshot(tripId);
  expect(sealed.status).toBe("sealed");
  expect(sealed.manifestRoot).toMatch(/^[0-9a-f]{64}$/);
  expect(sealed.manifestCount).toBeGreaterThan(0);
  expect(sealed.manifestPingCount).toBeGreaterThan(0);
  expect(sealed.counts.analytics).toBe(0);
  expect(sealed.counts.payout).toBe(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "■ End trip" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reconcile trip" })).toHaveCount(0);

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
