import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ read: vi.fn(), decide: vi.fn(), verify: vi.fn() }));
vi.mock("./actions", () => ({
  reviewPersonPayeeEvidenceAction: mocks.read,
  reviewPersonPayeeAction: mocks.decide,
  verifyPersonPayeeAccountAction: mocks.verify,
}));
import { PersonPayeeDecisionActions } from "./person-payee-decision-actions";

const props = {
  applicationId: "application-id",
  submissionId: "submission-id",
  bankAccountVersionId: "bank-version-id",
  bankAccountVerified: false,
  documentFileIds: {
    driver_license: "licence-file-id",
    driver_photo: "photo-file-id",
    signed_agreement: "agreement-file-id",
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.read.mockResolvedValue({ sensitiveValue: "protected current identity" });
});

it("keeps all five rows without allowing reads or decisions when nothing is submitted", () => {
  render(
    <PersonPayeeDecisionActions
      {...props}
      submissionId={null}
      bankAccountVersionId={null}
      documentFileIds={{}}
      status="not_submitted"
    />,
  );
  for (const name of [
    "Identity (NIN)",
    "Driver’s licence",
    "Driver photo",
    "Signed agreement",
    "Bank account",
  ]) {
    const row = within(screen.getByRole("region", { name }));
    expect(row.getByText("Not submitted")).toBeInTheDocument();
    expect(
      row.getByRole("button", { name: name === "Identity (NIN)" ? "Show NIN" : "View" }),
    ).toBeDisabled();
  }
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Check bank details" })).toBeNull();
  expect(mocks.read).not.toHaveBeenCalled();
  expect(mocks.verify).not.toHaveBeenCalled();
});

it.each([
  ["Identity (NIN)", "nin", "submission_id", "submission-id"],
  ["Bank account", "account", "bank_account_version_id", "bank-version-id"],
  ["Driver’s licence", "document", "file_id", "licence-file-id"],
  ["Driver photo", "document", "file_id", "photo-file-id"],
  ["Signed agreement", "document", "file_id", "agreement-file-id"],
])(
  "directly acknowledges and performs each existing logged read of %s",
  async (name, kind, idKey, id) => {
    const user = userEvent.setup();
    render(<PersonPayeeDecisionActions {...props} />);
    const row = within(screen.getByRole("region", { name }));
    const label = kind === "nin" ? "Show NIN" : "View";
    expect(row.getByRole("button", { name: label })).toBeEnabled();
    expect(row.queryByRole("checkbox")).toBeNull();
    expect(mocks.read).not.toHaveBeenCalled();
    expect(mocks.read).not.toHaveBeenCalled();
    await user.click(row.getByRole("button", { name: label }));
    await row.findByText("protected current identity");
    expect(mocks.read).toHaveBeenCalledTimes(1);
    const form = mocks.read.mock.calls[0]![1] as FormData;
    expect(form.get("kind")).toBe(kind);
    expect(form.get(idKey)).toBe(id);
    if (kind === "document") expect(form.get("submission_id")).toBe("submission-id");
    await user.click(row.getByRole("button", { name: "Hide" }));
    expect(row.queryByText("protected current identity")).toBeNull();
    expect(row.getByRole("button", { name: label })).toBeEnabled();
    expect(row.queryByText("protected current identity")).toBeNull();
    await user.click(row.getByRole("button", { name: label }));
    await waitFor(() => expect(mocks.read).toHaveBeenCalledTimes(2));
  },
);

it("clears the document link on hide and presents failed reads without exposing data", async () => {
  const user = userEvent.setup();
  mocks.read.mockResolvedValueOnce({ downloadUrl: "https://example.invalid/current-document" });
  render(<PersonPayeeDecisionActions {...props} />);
  const row = within(screen.getByRole("region", { name: "Driver photo" }));
  await user.click(row.getByRole("button", { name: "View" }));
  expect(await row.findByRole("link")).toHaveAttribute(
    "href",
    "https://example.invalid/current-document",
  );
  await user.click(row.getByRole("button", { name: "Hide" }));
  expect(row.queryByRole("link")).toBeNull();
  mocks.read.mockResolvedValueOnce({ error: "This document could not be opened." });
  await user.click(row.getByRole("button", { name: "View" }));
  await row.findByText("This document could not be opened.");
  expect(row.queryByRole("link")).toBeNull();
  expect(row.queryByText("protected current identity")).toBeNull();
});

it("discards revealed evidence and bank reference when current record IDs change", async () => {
  const user = userEvent.setup();
  mocks.read.mockResolvedValueOnce({ downloadUrl: "https://example.invalid/old-document" });
  const { rerender } = render(<PersonPayeeDecisionActions {...props} />);
  const photo = within(screen.getByRole("region", { name: "Driver photo" }));
  await user.click(photo.getByRole("button", { name: "View" }));
  await photo.findByRole("link");
  await user.type(
    screen.getByLabelText("Bank check reference, from the bank confirmation"),
    "old-bank-reference",
  );
  rerender(
    <PersonPayeeDecisionActions
      {...props}
      submissionId="new-submission"
      bankAccountVersionId="new-bank-version"
      documentFileIds={{ ...props.documentFileIds, driver_photo: "new-photo" }}
    />,
  );
  const current = within(screen.getByRole("region", { name: "Driver photo" }));
  expect(current.queryByRole("link")).toBeNull();
  expect(current.getByRole("button", { name: "View" })).toBeEnabled();
  expect(current.queryByRole("checkbox")).toBeNull();
  expect(screen.getByLabelText("Bank check reference, from the bank confirmation")).toHaveValue("");
  expect(mocks.read).toHaveBeenCalledTimes(1);
  await user.click(current.getByRole("button", { name: "View" }));
  await waitFor(() => expect(mocks.read).toHaveBeenCalledTimes(2));
  const payload = mocks.read.mock.calls[1]![1] as FormData;
  expect(payload.get("file_id")).toBe("new-photo");
  expect(payload.get("submission_id")).toBe("new-submission");
});

it("keeps unavailable document rows and the exact bank reference requirements", () => {
  render(<PersonPayeeDecisionActions {...props} documentFileIds={{}} />);
  for (const name of ["Driver’s licence", "Driver photo", "Signed agreement"]) {
    const row = within(screen.getByRole("region", { name }));
    expect(row.getByText("Not submitted")).toBeInTheDocument();
    expect(row.getByRole("button", { name: "View" })).toBeDisabled();
    expect(row.queryByRole("checkbox")).toBeNull();
  }
  const reference = screen.getByLabelText("Bank check reference, from the bank confirmation");
  expect(reference).toHaveAttribute("type", "password");
  expect(reference).toHaveAttribute("minlength", "16");
  expect(reference).toHaveAttribute("maxlength", "512");
  expect(reference).toBeRequired();
  const bank = within(screen.getByRole("region", { name: "Bank account" }));
  expect(bank.getByRole("button", { name: "Check bank details" })).toBeInTheDocument();
  expect(
    reference.closest("form")?.querySelector("input[name=bank_account_version_id]"),
  ).toHaveValue("bank-version-id");
  expect(screen.getByRole("button", { name: "Approve" })).toHaveAttribute("value", "approve");
  expect(screen.getByRole("button", { name: "Reject" })).toHaveAttribute("value", "reject");
  expect(screen.getByLabelText("Rejection reason")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Rejection reason"), {
    target: { value: "identity_mismatch" },
  });
  expect(screen.getByLabelText("Rejection reason")).toHaveValue("identity_mismatch");
  expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
});

it.each([
  ["approved", "Approved"],
  ["rejected", "Rejected"],
  ["expired", "Expired"],
])("shows the combined %s decision separately from a bank check", (status, label) => {
  render(<PersonPayeeDecisionActions {...props} status={status} bankAccountVerified />);
  expect(
    within(screen.getByRole("region", { name: "Bank account" })).getByText(label),
  ).toBeInTheDocument();
  expect(screen.getByText("Bank details checked")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
});

it("does not restore an old response after hide and a newer logged read", async () => {
  const user = userEvent.setup();
  let oldResolve!: (value: { downloadUrl: string }) => void;
  let newResolve!: (value: { downloadUrl: string }) => void;
  mocks.read
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          oldResolve = resolve;
        }),
    )
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          newResolve = resolve;
        }),
    );
  render(<PersonPayeeDecisionActions {...props} />);
  const row = within(screen.getByRole("region", { name: "Driver photo" }));
  await user.click(row.getByRole("button", { name: "View" }));
  expect(row.getByRole("button", { name: "Opening…" })).toBeDisabled();
  await user.click(row.getByRole("button", { name: "Hide" }));
  await user.click(row.getByRole("button", { name: "View" }));
  await act(async () => {
    newResolve({ downloadUrl: "https://example.invalid/new" });
  });
  await act(async () => {
    oldResolve({ downloadUrl: "https://example.invalid/old" });
  });
  expect(await row.findByRole("link")).toHaveAttribute("href", "https://example.invalid/new");
  expect(mocks.read).toHaveBeenCalledTimes(2);
});

it("requires a chosen reason only for Reject and posts the selected reason", async () => {
  const user = userEvent.setup();
  mocks.decide.mockResolvedValue({ done: "Recorded" });
  render(<PersonPayeeDecisionActions {...props} />);
  expect(screen.getByLabelText("Rejection reason")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Mark expired" })).toBeEnabled();
  await user.selectOptions(screen.getByLabelText("Rejection reason"), "identity_mismatch");
  await user.click(screen.getByRole("button", { name: "Reject" }));
  await screen.findByText("Recorded");
  const payload = mocks.decide.mock.calls[0]![1] as FormData;
  expect(payload.get("intent")).toBe("reject");
  expect(payload.get("reason_code")).toBe("identity_mismatch");
});
