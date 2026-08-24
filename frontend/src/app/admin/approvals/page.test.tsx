import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import AdminApprovalsPage from "./page";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const EVENT_ID = "00000000-0000-4000-8000-00000000000b";

describe("AdminApprovalsPage", () => {
  beforeEach(() => get.mockReset());

  it("loads the pending queue with each campaign's immutable review history", async () => {
    get
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: CAMPAIGN_ID,
              name: "Rainy season launch",
              description: "Waterproof taxi wraps.",
              status: "pending_review",
              organization: { name: "Acme Ads" },
              start_at: "2026-09-01T08:00:00Z",
              end_at: "2026-09-30T20:00:00Z",
              budget_amount: "500000",
              currency: "NGN",
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        },
      })
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: EVENT_ID,
              campaign_id: CAMPAIGN_ID,
              actor_user_id: "00000000-0000-4000-8000-00000000000c",
              prior_status: "draft",
              new_status: "pending_review",
              rejection_reason: null,
              reviewed_snapshot: { name: "Rainy season launch" },
              reviewed_snapshot_sha256: "a".repeat(64),
              submission_event_id: null,
              created_at: "2026-08-24T10:00:00Z",
            },
          ],
          total: 1,
          limit: 10,
          offset: 0,
        },
      });

    render(await AdminApprovalsPage());

    const card = screen.getByTestId(`campaign-approval-${CAMPAIGN_ID}`);
    expect(within(card).getAllByText("Pending review", { exact: true })).toHaveLength(2);
    expect(within(card).getByText("Acme Ads")).toBeInTheDocument();
    expect(within(card).getByText(/Draft → Pending review/)).toBeInTheDocument();
    expect(within(card).getByText(/Snapshot SHA-256/)).toBeInTheDocument();
    expect(within(card).getByLabelText("Rejection reason")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(get).toHaveBeenNthCalledWith(1, "/api/v1/admin/campaigns/pending-review", {
      params: { query: { limit: 25, offset: 0 } },
    });
    expect(get).toHaveBeenNthCalledWith(2, "/api/v1/admin/campaigns/{campaign_id}/review-history", {
      params: { path: { campaign_id: CAMPAIGN_ID }, query: { limit: 10, offset: 0 } },
    });
  });

  it("does not request history when the pending queue is empty", async () => {
    get.mockResolvedValue({ data: { items: [], total: 0, limit: 25, offset: 0 } });

    render(await AdminApprovalsPage());

    expect(screen.getByText("No campaigns awaiting review")).toBeInTheDocument();
    expect(get).toHaveBeenCalledOnce();
  });
});
