import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn(), client: vi.fn(), relay: true }));
vi.mock("next/headers", () => ({
  headers: async () => new Headers({ "x-client-ip": "203.0.113.9" }),
}));
vi.mock("@/lib/env", () => ({
  env: () => ({ LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: mocks.relay }),
}));
vi.mock("@/lib/api/client", () => ({ createLoginApiClient: mocks.client }));
import { submitCampaignEnquiry } from "./campaign-enquiry-actions";

function form() {
  const data = new FormData();
  Object.entries({
    company: " Brand ",
    contact_name: " Contact ",
    email: " Contact@Example.test ",
    phone: "",
    brief: " Abuja campaign ",
  }).forEach(([key, value]) => data.set(key, value));
  return data;
}

describe("campaign enquiry action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.client.mockReturnValue({ POST: mocks.post });
    mocks.relay = true;
  });
  it("relays only allowlisted values and confirms accepted submission", async () => {
    mocks.post.mockResolvedValue({ data: { status: "submitted" } });
    const data = form();
    data.set("recipient", "attacker@example.test");
    expect(await submitCampaignEnquiry({}, data)).toEqual({ submitted: true });
    expect(mocks.client).toHaveBeenCalledWith("203.0.113.9");
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/campaign-enquiries", {
      body: {
        company: "Brand",
        contact_name: "Contact",
        email: "contact@example.test",
        phone: "",
        brief: "Abuja campaign",
      },
    });
  });
  it("does not relay untrusted IP configuration", async () => {
    mocks.relay = false;
    mocks.post.mockResolvedValue({ data: { status: "submitted" } });
    await submitCampaignEnquiry({}, form());
    expect(mocks.client).toHaveBeenCalledWith(undefined);
  });
  it.each([
    ["company", " "],
    ["email", "bad"],
    ["brief", "x".repeat(2001)],
  ])("rejects invalid %s without a request", async (field, value) => {
    const data = form();
    data.set(field, value);
    const state = await submitCampaignEnquiry({}, data);
    expect(state.fieldErrors?.[field as "company"]).toBeTruthy();
    expect(mocks.post).not.toHaveBeenCalled();
  });
  it("rejects File entries without serializing them", async () => {
    const data = form();
    data.set("company", new File(["secret"], "company.txt"));
    const state = await submitCampaignEnquiry({}, data);
    expect(state.fieldErrors?.company).toBeTruthy();
    expect(state.values?.company).toBe("");
    expect(mocks.post).not.toHaveBeenCalled();
  });
  it.each([undefined, { status: "unexpected" }])(
    "missing success never clears entered values",
    async (data) => {
      mocks.post.mockResolvedValue({ data });
      const state = await submitCampaignEnquiry({}, form());
      expect(state.submitted).toBeUndefined();
      expect(state.error).toBeTruthy();
      expect(state.values?.company).toBe(" Brand ");
    },
  );
  it.each([429, 503])("shows a safe retry error for %s", async (status) => {
    mocks.post.mockRejectedValue(
      new ApiError(status, { code: "failure", message: "internal secret" }),
    );
    const state = await submitCampaignEnquiry({}, form());
    expect(state.error).not.toContain("internal secret");
    expect(state.values?.brief).toBe(" Abuja campaign ");
    expect(state.submitted).toBeUndefined();
  });
  it("handles network failures", async () => {
    mocks.post.mockRejectedValue(new Error("internal hostname"));
    expect((await submitCampaignEnquiry({}, form())).error).not.toContain("internal hostname");
  });
});
