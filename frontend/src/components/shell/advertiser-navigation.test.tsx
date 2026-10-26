import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const path = vi.hoisted(() => ({ value: "/advertiser" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.value }));
import { AdvertiserNavigation } from "./advertiser-navigation";
const show = vi.fn(function (this: HTMLDialogElement) {
  this.setAttribute("open", "");
});
const close = vi.fn(function (this: HTMLDialogElement) {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
});
beforeEach(() => {
  vi.clearAllMocks();
  path.value = "/advertiser";
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: show,
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: close });
  window.matchMedia = vi
    .fn()
    .mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() });
});
it("opens a native modal left menu, then closes after choosing a destination", () => {
  render(<AdvertiserNavigation account={<button>Sign out</button>} />);
  fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
  expect(show).toHaveBeenCalledTimes(1);
  expect(document.body.style.overflow).toBe("hidden");
  expect(screen.getByRole("dialog", { name: "Menu" })).toHaveAttribute("open");
  fireEvent.click(screen.getByRole("button", { name: "Close menu" }));
  expect(document.body.style.overflow).toBe("");
  expect(screen.getByRole("button", { name: "Open menu" })).toHaveFocus();
});
it("restores body scrolling on unmount while the menu is open", () => {
  const view = render(<AdvertiserNavigation account={<span>Account</span>} />);
  fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
  view.unmount();
  expect(document.body.style.overflow).toBe("");
});
it("wraps Tab and Shift-Tab inside the phone menu", () => {
  render(<AdvertiserNavigation account={<button>Sign out</button>} />);
  fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
  const menu = screen.getByRole("dialog", { name: "Menu" });
  for (const control of menu.querySelectorAll("a,button")) {
    Object.defineProperty(control, "getClientRects", { value: () => ({ length: 1 }) });
  }
  const first = within(menu).getByRole("button", { name: "Close menu" });
  const last = within(menu).getByRole("button", { name: "Sign out" });
  last.focus();
  fireEvent.keyDown(last, { key: "Tab" });
  expect(first).toHaveFocus();
  fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
  expect(last).toHaveFocus();
});
it("keeps advanced planning out of the main side list", () => {
  render(<AdvertiserNavigation account={<span>Profile</span>} />);
  for (const name of ["Home", "Campaigns", "Billing", "Help", "Account"])
    expect(screen.getByRole("link", { name })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Retargeting" })).toBeNull();
});
it("lists Account once; its page holds company, people and password", () => {
  render(<AdvertiserNavigation account={<span>Signed in</span>} />);
  // The same list appears in the desktop sidebar and the phone menu; each lists Account once.
  expect(within(screen.getByRole("complementary")).getAllByText("Account")).toHaveLength(1);
  expect(within(screen.getByRole("dialog", { hidden: true })).getAllByText("Account")).toHaveLength(
    1,
  );
  expect(screen.queryByRole("link", { name: "People" })).toBeNull();
});
