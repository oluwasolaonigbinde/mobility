import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./actions", () => ({ createSourceLinkAction: vi.fn() }));

import { LinkForm } from "./link-form";

const source = { id: "s1", label: "Website visitors" };
const campaign = { id: "c1", label: "Wuse launch" };
const zone = { id: "z1", campaignId: "c1", label: "Wuse II core" };

function connect() {
  return screen.getByRole("button", { name: "Link audience to area" });
}

describe("LinkForm prerequisites", () => {
  it.each([
    [{ sources: [], campaigns: [campaign], zones: [zone] }, "Describe an audience first."],
    [{ sources: [source], campaigns: [], zones: [] }, "Create a campaign first."],
    [
      { sources: [source], campaigns: [campaign], zones: [] },
      "This campaign has no areas yet. Add one from the campaign's Areas tab.",
    ],
    [
      { sources: [source], campaigns: [campaign], zones: [], zonesIncomplete: true },
      "Campaign areas couldn't be loaded. Refresh the page to try again.",
    ],
  ])("names the missing step and ties it to the disabled button", (props, message) => {
    render(<LinkForm scopeCampaignId="c1" {...props} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(connect()).toBeDisabled();
    expect(connect()).toHaveAccessibleDescription(message);
  });

  it("enables linking once an audience, campaign and area exist", () => {
    render(
      <LinkForm scopeCampaignId="c1" sources={[source]} campaigns={[campaign]} zones={[zone]} />,
    );
    expect(connect()).toBeEnabled();
    expect(screen.getByRole("option", { name: "Wuse II core" })).toBeInTheDocument();
  });
});
