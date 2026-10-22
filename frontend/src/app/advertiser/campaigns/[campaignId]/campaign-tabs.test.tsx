import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const path = vi.hoisted(() => ({ value: "/advertiser/campaigns/one/invoices/invoice" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.value }));
import { CampaignTabs } from "./campaign-tabs";
it("keeps invoice detail under the selected Invoices tab", () => {
  render(<CampaignTabs campaignId="one" />);
  expect(screen.getByRole("link", { name: "Invoices" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  expect(screen.queryByRole("link", { name: "Reach these people again" })).toBeNull();
});
