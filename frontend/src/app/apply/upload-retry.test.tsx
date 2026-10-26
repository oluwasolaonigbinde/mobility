import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

vi.mock("@/lib/files/onboarding-upload", async (original) => ({
  ...(await original<object>()),
  uploadOnboardingFile: vi.fn(),
}));

vi.mock("@/components/driver/application-bank-details", () => ({
  ApplicationBankDetails: () => (
    <>
      <input name="bank_check_receipt" value="receipt" readOnly />
      <input name="account_name" value="Test Driver" readOnly />
    </>
  ),
}));
afterEach(() => vi.unstubAllGlobals());
const cases = [
  {
    show: () => render(<PersonPayeeForm accessToken="first-access" />),
    files: ["Driver's licence", "Photo of you"],
    field: "driver_license_file_id",
  },
  {
    show: () => render(<VehicleForm accessToken="first-access" cars={[]} />),
    files: ["Registration papers", "Insurance certificate", "Photo of the car"],
    field: "registration_file_id",
  },
];

describe.each(cases)("$field upload retry", ({ show, files, field }) => {
  beforeEach(() => {
    vi.mocked(uploadOnboardingFile).mockReset();
    vi.mocked(uploadOnboardingFile).mockImplementation(
      async (_token, file, key) => `${file.name}-${key}`,
    );
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          Response.json({ error: { message: "Submission failed" } }, { status: 503 }),
        )
        .mockResolvedValue(Response.json({ status: "pending_review", version: 1 })),
    );
  });

  function setup() {
    show();
    files.forEach((label) =>
      fireEvent.change(screen.getByLabelText(label), {
        target: { files: [new File([label], "same.png", { type: "image/png" })] },
      }),
    );
    const agreement = screen.queryByLabelText("I agree");
    if (agreement) fireEvent.click(agreement);
    return screen.getByRole("button", { name: /^Send my/ }).closest("form")!;
  }

  async function fail(form: HTMLFormElement) {
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Submission failed");
  }

  it("shows which file failed to upload and which uploaded", async () => {
    vi.mocked(uploadOnboardingFile)
      .mockResolvedValueOnce("first-file")
      .mockRejectedValueOnce(new Error("A file didn't upload."))
      .mockResolvedValueOnce("third-file");
    const form = setup();
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("A file didn't upload.");
    await waitFor(() => expect(screen.getAllByText("Uploaded")).toHaveLength(files.length - 1));
    expect(screen.getAllByText("Upload failed")).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reuses exact uploads and request identity on unchanged retry", async () => {
    const form = setup();
    await fail(form);
    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length);
    expect(vi.mocked(fetch).mock.calls[1]![1]!.body).toEqual(
      vi.mocked(fetch).mock.calls[0]![1]!.body,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rebinds uploads and submission identity after changing a file", async () => {
    const form = setup();
    await fail(form);
    fireEvent.change(screen.getByLabelText(files[0]!), {
      target: { files: [new File(["replacement"], "same.png", { type: "image/png" })] },
    });
    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1);
    const bodies = vi.mocked(fetch).mock.calls.map(([, init]) => JSON.parse(init!.body as string));
    expect(bodies[1][field]).not.toEqual(bodies[0][field]);
    expect(bodies[1].client_request_id).not.toEqual(bodies[0].client_request_id);
    expect(
      vi.mocked(uploadOnboardingFile).mock.calls.every(([token]) => token === "first-access"),
    ).toBe(true);
  });

  it("cannot submit or cache stale uploads after a file changes in flight", async () => {
    {
      let release!: (id: string) => void;
      vi.mocked(uploadOnboardingFile).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            release = resolve;
          }),
      );
      const form = setup();
      fireEvent.submit(form);
      await waitFor(() => expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length));
      fireEvent.change(screen.getByLabelText(files[0]!), {
        target: { files: [new File(["new"], "same.png", { type: "image/png" })] },
      });
      release("obsolete-file");
      await waitFor(() => expect(screen.getByRole("button", { name: /^Send my/ })).toBeEnabled());
      expect(fetch).not.toHaveBeenCalled();
      fireEvent.submit(form);
      await screen.findByRole("alert");
      expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1);
      expect(JSON.parse(vi.mocked(fetch).mock.calls[0]![1]!.body as string)[field]).not.toBe(
        "obsolete-file",
      );
    }
  });

  it("treats a new same-content File as a replacement and retains clean siblings", async () => {
    const form = setup();
    await fail(form);
    const previous = vi.mocked(uploadOnboardingFile).mock.calls[0]!;
    fireEvent.change(screen.getByLabelText(files[0]!), {
      target: { files: [new File([files[0]!], "same.png", { type: "image/png" })] },
    });
    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1);
    const replacement = vi.mocked(uploadOnboardingFile).mock.calls[files.length]!;
    expect(replacement[1]).not.toBe(previous[1]);
    expect(replacement[2]).not.toBe(previous[2]);
  });

  it.each(["logout", "unmount"])("fences late upload results after %s", async (end) => {
    let release!: (id: string) => void;
    vi.mocked(uploadOnboardingFile).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const form = setup();
    fireEvent.submit(form);
    await waitFor(() => expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length));
    if (end === "logout") fireEvent(window, new Event("cardvert-driver-logout"));
    else cleanup();
    await act(async () => {
      release("late-file");
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("retries only the failed file while coalescing a sibling still running after rejection", async () => {
    let release!: (id: string) => void;
    vi.mocked(uploadOnboardingFile)
      .mockRejectedValueOnce(new Error("upload offline"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            release = resolve;
          }),
      );
    const form = setup();
    fireEvent.submit(form);
    await screen.findByText("upload offline");
    fireEvent.submit(form);
    await waitFor(() => expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1));
    release("continuing-sibling");
    await screen.findByText("Submission failed");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1);
    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length + 1);
    const body = JSON.parse(vi.mocked(fetch).mock.calls[1]![1]!.body as string);
    expect(Object.values(body)).toContain("continuing-sibling");
  });

  it("resumes a failed scan through the real helper without recreating any received uploads", async () => {
    const real = await vi.importActual<typeof import("@/lib/files/onboarding-upload")>(
      "@/lib/files/onboarding-upload",
    );
    vi.mocked(uploadOnboardingFile).mockImplementation(real.uploadOnboardingFile);
    const original = globalThis.crypto;
    vi.stubGlobal("crypto", {
      randomUUID: () => original.randomUUID(),
      subtle: { digest: async () => new ArrayBuffer(32) },
    });
    const form = setup();
    for (const label of files) {
      const file = (screen.getByLabelText(label) as HTMLInputElement).files![0]!;
      Object.defineProperty(file, "arrayBuffer", { value: async () => new ArrayBuffer(8) });
    }
    let intents = 0;
    let firstScan = true;
    const requests = vi.fn(async (url: string) => {
      if (url === "/api/apply/onboarding/uploads") {
        intents += 1;
        return Response.json({
          upload_id: `intent-${intents}`,
          upload: { url: `https://storage/${intents}`, fields: {} },
        });
      }
      if (url.startsWith("https://storage/")) return new Response(null, { status: 204 });
      if (url.endsWith("/confirm"))
        return Response.json({ id: url.split("/").at(-2)!, scan_status: "pending" });
      if (url.endsWith("/status")) {
        if (url.includes("intent-1") && firstScan) {
          firstScan = false;
          throw new Error("Scan connection lost");
        }
        return Response.json({ scan_status: "clean" });
      }
      return Response.json({ status: "pending_review", version: 1 });
    });
    vi.stubGlobal("fetch", requests);
    fireEvent.submit(form);
    await screen.findByText("Scan connection lost");
    await waitFor(() => expect(screen.getAllByText("Uploaded")).toHaveLength(files.length - 1));
    fireEvent.submit(form);
    await screen.findByRole("status");
    const urls = requests.mock.calls.map(([url]) => url);
    expect(urls.filter((url) => url === "/api/apply/onboarding/uploads")).toHaveLength(
      files.length,
    );
    expect(urls.filter((url) => url.startsWith("https://storage/"))).toHaveLength(files.length);
    expect(urls.filter((url) => url.endsWith("/confirm"))).toHaveLength(files.length);
    expect(urls.filter((url) => url.endsWith("/status"))).toHaveLength(files.length + 1);
    expect(urls.at(-1)).toBe(
      field === "driver_license_file_id"
        ? "/api/apply/onboarding/person-payee"
        : "/api/apply/onboarding/vehicle",
    );
  });
});

describe("vehicle upload scope", () => {
  it("replaces cached uploads when selecting another owned car, then reuses that car's retry", async () => {
    vi.mocked(uploadOnboardingFile).mockReset();
    vi.mocked(uploadOnboardingFile).mockImplementation(
      async (_token, file, key) => `${file.name}-${key}`,
    );
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        attempts += 1;
        return attempts < 3
          ? Response.json({ error: { message: "Submission failed" } }, { status: 503 })
          : Response.json({ status: "pending_review", version: 1, vehicle_id: "car-b" });
      }),
    );
    render(
      <VehicleForm
        accessToken="access"
        cars={[
          { vehicle_id: "car-a", plate_number: "CAR-A", status: "rejected" },
          { vehicle_id: "car-b", plate_number: "CAR-B", status: "rejected" },
        ]}
      />,
    );
    for (const label of ["Registration papers", "Insurance certificate", "Photo of the car"])
      fireEvent.change(screen.getByLabelText(label), {
        target: { files: [new File([label], `${label}.png`, { type: "image/png" })] },
      });
    fireEvent.click(screen.getByRole("radio", { name: /CAR-A/ }));
    const form = screen.getByRole("button", { name: /^Send my/ }).closest("form")!;
    const submissions = () =>
      vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => String(url) === "/api/apply/onboarding/vehicle");
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Submission failed");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(3);
    const first = JSON.parse(String(submissions()[0]![1]!.body));
    expect(first.vehicle_id).toBe("car-a");

    fireEvent.click(screen.getByRole("radio", { name: /CAR-B/ }));
    expect(screen.queryAllByText("Uploaded")).toHaveLength(0);
    fireEvent.submit(form);
    await waitFor(() => expect(submissions()).toHaveLength(2));
    expect(await screen.findByRole("alert")).toHaveTextContent("Submission failed");
    const second = JSON.parse(String(submissions()[1]![1]!.body));
    expect(second.vehicle_id).toBe("car-b");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(6);
    for (const key of ["registration_file_id", "insurance_file_id", "vehicle_photo_file_id"])
      expect(second[key]).not.toBe(first[key]);
    for (let index = 0; index < 3; index += 1)
      expect(vi.mocked(uploadOnboardingFile).mock.calls[index + 3]![1]).toBe(
        vi.mocked(uploadOnboardingFile).mock.calls[index]![1],
      );

    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(6);
    expect(submissions()[2]![1]!.body).toBe(submissions()[1]![1]!.body);
  });
});
