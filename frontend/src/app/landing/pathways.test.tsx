import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pathways } from "./pathways";
import { CONTACT } from "./content";

describe("Pathways", () => {
  it("shows the brand side first, with only the selected tab focusable", () => {
    render(<Pathways />);

    const brands = screen.getByRole("tab", { name: "For brands" });
    const drivers = screen.getByRole("tab", { name: "For drivers" });

    expect(brands).toHaveAttribute("aria-selected", "true");
    expect(drivers).toHaveAttribute("aria-selected", "false");
    expect(brands.tabIndex).toBe(0);
    expect(drivers.tabIndex).toBe(-1);
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("For brands");
  });

  it("switches to the driver side on click and swaps the call to action", async () => {
    const user = userEvent.setup();
    render(<Pathways />);

    await user.click(screen.getByRole("tab", { name: "For drivers" }));

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAccessibleName("For drivers");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      /get paid for the driving/i,
    );

    const cta = screen.getByRole("link", { name: /apply to drive/i });
    expect(cta.getAttribute("href")).toContain(`mailto:${CONTACT.email}`);
    expect(decodeURIComponent(cta.getAttribute("href") ?? "")).toContain("Driver application");
  });

  it("moves between tabs with the arrow keys and wraps around", async () => {
    const user = userEvent.setup();
    render(<Pathways />);

    const brands = screen.getByRole("tab", { name: "For brands" });
    brands.focus();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "For drivers" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("For drivers");

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "For brands" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("For brands");

    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "For drivers" })).toHaveFocus();
  });

  it("never advertises mileage-based driver pay", async () => {
    const user = userEvent.setup();
    render(<Pathways />);
    await user.click(screen.getByRole("tab", { name: "For drivers" }));

    const text = screen.getByRole("tabpanel").textContent ?? "";
    expect(text).toMatch(/hourly amount/i);
    expect(text).not.toMatch(/per kilometre|per km|mileage/i);
  });
});
