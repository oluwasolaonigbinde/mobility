import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrderActions } from "./order-actions";

vi.mock("./actions", () => ({
  newOrderAction: vi.fn(),
  orderTransitionAction: vi.fn(),
}));

const ORDER_ID = "00000000-0000-4000-8000-00000000000a";

function renderActions(
  props: Partial<Parameters<typeof OrderActions>[0]> & {
    status: Parameters<typeof OrderActions>[0]["status"];
  },
) {
  return render(
    <OrderActions orderId={ORDER_ID} isCreator={false} requiresReleaseAt={false} {...props} />,
  );
}

describe("OrderActions — state × role availability (Q22 maker-checker)", () => {
  it("draft: the creator can submit", () => {
    renderActions({ status: "draft", isCreator: true });
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeEnabled();
  });

  it("draft: a non-creator cannot submit and sees why", () => {
    renderActions({ status: "draft", isCreator: false });
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeDisabled();
    expect(screen.getByText(/only the creator may submit/i)).toBeInTheDocument();
  });

  it("pending approval: approve is disabled for the creator with maker-checker messaging", () => {
    renderActions({ status: "pending_approval", isCreator: true });
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
    expect(screen.getByText(/different admin must approve/i)).toBeInTheDocument();
  });

  it("pending approval: another admin can approve or reject", () => {
    renderActions({ status: "pending_approval", isCreator: false });
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("approved with positive deltas: execute requires a release date", () => {
    renderActions({ status: "approved", isCreator: true, requiresReleaseAt: true });
    expect(screen.getByRole("button", { name: "Execute" })).toBeEnabled();
    expect(screen.getByLabelText("Release at")).toBeRequired();
  });

  it("approved with no positive deltas: execute needs no release date", () => {
    renderActions({ status: "approved", isCreator: false });
    expect(screen.getByRole("button", { name: "Execute" })).toBeEnabled();
    expect(screen.queryByLabelText("Release at")).not.toBeInTheDocument();
  });

  it.each(["executed", "rejected", "stale"] as const)("%s: no actions remain", (status) => {
    renderActions({ status });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("stale explains that the projection drifted", () => {
    renderActions({ status: "stale" });
    expect(screen.getByText(/projection drifted/i)).toBeInTheDocument();
  });
});
