import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEMES } from "@/lib/themes";
import { ThemeSwitcher } from "./theme-switcher";

const pathname = vi.hoisted(() => ({ value: "/advertiser" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

const exactName = (name: string) => new RegExp(`^${name}\\s*·?$`);

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    pathname.value = "/advertiser";
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    delete document.documentElement.dataset.theme;
  });

  it("lists every registered direction, including the newest", async () => {
    const user = userEvent.setup();
    render(<ThemeSwitcher />);
    await user.click(screen.getByRole("button", { name: exactName("Direction 1") }));

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(THEMES.length);
    // The popover stays reachable at short viewport heights.
    const popover = screen.getByRole("listbox").parentElement;
    expect(popover).toHaveClass("overflow-y-auto", "max-h-[calc(100dvh-6rem)]");
    for (const theme of THEMES) {
      expect(screen.getByRole("option", { name: exactName(theme.name) })).toBeInTheDocument();
    }
  });

  it.each([
    ["Direction 1", "ivory-ledger"],
    ["Direction 2", "broadside"],
    ["Direction 3", "dispatch"],
    ["Direction 4", "ledger"],
    ["Direction 5", "route"],
    ["Direction 6", "wrap"],
  ])("applies %s and marks it selected", async (name, slug) => {
    const user = userEvent.setup();
    const exact = exactName(name);
    render(<ThemeSwitcher />);
    await user.click(screen.getByRole("button", { name: exactName("Direction 1") }));
    await user.click(screen.getByRole("option", { name: exact }));

    expect(document.documentElement.dataset.theme).toBe(slug);
    expect(screen.getByRole("option", { name: exact })).toHaveAttribute("aria-selected", "true");
  });

  it("stays out of the driver PWA", () => {
    pathname.value = "/driver/track";
    const { container } = render(<ThemeSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });

  it("stays off the public landing route", () => {
    pathname.value = "/";
    const { container } = render(<ThemeSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
