import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RecordPhoneVerification } from "./record-phone-verification";
const mocks = vi.hoisted(() => ({ action: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));
vi.mock("./phone-verification-actions", () => ({ recordPhoneVerificationAction: mocks.action }));
beforeEach(() => {
  mocks.action.mockReset();
  mocks.refresh.mockClear();
});
function open() {
  render(<RecordPhoneVerification driverId="driver" challengeId="challenge" />);
  expect(screen.queryByLabelText("Code received")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Record phone verification" }));
  const code = screen.getByLabelText("Code received");
  expect(code).toHaveValue("");
  expect(code).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("Sender phone number, including country code")).toHaveValue("");
  return code.closest("form")!;
}
it("starts with empty received-message inputs and records success once", async () => {
  mocks.action.mockResolvedValue({ done: "Phone verified." });
  fireEvent.submit(open());
  await screen.findByText("Phone verified.");
  expect(screen.getByRole("button", { name: "Record verification" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Refresh phone status" }));
  expect(mocks.refresh).toHaveBeenCalledOnce();
});
it("shows a safe error and allows a correction", async () => {
  mocks.action.mockResolvedValue({ error: "The code or sender did not match." });
  fireEvent.submit(open());
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Record verification" })).toBeEnabled();
});
