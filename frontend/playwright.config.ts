import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the real Next.js app, which proxies to the FastAPI
 * backend. Start the backend first: `docker compose up -d` from the repo root
 * (plus migrations + demo seed) — see frontend/README.md.
 */
// Specialist modes are opt-in and mutually exclusive. Ordinary real-stack E2E
// never inherits their mock servers, deployment assumptions, or authority.
const specialistModes = [
  ["w401c", process.env.W401C_SYNTHETIC === "1"],
  ["w401d", process.env.W401D_SYNTHETIC === "1"],
  ["w403b", process.env.W403B_SYNTHETIC === "1"],
  ["r59", process.env.R59_REAL_STACK === "1"],
  ["r14", process.env.R14_SECURITY_BOUNDARY === "1"],
] as const;
const selectedModes = specialistModes.filter(([, enabled]) => enabled);
if (selectedModes.length > 1) {
  throw new Error(`Playwright specialist modes are mutually exclusive: ${selectedModes.map(([name]) => name).join(", ")}`);
}
const mode = selectedModes[0]?.[0] ?? "ordinary";
const w401cMockServer = mode === "w401c" || mode === "w403b";
const w401dSynthetic = mode === "w401d";
const r59RealStack = mode === "r59";
const r14SecurityBoundary = mode === "r14";
const specialistSpecs = [
  "**/r59-real-stack.spec.ts",
  "**/security-boundary.spec.ts",
  "**/w401c-campaign-journey.spec.ts",
  "**/w401d-release-rehearsal.spec.ts",
  "**/w403b-synthetic-pilot-journey.spec.ts",
];
const specialistSpecByMode = {
  w401c: "**/w401c-campaign-journey.spec.ts",
  w401d: "**/w401d-release-rehearsal.spec.ts",
  w403b: "**/w403b-synthetic-pilot-journey.spec.ts",
  r59: "**/r59-real-stack.spec.ts",
  r14: "**/security-boundary.spec.ts",
} as const;
const baseURL =
  process.env.PLAYWRIGHT_BASE_URL ??
  (w401dSynthetic ? "http://127.0.0.1:34101" : "http://localhost:3000");

export default defineConfig({
  testDir: "./e2e",
  testMatch: mode === "ordinary" ? undefined : specialistSpecByMode[mode],
  testIgnore: mode === "ordinary" ? specialistSpecs : undefined,
  outputDir: r59RealStack ? "test-results/r59-real-stack/playwright" : undefined,
  fullyParallel: mode !== "ordinary" && !r59RealStack,
  forbidOnly: !!process.env.CI,
  retries: r59RealStack ? 0 : process.env.CI ? 2 : 0,
  workers: mode === "ordinary" || r59RealStack ? 1 : undefined,
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
  webServer: r59RealStack || r14SecurityBoundary
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
        : w401cMockServer
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
