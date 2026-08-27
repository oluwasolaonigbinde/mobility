import { devices, expect, test, type BrowserContext, type Page } from "@playwright/test";

const iphone13Device = devices["iPhone 13"];
const iphone13 = {
  userAgent: iphone13Device.userAgent,
  viewport: iphone13Device.viewport,
  deviceScaleFactor: iphone13Device.deviceScaleFactor,
  isMobile: iphone13Device.isMobile,
  hasTouch: iphone13Device.hasTouch,
};

async function installSession(context: BrowserContext, token: string) {
  await context.addCookies([
    {
      name: "mobility_session",
      value: token,
      url: "http://localhost:3000",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

async function installForegroundPwaCapabilities(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: query === "(display-mode: standalone)",
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }),
    });
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        register: async () => ({}),
        getRegistration: async () => ({}),
      },
    });
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
    const position = {
      coords: {
        latitude: 6.5244,
        longitude: 3.3792,
        accuracy: 8,
        altitude: null,
        altitudeAccuracy: null,
        heading: null,
        speed: 4,
      },
      timestamp: Date.now(),
    } as GeolocationPosition;
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (success: PositionCallback) => success(position),
        watchPosition: (success: PositionCallback) => {
          success(position);
          return 1;
        },
        clearWatch: () => undefined,
      },
    });
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: async (
          _name: string,
          _options: unknown,
          callback: (lock: object) => Promise<unknown>,
        ) => callback({}),
      },
    });
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: {
        request: async () => {
          const sentinel = new EventTarget() as EventTarget & {
            released: boolean;
            release(): Promise<void>;
          };
          sentinel.released = false;
          sentinel.release = async () => {
            sentinel.released = true;
            sentinel.dispatchEvent(new Event("release"));
          };
          return sentinel;
        },
      },
    });
  });
}

test.describe("W4-01C governed campaign journey", () => {
  test("Pixel 7 profile reaches READY, starts explicitly, and ends with durable evidence", async ({
    context,
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile-chrome", "one Android-profile journey is enough");
    await installSession(context, "w401c-ready");
    await installForegroundPwaCapabilities(page);
    page.on("dialog", (dialog) => dialog.accept());

    await page.goto("/driver/profile");
    await expect(page.getByRole("heading", { name: "Your campaign journey" })).toBeVisible();
    await expect(page.getByText("READY", { exact: true })).toBeVisible();
    await expect(page.getByText("Person & payee approved")).toBeVisible();
    await expect(page.getByText("SYN-001 approved")).toBeVisible();
    await expect(page.getByText("Campaign activated")).toBeVisible();

    await page.goto("/driver/track");
    const start = page.getByRole("button", { name: "▶ Start trip" });
    await expect(start).toBeEnabled();
    await start.click();
    await expect(page.getByRole("button", { name: "■ End trip" })).toBeEnabled();
    await expect(page.getByTestId("tracking-health")).toContainText("active");

    await page.getByRole("button", { name: "■ End trip" }).click();
    await expect(page.getByRole("button", { name: "▶ Start trip" })).toBeVisible();
  });

  test.describe("iPhone browser profile", () => {
    test.use(iphone13);

    test("degraded evidence authority is visible and cannot imply Start", async ({
      context,
      page,
    }, testInfo) => {
      test.skip(testInfo.project.name !== "chromium", "one iOS-sized browser profile is enough");
      await installSession(context, "w401c-degraded");

      await page.goto("/driver/profile");
      await expect(page.getByText("DEGRADED", { exact: true })).toBeVisible();
      await expect(page.getByText("Vehicle status unavailable")).toBeVisible();
      await page.goto("/driver/track");
      await expect(page.getByRole("button", { name: /Start trip/ })).toHaveCount(0);
      await expect(page.getByText(/could not be verified/i).first()).toBeVisible();

      await page.goto("/apply");
      await expect(
        page.getByText("Wait for admin review and invitation", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText(/never grant a session, campaign work, or tracking/i),
      ).toBeVisible();
      await expect(page.getByRole("link", { name: /already invited.*sign in/i })).toBeVisible();
    });
  });
});
