import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const ApplicationJourney = vi.hoisted(() =>
  vi.fn(({ requestedStep }: { requestedStep?: string }) => (
    <p>Journey step: {requestedStep ?? "none"}</p>
  )),
);
vi.mock("./application-journey", () => ({ ApplicationJourney }));

import ApplyPage from "./page";

async function renderStep(step?: string) {
  render(await ApplyPage({ searchParams: Promise.resolve(step ? { step } : {}) }));
}

describe("public driver application page", () => {
  it("shows the application journey with a sign-in link for existing drivers", async () => {
    await renderStep();

    expect(screen.getByRole("heading", { level: 1, name: "Apply to drive" })).toBeInTheDocument();
    expect(screen.getByText("Journey step: none")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Already have a driver account? Sign in" }),
    ).toHaveAttribute("href", "/login");
    expect(screen.queryByText("Drive the city.")).not.toBeInTheDocument();
  });

  it("passes the requested step to the journey, which decides what it may show", async () => {
    await renderStep("car");
    expect(screen.getByText("Journey step: car")).toBeInTheDocument();
  });
});
