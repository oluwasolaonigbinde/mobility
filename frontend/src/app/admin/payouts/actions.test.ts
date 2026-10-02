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
  expect(result.steps?.[0]).toContain("1 trip review(s)");
  expect(result.steps?.[2]).toContain("Pay status: " + label);
  expect(result.steps?.join(" ")).not.toMatch(/fraud|ledger|raw_review_code|unknown_wire_status/);
  expect(mocks.post).toHaveBeenNthCalledWith(3, "/api/v1/admin/trips/{trip_id}/calculate-payout", {
    params: { path: { trip_id: "11111111-1111-4111-8111-111111111111" } },
    body: {},
  });
});
