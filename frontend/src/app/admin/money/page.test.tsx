import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  role: vi.fn(),
  run: vi.fn(),
  payment: vi.fn(),
  invoices: vi.fn(),
  corrections: vi.fn(),
  automatic: vi.fn(),
  runs: vi.fn(),
  ready: vi.fn(),
}));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("../payouts/automatic/content", () => ({ default: mocks.automatic }));
vi.mock("../payouts/batches/content", () => ({ default: mocks.runs, ReadyToPay: mocks.ready }));
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
const sections = {
  runs: "Payment list",
  ready: "Earnings list",
  automatic: "Automatic controls",
  invoices: "Invoices list",
  corrections: "Correction list",
} as const;
describe("Money tabs: one job per screen", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.role.mockResolvedValue({});
    mocks.run.mockResolvedValue(<div>Run detail</div>);
    mocks.payment.mockResolvedValue(<div>Payment detail</div>);
    mocks.invoices.mockResolvedValue(<div>{sections.invoices}</div>);
    mocks.corrections.mockResolvedValue(<div>{sections.corrections}</div>);
    mocks.automatic.mockResolvedValue(<div>{sections.automatic}</div>);
    mocks.runs.mockResolvedValue(<div>{sections.runs}</div>);
    mocks.ready.mockResolvedValue(<div>{sections.ready}</div>);
  });
  it("opens on Payment runs and loads nothing else", async () => {
    render(await Page({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(sections.runs)).toBeVisible();
    for (const mock of [mocks.ready, mocks.automatic, mocks.invoices, mocks.corrections])
      expect(mock).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Payment runs" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      ["Payment runs", "/admin/money?tab=runs"],
      ["Ready to pay", "/admin/money?tab=ready"],
      ["Automatic", "/admin/money?tab=automatic"],
      ["Invoices", "/admin/money?tab=invoices"],
      ["Corrections", "/admin/money?tab=corrections"],
    ]);
  });
  it.each(Object.keys(sections) as (keyof typeof sections)[])(
    "shows only the %s screen",
    async (tab) => {
      render(await Page({ searchParams: Promise.resolve({ tab }) }));
      for (const [key, text] of Object.entries(sections)) {
        if (key === tab) expect(screen.getByText(text)).toBeVisible();
        else expect(screen.queryByText(text)).not.toBeInTheDocument();
      }
    },
  );
  it.each(["runs", "ready", "automatic"])(
    "opens one payment drawer on %s and keeps the list query when closing",
    async (tab) => {
      const query = {
        tab,
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
        `/admin/money?tab=${tab}&day=2026-10-01&runs=2&credits=1`,
      );
    },
  );
  it.each(["invoices", "corrections"])("opens no payment drawer on %s", async (tab) => {
    render(
      await Page({ searchParams: Promise.resolve({ tab, batch: "ignored", line: "ignored" }) }),
    );
    expect(mocks.run).not.toHaveBeenCalled();
    expect(mocks.payment).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("ignores repeated or unknown query values", async () => {
    render(
      await Page({
        searchParams: Promise.resolve({
          tab: ["ready", "invoices"],
          batch: ["one", "two"],
          currency: ["NGN", "USD"],
        }),
      }),
    );
    expect(mocks.run).not.toHaveBeenCalled();
    expect(screen.getByText(sections.runs)).toBeVisible();
    render(await Page({ searchParams: Promise.resolve({ tab: "payouts" }) }));
    expect(screen.getAllByText(sections.runs)).toHaveLength(2);
  });
});
