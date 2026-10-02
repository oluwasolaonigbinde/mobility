import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn(), actions: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("./new-order-form", () => ({ NewOrderForm: () => <div>Named campaign selector</div> }));
vi.mock("./order-actions", () => ({
  OrderActions: (props: unknown) => {
    mocks.actions(props);
    return <div>Existing correction actions</div>;
  },
}));
vi.mock("../../hub-drawer", () => ({
  HubDrawer: ({
    title,
    closeHref,
    children,
  }: {
    title: string;
    closeHref: string;
    children: React.ReactNode;
  }) => (
    <div role="dialog" aria-label={title}>
      <a href={closeHref}>Close</a>
      {children}
    </div>
  ),
}));
import Content from "./content";
const order = {
  id: "selected",
  campaign_id: "campaign",
  created_by_user_id: "creator",
  status: "approved",
  lagos_day: "2026-10-01",
  reason: "Correct distance",
  projected_delta: {},
};
describe("selected pay corrections", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.role.mockResolvedValue({ user: { id: "reviewer" } });
  });
  it("independently resolves selected order off-page and preserves selection through pagination", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { items: [], total: 60 } })
      .mockResolvedValueOnce({ data: order })
      .mockResolvedValueOnce({ data: { id: "campaign", name: "Named campaign" } });
    render(
      await Content({
        query: {
          tab: "corrections",
          correction: "selected",
          correction_offset: "25",
          correction_status: "approved",
        },
      }),
    );
    expect(mocks.get).toHaveBeenNthCalledWith(
      2,
      "/api/v1/admin/payouts/correction-orders/{order_id}",
      { params: { path: { order_id: "selected" } } },
    );
    expect(screen.getByText("Correct distance")).toBeVisible();
    expect(mocks.actions).toHaveBeenCalledWith(
      expect.objectContaining({ orderId: "selected", status: "approved", isCreator: false }),
    );
    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      "/admin/money?tab=corrections&correction=selected&correction_offset=50&correction_status=approved",
    );
    expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
      "href",
      "/admin/money?tab=corrections&correction_offset=25&correction_status=approved",
    );
  });
  it("never offers actions for a mismatched selected order", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: { items: [], total: 0 } })
      .mockResolvedValueOnce({ data: { ...order, id: "wrong" } });
    render(await Content({ query: { tab: "corrections", correction: "selected" } }));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(mocks.actions).not.toHaveBeenCalled();
  });
});
