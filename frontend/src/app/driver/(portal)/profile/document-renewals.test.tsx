import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { DocumentRenewals } from "./document-renewals";
const mocks = vi.hoisted(() => ({ upload: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));
vi.mock("@/lib/files/onboarding-upload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/files/onboarding-upload")>()),
  uploadDriverDocument: mocks.upload,
}));
const fetchMock = vi.fn();
const documents = {
  person_payee: {
    status: "rejected",
    submission_id: "person",
    reason_code: "bank_account_mismatch",
  },
  person_document_names: { driver_license: "driver-kyc.png" },
  vehicles: [
    {
      vehicle_id: "vehicle",
      submission_id: "car",
      plate_number: "ABJ-714-KM",
      status: "expired",
      valid_until: "2026-10-03T10:00:00Z",
      reason_code: "expired_evidence",
    },
  ],
  vehicle_document_names: { vehicle: { insurance: "vehicle-evidence.png" } },
};
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(Response.json(documents));
  mocks.upload.mockReset();
  mocks.upload.mockResolvedValue("file-id");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("shows the actual reasons, files and recorded vehicle date without inventing licence expiry", async () => {
  render(<DocumentRenewals />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  await screen.findByText(/Your bank details did not match/);
  expect(screen.getByText(/Driving licence: driver-kyc.png/)).toBeTruthy();
  expect(screen.getByText(/expired on/)).toHaveTextContent("3 Oct");
  expect(screen.queryByText(/licence expired/)).toBeNull();
  expect(screen.getAllByRole("button", { name: "Send new documents" })).toHaveLength(2);
});
it("handles load failure/retry and missing/current waiting documents", async () => {
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  render(<DocumentRenewals />);
  await screen.findByRole("alert");
  fetchMock.mockResolvedValue(
    Response.json({ person_payee: { status: "not_submitted" }, vehicles: [] }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText(/No documents are recorded yet/);
  expect(screen.queryByRole("button", { name: "Send new documents" })).toBeNull();
});
it("hides replacement controls for approved and pending documents", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      ...documents,
      person_payee: { status: "pending_review" },
      vehicles: [{ status: "approved", vehicle_id: "v", plate_number: "ABC" }],
    }),
  );
  render(<DocumentRenewals />);
  await screen.findByText(/waiting for Terrax to review/);
  expect(screen.getByText("Your documents are approved.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Send new documents" })).toBeNull();
});
it("requires complete files and retains a recoverable upload failure", async () => {
  render(<DocumentRenewals />);
  await screen.findByText(/Your bank details did not match/);
  const form = screen.getAllByRole("button", { name: "Send new documents" })[0]!.closest("form")!;
  fireEvent.submit(form);
  await screen.findByRole("alert");
  expect(mocks.upload).not.toHaveBeenCalled();
});
function mockCompleteForm() {
  const file = new File(["fictional document"], "renewal.png", { type: "image/png" });
  Object.defineProperty(file, "arrayBuffer", { value: async () => new ArrayBuffer(4) });
  const original = globalThis.crypto;
  vi.stubGlobal("crypto", {
    randomUUID: () => original.randomUUID(),
    subtle: { digest: async () => new ArrayBuffer(32) },
  });
  vi.spyOn(FormData.prototype, "get").mockImplementation((key) => {
    const fields: Record<string, string> = {
      nin: "00000000000",
      account_name: "Damilola Akinwale",
      account_number: "0000000000",
      bank_code: "000",
    };
    return fields[key] ?? file;
  });
}
it.each([0, 1])(
  "reuses uploads and the complete revision on a lost response, then shows waiting state (%s)",
  async (index) => {
    mockCompleteForm();
    render(<DocumentRenewals />);
    await screen.findByText(/Your bank details did not match/);
    const form = screen
      .getAllByRole("button", { name: "Send new documents" })
      [index]!.closest("form")!;
    fetchMock.mockRejectedValueOnce(new Error("Connection lost. Try again."));
    fireEvent.submit(form);
    await screen.findByText("Connection lost. Try again.");
    const firstBody = fetchMock.mock.calls.find((call) => call[1]?.method === "POST")![1].body;
    expect(JSON.parse(firstBody).expected_submission_id).toBe(index ? "car" : "person");
    expect(mocks.upload).toHaveBeenCalledTimes(3);
    fetchMock.mockResolvedValueOnce(Response.json({ id: "new-revision" }));
    fetchMock.mockResolvedValueOnce(
      Response.json({
        ...documents,
        person_payee: { status: "pending_review" },
        vehicles: [{ vehicle_id: "vehicle", status: "pending_review" }],
      }),
    );
    fireEvent.submit(form);
    await waitFor(() =>
      expect(screen.getAllByText(/waiting for Terrax to review/)).toHaveLength(2),
    );
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts[1]![1].body).toBe(firstBody);
    expect(mocks.upload).toHaveBeenCalledTimes(3);
    expect(mocks.refresh).toHaveBeenCalled();
  },
);
it("can retry a failed scan upload without submitting a partial revision", async () => {
  mockCompleteForm();
  mocks.upload.mockRejectedValueOnce(new Error("Choose another file."));
  render(<DocumentRenewals />);
  await screen.findByText(/Your bank details did not match/);
  fireEvent.submit(
    screen.getAllByRole("button", { name: "Send new documents" })[0]!.closest("form")!,
  );
  await screen.findByText("Choose another file.");
  expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
  expect(screen.getAllByRole("button", { name: "Send new documents" })[0]).toBeEnabled();
});
