import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { PhoneVerification } from "./phone-verification";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const fetchMock = vi.fn();
const code = "485921";
const challenge = {
  id: "challenge",
  code,
  status: "pending",
  expires_at: new Date(Date.now() + 600000).toISOString(),
  terrax_number: "+447700900999",
};
const contact = {
  verification_available: true,
  phone: { verified: false, masked_phone: "+44••••0101" },
  challenge: { id: "challenge", status: "pending" },
};
function reply(value: unknown, status = 200) {
  return Promise.resolve(Response.json(value, { status }));
}
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  refresh.mockClear();
  fetchMock.mockImplementation((url: string) =>
    reply(url.endsWith("phone-verification") ? challenge : contact),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
});
it.each(["verified", "replaced", "expired"])(
  "does not redisplay delayed issuance after authoritative %s status",
  async (status) => {
    let release!: (response: Response) => void;
    render(<PhoneVerification savedPhone="+447700900101" />);
    const button = await screen.findByRole("button", { name: "Verify my phone" });
    fetchMock.mockImplementation((url: string) =>
      url.endsWith("phone-verification")
        ? new Promise<Response>((resolve) => {
            release = resolve;
          })
        : reply({
            ...contact,
            phone: { ...contact.phone, verified: status === "verified" },
            challenge: {
              id: status === "replaced" ? "new" : "challenge",
              status: status === "expired" ? "expired" : "pending",
            },
          }),
    );
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: "Check verification status" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    await act(async () => release(Response.json(challenge)));
    expect(screen.queryByText(code)).toBeNull();
  },
);

it("hides issuance without configured authority and shows loading safely", async () => {
  fetchMock.mockImplementation(() => reply({ ...contact, verification_available: false }));
  render(<PhoneVerification savedPhone="+447700900101" />);
  expect(screen.getByText("Checking phone status…")).toBeTruthy();
  await screen.findByText(/Not verified yet/);
  expect(screen.queryByRole("button", { name: "Verify my phone" })).toBeNull();
  expect(screen.queryByText(code)).toBeNull();
});
it("shows driver-only instructions, recovers same live code, hides on phone change and records verified refresh", async () => {
  const { rerender } = render(<PhoneVerification savedPhone="+447700900101" />);
  fireEvent.click(await screen.findByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  expect(screen.getByText(/Send this code by WhatsApp or SMS/)).toBeTruthy();
  expect(screen.getByText("+447700900999")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Hide code" }));
  expect(screen.queryByText(code)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  rerender(<PhoneVerification savedPhone="+447700900102" />);
  expect(screen.queryByText(code)).toBeNull();
  fetchMock.mockImplementation(() => reply({ ...contact, phone: { verified: true } }));
  fireEvent.click(await screen.findByRole("button", { name: "Check verification status" }));
  await screen.findByText("Your phone is verified.");
  expect(screen.queryByRole("button", { name: "Verify my phone" })).toBeNull();
});
it("clears expired code and explains exhausted challenges", async () => {
  fetchMock.mockImplementation((url: string) =>
    reply(
      url.endsWith("phone-verification")
        ? { ...challenge, expires_at: new Date(Date.now() - 100).toISOString() }
        : { ...contact, challenge: { status: "exhausted" } },
    ),
  );
  render(<PhoneVerification savedPhone="+447700900101" />);
  await screen.findByText(/previous code can no longer be used/);
  fireEvent.click(screen.getByRole("button", { name: "Verify my phone" }));
  await waitFor(() => expect(screen.queryByText(code)).toBeNull());
});
it("saves a changed phone, clears code and reports failed issuance without secret state", async () => {
  render(<PhoneVerification savedPhone="+447700900101" />);
  fireEvent.click(await screen.findByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  const input = screen.getByLabelText(/Your phone number/);
  fireEvent.change(input, { target: { value: "+447700900102" } });
  fireEvent.submit(input.closest("form")!);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/driver/contact/phone",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ phone: "+447700900102" }) }),
    ),
  );
  await waitFor(() => expect(screen.queryByText(code)).toBeNull());
  fetchMock.mockImplementation(() =>
    reply({ error: { message: "Verification unavailable" } }, 503),
  );
  fireEvent.click(screen.getByRole("button", { name: "Verify my phone" }));
  await screen.findByRole("alert");
  expect(screen.queryByText(code)).toBeNull();
});
it("clears code on backgrounding and handles initial load failure", async () => {
  const { unmount } = render(<PhoneVerification savedPhone="+447700900101" />);
  fireEvent.click(await screen.findByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(screen.queryByText(code)).toBeNull();
  unmount();
  fetchMock.mockRejectedValue(new Error("offline"));
  render(<PhoneVerification savedPhone="" />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Verify my phone" })).toBeNull();
});

it("replaces terminal status after requesting a fresh code without retaining a stale expiry hint", async () => {
  fetchMock.mockImplementation((url: string) =>
    reply(
      url.endsWith("phone-verification")
        ? challenge
        : { ...contact, challenge: { id: "old", status: "expired" } },
    ),
  );
  render(<PhoneVerification savedPhone="+447700900101" />);
  await screen.findByText(/previous code can no longer be used/);
  fireEvent.click(screen.getByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  expect(screen.queryByText(/previous code can no longer be used/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Hide code" }));
  expect(screen.queryByText(code)).toBeNull();
  expect(screen.queryByText(/previous code can no longer be used/)).toBeNull();
});

it("recognizes a saved number established by first issuance even after hiding the code", async () => {
  fetchMock.mockImplementation((url: string) =>
    reply(
      url.endsWith("phone-verification") ? challenge : { ...contact, phone: null, challenge: null },
    ),
  );
  render(<PhoneVerification savedPhone="+447700900101" />);
  await screen.findByText("Save your number before verifying it.");
  fireEvent.click(screen.getByRole("button", { name: "Verify my phone" }));
  await screen.findByText(code);
  expect(screen.queryByText("Save your number before verifying it.")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Hide code" }));
  expect(screen.getByText("Not verified yet.")).toBeTruthy();
  expect(screen.queryByText(code)).toBeNull();
});
