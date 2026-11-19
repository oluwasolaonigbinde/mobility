import { expect, it, vi } from "vitest";
import { orderTransitionAction } from "./actions";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

it("sends a correction release time entered in Nigeria as the corresponding UTC instant", async () => {
  const id = "00000000-0000-4000-8000-000000000001";
  const form = new FormData();
  form.set("order_id", id);
  form.set("reason", "Approve verified correction");
  form.set("release_at", "2026-11-19T00:00");
  await orderTransitionAction({}, form);
  expect(post).toHaveBeenCalledWith("/api/v1/admin/payouts/correction-orders/{order_id}/approve", {
    params: { path: { order_id: id } },
    body: { reason: "Approve verified correction", release_at: "2026-11-18T23:00:00.000Z" },
  });
});
