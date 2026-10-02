import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SiteHeader } from "./site-header";

describe("Terrax marketing header", () => {
  it("provides both audience actions and sign in, and closes on a mobile action", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Apply to drive" })).toHaveAttribute("href", "/apply");
    expect(screen.getByRole("link", { name: "Request a campaign quote" })).toHaveAttribute(
      "href",
      "#campaign-enquiry",
    );
    await user.click(screen.getByRole("button", { name: /open menu/i }));
    const menu = document.getElementById("primary-menu")!;
    await user.click(within(menu).getByRole("link", { name: "Apply to drive" }));
    expect(document.getElementById("primary-menu")).toBeNull();
  });
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
});
