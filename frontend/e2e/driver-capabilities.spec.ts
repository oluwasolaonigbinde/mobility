import { expect, test, type Page } from "@playwright/test";

test("R14-A session probe fails closed without an authenticated session", async ({ browser }) => {
  // A cookieless request to the guarded probe path must never answer 200:
  // the portal guard redirects/rejects, which probeBffSession (redirect:
  // "manual") classifies as "invalid" — proving "valid" is backed by the
  // auth guard, not by a public page.
  const context = await browser.newContext();
  const response = await context.request.get("/driver/capabilities?session-probe=1", {
    maxRedirects: 0,
  });
  expect([301, 302, 303, 307, 308, 401, 403]).toContain(response.status());
  await context.close();
});

async function loginAsDriver(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("driver@demo.mobility.local");
  await page.getByLabel("Password").fill("DemoDriver12345!");
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/driver");
}

test("R14-A harness probes capabilities without requesting location on load", async ({ page }: { page: Page }) => {
  await page.addInitScript(() => {
    const probeWindow = window as typeof window & { __r14LocationCalls?: number };
    probeWindow.__r14LocationCalls = 0;

    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        query: async () => ({
          state: "granted",
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }),
      },
    });
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (
          _success: PositionCallback,
          error: PositionErrorCallback,
        ) => {
          probeWindow.__r14LocationCalls = (probeWindow.__r14LocationCalls ?? 0) + 1;
          error({ code: 1 } as GeolocationPositionError);
        },
      },
    });

    let lockHeld = false;
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: async (
          _name: string,
          _options: unknown,
          callback: (lock: object | null) => unknown,
        ) => {
          if (lockHeld) return callback(null);
          lockHeld = true;
          try {
            return await callback({});
          } finally {
            lockHeld = false;
          }
        },
      },
    });
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: {
        request: async () => ({ release: async () => undefined }),
      },
    });
  });

  await loginAsDriver(page);
  await page.goto("/driver/capabilities");
  await expect(
    page.getByRole("heading", { name: "Production PWA capability probe" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Physical Android\/iPhone journeys.*still required post-build/),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const probeWindow = window as typeof window & { __r14LocationCalls?: number };
        return probeWindow.__r14LocationCalls ?? 0;
      }),
    )
    .toBe(0);
  await expect(page.getByTestId("capability-location")).toHaveAttribute(
    "data-status",
    "degraded",
  );
  await expect(page.getByTestId("capability-location")).toContainText("LOCATION_UNPROBED");

  await page.getByRole("button", { name: "Test storage + queue" }).click();
  await expect(page.getByRole("status")).toContainText("Durable queue probe passed");

  await page.getByRole("button", { name: "Test Web Locks" }).click();
  await expect(page.getByRole("status")).toContainText("Web Locks probe passed");

  await page.getByRole("button", { name: "Test screen wake lock" }).click();
  await expect(page.getByRole("status")).toContainText("Screen Wake Lock probe passed");

  await page.getByRole("button", { name: "Test BFF session" }).click();
  await expect(page.getByRole("status")).toContainText("BFF session probe passed");

  await page.getByRole("button", { name: "Test foreground location" }).click();
  await expect(page.getByRole("status")).toContainText("location probe returned denied");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const probeWindow = window as typeof window & { __r14LocationCalls?: number };
        return probeWindow.__r14LocationCalls ?? 0;
      }),
    )
    .toBe(1);
  await expect(page.getByTestId("capability-location")).toHaveAttribute(
    "data-status",
    "rejected",
  );

  const report = page.getByTestId("capability-report");
  await expect(report).toContainText("BACKGROUND_CAPTURE_OUT_OF_SCOPE");
  await expect(report).not.toContainText("latitude");
  await expect(report).not.toContainText("longitude");
  await expect(report).not.toContainText("r14-a-synthetic-probe");
});
