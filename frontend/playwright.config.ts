import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the real Next.js app, which proxies to the FastAPI
 * backend. Start the backend first: `docker compose up -d` from the repo root
 * (plus migrations + demo seed) — see frontend/README.md.
 */
// UI-only synthetic rehearsal modes. They do not provide real-stack release authority.
const w403bSynthetic = process.env.W403B_SYNTHETIC === "1";
const w401cSynthetic = process.env.W401C_SYNTHETIC === "1" || w403bSynthetic;
const w401dSynthetic = process.env.W401D_SYNTHETIC === "1";
const r59RealStack = process.env.R59_REAL_STACK === "1";
const baseURL =
  process.env.PLAYWRIGHT_BASE_URL ??
  (w401dSynthetic ? "http://127.0.0.1:34101" : "http://localhost:3000");

export default defineConfig({
  testDir: "./e2e",
  outputDir: r59RealStack ? "test-results/r59-real-stack/playwright" : undefined,
  fullyParallel: !r59RealStack,
  forbidOnly: !!process.env.CI,
  retries: r59RealStack ? 0 : process.env.CI ? 2 : 0,
  workers: r59RealStack ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    ignoreHTTPSErrors: process.env.PLAYWRIGHT_IGNORE_HTTPS_ERRORS === "1",
    launchOptions:
      process.env.PLAYWRIGHT_IGNORE_HTTPS_ERRORS === "1"
        ? { args: ["--ignore-certificate-errors"] }
        : undefined,
    trace: r59RealStack ? "retain-on-failure" : "on-first-retry",
  },
  projects: r59RealStack
    ? [
        {
          name: "r59-chromium",
          use: { ...devices["Desktop Chrome"] },
        },
      ]
    : w401dSynthetic
      ? [
          { name: "chromium", use: { ...devices["Desktop Chrome"] } },
          { name: "mobile-webkit", use: { ...devices["iPhone 13"] } },
        ]
      : [
          { name: "chromium", use: { ...devices["Desktop Chrome"] } },
          { name: "mobile-chrome", use: { ...devices["Pixel 7"] } },
        ],
  // When PLAYWRIGHT_BASE_URL points at an already-running dev server
  // (e.g. autoPort moved it off 3000), reuse it instead of spawning one.
  webServer: r59RealStack
    ? undefined
    : process.env.PLAYWRIGHT_BASE_URL
      ? undefined
      : w401dSynthetic
        ? [
            {
              command: "node e2e/support/w401d-mock-api.mjs",
              url: "http://127.0.0.1:38101/health",
              reuseExistingServer: false,
              timeout: 30_000,
            },
            {
              command:
                "API_BASE_URL=http://127.0.0.1:38101 npm run build && cp -R public .next/standalone/public && mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/static && API_BASE_URL=http://127.0.0.1:38101 PORT=34101 HOSTNAME=127.0.0.1 node .next/standalone/server.js",
              url: baseURL,
              reuseExistingServer: false,
              timeout: 180_000,
            },
          ]
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
