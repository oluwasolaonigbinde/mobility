import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SiteHeader } from "./site-header";
import { CONTACT } from "./content";

/** jsdom has no matchMedia; the header queries it to drop the menu at desktop. */
function stubMatchMedia(matches = false) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    })),
  );
}

describe("SiteHeader", () => {
  beforeEach(() => {
    stubMatchMedia();
    document.body.style.overflow = "";
  });

  it("starts with the menu closed", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("button", { name: /open menu/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(document.querySelector(".tx-menu")).toBeNull();
  });

  it("opens the menu, locks scrolling and moves focus into it", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);

    await user.click(screen.getByRole("button", { name: /open menu/i }));

    const toggle = screen.getByRole("button", { name: /close menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.body.style.overflow).toBe("hidden");

    const panel = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(panel).not.toBeNull();
    expect(panel).toContainElement(document.activeElement as HTMLElement);
  });

  it("closes on Escape, restores scrolling and returns focus to the toggle", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    await user.keyboard("{Escape}");

    const toggle = screen.getByRole("button", { name: /open menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.body.style.overflow).toBe("");
    expect(toggle).toHaveFocus();
  });

  it("closes when a menu link is followed", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);

    await user.click(screen.getByRole("button", { name: /open menu/i }));
    const mobileNav = screen.getByRole("navigation", { name: /mobile/i });
    await user.click(within(mobileNav).getByRole("link", { name: "Cardvert" }));

    expect(screen.getByRole("button", { name: /open menu/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("points its call to action at the approved business address", () => {
    render(<SiteHeader />);
    const cta = screen.getByRole("link", { name: /start a campaign/i });
    expect(cta.getAttribute("href")).toContain(`mailto:${CONTACT.email}`);
  });
});
