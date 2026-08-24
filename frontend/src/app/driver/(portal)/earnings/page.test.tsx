import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import DriverEarningsPage from "./page";

describe("DriverEarningsPage debt settlement summary", () => {
  beforeEach(() => get.mockReset());

  it("renders batch-payable and carried debt as distinct values", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              {
                currency: "NGN",
                batch_payable_amount: "90.00",
                carry_forward_debt_amount: "60.00",
                lifetime_earned_amount: "190.00",
                pending_amount: "0.00",
              },
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return { data: { items: [] } };
    });

    render(await DriverEarningsPage());

    expect(screen.getByText("Batch-payable")).toBeInTheDocument();
    expect(screen.getByText("Carried debt")).toBeInTheDocument();
    expect(screen.getAllByText("₦90.00")).toHaveLength(1);
    expect(screen.getAllByText("₦60.00")).toHaveLength(1);
  });
});
