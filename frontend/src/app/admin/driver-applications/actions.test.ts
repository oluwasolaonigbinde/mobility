import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { reviewPersonPayeeAction } from "./actions";

const APPLICATION_ID = "00000000-0000-4000-8000-00000000000a";

function form(intent: "approve" | "reject" | "expire", checks = true): FormData {
  const data = new FormData();
  data.set("application_id", APPLICATION_ID);
  data.set("client_request_id", "00000000-0000-4000-8000-0000000000aa");
  data.set("intent", intent);
  data.set("reason_code", "unreadable_evidence");
  if (checks) {
    data.set("identity_match_confirmed", "on");
    data.set("bank_account_match_confirmed", "on");
    data.set("documents_readable_confirmed", "on");
  }
  return data;
}

describe("reviewPersonPayeeAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { status: "approved" } });
  });

  it("requires all explicit approval facts before the governed decision endpoint", async () => {
    await expect(reviewPersonPayeeAction({}, form("approve", false))).resolves.toEqual({
      error: "Confirm identity, account match and document readability before approval.",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    await expect(reviewPersonPayeeAction({}, form("approve"))).resolves.toEqual({
      done: "Person/payee evidence approved.",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/driver-applications/{application_id}/person-payee-decision",
      {
        params: { path: { application_id: APPLICATION_ID } },
        body: {
          client_request_id: "00000000-0000-4000-8000-0000000000aa",
          decision: "approved",
          reason_code: "complete_current_evidence",
          identity_match_confirmed: true,
          bank_account_match_confirmed: true,
          documents_readable_confirmed: true,
        },
      },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/driver-applications");
  });

  it("records typed rejection evidence without approval attestations", async () => {
    await expect(reviewPersonPayeeAction({}, form("reject", false))).resolves.toEqual({
      done: "Person/payee evidence rejected.",
    });
    expect(mocks.post.mock.calls[0]?.[1].body).toMatchObject({
      decision: "rejected",
      reason_code: "unreadable_evidence",
      identity_match_confirmed: false,
      bank_account_match_confirmed: false,
      documents_readable_confirmed: false,
    });
  });
});
