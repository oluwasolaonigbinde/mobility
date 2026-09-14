import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pending = vi.hoisted(() => ({
  resolve: undefined as undefined | ((state: { done?: string; error?: string }) => void),
  calls: [] as FormData[],
}));

vi.mock("./actions", () => {
  const action = (_previous: unknown, formData: FormData) => {
    pending.calls.push(formData);
    return new Promise((resolve) => {
      pending.resolve = resolve;
    });
  };
  return {
    reviewCampaignAction: action,
    reviewCreativeAction: action,
    reviewInstallationEvidenceAction: action,
    reviewCampaignChangeAction: action,
  };
});

import { CampaignChangeReviewActions } from "./campaign-change-review-actions";
import { CreativeReviewActions } from "./creative-review-actions";
import { InstallationReviewActions } from "./installation-review-actions";
import { ReviewActions } from "./review-actions";

const ID = "00000000-0000-4000-8000-00000000000a";

const cases = [
  { name: "campaign", ui: <ReviewActions campaignId={ID} />, approve: "Approve", reject: "Reject" },
  {
    name: "creative",
    ui: <CreativeReviewActions creativeId={ID} />,
    approve: "Approve",
    reject: "Reject",
  },
  {
    name: "installation",
    ui: <InstallationReviewActions submissionId={ID} photos={[]} />,
    approve: "Approve",
    reject: "Reject",
  },
  {
    name: "campaign change",
    ui: <CampaignChangeReviewActions requestId={ID} initialReason="Headroom verified" />,
    approve: "Approve change",
    reject: "Reject change",
  },
];

describe("review decision pending feedback", () => {
  beforeEach(() => {
    pending.resolve = undefined;
    pending.calls = [];
  });

  it.each(cases)("labels only the running rejection for $name review", async (item) => {
    render(item.ui);
    const reason = screen.getByRole("textbox");
    fireEvent.change(reason, { target: { value: "Replace the rear view." } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: item.reject }));
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Rejecting…" })).toBeDisabled());
    expect(screen.getByRole("button", { name: item.approve })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Approving…" })).toBeNull();
    expect(pending.calls.at(-1)?.get("intent")).toBe("reject");
    expect(pending.calls.at(-1)?.get("reason")).toBe("Replace the rear view.");

    await act(async () =>
      pending.resolve?.({ error: "Review state changed. Refresh and try again." }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Review state changed");
    expect(screen.getByRole("button", { name: item.reject })).toBeEnabled();
    expect(screen.getByRole("button", { name: item.approve })).toBeEnabled();
  });

  it.each(cases)("labels only the running approval for $name review", async (item) => {
    render(item.ui);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: item.approve }));
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Approving…" })).toBeDisabled());
    expect(screen.getByRole("button", { name: item.reject })).toBeDisabled();
    expect(pending.calls.at(-1)?.get("intent")).toBe("approve");

    await act(async () => pending.resolve?.({ done: "Recorded" }));
    expect(screen.getByText("✓ Recorded")).toBeInTheDocument();
  });
});
