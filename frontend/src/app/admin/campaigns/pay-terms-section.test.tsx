import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("../payouts/rules/actions", () => ({
  publishDailyRateAction: vi.fn(),
  createRevisionAction: vi.fn(),
  saveRuleAction: vi.fn(),
}));
vi.mock("../payouts/rules/rule-form", () => ({
  RuleForm: () => <p>hourly or legacy rule form</p>,
}));
vi.mock("../payouts/rules/revisions-panel", () => ({
  RevisionsPanel: () => <p>hourly revisions panel</p>,
}));
vi.mock("../payouts/rules/daily-rate-panel", () => ({
  DailyRatePanel: ({
    publishingEnabled,
    revisions,
  }: {
    publishingEnabled: boolean;
    revisions: unknown[];
  }) => (
    <p>
      daily rate panel · switched {publishingEnabled ? "on" : "off"} · {revisions.length} revisions
    </p>
  ),
}));

import PayTermsSection from "./pay-terms-section";

const CAMPAIGN = { id: "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f", name: "Wuse Blitz" };

function api({
  rule,
  status = true,
  failStatus = false,
  failRevisions = false,
}: {
  rule?: { id: string; status: string; formula_version: string };
  status?: boolean;
  failStatus?: boolean;
  failRevisions?: boolean;
}) {
  mocks.get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/admin/campaigns") return { data: { items: [CAMPAIGN] } };
    if (path === "/api/v1/admin/campaigns/{campaign_id}/payout-rules") {
      return { data: { items: rule ? [rule] : [] } };
    }
    if (path.endsWith("/revisions")) {
      if (failRevisions) throw new ApiError(502, { code: "UPSTREAM", message: "down" });
      return { data: { items: [{ id: "r1" }, { id: "r2" }] } };
    }
    if (path === "/api/v1/admin/payout-v4/status") {
      if (failStatus) throw new ApiError(502, { code: "UPSTREAM", message: "down" });
      return { data: { publishing_enabled: status } };
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

const page = () => PayTermsSection({ campaignId: CAMPAIGN.id });

describe("PayoutRulesPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("governs a daily-rate campaign only through the daily-rate panel", async () => {
    api({ rule: { id: "rule-4", status: "active", formula_version: "payout_v4" } });
    render(await page());

    expect(screen.getByText(/daily rate panel · switched on · 2 revisions/)).toBeInTheDocument();
    expect(screen.queryByText("hourly revisions panel")).not.toBeInTheDocument();
    expect(screen.queryByText("hourly or legacy rule form")).not.toBeInTheDocument();
  });

  it("offers both the rule form and the switched-off daily rate when no rule exists", async () => {
    api({ status: false });
    render(await page());
    expect(screen.getByText("hourly or legacy rule form")).toBeInTheDocument();
    expect(screen.getByText(/daily rate panel · switched off · 0 revisions/)).toBeInTheDocument();
  });

  it("keeps hourly campaigns on the hourly chain without the daily-rate panel", async () => {
    api({ rule: { id: "rule-2", status: "active", formula_version: "payout_v2" } });
    render(await page());
    expect(screen.getByText("hourly revisions panel")).toBeInTheDocument();
    expect(screen.queryByText(/daily rate panel/)).not.toBeInTheDocument();
  });

  it("shows a retry state when the daily-rate data cannot load", async () => {
    api({ failStatus: true });
    render(await page());
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  });

  it("still surfaces an hourly revision load failure to the error boundary", async () => {
    api({
      rule: { id: "rule-2", status: "active", formula_version: "payout_v2" },
      failRevisions: true,
    });
    render(await page());
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
    expect(screen.queryByText("hourly revisions panel")).toBeNull();
  });
});
