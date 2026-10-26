import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pending = vi.hoisted(() => ({
  resolve: undefined as undefined | ((state: { done?: string; error?: string }) => void),
  calls: [] as FormData[],
  realChangeAction: false,
  post: vi.fn(),
  resolveResponse: undefined as
    undefined | ((response: { data: { status: string }; response: Response }) => void),
}));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: pending.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

vi.mock("./actions", async (importOriginal) => {
  const original = await importOriginal<typeof import("./actions")>();
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
    reviewCampaignChangeAction: (previous: unknown, formData: FormData) => {
      if (!pending.realChangeAction) return action(previous, formData);
      pending.calls.push(formData);
      return original.reviewCampaignChangeAction({}, formData);
    },
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
it("keeps only the retry approval for an approved change waiting for funding", async () => {
  pending.realChangeAction = true;
  pending.post.mockImplementation(
    () =>
      new Promise((resolve) => {
        pending.resolveResponse = resolve;
      }),
  );
  render(
    <CampaignChangeReviewActions
      requestId={ID}
      pendingFunding
      initialReason="Approved; funding pending"
    />,
  );
  expect(
    screen.getByText(
      "This change is approved. The approval stays in place. When there is enough funding, press Retry approved change to apply it.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Reject change" })).toBeNull();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Retry approved change" }));
  });
  expect(pending.calls.at(-1)?.get("intent")).toBe("approve");
  await act(async () =>
    pending.resolveResponse?.({
      data: { status: "pending_funding" },
      response: new Response(JSON.stringify({ status: "pending_funding" }), { status: 200 }),
    }),
  );
  expect(screen.getByText("Approval kept. Still waiting for enough funding.")).toBeVisible();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByText(/Change approved/)).toBeNull();
  expect(screen.getByRole("button", { name: "Retry approved change" })).toBeEnabled();
  expect(pending.post).toHaveBeenCalledWith(
    "/api/v1/admin/campaign-change-requests/{request_id}/approve",
    { params: { path: { request_id: ID } }, body: { reason: "Approved; funding pending" } },
  );
  pending.realChangeAction = false;
});
