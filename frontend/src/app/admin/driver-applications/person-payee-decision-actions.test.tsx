import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

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
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "open").mockReturnValue(null);
  mocks.read.mockResolvedValue({ sensitiveValue: "protected current identity" });
});

afterEach(() => vi.restoreAllMocks());

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
  for (const name of ["Identity (NIN)", "Driver’s licence", "Driver photo", "Bank account"]) {
    const row = within(screen.getByRole("region", { name }));
    expect(row.getByText("Not submitted")).toBeInTheDocument();
    expect(
      row.getByRole("button", {
        name:
          name === "Identity (NIN)"
            ? "Show NIN"
            : name === "Bank account"
              ? "Show account number"
              : "Open document",
      }),
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
])(
  "directly acknowledges and performs each existing logged read of %s",
  async (name, kind, idKey, id) => {
    const user = userEvent.setup();
    render(<PersonPayeeDecisionActions {...props} />);
    const row = within(screen.getByRole("region", { name }));
    const label =
      kind === "nin" ? "Show NIN" : kind === "account" ? "Show account number" : "Open document";
    if (kind === "document")
      mocks.read.mockResolvedValue({ downloadUrl: "https://example.invalid/doc" });
    expect(row.getByRole("button", { name: label })).toBeEnabled();
    expect(row.queryByRole("checkbox")).toBeNull();
    expect(mocks.read).not.toHaveBeenCalled();
    expect(mocks.read).not.toHaveBeenCalled();
    await user.click(row.getByRole("button", { name: label }));
    if (kind === "document") await row.findByRole("link", { name: "Open document" });
    else await row.findByText("protected current identity");
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
  await user.click(row.getByRole("button", { name: "Open document" }));
  const link = await row.findByRole("link", { name: "Open document" });
  expect(link).toHaveAttribute("href", "https://example.invalid/current-document");
  expect(link).toHaveAttribute("data-feedback-private");
  await user.click(row.getByRole("button", { name: "Hide" }));
  expect(row.queryByRole("link")).toBeNull();
  mocks.read.mockResolvedValueOnce({ error: "This document could not be opened." });
  await user.click(row.getByRole("button", { name: "Open document" }));
  await row.findByText("This document could not be opened.");
  expect(row.queryByRole("link")).toBeNull();
  expect(row.queryByText("protected current identity")).toBeNull();
});

it("discards revealed evidence and bank reference when current record IDs change", async () => {
  const user = userEvent.setup();
  mocks.read.mockResolvedValueOnce({ downloadUrl: "https://example.invalid/old-document" });
  const { rerender } = render(<PersonPayeeDecisionActions {...props} />);
  const photo = within(screen.getByRole("region", { name: "Driver photo" }));
  await user.click(photo.getByRole("button", { name: "Open document" }));
  await photo.findByRole("link");
  await user.type(
    screen.getByLabelText("Reference of the small test payment you sent to this account"),
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
  expect(current.getByRole("button", { name: "Open document" })).toBeEnabled();
  expect(current.queryByRole("checkbox")).toBeNull();
  expect(
    screen.getByLabelText("Reference of the small test payment you sent to this account"),
  ).toHaveValue("");
  expect(mocks.read).toHaveBeenCalledTimes(1);
  await user.click(current.getByRole("button", { name: "Open document" }));
  await waitFor(() => expect(mocks.read).toHaveBeenCalledTimes(2));
  const payload = mocks.read.mock.calls[1]![1] as FormData;
  expect(payload.get("file_id")).toBe("new-photo");
  expect(payload.get("submission_id")).toBe("new-submission");
});

it("keeps unavailable document rows and the exact bank reference requirements", () => {
  render(<PersonPayeeDecisionActions {...props} documentFileIds={{}} />);
  for (const name of ["Driver’s licence", "Driver photo"]) {
    const row = within(screen.getByRole("region", { name }));
    expect(row.getByText("Not submitted")).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Open document" })).toBeDisabled();
    expect(row.queryByRole("checkbox")).toBeNull();
  }
  const reference = screen.getByLabelText(
    "Reference of the small test payment you sent to this account",
  );
  expect(reference).toHaveAttribute("type", "text");
  expect(reference).toHaveAttribute("autocomplete", "off");
  expect(reference).toHaveAttribute("data-feedback-private");
  expect(reference).toHaveAccessibleDescription(/Send a small payment to the account shown above/);
  expect(reference).toHaveAttribute("minlength", "1");
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
  expect(
    within(screen.getByRole("region", { name: "Bank account" })).getByRole("status"),
  ).toHaveTextContent("Bank details checked.");
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
});

it("confirms a successful bank check after the page refreshes as checked", async () => {
  const user = userEvent.setup();
  mocks.verify.mockResolvedValue({
    done: "Bank details checked.",
    verifiedAt: "2026-11-21T08:15:00Z",
  });
  const { rerender } = render(<PersonPayeeDecisionActions {...props} />);
  const bank = within(screen.getByRole("region", { name: "Bank account" }));
  await user.type(
    bank.getByLabelText("Reference of the small test payment you sent to this account"),
    "REF-0001",
  );
  await user.click(bank.getByRole("button", { name: "Check bank details" }));
  await waitFor(() => expect(mocks.verify).toHaveBeenCalledTimes(1));

  // The successful action refreshes the page, which now reports the account as checked.
  rerender(<PersonPayeeDecisionActions {...props} bankAccountVerified />);

  const refreshed = within(screen.getByRole("region", { name: "Bank account" }));
  expect(refreshed.getByRole("status")).toHaveTextContent("Bank details checked on 21 Nov 2026");
  expect(refreshed.queryByRole("button", { name: "Check bank details" })).toBeNull();
  expect(
    refreshed.queryByLabelText("Reference of the small test payment you sent to this account"),
  ).toBeNull();
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
  await user.click(row.getByRole("button", { name: "Open document" }));
  expect(row.getByRole("button", { name: "Opening…" })).toBeDisabled();
  await user.click(row.getByRole("button", { name: "Hide" }));
  await user.click(row.getByRole("button", { name: "Open document" }));
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
  expect(screen.queryByRole("button", { name: "Mark expired" })).toBeNull();
  await user.selectOptions(screen.getByLabelText("Rejection reason"), "identity_mismatch");
  await user.click(screen.getByRole("button", { name: "Reject" }));
  await screen.findByText("Recorded");
  const payload = mocks.decide.mock.calls[0]![1] as FormData;
  expect(payload.get("intent")).toBe("reject");
  expect(payload.get("reason_code")).toBe("identity_mismatch");
});

it("keeps the reviewer's ticks, outcomes and dates after a refused Approve", async () => {
  const user = userEvent.setup();
  mocks.decide.mockResolvedValue({ error: "Check the bank details for payouts before approving." });
  render(<PersonPayeeDecisionActions {...props} />);
  await user.click(screen.getByLabelText("Identity matches"));
  await user.click(screen.getByLabelText("Account matches"));
  await user.click(screen.getByLabelText("Documents readable"));
  const outcomes = screen.getAllByLabelText("Outcome");
  await user.selectOptions(outcomes[0]!, "accepted");
  await user.selectOptions(outcomes[1]!, "replace");
  fireEvent.change(screen.getByLabelText("Driving licence expiry (if recorded)"), {
    target: { value: "2027-05-01" },
  });
  await user.click(screen.getByRole("button", { name: "Approve" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Check the bank details");
  const payload = mocks.decide.mock.calls[0]![1] as FormData;
  expect(payload.get("intent")).toBe("approve");
  expect(payload.get("identity_match_confirmed")).toBe("on");
  expect(screen.getByLabelText("Identity matches")).toBeChecked();
  expect(screen.getByLabelText("Account matches")).toBeChecked();
  expect(screen.getByLabelText("Documents readable")).toBeChecked();
  expect(screen.getAllByLabelText("Outcome")[0]).toHaveValue("accepted");
  expect(screen.getAllByLabelText("Outcome")[1]).toHaveValue("replace");
  expect(screen.getByLabelText("Driving licence expiry (if recorded)")).toHaveValue("2027-05-01");
});

it("keeps viewed evidence and decision choices when a bank check refreshes the page", async () => {
  const user = userEvent.setup();
  mocks.verify.mockResolvedValue({ done: "These bank details have been checked for payouts." });
  const { rerender } = render(<PersonPayeeDecisionActions {...props} />);
  const nin = within(screen.getByRole("region", { name: "Identity (NIN)" }));
  await user.click(nin.getByRole("button", { name: "Show NIN" }));
  await nin.findByText("protected current identity");
  await user.click(screen.getByLabelText("Identity matches"));
  await user.selectOptions(screen.getAllByLabelText("Outcome")[0]!, "accepted");
  const bank = within(screen.getByRole("region", { name: "Bank account" }));
  await user.type(
    bank.getByLabelText("Reference of the small test payment you sent to this account"),
    "REF-0001",
  );
  await user.click(bank.getByRole("button", { name: "Check bank details" }));
  await waitFor(() => expect(mocks.verify).toHaveBeenCalledTimes(1));
  rerender(<PersonPayeeDecisionActions {...props} bankAccountVerified />);
  expect(nin.getByText("protected current identity")).toBeInTheDocument();
  expect(screen.getByLabelText("Identity matches")).toBeChecked();
  expect(screen.getAllByLabelText("Outcome")[0]).toHaveValue("accepted");
});

it("shows the accepted agreement version and date without a document read", () => {
  render(
    <PersonPayeeDecisionActions
      {...props}
      agreementVersion="1"
      agreementAcceptedAt="2026-10-12T12:00:00Z"
    />,
  );
  const agreement = within(screen.getByRole("region", { name: "Driver agreement" }));
  expect(agreement.getByText("Agreed to version 1 on 12 Oct 2026")).toBeVisible();
  expect(agreement.queryByRole("button")).toBeNull();
});

it("marks the bank name and account name private alongside the visible bank reference", async () => {
  const user = userEvent.setup();
  mocks.read.mockResolvedValueOnce({
    accountName: "Ada Driver",
    bankName: "GTBank",
    sensitiveValue: "0123456789",
  });
  render(<PersonPayeeDecisionActions {...props} />);
  const bank = within(screen.getByRole("region", { name: "Bank account" }));
  await user.click(bank.getByRole("button", { name: "Show account number" }));
  expect(await bank.findByText("Ada Driver")).toHaveAttribute("data-feedback-private");
  expect(bank.getByText("GTBank")).toHaveAttribute("data-feedback-private");
  const reference = bank.getByLabelText(
    "Reference of the small test payment you sent to this account",
  );
  await user.type(reference, "PAYMENT-REF");
  expect(reference).toHaveDisplayValue("PAYMENT-REF");
});

it("counts every supplied document and keeps decision feedback when status refreshes", async () => {
  mocks.decide.mockResolvedValue({ done: "Identity and bank approved." });
  const user = userEvent.setup();
  const documentFileIds = { ...props.documentFileIds, another_file: "another-file-id" };
  const { rerender } = render(
    <PersonPayeeDecisionActions {...props} documentFileIds={documentFileIds} />,
  );
  const checklist = screen.getByRole("group", { name: "Identity and bank review checklist" });
  expect(checklist).toHaveTextContent("0 of 5 done");
  await user.click(screen.getByRole("button", { name: "Show NIN" }));
  await screen.findByText("protected current identity");
  expect(checklist).toHaveTextContent("1 of 5 done");
  await user.click(screen.getByRole("button", { name: "Hide" }));
  expect(checklist).toHaveTextContent("1 of 5 done");
  const row = within(screen.getByRole("region", { name: "document" }));
  mocks.read.mockResolvedValueOnce({ downloadUrl: "#document" });
  await user.click(row.getByRole("button", { name: "Open document" }));
  const link = await row.findByRole("link", { name: "Open document" });
  link.addEventListener("click", (event) => event.preventDefault());
  fireEvent.click(link);
  expect(checklist).toHaveTextContent("2 of 5 done");
  await user.click(screen.getByRole("button", { name: "Approve" }));
  await screen.findByText("Identity and bank approved.");
  rerender(
    <PersonPayeeDecisionActions {...props} documentFileIds={documentFileIds} status="approved" />,
  );
  expect(screen.getByText("Identity and bank approved.")).toBeVisible();
});

it("marks only a bank name explicitly unconfirmed by the bank", () => {
  const { rerender } = render(<PersonPayeeDecisionActions {...props} bankNameConfirmed={false} />);
  const row = within(screen.getByRole("region", { name: "Bank account" }));
  expect(row.getByText("Name not confirmed by the bank")).toBeVisible();
  expect(row.getByRole("button", { name: "Check bank details" })).toBeEnabled();
  rerender(<PersonPayeeDecisionActions {...props} bankNameConfirmed />);
  expect(row.queryByText("Name not confirmed by the bank")).toBeNull();
  rerender(<PersonPayeeDecisionActions {...props} bankNameConfirmed={null} />);
  expect(row.queryByText("Name not confirmed by the bank")).toBeNull();
});
