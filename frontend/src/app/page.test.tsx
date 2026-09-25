import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import HomePage from "./page";

class IntersectionObserverStub {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}

it("lets keyboard users skip the marketing navigation to the main content", () => {
  vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);
  render(<HomePage />);

  const skip = screen.getByRole("link", { name: "Skip to content" });
  const main = screen.getByRole("main");
  expect(skip).toHaveAttribute("href", `#${main.id}`);
  expect(main.id).toBe("main");
});
