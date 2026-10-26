import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    agreement_version: "1",
    agreement_accepted_at: "2026-10-12T12:00:00Z",
    status: "rejected",
    submission_id: "person",
    reason_code: "unreadable_evidence",
    documents: {
      driver_license: { status: "rejected", reason_code: "unreadable_evidence" },
      driver_photo: { status: "accepted" },
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
  mocks.refresh.mockReset();
});

it.each(["person-submission", "vehicle-submission", "vehicle-id"])(
  "fences late uploads when current %s is refreshed",
  async (change) => {
    const changedPerson = change === "person-submission";
    const current = structuredClone(documents);
    if (changedPerson) current.vehicles[0]!.documents.insurance.status = "accepted";
    else current.person_payee.documents.driver_license.status = "accepted";
    fetchMock.mockResolvedValueOnce(Response.json(current));
    let release!: (id: string) => void;
    mocks.upload.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    render(<DocumentRenewals driverId="driver" />);
    const label = changedPerson ? "Replace Driving licence" : "Replace Insurance";
    const oldInput = await screen.findByLabelText(label);
    fireEvent.change(oldInput, { target: { files: [selectedFile()] } });
    const forms = screen.getAllByRole("button", { name: "Send for review" });
    const oldForm = forms[changedPerson ? 0 : 1]!.closest("form")!;
    fireEvent.submit(oldForm);
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1));
    const next = structuredClone(current);
    if (changedPerson) next.person_payee.submission_id = "new-person-submission";
    else if (change === "vehicle-id") next.vehicles[0]!.vehicle_id = "different-vehicle";
    else next.vehicles[0]!.submission_id = "new-car-submission";
    fetchMock.mockResolvedValueOnce(Response.json({ id: "auxiliary-renewal" }));
    fetchMock.mockResolvedValueOnce(Response.json(next));
    const refreshed = new Promise<void>((resolve) => {
      mocks.refresh.mockImplementationOnce(() => resolve());
    });
    // The refresh signal follows setDocuments, but only act also commits the
    // keyed form replacement and its cleanup before the old upload completes.
    await act(async () => {
      fireEvent.submit(forms[changedPerson ? 1 : 0]!.closest("form")!);
      await refreshed;
    });
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
    expect(oldForm).not.toBeInTheDocument();
    expect(screen.getByLabelText(label)).not.toBe(oldInput);
    await act(async () => {
      release("old-record-file");
    });
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]![1].body).not.toContain("old-record-file");
  },
);
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("shows each recorded outcome, only failed uploads, no filenames or saved identity/bank fields", async () => {
  render(<DocumentRenewals driverId="driver" />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  await screen.findByText("hard to read, upload a clearer photo");
  expect(screen.getByText("expired 3 Oct, upload a current document")).toBeTruthy();
  expect(screen.getAllByText("accepted")).toHaveLength(3);
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
  fetchMock.mockImplementation(async (url: string) =>
    url.includes("/banks")
      ? Response.json([{ code: "058", name: "GTBank" }])
      : Response.json({
          ...documents,
          person_payee: {
            ...documents.person_payee,
            replace_bank: true,
            documents: { driver_license: { status: "accepted" } },
          },
          vehicles: [],
        }),
  );
  render(<DocumentRenewals driverId="driver" />);
  await screen.findByRole("option", { name: "GTBank" });
  expect(screen.getByRole("option", { name: "GTBank" })).toHaveValue("058");
  expect(screen.queryByLabelText("Bank code")).toBeNull();
  expect(screen.queryByLabelText("NIN")).toBeNull();
  expect(screen.queryByLabelText(/Replace/)).toBeNull();
});
it("handles loading failure and retry", async () => {
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  render(<DocumentRenewals driverId="driver" />);
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
  render(<DocumentRenewals driverId="driver" />);
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
    render(<DocumentRenewals driverId="driver" />);
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
  render(<DocumentRenewals driverId="driver" />);
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
  render(<DocumentRenewals driverId="driver" />);
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
  return file;
}
it.each([0, 1])(
  "retries one replacement without duplicate upload or changing the request (%s)",
  async (index) => {
    const file = selectedFile();
    render(<DocumentRenewals driverId="driver" />);
    await screen.findByText("hard to read, upload a clearer photo");
    const form = screen
      .getAllByRole("button", { name: "Send for review" })
      [index]!.closest("form")!;
    fireEvent.change(
      screen.getByLabelText(index ? "Replace Insurance" : "Replace Driving licence"),
      { target: { files: [file] } },
    );
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
  const file = selectedFile();
  mocks.upload.mockRejectedValueOnce(new Error("Choose another file."));
  render(<DocumentRenewals driverId="driver" />);
  await screen.findByText("hard to read, upload a clearer photo");
  fireEvent.change(screen.getByLabelText("Replace Driving licence"), { target: { files: [file] } });
  fireEvent.submit(screen.getAllByRole("button", { name: "Send for review" })[0]!.closest("form")!);
  await screen.findByText("Choose another file.");
  expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
});

it("reuses a completed renewal sibling and the unfinished file's progress on retry", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      ...documents,
      vehicles: [],
      person_payee: {
        ...documents.person_payee,
        documents: { driver_license: { status: "rejected" }, driver_photo: { status: "rejected" } },
      },
    }),
  );
  mocks.upload
    .mockResolvedValueOnce("license-clean")
    .mockRejectedValueOnce(new Error("Scan offline"));
  render(<DocumentRenewals driverId="driver" />);
  await screen.findByLabelText("Replace Your photo");
  fireEvent.change(screen.getByLabelText("Replace Driving licence"), {
    target: { files: [selectedFile()] },
  });
  fireEvent.change(screen.getByLabelText("Replace Your photo"), {
    target: { files: [selectedFile()] },
  });
  const form = screen.getByRole("button", { name: "Send for review" }).closest("form")!;
  fireEvent.submit(form);
  await screen.findByText("Scan offline");
  const unfinished = mocks.upload.mock.calls[1]!;
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  fireEvent.submit(form);
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  expect(mocks.upload).toHaveBeenCalledTimes(3);
  expect(mocks.upload.mock.calls[2]).toEqual(unfinished);
  const body = JSON.parse(
    fetchMock.mock.calls.find(([, init]) => init?.method === "POST")![1].body,
  );
  expect(body.driver_license_file_id).toBe("license-clean");
  expect(body.driver_photo_file_id).toBe("file-id");
});

it("does not reuse a renewal File replaced by a new File with identical contents", async () => {
  const get = FormData.prototype.get;
  vi.spyOn(FormData.prototype, "get").mockImplementation(function (this: FormData, name) {
    if (name === "driver_license")
      return (screen.getByLabelText("Replace Driving licence") as HTMLInputElement).files![0]!;
    return get.call(this, name);
  });
  render(<DocumentRenewals driverId="driver" />);
  await screen.findByLabelText("Replace Driving licence");
  fireEvent.change(screen.getByLabelText("Replace Driving licence"), {
    target: { files: [selectedFile()] },
  });
  const form = screen.getAllByRole("button", { name: "Send for review" })[0]!.closest("form")!;
  fetchMock.mockRejectedValueOnce(new Error("Submission offline"));
  fireEvent.submit(form);
  await screen.findByText("Submission offline");
  const first = mocks.upload.mock.calls[0]!;
  fireEvent.change(screen.getByLabelText("Replace Driving licence"), {
    target: { files: [selectedFile()] },
  });
  fetchMock.mockRejectedValueOnce(new Error("Submission offline again"));
  fireEvent.submit(form);
  await screen.findByText("Submission offline again");
  expect(mocks.upload).toHaveBeenCalledTimes(2);
  expect(mocks.upload.mock.calls[1]![0]).not.toBe(first[0]);
  expect(mocks.upload.mock.calls[1]![1]).not.toBe(first[1]);
  expect(mocks.upload.mock.calls[1]![3]).not.toBe(first[3]);
});

it.each(["owner", "unmount", "logout"])(
  "fences renewal upload completion after %s changes",
  async (change) => {
    let release!: (id: string) => void;
    mocks.upload.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const view = render(<DocumentRenewals driverId="driver" />);
    await screen.findByLabelText("Replace Driving licence");
    fireEvent.change(screen.getByLabelText("Replace Driving licence"), {
      target: { files: [selectedFile()] },
    });
    fireEvent.submit(
      screen.getAllByRole("button", { name: "Send for review" })[0]!.closest("form")!,
    );
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1));
    if (change === "owner") view.rerender(<DocumentRenewals driverId="other-driver" />);
    else if (change === "unmount") view.unmount();
    else fireEvent(window, new Event("cardvert-driver-logout"));
    await act(async () => {
      release("late-old-owner-file");
    });
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(mocks.refresh).not.toHaveBeenCalled();
  },
);

it("resumes renewal scanning through the real helper and sends only the clean ID", async () => {
  const real = await vi.importActual<typeof import("@/lib/files/onboarding-upload")>(
    "@/lib/files/onboarding-upload",
  );
  mocks.upload.mockImplementation(real.uploadDriverDocument);
  let firstScan = true;
  let sent = false;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url === "/api/driver/documents")
      return Response.json(
        sent ? { person_payee: { status: "pending_review" }, vehicles: [] } : documents,
      );
    if (url === "/api/driver/files/uploads")
      return Response.json({
        upload_id: "original",
        upload: { url: "https://storage/renewal", fields: {} },
      });
    if (url === "https://storage/renewal") return new Response(null, { status: 204 });
    if (url.endsWith("/confirm")) return Response.json({ id: "received", scan_status: "pending" });
    if (url === "/api/driver/files/received") {
      if (firstScan) {
        firstScan = false;
        throw new Error("Scan offline");
      }
      return Response.json({ scan_status: "clean" });
    }
    expect(JSON.parse(init!.body as string).driver_license_file_id).toBe("received");
    sent = true;
    return Response.json({ id: "new-submission" });
  });
  render(<DocumentRenewals driverId="driver" />);
  await screen.findByLabelText("Replace Driving licence");
  fireEvent.change(screen.getByLabelText("Replace Driving licence"), {
    target: { files: [selectedFile()] },
  });
  const form = screen.getAllByRole("button", { name: "Send for review" })[0]!.closest("form")!;
  fireEvent.submit(form);
  await screen.findByText("Scan offline");
  expect(sent).toBe(false);
  fireEvent.submit(form);
  await screen.findByText("Terrax is reviewing your changes.");
  const urls = fetchMock.mock.calls.map(([url]) => url);
  expect(urls.filter((url) => url === "/api/driver/files/uploads")).toHaveLength(1);
  expect(urls.filter((url) => url === "https://storage/renewal")).toHaveLength(1);
  expect(urls.filter((url) => url.endsWith("/confirm"))).toHaveLength(1);
  expect(urls.filter((url) => url === "/api/driver/files/received")).toHaveLength(2);
});
