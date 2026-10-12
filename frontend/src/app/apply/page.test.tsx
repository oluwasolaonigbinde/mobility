import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ApplyPage from "./page";

async function renderStep(step?: string) {
  render(await ApplyPage({ searchParams: Promise.resolve(step ? { step } : {}) }));
}

describe("public driver application page", () => {
  it("starts on step 1 and shows only the application forms", async () => {
    await renderStep();

    expect(
      screen.getByRole("heading", { level: 1, name: "Start an application" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Cardvert // driver network")).not.toBeInTheDocument();
    expect(screen.queryByText("Drive the city.")).not.toBeInTheDocument();
    const steps = screen.getByRole("navigation", { name: "Application steps" });
    expect(steps).toHaveTextContent(/Apply.*Your details.*Your car/);
    expect(steps).toHaveTextContent("Your name and contact details");
    expect(screen.getByRole("link", { current: "step" })).toHaveAttribute(
      "href",
      "/apply?step=apply",
    );
    expect(screen.getByRole("heading", { name: "Your contact details" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Check application status" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Code not working? Get a new one" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("NIN (11 digits)")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Registration papers")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next: Your details →" })).toHaveAttribute(
      "href",
      "/apply?step=details",
    );
    expect(screen.getByRole("link", { name: "Already invited? Sign in →" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.queryByText(/No password, work access/)).not.toBeInTheDocument();
  });

  it("shows only the details form on step 2, with a way to get a new code", async () => {
    await renderStep("details");

    expect(screen.getByRole("link", { current: "step" })).toHaveAttribute(
      "href",
      "/apply?step=details",
    );
    expect(screen.getByRole("heading", { name: "Your ID and bank details" })).toBeInTheDocument();
    expect(screen.getByLabelText("NIN (11 digits)")).toBeInTheDocument();
    expect(screen.getByLabelText("Driver's licence")).toHaveAttribute("type", "file");
    expect(screen.queryByText(/switches on driver onboarding/)).not.toBeInTheDocument();
    expect(screen.queryByText(/malware/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your contact details" })).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Code not working? Get a new one" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Registration papers")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next: Your car →" })).toBeInTheDocument();
  });

  it("shows only the car form on step 3, with a car chooser instead of an ID field", async () => {
    await renderStep("car");

    expect(screen.getByRole("heading", { name: "Your car" })).toBeInTheDocument();
    expect(
      screen.getByText(/You can add your car after your ID and bank details are approved/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find my cars" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/vehicle ID/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("NIN (11 digits)")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Code not working? Get a new one" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Next:/ })).not.toBeInTheDocument();
  });

  it("falls back to step 1 for an unknown step", async () => {
    await renderStep("admin");
    expect(screen.getByRole("heading", { name: "Your contact details" })).toBeInTheDocument();
  });
});
