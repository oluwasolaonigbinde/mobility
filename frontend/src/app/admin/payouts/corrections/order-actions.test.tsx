import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrderActions } from "./order-actions";
vi.mock("./actions", () => ({ orderTransitionAction: vi.fn() }));
const orderId = "00000000-0000-4000-8000-00000000000a";
describe("one-admin pay correction", () => {
  it("requires a reason for the single approval action", () => {
    render(<OrderActions orderId={orderId} status="draft" requiresReleaseAt={false} />);
    expect(screen.getByRole("button", { name: "Approve and apply" })).toBeEnabled();
    expect(screen.getByLabelText("Approval reason")).toBeRequired();
    expect(screen.queryByLabelText("Release at")).toBeNull();
  });
  it("requires a release date for positive extra pay", () => {
    render(<OrderActions orderId={orderId} status="draft" requiresReleaseAt />);
    expect(screen.getByLabelText("Release at")).toBeRequired();
  });
  it.each(["executed", "stale"] as const)("%s has no further action", (status) => {
    render(<OrderActions orderId={orderId} status={status} requiresReleaseAt={false} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
  it("explains a stale preview", () => {
    render(<OrderActions orderId={orderId} status="stale" requiresReleaseAt={false} />);
    expect(screen.getByText(/saved preview has changed/i)).toBeInTheDocument();
  });
});
