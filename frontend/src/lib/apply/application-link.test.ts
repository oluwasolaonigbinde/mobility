import { afterEach, beforeEach, expect, it, vi } from "vitest";
beforeEach(() => {
  vi.resetModules();
  window.history.replaceState(null, "", "/apply");
});
afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});
it("clears the capability from the URL before it can be consumed, retaining it only once in memory", async () => {
  window.history.replaceState(
    { existing: true },
    "",
    "/apply?step=details#application_access_token=private-capability",
  );
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const fetch = vi.spyOn(window, "fetch");
  const link = await import("./application-link");
  expect(link.captureApplicationLink()).toBe(true);
  expect(window.location.href).not.toContain("private-capability");
  expect(window.location.hash).toBe("");
  expect(window.location.search).toBe("?step=details");
  expect(window.history.state).toEqual({ existing: true });
  expect(link.takeApplicationLink()).toEqual({ token: "private-capability", invalid: false });
  expect(link.takeApplicationLink()).toBeNull();
  expect(storage).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});
it.each(["", "a b", "a\nb", "a\u007fb", "a".repeat(8193)])(
  "clears and rejects an invalid capability without exposing it: %s",
  async (token) => {
    window.history.replaceState(
      null,
      "",
      `/apply#application_access_token=${encodeURIComponent(token)}`,
    );
    const link = await import("./application-link");
    expect(link.captureApplicationLink()).toBe(true);
    expect(window.location.hash).toBe("");
    expect(link.takeApplicationLink()).toEqual({ token: null, invalid: true });
  },
);
it("does not choose one of duplicate capabilities", async () => {
  window.history.replaceState(
    null,
    "",
    "/apply#application_access_token=one&application_access_token=two",
  );
  const link = await import("./application-link");
  expect(link.takeApplicationLink()).toEqual({ token: null, invalid: true });
  expect(window.location.hash).toBe("");
});
it("leaves unrelated pages alone and does not derive authority from a query step", async () => {
  window.history.replaceState(null, "", "/driver#application_access_token=private");
  const link = await import("./application-link");
  expect(link.takeApplicationLink()).toBeNull();
  expect(window.location.hash).toContain("private");
  window.history.replaceState(null, "", "/apply?step=car");
  expect(link.takeApplicationLink()).toBeNull();
});
it("fails closed when the URL cannot be cleared", async () => {
  window.history.replaceState(null, "", "/apply#application_access_token=private");
  const link = await import("./application-link");
  vi.spyOn(window.history, "replaceState").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(link.captureApplicationLink()).toBe(false);
  expect(link.takeApplicationLink()).toEqual({ token: null, invalid: true });
});
