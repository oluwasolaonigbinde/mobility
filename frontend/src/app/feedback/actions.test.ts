import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), revalidate: vi.fn() }));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("next/navigation", () => ({ unstable_rethrow: () => undefined }));
vi.mock("@/lib/env", () => ({ env: () => ({ API_BASE_URL: "http://api.test" }) }));

import { setFeedbackStatusAction } from "./actions";

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
  mocks.revalidate.mockReset();
});

it("updates a status with no password or token and refreshes the list", async () => {
  mocks.fetch.mockResolvedValue(Response.json({ id: ID, status: "resolved" }));
  await setFeedbackStatusAction(form({ id: ID, status: "resolved" }));
  expect(sent().method).toBe("PATCH");
  expect(sent().url).toBe(`http://api.test/api/v1/feedback/${ID}/status`);
  expect(sent().headers.get("authorization")).toBeNull();
  expect(sent().headers.get("x-feedback-review-token")).toBeNull();
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

it("refreshes the list after an unknown id or an outage", async () => {
  mocks.fetch.mockResolvedValueOnce(apiError(404)).mockResolvedValueOnce(apiError(503));
  await setFeedbackStatusAction(form({ id: ID, status: "resolved" }));
  await setFeedbackStatusAction(form({ id: ID, status: "opened" }));
  expect(mocks.revalidate).toHaveBeenCalledTimes(2);
});
