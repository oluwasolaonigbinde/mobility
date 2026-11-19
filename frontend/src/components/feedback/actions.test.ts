import { beforeEach, expect, it, vi } from "vitest";

const user = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/current-user", () => ({ getCurrentUser: user }));

import { feedbackNamePrefill } from "./actions";

beforeEach(() => user.mockReset());

it("prefills the signed-in name, trimmed and capped at 120 characters", async () => {
  user.mockResolvedValue({ user: { full_name: `  ${"A".repeat(130)}  ` } });
  expect(await feedbackNamePrefill()).toBe("A".repeat(120));
});

it("is blank when signed out or when the account can't be read", async () => {
  user.mockResolvedValue(null);
  expect(await feedbackNamePrefill()).toBe("");
  user.mockRejectedValue(new Error("API down"));
  expect(await feedbackNamePrefill()).toBe("");
});
