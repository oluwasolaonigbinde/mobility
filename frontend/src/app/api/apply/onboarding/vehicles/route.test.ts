import { beforeEach, expect, it, vi } from "vitest";
import { POST } from "./route";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  createApiClient: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.getSessionToken }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.createApiClient }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSessionToken.mockResolvedValue(undefined);
  mocks.createApiClient.mockReturnValue({ POST: mocks.post });
});

it("forwards the onboarding code in the body and returns the applicant's cars", async () => {
  const items = [{ vehicle_id: "car-1", plate_number: "ABC-123-XY", status: "approved" }];
  mocks.post.mockResolvedValue({ data: { items } });

  const response = await POST(
    new Request("http://localhost/api/apply/onboarding/vehicles", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_access_token: "emailed-code" }),
    }),
  );

  expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/driver-onboarding/vehicles", {
    body: { application_access_token: "emailed-code" },
  });
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ items });
});
