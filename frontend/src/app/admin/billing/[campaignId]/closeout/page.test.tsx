import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MoneyCloseoutPage from "./page";
const api = vi.hoisted(() => vi.fn());
vi.mock("../../../payouts/batches/batch-api", () => ({ batchApi: api }));
const props = {
  params: Promise.resolve({ campaignId: "campaign" }),
  searchParams: Promise.resolve({}),
};
const position = {
  campaign_name: "Named campaign",
  items: [],
  cancellation: null,
  settlements: [],
  total: 0,
  settlements_total: 0,
  external_blockers: ["Physical removal requires evidence"],
};

describe("recorded campaign money position", () => {
  beforeEach(() => vi.resetAllMocks());
  it("does not infer cancellation, settlements or completion from an empty position", async () => {
    api.mockResolvedValue(position);
    render(await MoneyCloseoutPage(props));
    expect(screen.getByText("No cancellation has been recorded.")).toBeVisible();
    expect(screen.getByText("No settlement has been recorded on this page.")).toBeVisible();
    expect(screen.getByText(/do not confirm physical removal/)).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("shows backend currency amounts and explicitly labels cross-campaign debt", async () => {
    api.mockResolvedValue({
      ...position,
      total: 60,
      settlements_total: 60,
      cancellation: {
        cutoff_at: "2026-09-14T10:00:00Z",
        disposition: "recorded_refund",
        currency: "NGN",
        refundable_amount: "12.03",
      },
      settlements: [
        {
          id: "settlement",
          disposition: "recorded_refund",
          amount: "12.03",
          currency: "NGN",
          recorded_at: "2026-09-14T10:00:00Z",
        },
      ],
      items: [
        {
          driver_profile_id: "driver",
          driver_name: "Ada Driver",
          currency: "NGN",
          earned_net: "100.07",
          unbatched_available: "20.01",
          reserved: "30.02",
          in_flight: "40.03",
          terminal_failed: "0.00",
          cash_paid: "10.01",
          provider_verified_paid: "20.02",
          driver_wide_debt: "5.04",
        },
      ],
    });
    render(await MoneyCloseoutPage({ ...props, searchParams: Promise.resolve({ page: "1" }) }));
    expect(api).toHaveBeenCalledWith("/campaigns/campaign/position?limit=25&offset=25");
    expect(screen.getByText("Economic ledger paid: ₦10.01")).toBeVisible();
    expect(screen.getByText("Verified provider transfers: ₦20.02")).toBeVisible();
    expect(screen.getByText("Unresolved provider exposure: ₦40.03")).toBeVisible();
    expect(screen.getByText(/Economic ledger totals count each credit once/)).toBeVisible();
    expect(screen.getByText("Driver-wide carry-forward debt (all campaigns): ₦5.04")).toBeVisible();
    expect(screen.getByText("Physical removal requires evidence")).toBeVisible();
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "?page=2");
  });
});
