import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  submit: vi.fn(),
  upload: vi.fn(),
}));

vi.mock("./actions", () => ({
  replaceCreativeAndSubmitAction: mocks.replace,
  submitCreativeForReviewAction: mocks.submit,
}));
vi.mock("@/lib/files/creative-upload", () => ({ uploadCreativeFile: mocks.upload }));

import { CreativeStatusActions } from "./creative-status-actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const CREATIVE_ID = "00000000-0000-4000-8000-00000000000b";
const STORED_FILE_ID = "00000000-0000-4000-8000-00000000000c";
const FIRST_UPLOAD_ID = "00000000-0000-4000-8000-000000000001";
const SECOND_UPLOAD_ID = "00000000-0000-4000-8000-000000000002";

function renderActions(status: string) {
  return render(
    <CreativeStatusActions campaignId={CAMPAIGN_ID} creativeId={CREATIVE_ID} status={status} />,
  );
}

function wrap(name = "wrap.png", content = "artwork") {
  return new File([content], name, { type: "image/png", lastModified: 1 });
}

function chooseReplacement(file: File | undefined) {
  fireEvent.change(screen.getByLabelText("Replace artwork"), {
    target: { files: file ? [file] : [] },
  });
}

describe("CreativeStatusActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn().mockReturnValueOnce(FIRST_UPLOAD_ID).mockReturnValue(SECOND_UPLOAD_ID),
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ["pending_review", "Under admin review"],
    ["approved", "Admin approved"],
  ])("shows %s artwork as read-only review state", (status, copy) => {
    renderActions(status);
    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Replace artwork")).not.toBeInTheDocument();
  });

  it("offers no mutation for artwork outside draft or rejected review states", () => {
    const { container } = renderActions("archived");
    expect(container).toBeEmptyDOMElement();
  });

  it("submits the exact draft creative and shows the confirmed result", async () => {
    const user = userEvent.setup();
    mocks.submit.mockResolvedValue({ done: "Creative submitted for admin review." });
    renderActions("draft");

    await user.click(screen.getByRole("button", { name: "Submit creative" }));

    expect(await screen.findByText("✓ Creative submitted for admin review.")).toBeInTheDocument();
    const form = mocks.submit.mock.calls[0]?.[1] as FormData;
    expect(form.get("campaign_id")).toBe(CAMPAIGN_ID);
    expect(form.get("creative_id")).toBe(CREATIVE_ID);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disables resubmission while pending and keeps a failed resubmission visible", async () => {
    const user = userEvent.setup();
    let finish!: (state: { error: string }) => void;
    mocks.submit.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    renderActions("rejected");

    await user.click(screen.getByRole("button", { name: "Resubmit current artwork" }));
    expect(await screen.findByRole("button", { name: "Submitting…" })).toBeDisabled();

    finish({ error: "The creative state changed. Refresh and try again." });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The creative state changed. Refresh and try again.",
    );
    expect(screen.getByRole("button", { name: "Resubmit current artwork" })).toBeEnabled();
    expect(screen.queryByText(/✓/)).not.toBeInTheDocument();
  });

  it("does not start an upload when the file picker is dismissed", () => {
    renderActions("rejected");
    chooseReplacement(undefined);
    expect(mocks.upload).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Replace and submit" })).not.toBeInTheDocument();
  });

  it("offers replacement submission only after the upload passes its scan", async () => {
    const user = userEvent.setup();
    let release!: (value: { storedFileId: string; creativeType: "image" }) => void;
    mocks.upload.mockImplementation(
      (_file: File, onPhase: (phase: string) => void) =>
        new Promise((resolve) => {
          onPhase("scanning");
          release = resolve;
        }),
    );
    mocks.replace.mockResolvedValue({ done: "Replacement artwork submitted for admin review." });
    renderActions("rejected");
    const file = wrap();

    chooseReplacement(file);

    expect(await screen.findByText("scanning…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replace and submit" })).not.toBeInTheDocument();
    expect(mocks.upload).toHaveBeenCalledWith(file, expect.any(Function), {
      clientRequestId: FIRST_UPLOAD_ID,
    });

    release({ storedFileId: STORED_FILE_ID, creativeType: "image" });
    expect(await screen.findByText("✓ Replacement passed security scan")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Replace and submit" }));

    expect(
      await screen.findByText("✓ Replacement artwork submitted for admin review."),
    ).toBeInTheDocument();
    const form = mocks.replace.mock.calls[0]?.[1] as FormData;
    expect(Object.fromEntries(form.entries())).toEqual({
      campaign_id: CAMPAIGN_ID,
      creative_id: CREATIVE_ID,
      stored_file_id: STORED_FILE_ID,
      creative_type: "image",
    });
  });

  it("keeps a failed replacement submission retryable without hiding the cleared file", async () => {
    const user = userEvent.setup();
    let finish!: (state: { error: string }) => void;
    mocks.upload.mockResolvedValue({ storedFileId: STORED_FILE_ID, creativeType: "video" });
    mocks.replace.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    renderActions("draft");

    chooseReplacement(new File(["clip"], "clip.mp4", { type: "video/mp4" }));
    await user.click(await screen.findByRole("button", { name: "Replace and submit" }));
    expect(await screen.findByRole("button", { name: "Replacing…" })).toBeDisabled();

    finish({ error: "The artwork result is not yet confirmed." });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The artwork result is not yet confirmed.",
    );
    expect(screen.getByRole("button", { name: "Replace and submit" })).toBeEnabled();
    expect((mocks.replace.mock.calls[0]?.[1] as FormData).get("creative_type")).toBe("video");
  });

  it("reuses the upload identity when the same file is retried after a failure", async () => {
    mocks.upload
      .mockRejectedValueOnce(new Error("The security scan could not complete. Retry the upload."))
      .mockResolvedValueOnce({ storedFileId: STORED_FILE_ID, creativeType: "image" });
    renderActions("rejected");

    chooseReplacement(wrap());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The security scan could not complete. Retry the upload.",
    );
    expect(screen.queryByRole("button", { name: "Replace and submit" })).not.toBeInTheDocument();

    chooseReplacement(wrap());
    expect(await screen.findByText("✓ Replacement passed security scan")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(mocks.upload.mock.calls.map((call) => call[2])).toEqual([
      { clientRequestId: FIRST_UPLOAD_ID },
      { clientRequestId: FIRST_UPLOAD_ID },
    ]);
  });

  it("binds a different file to a new upload identity and hides non-error failure details", async () => {
    mocks.upload.mockRejectedValueOnce("storage host secret.internal").mockResolvedValueOnce({
      storedFileId: STORED_FILE_ID,
      creativeType: "image",
    });
    renderActions("rejected");

    chooseReplacement(wrap("first.png"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The replacement upload failed. Retry it.",
    );
    expect(screen.queryByText(/secret\.internal/)).not.toBeInTheDocument();

    chooseReplacement(wrap("second.png", "different artwork"));
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(2));
    expect(mocks.upload.mock.calls.map((call) => call[2])).toEqual([
      { clientRequestId: FIRST_UPLOAD_ID },
      { clientRequestId: SECOND_UPLOAD_ID },
    ]);
  });
});
