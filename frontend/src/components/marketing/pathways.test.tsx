import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Pathways } from "./pathways";

describe("driver pay introduction", () => {
  beforeEach(() =>
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        disconnect() {}
      },
    ),
  );
  afterEach(() => vi.unstubAllGlobals());
  it("explains the daily miles condition and shorter-day proportional pay beside the application link", () => {
    render(<Pathways />);
    const heading = screen.getByRole("heading", { name: "Earn from the miles you already drive" });
    const card = heading.closest("article")!;
    expect(within(card).getByText(/daily rate.*expected miles/)).toBeInTheDocument();
    expect(
      within(card).getByText(/Only miles inside the campaign area.*shorter days.*proportion/),
    ).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Apply to drive" })).toHaveAttribute(
      "href",
      "/apply",
    );
    expect(card).not.toHaveTextContent("₦");
  });
});
