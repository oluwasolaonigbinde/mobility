import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, GET: mocks.get }),
}));

import { checkDriverApplicationStatusAction, submitDriverApplicationAction } from "./actions";

describe("driver application actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits the allowlisted fields and returns the reference", async () => {
    mocks.post.mockResolvedValue({
      data: {
        status: "pending",
        message: "Application received for review.",
        application_reference: "reference-secret",
      },
    });
    const form = new FormData();
    form.set("email", " Driver@Example.com ");
    form.set("full_name", " Driver Name ");
    form.set("phone", "+2348000000000");
    form.set("service_city", " Lagos ");
    form.set("country_code", "ng");

    await expect(submitDriverApplicationAction({}, form)).resolves.toEqual({
      submitted: true,
      reference: "reference-secret",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/register-driver", {
      body: {
        email: "driver@example.com",
        full_name: "Driver Name",
        phone: "+2348000000000",
        service_city: "Lagos",
        country_code: "NG",
      },
    });
  });

  it("keeps disabled or duplicate responses generic", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(404, { code: "APPLICATION_UNAVAILABLE", message: "hidden" }),
    );
    const form = new FormData();
    form.set("email", "driver@example.com");
    form.set("full_name", "Driver Name");

    await expect(submitDriverApplicationAction({}, form)).resolves.toEqual({
      error: "Application service is unavailable right now.",
    });
  });

  it("shows one pending status envelope for a reference", async () => {
    mocks.get.mockResolvedValue({
      data: { status: "pending", message: "Application status is pending review." },
    });
    const form = new FormData();
    form.set("reference", "reference-secret");

    await expect(checkDriverApplicationStatusAction({}, form)).resolves.toEqual({ pending: true });
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/auth/driver-application-status/{reference}", {
      params: { path: { reference: "reference-secret" } },
    });
  });
});
