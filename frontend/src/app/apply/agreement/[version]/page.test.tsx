import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NOT_FOUND");
  },
}));

import AgreementPage from "./page";

it("renders the current agreement and its trip-only GPS terms", async () => {
  render(await AgreementPage({ params: Promise.resolve({ version: "1" }) }));
  expect(screen.getByRole("heading", { name: "Driver agreement" })).toBeInTheDocument();
  expect(screen.getByText("Terrax Media · Version 1")).toBeInTheDocument();
  expect(screen.getByText(/GPS is tracked only while you are on a trip/)).toBeInTheDocument();
  expect(screen.queryByText(/draft|placeholder/i)).toBeNull();
});

it.each(["2", "constructor", "__proto__"])(
  "returns not found for unsupported version %s",
  async (version) => {
    await expect(AgreementPage({ params: Promise.resolve({ version }) })).rejects.toThrow(
      "NOT_FOUND",
    );
  },
);
