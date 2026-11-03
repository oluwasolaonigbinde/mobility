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
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/driver");
}

test("R14-A harness probes capabilities without requesting location on load", async ({
  page,
}: {
  page: Page;
}) => {
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
        getCurrentPosition: (_success: PositionCallback, error: PositionErrorCallback) => {
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
  // The Phone check remains plain even with the former support query parameter.
  await page.goto("/driver/capabilities");
  await expect(page.getByRole("heading", { name: "Phone check" })).toBeVisible();
  await expect(page.getByText("LOCATION_UNPROBED")).toHaveCount(0);
  await expect(page.getByTestId("capability-report")).toHaveCount(0);
  // Location is never requested on load, only by the explicit "Check this phone" press.
  expect(
    await page.evaluate(
      () => (window as typeof window & { __r14LocationCalls?: number }).__r14LocationCalls ?? 0,
    ),
  ).toBe(0);
  await page.getByRole("button", { name: "Check this phone" }).click();
  await expect(page.getByRole("button", { name: "Check again" })).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as typeof window & { __r14LocationCalls?: number }).__r14LocationCalls ?? 0,
    ),
  ).toBe(1);
  await expect(page.getByRole("button", { name: "Copy for support" })).toBeVisible();
  await page.goto("/driver/capabilities?view=support");
  await expect(page.getByRole("heading", { name: "Phone check" })).toBeVisible();
  await expect(page.getByText("Production PWA capability probe")).toHaveCount(0);
  await expect(page.getByTestId("capability-report")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => (window as typeof window & { __r14LocationCalls?: number }).__r14LocationCalls ?? 0,
    ),
  ).toBe(0);
  await page.getByRole("button", { name: "Check this phone" }).click();
  await expect(page.getByRole("button", { name: "Check again" })).toBeVisible();
  await expect(
    page.getByText("Allow location for Cardvert in your phone settings, then check again."),
  ).toBeVisible();
  await expect(page.getByTestId("capability-report")).toHaveCount(0);
});
