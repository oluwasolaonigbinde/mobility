import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { HubNav } from "./hub-section";

it("keeps hub navigation in the page flow below the medium breakpoint", () => {
  render(<HubNav sections={[{ id: "documents", title: "Documents" }]} />);
  const nav = screen.getByRole("navigation", { name: "Page sections" });
  expect(nav).toHaveClass("md:sticky", "md:top-14");
  expect(nav).not.toHaveClass("sticky");
  expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "#documents");
});
