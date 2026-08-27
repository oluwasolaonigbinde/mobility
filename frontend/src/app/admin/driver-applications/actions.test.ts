import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import {
  reviewPersonPayeeAction,
  reviewPersonPayeeEvidenceAction,
  reviewVehicleAction,
  reviewVehicleEvidenceAction,
  verifyPersonPayeeAccountAction,
} from "./actions";

const APPLICATION_ID = "00000000-0000-4000-8000-00000000000a";
const SUBMISSION_ID = "00000000-0000-4000-8000-00000000000b";
const VERSION_ID = "00000000-0000-4000-8000-00000000000c";
const FILE_ID = "00000000-0000-4000-8000-00000000000d";
const VEHICLE_ID = "00000000-0000-4000-8000-00000000000e";

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

  it("performs explicit audited reads of the exact identity, account and document", async () => {
    mocks.post
      .mockResolvedValueOnce({ data: { nin: "12345678901" } })
      .mockResolvedValueOnce({
        data: { account_name: "Test Driver", bank_code: "058", account_number: "0123456789" },
      })
      .mockResolvedValueOnce({ data: { url: "https://private.test/review" } });
    const nin = new FormData();
    nin.set("kind", "nin");
    nin.set("submission_id", SUBMISSION_ID);
    const account = new FormData();
    account.set("kind", "account");
    account.set("bank_account_version_id", VERSION_ID);
    const document = new FormData();
    document.set("kind", "document");
    document.set("submission_id", SUBMISSION_ID);
    document.set("file_id", FILE_ID);

    await expect(reviewPersonPayeeEvidenceAction({}, nin)).resolves.toMatchObject({
      done: "NIN read audited.",
      sensitiveValue: "12345678901",
    });
    await expect(reviewPersonPayeeEvidenceAction({}, account)).resolves.toMatchObject({
      done: "Account read audited.",
      sensitiveValue: "Test Driver · 058 · 0123456789",
    });
    await expect(reviewPersonPayeeEvidenceAction({}, document)).resolves.toMatchObject({
      done: "Document read audited.",
      downloadUrl: "https://private.test/review",
    });
    expect(mocks.post).toHaveBeenNthCalledWith(
      1,
      "/api/v1/admin/kyc/submissions/{submission_id}/nin/reveal",
      {
        params: { path: { submission_id: SUBMISSION_ID } },
        body: { purpose: "person_payee_approval" },
      },
    );
    expect(mocks.post).toHaveBeenNthCalledWith(
      2,
      "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal",
      { params: { path: { version_id: VERSION_ID } }, body: { purpose: "person_payee_approval" } },
    );
    expect(mocks.post).toHaveBeenNthCalledWith(3, "/api/v1/admin/files/{file_id}/download", {
      params: { path: { file_id: FILE_ID } },
      body: { purpose: "kyc_review", reason: `person_payee_approval:${SUBMISSION_ID}` },
    });
  });

  it("promotes only the exact account version with an authorized reference", async () => {
    const data = new FormData();
    data.set("bank_account_version_id", VERSION_ID);
    data.set("verification_reference", "provider-authority-reference-001");

    await expect(verifyPersonPayeeAccountAction({}, data)).resolves.toEqual({
      done: "Exact account version verified for payout review.",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/payees/bank-account-versions/{version_id}/payout-verification",
      {
        params: { path: { version_id: VERSION_ID } },
        body: { verification_reference: "provider-authority-reference-001" },
      },
    );
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

  it("audits exact vehicle evidence and requires every approval fact", async () => {
    mocks.post.mockResolvedValueOnce({ data: { url: "https://private.test/vehicle" } });
    const evidence = new FormData();
    evidence.set("file_id", FILE_ID);
    evidence.set("submission_id", SUBMISSION_ID);
    await expect(reviewVehicleEvidenceAction({}, evidence)).resolves.toEqual({
      done: "Vehicle evidence read audited.",
      downloadUrl: "https://private.test/vehicle",
    });
    expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/admin/files/{file_id}/download", {
      params: { path: { file_id: FILE_ID } },
      body: { purpose: "kyc_review", reason: `vehicle_approval:${SUBMISSION_ID}` },
    });

    const decision = new FormData();
    decision.set("application_id", APPLICATION_ID);
    decision.set("vehicle_id", VEHICLE_ID);
    decision.set("submission_id", SUBMISSION_ID);
    decision.set("client_request_id", "00000000-0000-4000-8000-0000000000aa");
    decision.set("intent", "approve");
    decision.set("valid_until", "2099-01-01T00:00");
    await expect(reviewVehicleAction({}, decision)).resolves.toEqual({
      error: "Complete every vehicle approval confirmation.",
    });
    for (const name of [
      "owner_match_confirmed",
      "vehicle_identity_confirmed",
      "roadworthy_confirmed",
      "pilot_car_confirmed",
      "documents_readable_confirmed",
    ])
      decision.set(name, "on");
    mocks.post.mockResolvedValueOnce({ data: { status: "approved" } });
    await expect(reviewVehicleAction({}, decision)).resolves.toEqual({
      done: "Vehicle evidence approved.",
    });
    expect(mocks.post).toHaveBeenLastCalledWith(
      "/api/v1/admin/driver-applications/{application_id}/vehicles/{vehicle_id}/submissions/{submission_id}/decision",
      expect.objectContaining({
        params: {
          path: {
            application_id: APPLICATION_ID,
            vehicle_id: VEHICLE_ID,
            submission_id: SUBMISSION_ID,
          },
        },
        body: expect.objectContaining({
          decision: "approved",
          reason_code: "complete_current_evidence",
          owner_match_confirmed: true,
          documents_readable_confirmed: true,
        }),
      }),
    );
  });
});
