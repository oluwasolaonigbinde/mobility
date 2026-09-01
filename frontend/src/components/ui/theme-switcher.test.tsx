import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEMES } from "@/lib/themes";
import { ThemeSwitcher } from "./theme-switcher";

const pathname = vi.hoisted(() => ({ value: "/advertiser" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    pathname.value = "/advertiser";
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    delete document.documentElement.dataset.theme;
  });

  it("lists every registered direction, including Direction 9", async () => {
    const user = userEvent.setup();
    render(<ThemeSwitcher />);
    await user.click(screen.getByRole("button", { name: /Direction 1/ }));

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(THEMES.length);
    expect(screen.getByRole("option", { name: /Direction 9/ })).toBeInTheDocument();
  });

  it.each([
    ["Direction 7", "terra-grain"],
    ["Direction 8", "coverage"],
    ["Direction 9", "broadside"],
  ])("applies %s and marks it selected", async (name, slug) => {
    const user = userEvent.setup();
    render(<ThemeSwitcher />);
    await user.click(screen.getByRole("button", { name: /Direction 1/ }));
    await user.click(screen.getByRole("option", { name: new RegExp(name) }));

    expect(document.documentElement.dataset.theme).toBe(slug);
    expect(screen.getByRole("option", { name: new RegExp(name) })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("stays out of the driver PWA", () => {
    pathname.value = "/driver/track";
    const { container } = render(<ThemeSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
