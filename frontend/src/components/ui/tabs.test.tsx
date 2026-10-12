import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ViewTabs } from "./tabs";

const originalScroll = HTMLElement.prototype.scrollIntoView;
afterEach(() => {
  HTMLElement.prototype.scrollIntoView = originalScroll;
});

it("keeps the newly selected view visible when navigation reuses the tabs", () => {
  const scrolled: string[] = [];
  HTMLElement.prototype.scrollIntoView = vi.fn(function (this: HTMLElement) {
    scrolled.push(this.textContent ?? "");
  });
  const items = [
    { href: "/first", label: "First", active: true },
    { href: "/last", label: "Last", active: false },
  ];
  const { rerender } = render(<ViewTabs label="Views" items={items} />);
  expect(scrolled).toEqual(["First"]);
  rerender(
    <ViewTabs
      label="Views"
      items={items.map((item) => ({ ...item, active: item.href === "/last" }))}
    />,
  );
  expect(screen.getByRole("link", { name: "Last" })).toHaveAttribute("aria-current", "page");
  expect(scrolled).toEqual(["First", "Last"]);
});
