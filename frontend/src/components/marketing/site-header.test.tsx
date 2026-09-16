import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CONTACT, ROUTES } from "@/lib/marketing/site";
import { SiteHeader } from "./site-header";

describe("Terrax marketing header", () => {
  it("opens and closes its mobile disclosure with Escape", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);

    const button = screen.getByRole("button", { name: /open menu/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(screen.getAllByRole("navigation", { name: "Primary" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: /close menu/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: /open menu/i })).toHaveFocus();
  });

  it("exposes the product and acquisition paths in the mobile menu", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    await user.click(screen.getByRole("button", { name: /open menu/i }));

    const nav = screen.getAllByRole("navigation", { name: "Primary" }).at(-1);
    expect(nav).toBeDefined();
    if (!nav) throw new Error("mobile navigation was not rendered");
    expect(within(nav).getByRole("link", { name: "Open Cardvert" })).toHaveAttribute(
      "href",
      ROUTES.signIn,
    );
    expect(within(nav).getByRole("link", { name: "Start a Campaign" })).toHaveAttribute(
      "href",
      expect.stringContaining(`mailto:${CONTACT.email}?`),
    );
  });
});
