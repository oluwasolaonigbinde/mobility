import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
import { HubDrawer } from "./hub-drawer";
beforeEach(() => {
  push.mockReset();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    }),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    }),
  });
});
it("focuses the named drawer's Close button and restores the opening control on unmount", () => {
  const trigger = document.createElement("button");
  document.body.append(trigger);
  trigger.focus();
  const view = render(
    <HubDrawer title="Trip details" closeHref="/admin/drivers/driver#trips-and-pay">
      <p>Trip evidence</p>
    </HubDrawer>,
  );
  expect(screen.getByRole("dialog", { name: "Trip details" })).toHaveTextContent("Trip evidence");
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  view.unmount();
  expect(trigger).toHaveFocus();
  trigger.remove();
});
it("closes to the hub's selected section without a page scroll", async () => {
  render(
    <HubDrawer title="Trip details" closeHref="/admin/drivers/driver#trips-and-pay">
      Evidence
    </HubDrawer>,
  );
  await userEvent.setup().click(screen.getByRole("button", { name: "Close" }));
  expect(push).toHaveBeenCalledWith("/admin/drivers/driver#trips-and-pay", { scroll: false });
});
it("Escape follows the same close destination instead of leaving a stale drawer URL", () => {
  render(
    <HubDrawer title="Trip details" closeHref="/admin/drivers/driver#trips-and-pay">
      Evidence
    </HubDrawer>,
  );
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
  expect(push).toHaveBeenCalledWith("/admin/drivers/driver#trips-and-pay", { scroll: false });
});
