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
    reason_code: "unreadable_evidence",
    documents: {
      driver_license: { status: "rejected", reason_code: "unreadable_evidence" },
      driver_photo: { status: "accepted" },
      signed_agreement: { status: "accepted" },
    },
  },
  vehicles: [
    {
      vehicle_id: "vehicle",
      submission_id: "car",
      plate_number: "ABJ-714-KM",
      status: "expired",
      documents: {
        registration: { status: "accepted" },
        insurance: { status: "expired", reason_code: "expired_evidence", expires_on: "2026-10-03" },
        vehicle_photo: { status: "accepted" },
      },
    },
  ],
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
it("shows each recorded outcome, only failed uploads, no filenames or saved identity/bank fields", async () => {
  render(<DocumentRenewals />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  await screen.findByText("hard to read, upload a clearer photo");
  expect(screen.getByText("expired 3 Oct, upload a current document")).toBeTruthy();
  expect(screen.getAllByText("accepted")).toHaveLength(4);
  expect(screen.getByLabelText("Replace Driving licence")).toBeTruthy();
  expect(screen.getByLabelText("Replace Insurance")).toBeTruthy();
  expect(screen.queryByLabelText("NIN")).toBeNull();
  expect(screen.queryByLabelText("Bank account number")).toBeNull();
  expect(screen.queryByLabelText("Replace Your photo")).toBeNull();
  expect(screen.queryByText(/\.png|No file chosen|Choose File/)).toBeNull();
  expect(screen.getByText(/Starting new campaign trips is paused/)).toBeTruthy();
  expect(screen.getByText(/Starting new campaign trips in this car is paused/)).toBeTruthy();
});
it("offers a named bank list only for rejected bank details", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      ...documents,
      person_payee: {
        ...documents.person_payee,
        replace_bank: true,
        documents: { driver_license: { status: "accepted" } },
      },
      vehicles: [],
    }),
  );
  render(<DocumentRenewals />);
  await screen.findByLabelText("Bank");
  expect(screen.getByRole("option", { name: "Guaranty Trust Bank" })).toHaveValue("058");
  expect(screen.queryByLabelText("Bank code")).toBeNull();
  expect(screen.queryByLabelText("NIN")).toBeNull();
  expect(screen.queryByLabelText(/Replace/)).toBeNull();
});
it("handles loading failure and retry", async () => {
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  render(<DocumentRenewals />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("hard to read, upload a clearer photo");
});
it("requests all fresh vehicle files after payload purge", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      person_payee: { status: "approved" },
      vehicles: [{ ...documents.vehicles[0], purged_at: "2026-10-07T10:00:00Z", documents: {} }],
    }),
  );
  render(<DocumentRenewals />);
  await screen.findByLabelText("Replace Vehicle registration");
  expect(screen.getByLabelText("Replace Insurance")).toBeTruthy();
  expect(screen.getByLabelText("Replace Vehicle photo")).toBeTruthy();
});
it.each(["driver_photo", "insurance"])(
  "offers the missing retained document (%s)",
  async (kind) => {
    const data = structuredClone(documents);
    const group = kind === "insurance" ? data.vehicles[0]!.documents : data.person_payee.documents;
    Object.assign(group, { [kind]: { status: "rejected", reason_code: "missing_evidence" } });
    fetchMock.mockResolvedValue(Response.json(data));
    render(<DocumentRenewals />);
    await screen.findByText("missing, upload this document");
    expect(
      screen.getByLabelText(kind === "insurance" ? "Replace Insurance" : "Replace Your photo"),
    ).toBeTruthy();
  },
);
it("hides renewal controls while waiting and for approved documents", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      ...documents,
      person_payee: { status: "pending_review" },
      vehicles: [
        { vehicle_id: "v", status: "approved", documents: { insurance: { status: "accepted" } } },
      ],
    }),
  );
  render(<DocumentRenewals />);
  await screen.findByText("Terrax is reviewing your changes.");
  expect(screen.queryByRole("button", { name: "Send for review" })).toBeNull();
});
it("offers zero-file renewal for an expired whole-car approval without relabelling accepted insurance", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      person_payee: { status: "approved" },
      vehicles: [
        {
          vehicle_id: "v",
          submission_id: "s",
          status: "expired",
          valid_until: "2026-10-03T10:00:00Z",
          documents: { insurance: { status: "accepted" } },
        },
      ],
    }),
  );
  render(<DocumentRenewals />);
  await screen.findByText(/Vehicle approval expired/);
  expect(screen.getByText("accepted")).toBeTruthy();
  expect(screen.queryByLabelText(/Replace/)).toBeNull();
  fireEvent.submit(screen.getByRole("button", { name: "Send for review" }).closest("form")!);
  await waitFor(() =>
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true),
  );
  expect(mocks.upload).not.toHaveBeenCalled();
});
function selectedFile() {
  const file = new File(["fictional document"], "secret-filename.png", { type: "image/png" });
  Object.defineProperty(file, "arrayBuffer", { value: async () => new ArrayBuffer(4) });
  const original = globalThis.crypto;
  vi.stubGlobal("crypto", {
    randomUUID: () => original.randomUUID(),
    subtle: { digest: async () => new ArrayBuffer(32) },
  });
  vi.spyOn(FormData.prototype, "get").mockImplementation(() => file);
}
it.each([0, 1])(
  "retries one replacement without duplicate upload or changing the request (%s)",
  async (index) => {
    selectedFile();
    render(<DocumentRenewals />);
    await screen.findByText("hard to read, upload a clearer photo");
    const form = screen
      .getAllByRole("button", { name: "Send for review" })
      [index]!.closest("form")!;
    fetchMock.mockRejectedValueOnce(new Error("Connection lost. Try again."));
    fireEvent.submit(form);
    await screen.findByText("Connection lost. Try again.");
    const firstBody = fetchMock.mock.calls.find((call) => call[1]?.method === "POST")![1].body;
    const body = JSON.parse(firstBody);
    expect(Object.keys(body).sort()).toEqual(
      [
        "client_request_id",
        "expected_submission_id",
        index ? "insurance_file_id" : "driver_license_file_id",
      ].sort(),
    );
    expect(mocks.upload).toHaveBeenCalledTimes(1);
    fetchMock.mockResolvedValueOnce(Response.json({ id: "new" }));
    fetchMock.mockResolvedValueOnce(
      Response.json({ person_payee: { status: "pending_review" }, vehicles: [] }),
    );
    fireEvent.submit(form);
    await screen.findByText("Terrax is reviewing your changes.");
    const posts = fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");
    expect(posts[1]![1].body).toBe(firstBody);
    expect(mocks.upload).toHaveBeenCalledTimes(1);
  },
);
it("recovers a failed scan without submitting a revision", async () => {
  selectedFile();
  mocks.upload.mockRejectedValueOnce(new Error("Choose another file."));
  render(<DocumentRenewals />);
  await screen.findByText("hard to read, upload a clearer photo");
  fireEvent.submit(screen.getAllByRole("button", { name: "Send for review" })[0]!.closest("form")!);
  await screen.findByText("Choose another file.");
  expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
});
