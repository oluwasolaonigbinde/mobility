import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const { get, guard } = vi.hoisted(() => ({ get: vi.fn(), guard: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: guard }));
import Page from "./page";
import { collectWorkQueue, waitingCounts } from "./work-queue";
import type { ApiClient } from "@/lib/api/client";
const date = "2026-09-01T00:00:00Z";
const api = { GET: get } as unknown as ApiClient;
const page = (query: Record<string, string> = {}) => Page({ searchParams: Promise.resolve(query) });
describe("Work queue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    guard.mockResolvedValue({});
    get.mockResolvedValue({ data: { items: [], total: 0 } });
  });
  it("enumerates every application page and shows the five oldest items with exact count", async () => {
    const rows = Array.from({ length: 101 }, (_, i) => ({
      id: `app${i}`,
      driver_profile_id: `driver${i}`,
      full_name: `Driver ${i}`,
      created_at: new Date(Date.parse(date) + (100 - i) * 3600000).toISOString(),
    }));
    get.mockImplementation(async (path, options) =>
      path.endsWith("/driver-applications")
        ? {
            data: {
              items: rows.slice(options.params.query.offset, options.params.query.offset + 100),
              total: 101,
            },
          }
        : { data: { items: [], total: 0 } },
    );
    render(await page());
    const operations = screen.getByRole("region", { name: "Operations" });
    expect(within(operations).getAllByRole("listitem")).toHaveLength(5);
    expect(within(operations).getAllByRole("link")[0]).toHaveAttribute(
      "href",
      "/admin/drivers/driver100#checklist",
    );
    expect(within(operations).getByRole("link", { name: "See all (101)" })).toHaveAttribute(
      "href",
      "/admin?department=Operations",
    );
    expect(get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
      params: { query: { limit: 100, offset: 100 } },
    });
  });
  it("excludes completed contact and funding-pending changes, and counts failed outcomes once per run", async () => {
    get.mockImplementation(async (path) => {
      if (path.endsWith("/manual-driver-contact-tasks"))
        return {
          data: {
            items: [
              { id: "done", completed_at: date, status: "open" },
              {
                id: "current",
                completed_at: null,
                status: "open",
                driver_name: "Ada",
                driver_profile_id: "driver",
                created_at: date,
              },
            ],
            total: 2,
          },
        };
      if (path.endsWith("/campaign-change-requests/pending"))
        return {
          data: {
            items: [
              { id: "funding", status: "pending_funding" },
              { id: "change", status: "pending_admin", created_at: date, campaign_id: "campaign" },
            ],
          },
        };
      if (path.endsWith("/payout-batches/summaries"))
        return {
          data: {
            items: [
              {
                id: "both",
                created_at: date,
                status: "reserved",
                approval_mode: "maker_checker",
                approved_at: null,
                outcomes: { failed: 1 },
              },
              {
                id: "nonfailed-run",
                created_at: date,
                status: "submitted",
                approval_mode: "automatic",
                outcomes: { failed: 1 },
              },
            ],
            total: 2,
          },
        };
      return { data: { items: [], total: 0 } };
    });
    const queue = await collectWorkQueue(api);
    expect(queue["Customer Service"]?.map((row) => row.key)).toEqual(["contact:current"]);
    expect(queue.Admin?.map((row) => row.key)).toEqual(["change:change"]);
    expect(queue.Finance?.map((row) => row.key)).toEqual(["run:both", "run:nonfailed-run"]);
    expect(await queue.Finance![0]!.describe()).toMatchObject({
      reason: "Needs approval · Has failed payments",
    });
    expect(waitingCounts(queue)).toMatchObject({ total: 4, support: 1, money: 2, campaigns: 1 });
  });
  it("shows one failed department and keeps unrelated departments truthful", async () => {
    get.mockImplementation(async (path) => {
      if (path.endsWith("/vehicles")) throw new Error("offline");
      return { data: { items: [], total: 0 } };
    });
    render(await page());
    expect(
      within(screen.getByRole("region", { name: "Operations" })).getByRole("alert"),
    ).toHaveTextContent("Couldn't load this section — try again");
    expect(
      within(screen.getByRole("region", { name: "Finance" })).getByText("Nothing waiting"),
    ).toBeVisible();
  });
  it("does not display a partial oldest list when its named record fails", async () => {
    get.mockImplementation(async (path) =>
      path.endsWith("/fraud-disputes")
        ? {
            data: {
              items: [
                {
                  id: "dispute",
                  created_at: date,
                  driver_profile_id: "driver",
                  fraud_flag_id: "flag",
                },
              ],
              total: 1,
            },
          }
        : path.endsWith("{driver_profile_id}")
          ? {}
          : { data: { items: [], total: 0 } },
    );
    render(await page());
    expect(
      within(screen.getByRole("region", { name: "Customer Service" })).getByRole("alert"),
    ).toBeVisible();
    expect(screen.queryByText("See all (1)")).toBeNull();
  });
  it("offers a filtered department list with pagination", async () => {
    const rows = Array.from({ length: 30 }, (_, i) => ({
      id: `app${i}`,
      full_name: `Driver ${i}`,
      driver_profile_id: `driver${i}`,
      created_at: date,
    }));
    get.mockImplementation(async (path) =>
      path.endsWith("/driver-applications")
        ? { data: { items: rows, total: 30 } }
        : { data: { items: [], total: 0 } },
    );
    render(await page({ department: "Operations", offset: "25" }));
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByRole("link", { name: /Prev/ })).toHaveAttribute(
      "href",
      "/admin?department=Operations&offset=0",
    );
  });
  it("never reads the queue before staff authorization", async () => {
    guard.mockRejectedValue(new Error("denied"));
    await expect(page()).rejects.toThrow("denied");
    expect(get).not.toHaveBeenCalled();
  });
  it("routes named work from every department to the exact record and keeps actual event dates", async () => {
    const job = {
      id: "job",
      driver_profile_id: "driver",
      campaign_id: "campaign",
      driver_profile: { full_name: "Ada Driver" },
      vehicle: { plate_number: "ABC-123" },
      campaign: { name: "PalmPay" },
      accepted_at: date,
    };
    const sources: Record<string, unknown[]> = {
      "/vehicles": [
        {
          id: "car",
          driver_profile_id: "driver",
          driver_profile: job.driver_profile,
          plate_number: "ABC-123",
          created_at: date,
        },
      ],
      "/campaign-assignments": [job],
      "/trips/quarantined-batches": [{ id: "late", trip_session_id: "trip", received_at: date }],
      "/campaigns/pending-review": [{ id: "review", name: "Campaign review", created_at: date }],
      "/creatives/pending-review": [
        {
          creative: {
            id: "artwork",
            campaign_id: "campaign",
            name: "Blue poster",
            created_at: date,
          },
          campaign_name: "PalmPay",
        },
      ],
      "/evidence-verifications": [{ id: "check", driver_profile_id: "driver", issued_at: date }],
      "/payouts/automatic/alerts": [
        { id: "alert", driver_name: "Ada Driver", batch_id: "batch", created_at: date },
      ],
      "/complaints": [
        {
          id: "complaint",
          party_name: "Ada Driver",
          category: "billing_or_invoice",
          last_message_at: date,
        },
      ],
      "/campaigns": [{ id: "paused", name: "Paused campaign", status: "paused", updated_at: date }],
    };
    get.mockImplementation(async (path) => {
      if (path.endsWith("/trips/{trip_id}/analytics"))
        return {
          data: {
            trip_session_id: "trip",
            driver_profile_id: "driver",
            campaign_id: "campaign",
            assignment_id: "job",
            started_at: date,
          },
        };
      if (path.endsWith("/campaign-assignments/{assignment_id}")) return { data: job };
      if (path.endsWith("/drivers/{driver_profile_id}"))
        return { data: { id: "driver", full_name: "Ada Driver" } };
      const items = sources[path.replace("/api/v1/admin", "")] ?? [];
      return { data: { items, total: items.length } };
    });
    const queue = await collectWorkQueue(api);
    const rows = Object.values(queue).flatMap((items) => items ?? []);
    const links: Record<string, string> = {};
    for (const row of rows) {
      links[row.key] = (await row.describe()).href;
      expect(row.at).toBe(date);
    }
    expect(links).toEqual({
      "vehicle:car": "/admin/drivers/driver#cars",
      "job:job": "/admin/campaigns/campaign?drawer=job&job=job#drivers",
      "late:late": "/admin/trip-checks?tab=late&late=late",
      "campaign:review": "/admin/campaigns/review#overview",
      "artwork:artwork": "/admin/campaigns/campaign#artwork",
      "check:check": "/admin/trip-checks?tab=in-person&check=check",
      "alert:alert": "/admin/money?tab=payouts&batch=batch",
      "complaint:complaint": "/admin/support?tab=complaints&complaint=complaint",
      "paused:paused": "/admin/campaigns/paused#overview",
    });
    expect(queue.Admin?.[0]?.event).toBe("Updated");
    expect(queue["Customer Service"]?.[0]?.event).toBe("Last message");
  });
  it("fails the department rather than counting duplicate unpaged work twice", async () => {
    get.mockImplementation(async (path) =>
      path.endsWith("/installation-evidence/pending")
        ? { data: { items: [{ id: "duplicate" }, { id: "duplicate" }] } }
        : { data: { items: [], total: 0 } },
    );
    const queue = await collectWorkQueue(api);
    expect(queue.Compliance).toBeUndefined();
    expect(waitingCounts(queue).total).toBeUndefined();
    expect(queue.Finance).toEqual([]);
  });
  it("limits context reads across departments to four concurrent requests", async () => {
    let active = 0,
      peak = 0;
    const rows = (kind: string) =>
      Array.from({ length: 5 }, (_, i) => ({
        id: `${kind}${i}`,
        driver_profile_id: `${kind}-driver${i}`,
        campaign_id: `${kind}-campaign${i}`,
        assignment_id: `job${i}`,
        fraud_flag_id: `flag${i}`,
        trip_session_id: `trip${i}`,
        created_at: date,
        detected_at: date,
        submitted_at: date,
        issued_at: date,
        money_effect: { held_currency: null, held_pending_net: "0.00" },
      }));
    get.mockImplementation(async (path, options) => {
      active++;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, 5));
      active--;
      if (path.endsWith("{driver_profile_id}"))
        return { data: { id: options.params.path.driver_profile_id, full_name: "Ada Driver" } };
      if (path.endsWith("{campaign_id}"))
        return { data: { id: options.params.path.campaign_id, name: "PalmPay" } };
      if (path.endsWith("/fraud-flags"))
        return {
          data: {
            items: options.params.query.status === "open" ? rows("flag") : [],
            total: options.params.query.status === "open" ? 5 : 0,
          },
        };
      if (path.endsWith("/installation-evidence/pending"))
        return { data: { items: rows("photos") } };
      if (path.endsWith("/correction-orders"))
        return { data: { items: rows("correction"), total: 5 } };
      if (path.endsWith("/fraud-disputes")) return { data: { items: rows("dispute"), total: 5 } };
      return { data: { items: [], total: 0 } };
    });
    render(await page());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(peak).toBe(4);
  });
});
