import { beforeEach, expect, it, vi } from "vitest";
import { POST } from "./route";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ token: vi.fn(), client: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.client }));

const campaignId = "00000000-0000-4000-8000-0000000000c1";
const body = { client_request_id: "request-1" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.token.mockResolvedValue("server-session");
  mocks.client.mockReturnValue({ POST: mocks.post });
});

function rerun() {
  return POST(
    new Request(`http://localhost/api/admin/campaigns/${campaignId}/reports/re-run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
    { params: Promise.resolve({ campaignId }) },
  );
}

it.each([
  [409, "REPORT_NOT_DUE", "A new report can't be prepared yet."],
  [404, "CAMPAIGN_NOT_FOUND", "This campaign couldn't be found. Refresh the page."],
  [
    409,
    "REPORT_REQUEST_CONFLICT",
    "This request was already used. Refresh the page and try again.",
  ],
])("maps the %s %s refusal to fixed copy", async (status, code, message) => {
  mocks.post.mockRejectedValue(
    new ApiError(status, {
      code,
      message: "internal backend detail",
      details: { secret: "x" },
      request_id: "req-1",
    }),
  );
  const result = await rerun();
  expect(result.status).toBe(status);
  expect(result.headers.get("cache-control")).toBe("no-store");
  expect(await result.json()).toEqual({
    error: { code, message, details: {}, request_id: "req-1" },
  });
});

it("gives an unknown refusal the generic fallback without leaking the backend message", async () => {
  mocks.post.mockRejectedValue(
    new ApiError(422, { code: "SOMETHING_ELSE", message: "internal backend detail" }),
  );
  const result = await rerun();
  const json = await result.json();
  expect(result.status).toBe(422);
  expect(json.error.code).toBe("SOMETHING_ELSE");
  expect(json.error.message).toBe("That didn't work. Try again.");
  expect(JSON.stringify(json)).not.toContain("internal backend detail");
});

it("sends the request body to the re-run endpoint", async () => {
  mocks.post.mockResolvedValue({ data: { id: "report", status: "queued" } });
  const result = await rerun();
  expect(result.status).toBe(202);
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/campaigns/{campaign_id}/reports/re-run", {
    params: { path: { campaign_id: campaignId } },
    body,
  });
});
