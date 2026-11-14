import { beforeEach, describe, expect, it, vi } from "vitest";

type Links = typeof import("./invite-link");
const pages = [
  ["advertiserInviteLink", "/advertiser-invite"],
  ["passwordResetLink", "/reset-password"],
  ["driverAccountSetupLink", "/driver-account-setup"],
] as const;

beforeEach(() => {
  vi.resetModules();
  window.history.replaceState(null, "", "/");
});

describe.each(pages)("%s (%s)", (name, path) => {
  const load = async () => ((await import("./invite-link")) as Links)[name];

  it("removes the fragment before monitoring and retains the bearer only in page memory", async () => {
    window.history.replaceState(null, "", `${path}?keep=1#token=one-time-secret`);
    const link = await load();
    expect(link.capture()).toBe(true);
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("?keep=1");
    expect(link.snapshot()).toBe("one-time-secret");
    expect(link.serverSnapshot()).toBeNull();
  });

  it.each(["token=one&token=two", `token=${"x".repeat(513)}`, "token=has%20space", "token="])(
    "rejects an invalid fragment: %s",
    async (hash) => {
      window.history.replaceState(null, "", `${path}#${hash}`);
      const link = await load();
      expect(link.capture()).toBe(true);
      expect(link.snapshot()).toBe("");
      expect(window.location.hash).toBe("");
    },
  );

  it("treats a page opened without a fragment as an incomplete link", async () => {
    window.history.replaceState(null, "", path);
    const link = await load();
    expect(link.snapshot()).toBeNull();
    expect(link.capture()).toBe(true);
    expect(link.snapshot()).toBe("");
  });

  it("keeps monitoring off if the fragment cannot be removed", async () => {
    window.history.replaceState(null, "", `${path}#token=secret`);
    const link = await load();
    const replace = vi.spyOn(window.history, "replaceState").mockImplementation(() => {
      throw new Error("unavailable");
    });
    expect(link.capture()).toBe(false);
    expect(link.snapshot()).toBe("");
    replace.mockRestore();
  });

  it("captures a fragment that arrives after subscription and stops listening on cleanup", async () => {
    window.history.replaceState(null, "", path);
    const link = await load();
    const changed = vi.fn();
    const unsubscribe = link.subscribe(changed);
    expect(changed).toHaveBeenCalledTimes(1);
    expect(link.snapshot()).toBe("");
    window.history.replaceState(null, "", `${path}#token=later-secret`);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(changed).toHaveBeenCalledTimes(2);
    expect(link.snapshot()).toBe("later-secret");
    unsubscribe();
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(changed).toHaveBeenCalledTimes(2);
  });
});

it("leaves other pages' fragments alone", async () => {
  window.history.replaceState(null, "", "/apply#token=not-mine");
  const links = (await import("./invite-link")) as Links;
  for (const [name] of pages) expect(links[name].capture()).toBe(true);
  expect(window.location.hash).toBe("#token=not-mine");
  for (const [name] of pages) expect(links[name].snapshot()).toBeNull();
});
