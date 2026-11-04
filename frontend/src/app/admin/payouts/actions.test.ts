import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ post: vi.fn(), revalidate: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
import { processTripAction } from "./actions";
beforeEach(() => {
  vi.resetAllMocks();
});
it.each([
  ["paid", "Paid"],
  ["unknown_wire_status", "Unknown status"],
  [undefined, "Not recorded"],
])("uses staff pay status for %s without exposing raw codes", async (status, label) => {
  mocks.post
    .mockResolvedValueOnce({
      data: {
        valid_ping_count: 2,
        ping_count: 3,
        distance_m: 1000,
        quality_score: 90,
        fraud_flags: ["raw_review_code"],
      },
    })
    .mockResolvedValueOnce({ data: { estimated_impressions: "120.00", confidence_score: 80 } })
    .mockResolvedValueOnce({
      data: { final_payout: "123.45", currency: "NGN", ledger_entry: status ? { status } : null },
    });
  const form = new FormData();
  form.set("trip_id", "11111111-1111-4111-8111-111111111111");
  const result = await processTripAction({}, form);
  expect(result.error).toBeUndefined();
  expect(result.steps).toHaveLength(3);
  expect(result.steps?.[0]).toBe("Trip recalculated: 0.6 miles");
  expect(result.steps?.[2]).toContain("Status: " + label);
  expect(result.steps?.join(" ")).not.toMatch(/fraud|ledger|raw_review_code|unknown_wire_status/);
  expect(mocks.post).toHaveBeenNthCalledWith(3, "/api/v1/admin/trips/{trip_id}/calculate-payout", {
    params: { path: { trip_id: "11111111-1111-4111-8111-111111111111" } },
    body: {},
  });
});

import { ApiError } from "@/lib/api/errors";
it.each([0, 1, 2])("reports only completed work when payout step %s fails", async (failedStep) => {
  const completed = ["Trip recalculated: 1.0 miles", "Estimated views: 120"];
  const replies = [{ data: { distance_m: 1609.344 } }, { data: { estimated_impressions: "120" } }];
  for (const reply of replies.slice(0, failedStep)) mocks.post.mockResolvedValueOnce(reply);
  mocks.post.mockRejectedValueOnce(
    new ApiError(409, { code: "PAY_NOT_ALLOWED", message: "private ledger detail" }),
  );
  const form = new FormData();
  form.set("trip_id", "11111111-1111-4111-8111-111111111111");
  const result = await processTripAction({}, form);
  expect(result.steps).toEqual(completed.slice(0, failedStep));
  expect(result.error).toBe(
    "That didn't work. Please try again." +
      (failedStep ? ` (completed: ${completed.slice(0, failedStep).join(" · ")})` : ""),
  );
  expect(mocks.post).toHaveBeenCalledTimes(failedStep + 1);
  expect(mocks.revalidate).not.toHaveBeenCalled();
});
it("reports a connection failure without claiming pay was calculated", async () => {
  mocks.post.mockRejectedValue(new Error("private network data"));
  const form = new FormData();
  form.set("trip_id", "11111111-1111-4111-8111-111111111111");
  expect(await processTripAction({}, form)).toEqual({
    error: "Could not reach the server. Try again.",
    steps: [],
  });
  expect(mocks.revalidate).not.toHaveBeenCalled();
});
it.each([undefined, "not-a-trip"])("refuses invalid trip %s before recalculating", async (id) => {
  const form = new FormData();
  if (id) form.set("trip_id", id);
  expect((await processTripAction({}, form)).error).toBe("Enter a valid trip ID");
  expect(mocks.post).not.toHaveBeenCalled();
});
