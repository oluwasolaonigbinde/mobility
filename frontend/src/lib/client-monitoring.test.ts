import { afterEach, expect, it, vi } from "vitest";
const sentry = vi.hoisted(() => ({ init: vi.fn(), captureException: vi.fn() }));
vi.mock("@sentry/nextjs", () => sentry);
afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  vi.clearAllMocks();
});

it("does not initialize or send errors without a DSN", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const monitoring = await import("./client-monitoring");
  expect(await monitoring.initializeClientMonitoring()).toBeNull();
  await monitoring.captureClientError(new Error("private failure"));
  expect(sentry.init).not.toHaveBeenCalled();
  expect(sentry.captureException).not.toHaveBeenCalled();
});

it("loads once when configured and preserves sensitive-event scrubbing", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://public@example.invalid/1");
  const monitoring = await import("./client-monitoring");
  const error = new Error("failure");
  await Promise.all([
    monitoring.captureClientError(error),
    monitoring.initializeClientMonitoring(),
  ]);
  expect(sentry.init).toHaveBeenCalledTimes(1);
  const options = sentry.init.mock.calls[0]![0];
  expect(options).toMatchObject({ tracesSampleRate: 0, sendDefaultPii: false });
  expect(options.beforeSend({ token: "secret", message: "https://private.invalid/file" })).toEqual({
    message: "[REDACTED_URL]",
  });
  expect(sentry.captureException).toHaveBeenCalledWith(error);
});
