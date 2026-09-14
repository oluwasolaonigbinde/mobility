import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DriverAccountSetupPage, { metadata } from "./page";

describe("DriverAccountSetupPage", () => {
  it("presents an authorized one-use setup action without implying activation by the form", async () => {
    render(
      await DriverAccountSetupPage({
        searchParams: Promise.resolve({ token: "private-one-use-token" }),
      }),
    );

    expect(screen.getByRole("heading", { name: "Set up your driver account" })).toBeInTheDocument();
    expect(screen.getByText(/does not sign you in or assign campaign work/i)).toBeInTheDocument();
    expect(metadata.referrer).toBe("no-referrer");
  });

  it("fails closed when the setup authority is missing", async () => {
    render(await DriverAccountSetupPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("alert")).toHaveTextContent("This setup action is incomplete");
    expect(screen.queryByRole("button", { name: "Set password" })).not.toBeInTheDocument();
  });
});
