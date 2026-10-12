import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "driver-session" }));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
}));
vi.mock("@/components/complaints/complainant-pages", () => ({
  ComplaintHelpPage: ({ party, driverPayText }: { party: string; driverPayText: string }) => (
    <section aria-label={`${party} help`}>{driverPayText}</section>
  ),
}));
import Help from "./page";

beforeEach(() => {
  mocks.get.mockReset();
});
afterEach(cleanup);

it.each(["0.0000", "0.5000"])(
  "explains the actual proportional job rate with outside-area weight %s",
  async (outsideAreaWeight) => {
    mocks.get.mockResolvedValue({
      data: {
        assignment: {
          offer_terms: {
            payout: {
              formula_version: "payout_v4",
              shortfall_strategy: "proportional",
              daily_rate_naira: "10000.00",
              daily_target_miles: "70",
              outside_area_weight: outsideAreaWeight,
            },
          },
        },
      },
    });
    render(await Help());
    expect(screen.getByRole("region", { name: "driver help" })).toHaveTextContent(
      `Your day rate is ₦10,000.00 for 70 miles${outsideAreaWeight === "0.0000" ? " inside the campaign area" : ""}; shorter days earn a proportional share, up to the day rate.`,
    );
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/driver/campaign-assignments/active");
  },
);

it.each([
  {},
  { assignment: null },
  { assignment: { offer_terms: {} } },
  { assignment: { offer_terms: { payout: { formula_version: "payout_v3" } } } },
  {
    assignment: {
      offer_terms: {
        payout: { formula_version: "payout_v4", shortfall_strategy: "per_mile_deduction" },
      },
    },
  },
])("does not invent pay values when there is no accepted daily-rate offer: %j", async (data) => {
  mocks.get.mockResolvedValue({ data });
  render(await Help());
  expect(screen.getByText(/Your accepted job keeps its agreed pay terms/)).toBeVisible();
  expect(screen.queryByText(/Your day rate is/)).not.toBeInTheDocument();
});

it("keeps support available when the pay read fails, without presenting a fabricated rate", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "Unavailable" }));
  render(await Help());
  expect(screen.getByText(/contact support for help with your calculation/)).toBeVisible();
  expect(screen.queryByText(/Your day rate is/)).not.toBeInTheDocument();
});

it("redirects an expired session before returning driver help", async () => {
  mocks.get.mockRejectedValue(new ApiError(401, { code: "UNAUTHORIZED", message: "Sign in" }));
  await expect(Help()).rejects.toThrow("redirect:/login");
});
