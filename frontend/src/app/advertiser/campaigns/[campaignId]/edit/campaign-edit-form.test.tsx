import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const update = vi.hoisted(() => vi.fn());
vi.mock("../actions", () => ({ updateCampaignDetailsAction: update }));

import { CampaignEditForm } from "./campaign-edit-form";

const defaults = {
  name: "Launch",
  description: "",
  start_at: "2026-10-01T09:00",
  end_at: "",
  budget_amount: "500000.00",
  daily_budget_amount: "",
};

describe("CampaignEditForm", () => {
  it("keeps the advertiser's edits and original references after a failed save", async () => {
    const user = userEvent.setup();
    update.mockImplementation(async (_state: unknown, form: FormData) => ({
      error: "The daily budget cannot exceed the total budget.",
      values: Object.fromEntries(
        Object.keys(defaults).map((field) => [field, String(form.get(field) ?? "")]),
      ),
    }));
    const { container } = render(
      <CampaignEditForm campaignId="campaign-1" currency="NGN" defaults={defaults} />,
    );

    await user.clear(screen.getByLabelText("Campaign name"));
    await user.type(screen.getByLabelText("Campaign name"), "Launch v2");
    await user.type(screen.getByLabelText("Daily budget (NGN)"), "900000");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The daily budget cannot exceed the total budget.",
    );
    expect(screen.getByLabelText("Campaign name")).toHaveValue("Launch v2");
    expect(screen.getByLabelText("Daily budget (NGN)")).toHaveValue("900000");
    // The comparison baseline stays the stored campaign, not the failed edit.
    expect(container.querySelector<HTMLInputElement>('input[name="original_name"]')?.value).toBe(
      "Launch",
    );
  });
});
