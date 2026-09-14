import { beforeEach, describe, expect, it, vi } from "vitest";
import { batchApi } from "./batch-api";
const mocks = vi.hoisted(() => ({ token: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/env", () => ({ env: () => ({ API_BASE_URL: "http://backend.test" }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));

describe("payout server reads", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal("fetch", mocks.fetch);
    mocks.token.mockResolvedValue("server-cookie-token");
  });

  it("uses the server session and never caches a money projection", async () => {
    mocks.fetch.mockResolvedValue(Response.json({ amount: "100.07" }));
    expect(await batchApi("/eligible")).toEqual({ amount: "100.07" });
    expect(mocks.fetch).toHaveBeenCalledWith(
      "http://backend.test/api/v1/admin/payout-batches/eligible",
      {
        cache: "no-store",
        headers: { Authorization: "Bearer server-cookie-token" },
      },
    );
  });

  it("preserves structured authorization failures for safe action messages", async () => {
    mocks.fetch.mockResolvedValue(
      Response.json(
        { error: { code: "FORBIDDEN_ROLE", message: "denied", details: {} } },
        { status: 403 },
      ),
    );
    await expect(
      batchApi("/selection-preview", { method: "POST", body: "{}" }),
    ).rejects.toMatchObject({ status: 403, code: "FORBIDDEN_ROLE" });
    expect(mocks.fetch.mock.calls[0]![1].headers["Content-Type"]).toBe("application/json");
  });

  it("handles non-JSON unavailable responses without treating them as money data", async () => {
    mocks.fetch.mockResolvedValue(new Response("private proxy failure", { status: 503 }));
    await expect(batchApi("/summaries")).rejects.toMatchObject({ status: 503 });
  });
});
