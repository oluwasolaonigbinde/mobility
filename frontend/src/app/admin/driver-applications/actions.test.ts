import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import {
  initiateDriverAccountSetupAction,
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
      done: "NIN access logged.",
      sensitiveValue: "12345678901",
    });
    await expect(reviewPersonPayeeEvidenceAction({}, account)).resolves.toMatchObject({
      done: "Bank details access logged.",
      sensitiveValue: "Test Driver · 058 · 0123456789",
    });
    await expect(reviewPersonPayeeEvidenceAction({}, document)).resolves.toMatchObject({
      done: "Document access logged.",
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

  it("audits every direct document read with the automatic application-review purpose", async () => {
    const document = new FormData();
    document.set("kind", "document");
    document.set("file_id", FILE_ID);
    document.set("submission_id", SUBMISSION_ID);
    mocks.post.mockResolvedValue({ data: { url: "https://private.test/review" } });
    await reviewPersonPayeeEvidenceAction({}, document);
    await reviewPersonPayeeEvidenceAction({}, document);
    expect(mocks.post).toHaveBeenCalledTimes(2);
    for (const args of mocks.post.mock.calls)
      expect(args).toEqual([
        "/api/v1/admin/files/{file_id}/download",
        {
          params: { path: { file_id: FILE_ID } },
          body: { purpose: "kyc_review", reason: `person_payee_approval:${SUBMISSION_ID}` },
        },
      ]);
  });
  it("refuses empty Reject reason but permits empty reason for Approve and Expire", async () => {
    const reject = form("reject");
    reject.set("reason_code", "");
    expect(await reviewPersonPayeeAction({}, reject)).toHaveProperty("error");
    expect(mocks.post).not.toHaveBeenCalled();
    for (const intent of ["approve", "expire"] as const) {
      const data = form(intent);
      data.set("reason_code", "");
      expect(await reviewPersonPayeeAction({}, data)).toHaveProperty("done");
    }
    expect(mocks.post).toHaveBeenCalledTimes(2);
  });
  it("promotes only the exact account version with an authorized reference", async () => {
    const data = new FormData();
    data.set("bank_account_version_id", VERSION_ID);
    data.set("verification_reference", "provider-authority-reference-001");

    await expect(verifyPersonPayeeAccountAction({}, data)).resolves.toEqual({
      done: "These bank details have been checked for payouts.",
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
      done: "Identity documents and bank details approved.",
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
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/drivers");
  });

  it("records typed rejection evidence without approval attestations", async () => {
    await expect(reviewPersonPayeeAction({}, form("reject", false))).resolves.toEqual({
      done: "Identity documents and bank details not approved.",
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
      done: "Car document access logged.",
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
      done: "Car documents approved.",
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

  it("starts approved driver account setup without exposing the one-use authority", async () => {
    const data = new FormData();
    data.set("application_id", APPLICATION_ID);
    data.set("client_request_id", "00000000-0000-4000-8000-0000000000aa");
    mocks.post.mockResolvedValueOnce({
      data: { id: "private-setup-id", state: "pending" },
    });

    await expect(initiateDriverAccountSetupAction({}, data)).resolves.toEqual({
      done: "A one-use setup link was created and queued for delivery to the applicant's stored email. Delivery is not confirmed.",
    });
    expect(mocks.post).toHaveBeenLastCalledWith(
      "/api/v1/admin/driver-applications/{application_id}/account-setup",
      {
        params: { path: { application_id: APPLICATION_ID } },
        body: { client_request_id: "00000000-0000-4000-8000-0000000000aa" },
      },
    );
  });
});

it("logs every vehicle View with automatic vehicle-review purpose and current IDs", async () => {
  mocks.post.mockReset();
  mocks.post.mockResolvedValue({ data: { url: "https://private.test/vehicle" } });
  const evidence = new FormData();
  evidence.set("file_id", FILE_ID);
  evidence.set("submission_id", SUBMISSION_ID);
  for (let attempt = 0; attempt < 2; attempt++) await reviewVehicleEvidenceAction({}, evidence);
  expect(mocks.post).toHaveBeenCalledTimes(2);
  for (const [endpoint, request] of mocks.post.mock.calls) {
    expect(endpoint).toBe("/api/v1/admin/files/{file_id}/download");
    expect(request).toEqual({
      params: { path: { file_id: FILE_ID } },
      body: { purpose: "kyc_review", reason: "vehicle_approval:" + SUBMISSION_ID },
    });
  }
});
