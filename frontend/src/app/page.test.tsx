import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";
import { CONTACT, NAV } from "@/lib/marketing/site";

class IntersectionObserverStub {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}

describe("public Terrax landing page", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);
  });

  it("renders as a public page with the three truthful conversion paths", () => {
    render(<HomePage />);

    for (const link of screen.getAllByRole("link", {
      name: /start a campaign|advertise with terrax|launch a campaign/i,
    })) {
      expect(link).toHaveAttribute("href", expect.stringContaining(`mailto:${CONTACT.email}?`));
    }

    for (const link of screen.getAllByRole("link", {
      name: /drive & earn|become a driver partner|join as a driver|apply to drive/i,
    })) {
      expect(link).toHaveAttribute("href", "/apply");
    }

    for (const link of screen.getAllByRole("link", { name: /open cardvert/i })) {
      expect(link).toHaveAttribute("href", "/login");
    }
  });

  it("keeps every informational navigation target on the page", () => {
    const { container } = render(<HomePage />);
    for (const item of NAV) {
      expect(item.href).toMatch(/^#/);
      expect(container.querySelector(item.href)).not.toBeNull();
    }
  });

  it("uses the isolated landing namespace", () => {
    const { container } = render(<HomePage />);
    expect(container.firstElementChild).toHaveClass("terrax-site");
    expect(container.querySelector("[class*='bg-terrax-']")).not.toBeNull();
  });
});
