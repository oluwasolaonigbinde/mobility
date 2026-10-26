import { beforeEach, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  window.history.replaceState(null, "", "/advertiser-invite");
});

it("removes the fragment before monitoring and retains the bearer only in page memory", async () => {
  window.history.replaceState(null, "", "/advertiser-invite#token=one-time-secret");
  const link = await import("./invite-link");
  expect(link.captureAdvertiserInviteLink()).toBe(true);
  expect(window.location.hash).toBe("");
  expect(link.inviteTokenSnapshot()).toBe("one-time-secret");
  expect(link.inviteServerSnapshot()).toBeNull();
});

it.each(["token=one&token=two", `token=${"x".repeat(513)}`, "token=has%20space"])(
  "rejects an invalid fragment: %s",
  async (hash) => {
    window.history.replaceState(null, "", `/advertiser-invite#${hash}`);
    const link = await import("./invite-link");
    expect(link.captureAdvertiserInviteLink()).toBe(true);
    expect(link.inviteTokenSnapshot()).toBe("");
    expect(window.location.hash).toBe("");
  },
);

it("keeps monitoring off if the fragment cannot be removed", async () => {
  window.history.replaceState(null, "", "/advertiser-invite#token=secret");
  const link = await import("./invite-link");
  const replace = vi.spyOn(window.history, "replaceState").mockImplementation(() => {
    throw new Error("unavailable");
  });
  expect(link.captureAdvertiserInviteLink()).toBe(false);
  expect(link.inviteTokenSnapshot()).toBe("");
  replace.mockRestore();
});
