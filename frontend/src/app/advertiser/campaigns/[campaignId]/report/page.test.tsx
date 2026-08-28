import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const get = vi.hoisted(() => vi.fn());
const notFound = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("NOT_FOUND");
  }),
);

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("next/navigation", () => ({ notFound }));

import CampaignReportPage from "./page";

describe("CampaignReportPage fail-closed states", () => {
  beforeEach(() => {
    get.mockReset();
    notFound.mockClear();
  });

  it("withholds the complete legacy report when frozen authority is missing", async () => {
    get.mockResolvedValue({ data: { measurement_run: null, measurement_result: null } });
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText(/failed its integrity check/i)).toBeInTheDocument();
    expect(screen.queryByText(/daily breakdown/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/modelled potential contacts/i)).not.toBeInTheDocument();
  });

  it("renders an explicit unavailable state for a blocked live analysis", async () => {
    get.mockRejectedValue(
      new ApiError(503, {
        code: "MEASUREMENT_LIVE_ISSUANCE_BLOCKED",
        message: "blocked",
      }),
    );
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText("Live analysis is unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/daily breakdown/i)).not.toBeInTheDocument();
  });

  it("preserves non-enumerating not-found behavior", async () => {
    get.mockRejectedValue(new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "not found" }));
    await expect(
      CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    ).rejects.toThrow("NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
  });
});
