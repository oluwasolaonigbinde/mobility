import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ApplyPage from "./page";

describe("public driver application page", () => {
  it("uses the current Cardvert product name without changing the application boundary", () => {
    render(<ApplyPage />);

    expect(screen.getByText("Cardvert // driver network")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Start an application" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Request a new onboarding code" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Submit or renew your pilot vehicle" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Vehicle approval never assigns campaign work automatically/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/administrator separately starts account setup.*then sign in/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Wait for person/payee approval")).toBeInTheDocument();
    expect(screen.getByText("Submit vehicle evidence after approval")).toBeInTheDocument();
    expect(
      screen.getByText(/vehicle evidence is accepted only after person and payee approval/i),
    ).toBeInTheDocument();
  });
});
