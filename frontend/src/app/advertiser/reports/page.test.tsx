import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ role: vi.fn(), load: vi.fn() }));

vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: vi.fn() }) }));
vi.mock("@/lib/advertiser/page-data", () => ({ loadAllAdvertiserPages: mocks.load }));
vi.mock("./report-list", () => ({
  Reports: ({ campaigns }: { campaigns: { id: string; name: string }[] }) => (
    <select aria-label="Campaign">
      {campaigns.map((campaign) => (
        <option key={campaign.id} value={campaign.id}>
          {campaign.name}
        </option>
      ))}
    </select>
  ),
}));

import ReportsPage from "./page";

describe("ReportsPage campaign choices", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.role.mockResolvedValue({
      user: { id: "owner" },
      advertiser_organization: { id: "company" },
    });
  });

  it("offers only campaigns that have started running", async () => {
    const campaign = (name: string, status: string, start_at: string | null) => ({
      id: name,
      name,
      status,
      start_at,
    });
    mocks.load.mockResolvedValue({
      available: true,
      data: [
        campaign("Running", "active", "2026-01-01T08:00:00Z"),
        campaign("Paused", "paused", "2026-01-01T08:00:00Z"),
        campaign("Finished", "finished", "2026-01-01T08:00:00Z"),
        campaign("Stopped", "cancelled", "2026-01-01T08:00:00Z"),
        campaign("Draft", "draft", "2026-01-01T08:00:00Z"),
        campaign("Awaiting payment", "awaiting_payment", "2026-01-01T08:00:00Z"),
        campaign("Undated", "active", null),
        campaign("Starts later", "active", "2099-01-01T08:00:00Z"),
      ],
    });

    render(await ReportsPage());

    expect(screen.getByRole("heading", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Running",
      "Paused",
      "Finished",
      "Stopped",
    ]);
  });

  it("shows a retry when the campaign list can't be loaded", async () => {
    mocks.load.mockResolvedValue({ available: false, reason: "unavailable" });

    render(await ReportsPage());

    expect(screen.getByText("Reports unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });
});
