import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  role: vi.fn(),
  run: vi.fn(),
  payment: vi.fn(),
  invoices: vi.fn(),
  corrections: vi.fn(),
}));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("../payouts/automatic/content", () => ({
  default: async () => <div>Automatic controls</div>,
}));
vi.mock("../payouts/batches/content", () => ({ default: async () => <div>Payment list</div> }));
vi.mock("../payouts/batches/[batchId]/content", () => ({ default: mocks.run }));
vi.mock("../payouts/batches/[batchId]/lines/[lineId]/content", () => ({ default: mocks.payment }));
vi.mock("./invoices", () => ({ default: mocks.invoices }));
vi.mock("../payouts/corrections/content", () => ({ default: mocks.corrections }));
vi.mock("../hub-drawer", () => ({
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
import Page from "./page";
describe("Money canonical tabs and drawers", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.role.mockResolvedValue({});
    mocks.run.mockResolvedValue(<div>Run detail</div>);
    mocks.payment.mockResolvedValue(<div>Payment detail</div>);
    mocks.invoices.mockResolvedValue(<div>Invoices list</div>);
    mocks.corrections.mockResolvedValue(<div>Correction list</div>);
  });
  it("opens one selected payment drawer and keeps the list query when closing", async () => {
    const query = {
      tab: "payouts",
      batch: "selected-batch",
      line: "selected-line",
      day: "2026-10-01",
      runs: "2",
      credits: "1",
      history_page: "2",
    };
    render(await Page({ searchParams: Promise.resolve(query) }));
    expect(mocks.payment).toHaveBeenCalledOnce();
    expect(mocks.run).not.toHaveBeenCalled();
    expect(await mocks.payment.mock.calls[0]![0].params).toEqual({
      batchId: "selected-batch",
      lineId: "selected-line",
    });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
      "href",
      "/admin/money?tab=payouts&day=2026-10-01&runs=2&credits=1",
    );
    expect(screen.queryByRole("textbox", { name: /ID/i })).not.toBeInTheDocument();
  });
  it.each(["invoices", "corrections"])(
    "opens only %s content without payment drawers",
    async (tab) => {
      render(
        await Page({ searchParams: Promise.resolve({ tab, batch: "ignored", line: "ignored" }) }),
      );
      expect(mocks.run).not.toHaveBeenCalled();
      expect(mocks.payment).not.toHaveBeenCalled();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(
        screen.getByRole("link", {
          name: tab === "invoices" ? "Invoices & payments" : "Corrections",
        }),
      ).toHaveAttribute("aria-current", "page");
    },
  );
  it("ignores repeated query values instead of converting them to a selected ID or filter", async () => {
    render(
      await Page({
        searchParams: Promise.resolve({
          tab: ["payouts", "invoices"],
          batch: ["one", "two"],
          currency: ["NGN", "USD"],
        }),
      }),
    );
    expect(mocks.run).not.toHaveBeenCalled();
    expect(mocks.payment).not.toHaveBeenCalled();
    expect(screen.getByText("Payment list")).toBeVisible();
  });
});
