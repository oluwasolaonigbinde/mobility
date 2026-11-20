import { expect, it, vi } from "vitest";

const current = vi.hoisted(() => ({ user: async (): Promise<unknown> => null }));
vi.mock("@/lib/auth/current-user", () => ({ getCurrentUser: () => current.user() }));

import { feedbackNamePrefill } from "./actions";

it("prefills the signed-in name, trimmed and capped at 120 characters", async () => {
  current.user = async () => ({ user: { full_name: `  ${"A".repeat(130)}  ` } });
  expect(await feedbackNamePrefill()).toBe("A".repeat(120));
});

it("is blank when signed out", async () => {
  current.user = async () => null;
  expect(await feedbackNamePrefill()).toBe("");
});

it("is blank when the account can't be read", async () => {
  current.user = async () => {
    throw new Error("API down");
  };
  expect(await feedbackNamePrefill()).toBe("");
});
