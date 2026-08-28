import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const correlationId = "w403b-abuja-pilot-001";

async function installSession(context: BrowserContext) {
  await context.addCookies([
    {
      name: "mobility_session",
      value: `w403b-driver-${correlationId}`,
      url: "http://localhost:3000",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

async function installAbujaForegroundCapabilities(page: Page) {
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
      value: { register: async () => ({}), getRegistration: async () => ({}) },
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
        latitude: 9.0765,
        longitude: 7.3986,
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

test("W4-03B Abuja PWA records only synthetic screen-on GPS evidence", async ({
  context,
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chrome", "one Android-profile proof is enough");
  await installSession(context);
  await installAbujaForegroundCapabilities(page);
  page.on("dialog", (dialog) => dialog.accept());

  await page.goto("/driver/profile");
  await expect(page.getByText(`Synthetic Abuja Campaign · ${correlationId}`)).toBeVisible();
  await page.goto("/driver/track");
  await page.getByRole("button", { name: "▶ Start trip" }).click();
  await expect(page.getByTestId("tracking-health")).toContainText("active");
  await page.getByRole("button", { name: "■ End trip" }).click();
  await expect(page.getByRole("button", { name: "▶ Start trip" })).toBeVisible();

  await expect
    .poll(async () => {
      const response = await request.get("http://127.0.0.1:38100/__test__/state");
      return response.json();
    })
    .toMatchObject({
      correlation_id: correlationId,
      city: "Abuja",
      identities: [
        "w403b-advertiser@cardvert.invalid",
        "w403b-admin@cardvert.invalid",
        "w403b-driver@cardvert.invalid",
      ],
      trip_status: "sealed",
      synthetic_ping_batches: 1,
      live_gps_claims: 0,
      live_report_issuances: 0,
      live_payout_submissions: 0,
      live_ad_activations: 0,
    });
  const finalResponse = await request.get("http://127.0.0.1:38100/__test__/state");
  console.log(`W403B_BROWSER_RECEIPT=${JSON.stringify(await finalResponse.json())}`);
});
