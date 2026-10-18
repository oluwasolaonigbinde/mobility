import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
  isAdvertiserViewer: (me: { viewer?: boolean }) => Boolean(me.viewer),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("./source-form", () => ({ SourceForm: () => <form aria-label="New audience" /> }));
vi.mock("./link-form", () => ({
  LinkForm: ({ campaigns }: { campaigns: Array<{ id: string; label: string }> }) => (
    <form aria-label="Link an audience">
      {campaigns.map((c) => (
        <span key={c.id}>{c.label}</span>
      ))}
    </form>
  ),
}));
vi.mock("./operation-form", () => ({ TerminalPlanningActionForm: () => <button>Unlink</button> }));
import Page from "./page";
const input = { params: Promise.resolve({ campaignId: "campaign-a" }) };
beforeEach(() => {
  mocks.role.mockResolvedValue({ viewer: false });
  mocks.get
    .mockReset()
    .mockImplementation(
      async (path: string, options?: { params?: { path?: { link_id?: string } } }) => {
        if (path.endsWith("/campaigns/{campaign_id}"))
          return { data: { id: "campaign-a", name: "Campaign A" } };
        if (path.endsWith("/retargeting-sources"))
          return {
            data: {
              items: [
                {
                  id: "source",
                  source_type: "manual-insight",
                  status: "active",
                  snapshot: { insight_category: "area-demand", confidence_band: "high" },
                  expires_at: "2027-01-01T00:00:00Z",
                },
              ],
            },
          };
        if (path.endsWith("/retargeting-source-links"))
          return {
            data: {
              items: [
                {
                  id: "link-a",
                  campaign_id: "campaign-a",
                  zone_id: "zone",
                  source_id: "source",
                  status: "active",
                },
                {
                  id: "link-b",
                  campaign_id: "campaign-b",
                  zone_id: "other",
                  source_id: "source",
                  status: "active",
                },
              ],
            },
          };
        if (path.endsWith("/zones"))
          return { data: { items: [{ id: "zone", name: "Wuse II" }], total: 1 } };
        if (path.endsWith("/recommendations"))
          return {
            data: {
              state: "suppressed",
              campaign_id:
                options?.params?.path?.link_id === "link-a" ? "campaign-a" : "campaign-b",
            },
          };
        throw new Error(`Unexpected path ${path}`);
      },
    );
});
it("only reads recommendations and offers link controls for the selected campaign", async () => {
  render(await Page(input));
  expect(screen.getByRole("heading", { name: "Reach these people again" })).toBeInTheDocument();
  expect(screen.getByRole("form", { name: "Link an audience" })).toHaveTextContent("Campaign A");
  const calls = mocks.get.mock.calls.filter((call) => String(call[0]).endsWith("/recommendations"));
  expect(calls.map((call) => call[1].params.path.link_id)).toEqual(["link-a"]);
  expect(screen.getAllByRole("button", { name: "Unlink" })).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "Stop using" })).toBeNull();
});
it("keeps writes hidden for viewers", async () => {
  mocks.role.mockResolvedValue({ viewer: true });
  render(await Page(input));
  expect(screen.queryByRole("form")).toBeNull();
  expect(screen.queryByRole("button", { name: "Unlink" })).toBeNull();
});
it("offers exports only for the route campaign and never requests another campaign's recommendations", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(
    async (path: string, options?: { params?: { path?: { link_id?: string } } }) => {
      if (path.endsWith("/recommendations"))
        return {
          data: {
            state: "ready",
            campaign_id: "campaign-a",
            segment_id: "own-segment",
            recommendations: [],
            disclaimer: "Use these suggestions for your own planning.",
          },
        };
      return original(path, options);
    },
  );
  const { container } = render(await Page(input));
  const exportForms = container.querySelectorAll("form[action*='exposure-segments']");
  expect(exportForms).toHaveLength(1);
  expect(exportForms[0]).toHaveAttribute(
    "action",
    "/api/advertiser/exposure-segments/own-segment/export",
  );
  expect(
    mocks.get.mock.calls
      .filter((call) => String(call[0]).endsWith("/recommendations"))
      .map((call) => call[1].params.path.link_id),
  ).toEqual(["link-a"]);
});
it("returns not found for an inaccessible campaign", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "MISSING", message: "Missing" }));
  await expect(Page(input)).rejects.toThrow("notFound");
});
it("retains a human error state with no forms when the reads fail", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "DOWN", message: "Private failure" }));
  render(await Page(input));
  expect(screen.getByRole("heading", { name: /Couldn't load your audiences/ })).toBeInTheDocument();
  expect(screen.queryByRole("form")).toBeNull();
  expect(document.body).not.toHaveTextContent("Private failure");
});
