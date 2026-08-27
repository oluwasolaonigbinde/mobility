import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ApplyPage from "./page";

describe("public driver application page", () => {
  it("uses the current Cardvert product name without changing the application boundary", () => {
    render(<ApplyPage />);

    expect(screen.getByText("Cardvert // driver network")).toBeInTheDocument();
    expect(screen.queryByText(/Vantage/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Start an application" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Submit your pilot vehicle" })).toBeInTheDocument();
    expect(
      screen.getByText(/Vehicle approval never assigns campaign work automatically/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/admin review and invitation.*sign in to the driver app/i),
    ).toBeInTheDocument();
  });
});
