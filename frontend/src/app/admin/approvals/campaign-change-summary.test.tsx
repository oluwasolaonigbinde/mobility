import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CampaignChangeSummary } from "./campaign-change-summary";

it("shows dates, budgets, the advertiser's reason and the funding effect", () => {
  render(
    <CampaignChangeSummary
      currency="NGN"
      change={{
        status: "pending_funding",
        requested_liability_amount: "25000.00",
        impact_preview: {
          request_reason: "Keep the advert running for the launch",
          before: {
            start_at: "2026-10-01T00:00:00Z",
            end_at: "2026-10-24T00:00:00Z",
            budget_amount: "100000.00",
            daily_budget_amount: "5000.00",
          },
          after: {
            start_at: "2026-10-01T00:00:00Z",
            end_at: "2026-10-31T00:00:00Z",
            budget_amount: "125000.00",
            daily_budget_amount: "6000.00",
          },
        },
      }}
    />,
  );
  expect(screen.getByText(/Keep the advert running/)).toBeVisible();
  expect(screen.getByText("₦100,000.00 → ₦125,000.00")).toBeVisible();
  expect(screen.getByText("₦5,000.00 → ₦6,000.00")).toBeVisible();
  expect(screen.getByText(/24 Oct 2026 → 31 Oct 2026/)).toBeVisible();
  expect(screen.getByText("₦25,000.00 · Waiting for funding")).toBeVisible();
  expect(document.body).not.toHaveTextContent(/car count|vehicles/i);
});
