import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the real Next.js app, which proxies to the FastAPI
 * backend. Start the backend first: `docker compose up -d` from the repo root
 * (plus migrations + demo seed) — see frontend/README.md.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const w401cSynthetic = process.env.W401C_SYNTHETIC === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 7"] } },
  ],
  // When PLAYWRIGHT_BASE_URL points at an already-running dev server
  // (e.g. autoPort moved it off 3000), reuse it instead of spawning one.
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : w401cSynthetic
      ? [
          {
            command: "node e2e/support/w401c-mock-api.mjs",
            url: "http://127.0.0.1:38100/health",
            reuseExistingServer: false,
            timeout: 30_000,
          },
          {
            command: "API_BASE_URL=http://127.0.0.1:38100 npm run dev",
            url: baseURL,
            reuseExistingServer: false,
            timeout: 120_000,
          },
        ]
      : {
          command: "npm run dev",
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
});
