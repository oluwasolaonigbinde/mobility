import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  token: vi.fn(),
  set: vi.fn(),
  clear: vi.fn(),
  revalidate: vi.fn(),
  headers: new Headers({ "x-client-ip": "203.0.113.5" }),
}));
vi.mock("next/headers", () => ({ headers: async () => mocks.headers }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("next/navigation", () => {
  class Redirect extends Error {}
  return {
    redirect: (path: string) => {
      throw new Redirect(`redirect:${path}`);
    },
    unstable_rethrow: (error: unknown) => {
      if (error instanceof Redirect) throw error;
    },
  };
});
vi.mock("@/lib/env", () => ({
  env: () => ({ API_BASE_URL: "http://api.test", LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: true }),
}));
vi.mock("./review-cookie", () => ({
  getReviewToken: mocks.token,
  setReviewToken: mocks.set,
  clearReviewToken: mocks.clear,
}));

import { setFeedbackStatusAction, unlockFeedbackAction } from "./actions";

const ID = "10000000-0000-4000-8000-000000000001";
const form = (values: Record<string, string>) => {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
};
const apiError = (status: number) =>
  Response.json({ error: { code: "X", message: "x", details: {} } }, { status });
const sent = () => mocks.fetch.mock.calls[0]![0] as Request;

beforeEach(() => {
  mocks.fetch.mockReset();
  vi.stubGlobal("fetch", mocks.fetch);
  mocks.token.mockReset().mockResolvedValue("review-token");
  mocks.set.mockReset();
  mocks.clear.mockReset();
  mocks.revalidate.mockReset();
});

it("unlocks with the relayed IP, stores the token, and opens the list", async () => {
  mocks.fetch.mockResolvedValue(
    Response.json({ token: "signed", expires_at: "2026-11-20T06:00:00Z" }),
  );
  await expect(unlockFeedbackAction({}, form({ password: "correct horse" }))).rejects.toThrow(
    "redirect:/feedback",
  );
  expect(sent().url).toBe("http://api.test/api/v1/feedback/review/unlock");
  expect(sent().headers.get("x-client-ip")).toBe("203.0.113.5");
  expect(await sent().json()).toEqual({ password: "correct horse" });
  expect(mocks.set).toHaveBeenCalledWith("signed", "2026-11-20T06:00:00Z");
});

it.each([
  [401, "That password did not match."],
  [429, "Too many attempts. Try again in a few minutes."],
  [404, "Feedback isn't switched on for this site."],
  [503, "Feedback is unavailable right now. Try again."],
])("maps an unlock %s to the gate copy without storing a token", async (status, error) => {
  mocks.fetch.mockResolvedValue(apiError(status));
  expect(await unlockFeedbackAction({}, form({ password: "guess" }))).toEqual({ error });
  expect(mocks.set).not.toHaveBeenCalled();
});

it("refuses an empty password without calling the API, and survives a network failure", async () => {
  expect(await unlockFeedbackAction({}, form({}))).toEqual({ error: "Enter the password." });
  expect(mocks.fetch).not.toHaveBeenCalled();
  mocks.fetch.mockRejectedValue(new TypeError("fetch failed"));
  expect(await unlockFeedbackAction({}, form({ password: "x" }))).toEqual({
    error: "Feedback is unavailable right now. Try again.",
  });
});

it("updates a status with the token in a header and refreshes the list", async () => {
  mocks.fetch.mockResolvedValue(Response.json({ id: ID, status: "resolved" }));
  await setFeedbackStatusAction(form({ id: ID, status: "resolved" }));
  expect(sent().method).toBe("PATCH");
  expect(sent().url).toBe(`http://api.test/api/v1/feedback/${ID}/status`);
  expect(sent().url).not.toContain("review-token");
  expect(sent().headers.get("x-feedback-review-token")).toBe("review-token");
  expect(await sent().json()).toEqual({ status: "resolved" });
  expect(mocks.revalidate).toHaveBeenCalledWith("/feedback");
});

it.each([
  { id: "not-a-uuid", status: "resolved" },
  { id: ID, status: "deleted" },
])("ignores a bad status request %j", async (values) => {
  await setFeedbackStatusAction(form(values));
  expect(mocks.fetch).not.toHaveBeenCalled();
  expect(mocks.revalidate).not.toHaveBeenCalled();
});

it("sends a reviewer without a token back to the gate", async () => {
  mocks.token.mockResolvedValue(undefined);
  await expect(setFeedbackStatusAction(form({ id: ID, status: "opened" }))).rejects.toThrow(
    "redirect:/feedback",
  );
  expect(mocks.fetch).not.toHaveBeenCalled();
});

it("clears an expired token and returns to the gate on 401", async () => {
  mocks.fetch.mockResolvedValue(apiError(401));
  await expect(setFeedbackStatusAction(form({ id: ID, status: "opened" }))).rejects.toThrow(
    "redirect:/feedback",
  );
  expect(mocks.clear).toHaveBeenCalled();
  expect(mocks.revalidate).not.toHaveBeenCalled();
});

it("keeps the cookie and refreshes the list after an unknown id or outage", async () => {
  mocks.fetch.mockResolvedValueOnce(apiError(404)).mockResolvedValueOnce(apiError(503));
  await setFeedbackStatusAction(form({ id: ID, status: "resolved" }));
  await setFeedbackStatusAction(form({ id: ID, status: "resolved" }));
  expect(mocks.clear).not.toHaveBeenCalled();
  expect(mocks.revalidate).toHaveBeenCalledTimes(2);
});
