import { afterEach, beforeEach, expect, it, vi } from "vitest";

const store = vi.hoisted(() => ({ get: vi.fn(), set: vi.fn(), delete: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => store }));

import {
  FEEDBACK_REVIEW_COOKIE,
  clearReviewToken,
  getReviewToken,
  setReviewToken,
} from "./review-cookie";

const NOW = Date.parse("2026-11-19T12:00:00Z");
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  store.get.mockReset();
  store.set.mockReset();
  store.delete.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

const options = () => store.set.mock.calls[0]![2];

it("stores the token httpOnly, Lax and site-wide, Secure in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  await setReviewToken("tok", "2026-11-19T18:00:00Z");
  expect(store.set).toHaveBeenCalledWith(FEEDBACK_REVIEW_COOKIE, "tok", expect.any(Object));
  expect(options()).toEqual({
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 6 * 3600,
  });
});

it("is not Secure outside production and never lives past 12 hours", async () => {
  vi.stubEnv("NODE_ENV", "development");
  await setReviewToken("tok", "2026-11-21T12:00:00Z");
  expect(options()).toMatchObject({ secure: false, maxAge: 12 * 3600 });
});

it("falls back to 12 hours for an unreadable expiry and to 0 for a past one", async () => {
  await setReviewToken("tok", "not a date");
  expect(options().maxAge).toBe(12 * 3600);
  store.set.mockReset();
  await setReviewToken("tok", "2026-11-19T11:00:00Z");
  expect(options().maxAge).toBe(0);
});

it("reads and clears the token, treating an empty value as missing", async () => {
  store.get.mockReturnValueOnce({ value: "tok" }).mockReturnValueOnce({ value: "" });
  expect(await getReviewToken()).toBe("tok");
  expect(await getReviewToken()).toBeUndefined();
  await clearReviewToken();
  expect(store.delete).toHaveBeenCalledWith(FEEDBACK_REVIEW_COOKIE);
});
