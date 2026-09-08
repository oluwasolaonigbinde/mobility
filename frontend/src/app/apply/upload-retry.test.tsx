import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

vi.mock("@/lib/files/onboarding-upload", async (original) => ({
  ...(await original<object>()),
  uploadOnboardingFile: vi.fn(),
}));

const cases = [
  {
    Component: PersonPayeeForm,
    files: ["Driver licence", "Driver photo", "Signed agreement"],
    field: "driver_license_file_id",
  },
  {
    Component: VehicleForm,
    files: ["Vehicle registration", "Current insurance", "Vehicle photo"],
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
    fireEvent.change(screen.getByLabelText("Onboarding access code"), {
      target: { value: "first-access" },
    });
    files.forEach((label) =>
      fireEvent.change(screen.getByLabelText(label), {
        target: { files: [new File([label], "same.png", { type: "image/png" })] },
      }),
    );
    return screen.getByRole("button").closest("form")!;
  }

  async function fail(form: HTMLFormElement) {
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Submission failed");
  }

  it("reuses exact uploads and request identity on unchanged retry", async () => {
    const form = setup();
    await fail(form);
    fireEvent.submit(form);
    await screen.findByRole("status");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(3);
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
        fireEvent.change(screen.getByLabelText("Onboarding access code"), {
          target: { value: "second-access" },
        });
      fireEvent.submit(form);
      await screen.findByRole("status");
      expect(uploadOnboardingFile).toHaveBeenCalledTimes(6);
      const bodies = vi
        .mocked(fetch)
        .mock.calls.map(([, init]) => JSON.parse(init!.body as string));
      expect(bodies[1][field]).not.toEqual(bodies[0][field]);
      expect(bodies[1].client_request_id).not.toEqual(bodies[0].client_request_id);
      if (change === "access")
        expect(
          vi
            .mocked(uploadOnboardingFile)
            .mock.calls.slice(3)
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
    await waitFor(() => expect(uploadOnboardingFile).toHaveBeenCalledTimes(3));
    fireEvent.change(screen.getByLabelText(files[0]!), {
      target: { files: [new File(["new"], "same.png", { type: "image/png" })] },
    });
    release("obsolete-file");
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.submit(form);
    await screen.findByRole("alert");
    expect(uploadOnboardingFile).toHaveBeenCalledTimes(6);
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0]![1]!.body as string)[field]).not.toBe(
      "obsolete-file",
    );
  });
});
