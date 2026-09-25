import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
});
