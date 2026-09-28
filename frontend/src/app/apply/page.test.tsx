import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ApplyPage from "./page";

async function renderStep(step?: string) {
  render(await ApplyPage({ searchParams: Promise.resolve(step ? { step } : {}) }));
}

describe("public driver application page", () => {
  it("starts on step 1 and shows only the application forms", async () => {
    await renderStep();

    expect(screen.getByText("Cardvert // driver network")).toBeInTheDocument();
    const steps = screen.getByRole("navigation", { name: "Application steps" });
    expect(steps).toHaveTextContent(/1Apply.*2Your details.*3Your car/);
    expect(screen.getByRole("link", { current: "step" })).toHaveAttribute(
      "href",
      "/apply?step=apply",
    );
    expect(screen.getByRole("heading", { name: "Start an application" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Request a new onboarding code" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("NIN")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Vehicle registration")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next: Your details →" })).toHaveAttribute(
      "href",
      "/apply?step=details",
    );
    expect(
      screen.getByText(/No password, work access, assignment, payout or document access/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Vehicle approval never assigns campaign work automatically/),
    ).toBeInTheDocument();
  });

  it("shows only the details form on step 2, with the one-line onboarding status", async () => {
    await renderStep("details");

    expect(screen.getByLabelText("NIN")).toBeInTheDocument();
    expect(
      screen.getByText("Document upload opens once Terrax Media switches on driver onboarding."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/legal\/privacy wording/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Start an application" })).toBeNull();
    expect(screen.queryByLabelText("Vehicle registration")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next: Your car →" })).toBeInTheDocument();
  });

  it("shows only the car form on step 3, with a car chooser instead of an ID field", async () => {
    await renderStep("car");

    expect(
      screen.getByRole("heading", { name: "Submit or renew your pilot vehicle" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find my cars" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/vehicle ID/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("NIN")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Next:/ })).not.toBeInTheDocument();
  });

  it("falls back to step 1 for an unknown step", async () => {
    await renderStep("admin");
    expect(screen.getByRole("heading", { name: "Start an application" })).toBeInTheDocument();
  });
});
