import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
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
  });

  it("returns visible success without putting feedback in a URL", async () => {
    await expect(acceptQuoteAction({}, quotationForm({ confirmed: true }))).resolves.toMatchObject({
      done: "Quotation accepted. Your immutable receipt is shown below.",
      acceptedTerms: {},
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
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
