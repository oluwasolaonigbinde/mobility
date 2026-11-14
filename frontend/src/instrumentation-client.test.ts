import { afterEach, expect, it, vi } from "vitest";
const initialized = vi.hoisted(() => vi.fn());
vi.mock("@/lib/client-monitoring", () => ({ initializeClientMonitoring: initialized }));
afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  initialized.mockReset();
  window.history.replaceState(null, "", "/");
});
it.each([
  "/apply?step=details#application_access_token=secret",
  "/advertiser-invite#token=secret",
  "/reset-password#token=secret",
  "/driver-account-setup#token=secret",
])("removes the secret from %s before monitoring initializes", async (url) => {
  window.history.replaceState(null, "", url);
  initialized.mockImplementation(() => {
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("secret");
  });
  await import("./instrumentation-client");
  expect(initialized).toHaveBeenCalledTimes(1);
});
it.each(["/apply#application_access_token=secret", "/reset-password#token=secret"])(
  "does not initialize monitoring when fragment clearing fails on %s",
  async (url) => {
    window.history.replaceState(null, "", url);
    vi.spyOn(window.history, "replaceState").mockImplementation(() => {
      throw new Error("blocked");
    });
    await import("./instrumentation-client");
    expect(initialized).not.toHaveBeenCalled();
  },
);
