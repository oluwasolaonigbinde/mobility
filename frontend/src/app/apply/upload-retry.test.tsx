import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
const cases = [
  {
    Component: PersonPayeeForm,
    files: ["Driver's licence", "Photo of you"],
    field: "driver_license_file_id",
  },
  {
    Component: VehicleForm,
    files: ["Registration papers", "Insurance certificate", "Photo of the car"],
    field: "registration_file_id",
  },
];

describe.each(cases)("$field upload retry", ({ Component, files, field }) => {
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
    render(<Component />);
    fireEvent.change(screen.getByLabelText("Code from your email"), {
      target: { value: "first-access" },
    });
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

  it.each(["file", "access"])(
    "rebinds uploads and submission identity after changing %s",
    async (change) => {
      const form = setup();
      await fail(form);
      if (change === "file")
        fireEvent.change(screen.getByLabelText(files[0]!), {
          target: { files: [new File(["replacement"], "same.png", { type: "image/png" })] },
        });
      else
        fireEvent.change(screen.getByLabelText("Code from your email"), {
          target: { value: "second-access" },
        });
      fireEvent.submit(form);
      await screen.findByRole("status");
      expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length * 2);
      const bodies = vi
        .mocked(fetch)
        .mock.calls.map(([, init]) => JSON.parse(init!.body as string));
      expect(bodies[1][field]).not.toEqual(bodies[0][field]);
      expect(bodies[1].client_request_id).not.toEqual(bodies[0].client_request_id);
      if (change === "access")
        expect(
          vi
            .mocked(uploadOnboardingFile)
            .mock.calls.slice(files.length)
            .every(([token]) => token === "second-access"),
        ).toBe(true);
    },
  );

  it("cannot submit or cache stale uploads after a selection changes in flight", async () => {
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
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(files.length * 2);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0]![1]!.body as string)[field]).not.toBe(
      "obsolete-file",
    );
  });
});
