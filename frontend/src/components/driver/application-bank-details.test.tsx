import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApplicationBankDetails } from "./application-bank-details";
import { BankPicker } from "./bank-picker";

const banks = [
  { code: "999992", name: "OPay" },
  { code: "50515", name: "Moniepoint" },
  { code: "058", name: "GTBank" },
  { code: "035", name: "Wema Bank" },
];
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.endsWith("/banks")
        ? Response.json(banks)
        : Response.json({
            outcome: "resolved",
            account_name: "TEST DRIVER",
            bank_check_receipt: "signed-check",
          }),
    ),
  );
});

async function fill() {
  await screen.findByRole("option", { name: "OPay" });
  fireEvent.change(screen.getByLabelText("Bank"), {
    target: { value: "999992" },
  });
  fireEvent.change(screen.getByLabelText("Account number (10 digits)"), {
    target: { value: "0123456789" },
  });
}

it("recovers a failed bank list fetch with the same picker", async () => {
  vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));
  render(<BankPicker />);
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Bank")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByRole("option", { name: "OPay" });
  expect(screen.getByLabelText("Bank")).toBeEnabled();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("retries an account check failure without granting manual entry", async () => {
  let checks = 0;
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (String(url).endsWith("/banks")) return Response.json(banks);
    if (++checks === 1)
      return Response.json({ error: { message: "Try again later" } }, { status: 503 });
    return Response.json({
      outcome: "resolved",
      account_name: "TEST DRIVER",
      bank_check_receipt: "retry-check",
    });
  });
  render(<ApplicationBankDetails accessToken="private-code" />);
  await fill();
  await screen.findByRole("alert");
  expect(screen.queryByLabelText("Name on bank account")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("Account name: TEST DRIVER. Is this you?");
  expect(checks).toBe(2);
});

it("searches the full shared list and keeps popular banks first", async () => {
  render(<BankPicker />);
  await screen.findByRole("option", { name: "OPay" });
  expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Choose your bank",
    "OPay",
    "Moniepoint",
    "GTBank",
    "Wema Bank",
  ]);
  fireEvent.change(screen.getByLabelText("Search banks"), {
    target: { value: "wema" },
  });
  expect(screen.queryByRole("option", { name: "OPay" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Bank"), { target: { value: "035" } });
  expect(screen.getByLabelText("Bank")).toHaveValue("035");
  fireEvent.change(screen.getByLabelText("Search banks"), {
    target: { value: "missing" },
  });
  expect(screen.getByRole("status")).toHaveTextContent("No banks found");
});

it("shows the resolved name and binds confirmation until an account edit", async () => {
  const { container } = render(<ApplicationBankDetails accessToken="private-code" />);
  await fill();
  await screen.findByText("Account name: TEST DRIVER. Is this you?");
  expect(screen.queryByLabelText("Name on bank account")).toBeNull();
  expect(
    container.querySelector<HTMLInputElement>("input[name=account_name_confirmed]")!.value,
  ).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "This is me" }));
  expect(
    container.querySelector<HTMLInputElement>("input[name=account_name_confirmed]")!.value,
  ).toBe("true");
  fireEvent.change(screen.getByLabelText("Account number (10 digits)"), {
    target: { value: "012345678" },
  });
  expect(screen.queryByText(/Account name:/)).toBeNull();
  expect(container.querySelector<HTMLInputElement>("input[name=bank_check_receipt]")!.value).toBe(
    "",
  );
});

it.each(["unavailable", "refused"])(
  "offers the private typed name after an authoritative %s outcome",
  async (outcome) => {
    vi.mocked(fetch).mockImplementation(async (url) =>
      String(url).endsWith("/banks")
        ? Response.json(banks)
        : Response.json({
            outcome,
            bank_check_receipt: "fallback",
          }),
    );
    const { container } = render(<ApplicationBankDetails accessToken="private-code" />);
    await fill();
    const name = await screen.findByLabelText("Name on bank account");
    expect(name).toBeRequired();
    expect(container.querySelector("input[name=bank_check_outcome]")).toHaveValue(outcome);
    expect(container.querySelector("input[name=bank_check_receipt]")).toHaveValue("fallback");
    expect(container.querySelector("input[name=account_name_confirmed]")).toHaveValue("false");
    expect(name).toHaveAttribute("data-feedback-private");
    expect(screen.getByRole("region", { name: "Bank details" })).toHaveAttribute(
      "data-feedback-private",
    );
    expect(screen.queryByRole("button", { name: "This is me" })).toBeNull();
  },
);

it.each([
  ["BANK_CHECK_INVALID", 422, "Check your bank and account details again"],
  ["BANK_CHECK_LIMITED", 429, "Too many bank checks. Try again shortly."],
  ["BANK_CHECK_LIMIT_UNAVAILABLE", 503, "Bank checks are paused for a moment. Try again shortly."],
])("does not offer typed name after %s (%s)", async (code, status, message) => {
  vi.mocked(fetch).mockImplementation(async (url) =>
    String(url).endsWith("/banks")
      ? Response.json(banks)
      : Response.json({ error: { code, message: "untrusted backend detail" } }, { status }),
  );
  render(<ApplicationBankDetails accessToken="private-code" />);
  await fill();
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByLabelText("Name on bank account")).toBeNull();
});

it("discards an in-flight name result after the bank or access code changes", async () => {
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementation(async (url) =>
    String(url).endsWith("/banks")
      ? Response.json(banks)
      : new Promise((resolve) => {
          finish = resolve;
        }),
  );
  const { rerender } = render(<ApplicationBankDetails accessToken="first-code" />);
  await fill();
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  rerender(<ApplicationBankDetails accessToken="second-code" />);
  finish(
    Response.json({
      outcome: "resolved",
      account_name: "STALE DRIVER",
      bank_check_receipt: "stale",
    }),
  );
  await waitFor(() => expect(screen.queryByText(/STALE DRIVER/)).toBeNull());
});

it("shows a Lagos retry time based on Retry-After", async () => {
  const now = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-21T08:58:30Z"));
  vi.mocked(fetch).mockImplementation(async (url) =>
    String(url).endsWith("/banks")
      ? Response.json(banks)
      : Response.json(
          { error: { code: "BANK_CHECK_LIMITED" } },
          { status: 429, headers: { "retry-after": "50" } },
        ),
  );
  try {
    render(<ApplicationBankDetails accessToken="private-code" />);
    await fill();
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again after 10:00");
    expect(screen.queryByLabelText("Name on bank account")).toBeNull();
  } finally {
    now.mockRestore();
  }
});

it("does not grant manual entry for an unrecognized outcome", async () => {
  vi.mocked(fetch).mockImplementation(async (url) =>
    String(url).endsWith("/banks")
      ? Response.json(banks)
      : Response.json({ outcome: "unknown", bank_check_receipt: "receipt" }),
  );
  const { container } = render(<ApplicationBankDetails accessToken="private-code" />);
  await fill();
  await waitFor(() =>
    expect(container.querySelector("input[name=bank_check_outcome]")).toHaveValue("unknown"),
  );
  expect(screen.queryByLabelText("Name on bank account")).toBeNull();
});
