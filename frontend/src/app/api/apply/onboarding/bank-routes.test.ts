import { beforeEach, expect, it, vi } from "vitest";
import { GET as banks } from "./banks/route";
import { POST as accountName } from "./account-name/route";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  session: vi.fn(),
  client: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.session }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.client }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.session.mockResolvedValue(undefined);
  mocks.client.mockReturnValue({ GET: mocks.get, POST: mocks.post });
});

it("makes the shared catalog public and uncacheable", async () => {
  mocks.get.mockResolvedValue({ data: [{ code: "999992", name: "OPay" }] });
  const response = await banks();
  expect(mocks.client).toHaveBeenCalledWith(undefined);
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/auth/driver-onboarding/banks");
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(await response.json()).toEqual([{ code: "999992", name: "OPay" }]);
});

it.each(["resolved", "unavailable"])(
  "relays the authoritative %s check and keeps the capability in the body",
  async (outcome) => {
    const payload = {
      application_access_token: "private-code",
      bank_code: "058",
      account_number: "0123456789",
    };
    const checked = {
      outcome,
      bank_check_receipt: "signed-receipt",
      ...(outcome === "resolved" ? { account_name: "TEST DRIVER" } : {}),
    };
    mocks.post.mockResolvedValue({ data: checked });
    const response = await accountName(
      new Request("http://localhost/api/apply/onboarding/account-name", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/driver-onboarding/account-name", {
      body: payload,
    });
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual(checked);
  },
);

it("preserves a denied account check as an error while redacting private backend content", async () => {
  mocks.post.mockRejectedValue(
    new ApiError(422, {
      code: "BANK_CHECK_INVALID",
      message: "private account 0123456789 and capability private-code",
      details: { account_number: "0123456789", application_access_token: "private-code" },
      request_id: "bank-denial-1",
    }),
  );
  const response = await accountName(
    new Request("http://localhost/api/apply/onboarding/account-name", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        application_access_token: "private-code",
        bank_code: "058",
        account_number: "0123456789",
      }),
    }),
  );
  expect(response.status).toBe(422);
  expect(response.headers.get("cache-control")).toBe("no-store");
  const denied = await response.json();
  expect(denied).toEqual({
    error: {
      code: "BANK_CHECK_INVALID",
      message: "The request could not be completed. Check the details and try again.",
      details: {},
      request_id: "bank-denial-1",
    },
  });
  expect(denied).not.toHaveProperty("outcome");
  expect(denied).not.toHaveProperty("bank_check_receipt");
  expect(denied).not.toHaveProperty("account_name");
  expect(JSON.stringify(denied)).not.toMatch(
    /private|0123456789|account_number|application_access_token/,
  );
});
