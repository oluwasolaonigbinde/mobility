import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/cache", () => ({
  revalidatePath: mocks.revalidatePath,
  refresh: mocks.refresh,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { acceptQuoteAction, requestQuoteAction } from "./commercial-actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000001";
const REVISION_ID = "00000000-0000-4000-8000-000000000002";

function quotationForm({ confirmed = false } = {}) {
  const form = new FormData();
  form.set("campaign_id", CAMPAIGN_ID);
  form.set("revision_id", REVISION_ID);
  if (confirmed) form.set("confirmed", "on");
  return form;
}

function campaignForm() {
  const form = new FormData();
  form.set("campaign_id", CAMPAIGN_ID);
  return form;
}

describe("commercial advertiser feedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("requires explicit confirmation for the exact quotation", async () => {
    await expect(acceptQuoteAction({}, quotationForm())).resolves.toEqual({
      error: "Review the quotation and confirm that you accept these exact terms.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it("refreshes preparation facts while retaining the accepted receipt and visible feedback", async () => {
    const acceptedTerms = { id: "accepted-terms", quotation_revision_id: REVISION_ID };
    mocks.post.mockResolvedValueOnce({ data: acceptedTerms });
    await expect(acceptQuoteAction({}, quotationForm({ confirmed: true }))).resolves.toMatchObject({
      done: "Quotation accepted. Your immutable receipt is shown below.",
      acceptedTerms,
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it.each(["missing receipt", "API failure"])("does not refresh after %s", async (failure) => {
    if (failure === "missing receipt") mocks.post.mockResolvedValueOnce({ data: undefined });
    else mocks.post.mockRejectedValueOnce(new Error("private backend detail"));
    const result = await acceptQuoteAction({}, quotationForm({ confirmed: true }));
    expect(result).toEqual({
      error:
        failure === "missing receipt"
          ? "The accepted terms receipt is unavailable. Try again."
          : "Could not accept the quotation. Try again.",
    });
    expect(mocks.refresh).not.toHaveBeenCalled();
    expect(JSON.stringify(result)).not.toContain("private backend detail");
  });

  it("says who posts the quotation after a request (D38a)", async () => {
    await expect(requestQuoteAction({}, campaignForm())).resolves.toEqual({
      done: "Quotation requested. Terrax Media will post it here for review.",
    });
  });

  it("maps known failures and never returns raw backend text", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, {
        code: "QUOTATION_REVISION_SUPERSEDED",
        message: "PRIVATE bank account 1234567890 stack trace",
      }),
    );
    const known = await acceptQuoteAction({}, quotationForm({ confirmed: true }));
    expect(known).toEqual({
      error: "A newer quotation is available. Review it before accepting.",
    });
    expect(JSON.stringify(known)).not.toContain("1234567890");

    mocks.post.mockRejectedValueOnce(
      new ApiError(500, { code: "PRIVATE_FAILURE", message: "raw database detail" }),
    );
    const unknown = await requestQuoteAction({}, campaignForm());
    expect(unknown).toEqual({ error: "Could not request a quotation. Try again." });
    expect(JSON.stringify(unknown)).not.toContain("database detail");
  });
});
