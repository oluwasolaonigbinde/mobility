import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const path = vi.hoisted(() => ({ value: "/advertiser/campaigns/one" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.value }));
import { CampaignTabs } from "./campaign-tabs";
it("keeps invoices in Billing and the campaign Overview selected", () => {
  render(<CampaignTabs campaignId="one" />);
  expect(screen.queryByRole("link", { name: "Invoices" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Reach these people again" })).toBeNull();
  expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
});
