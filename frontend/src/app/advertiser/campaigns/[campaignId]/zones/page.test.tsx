import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("./zones-editor", () => ({
  ZonesEditor: ({ editable }: { editable: boolean }) => (
    <div>{editable ? "Editing enabled" : "Saved areas"}</div>
  ),
}));
import CampaignZonesPage from "./page";
it.each(["draft", "rejected", "pending_review", "active"])(
  "matches the introduction to %s controls",
  async (status) => {
    get.mockImplementation(async (path: string) => ({
      data: path.endsWith("/zones") ? { items: [] } : { id: "c", name: "Abuja", status },
    }));
    render(await CampaignZonesPage({ params: Promise.resolve({ campaignId: "c" }) }));
    if (["draft", "rejected"].includes(status)) {
      expect(screen.getByText(/Draw the areas where/)).toBeVisible();
      expect(screen.getByText("Editing enabled")).toBeVisible();
    } else {
      expect(screen.queryByText(/Draw the areas/)).toBeNull();
      expect(
        screen.getByText("These are the areas for your advert and the places cars should avoid."),
      ).toBeVisible();
      expect(screen.getByText("Saved areas")).toBeVisible();
    }
  },
);
