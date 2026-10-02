import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PayoutBatchesPage from "./content";
import BatchDetailPage from "./[batchId]/content";
import LineHistoryPage from "./[batchId]/lines/[lineId]/content";

const mocks = vi.hoisted(() => ({ api: vi.fn(), role: vi.fn(), notFound: vi.fn() }));
vi.mock("./batch-api", () => ({ batchApi: mocks.api }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("./batch-forms", () => ({
  CreateBatchForm: ({ draftId }: { draftId?: string }) => <div>Credit selection {draftId}</div>,
  BatchActions: () => <div>Batch actions</div>,
  MaskedDestination: () => <div>Explicit destination review</div>,
  PollLineAction: () => <button>Verify line</button>,
}));
const summary = {
  id: "batch",
  status: "reserved",
  currency: "NGN",
  total_amount: "125.10",
  created_by_user_id: "maker",
  approved_by_user_id: null,
  maker_name: "Ada Maker",
  checker_name: null,
  created_at: "2026-09-14T10:00:00Z",
  approved_at: null,
  submitted_at: null,
  line_count: 2,
  outcomes: { queued: 2 },
};
const line = {
  id: "line",
  driver_name: "Named Driver",
  payee_name: "Named Payee",
  amount: "100.07",
  currency: "NGN",
  status: "reserved",
  outcome: "provider_unknown",
  reconciled_at: null,
  bank_account_version_id: "version",
};
const detailProps = (page?: string) => ({
  params: Promise.resolve({ batchId: "batch" }),
  searchParams: Promise.resolve({ line_page: page, batch: "batch", day: "2026-09-28", runs: "2" }),
});

describe("bounded payout pages", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.role.mockResolvedValue({ user: { id: "maker" } });
    mocks.notFound.mockImplementation(() => {
      throw new Error("not-found");
    });
  });

  it("keeps credit and batch pagination independent with named exact summaries", async () => {
    mocks.api
      .mockResolvedValueOnce({ items: [], total: 80 })
      .mockResolvedValueOnce({ items: [summary], total: 100 });
    render(
      await PayoutBatchesPage({
        searchParams: Promise.resolve({
          q: "Ada%",
          currency: "ngn",
          credits: "1",
          runs: "2",
          status: "reserved",
        }),
      }),
    );
    expect(mocks.role).toHaveBeenCalledWith("admin");
    expect(mocks.api).toHaveBeenNthCalledWith(
      1,
      "/eligible?limit=25&offset=25&search=Ada%25&currency=NGN",
    );
    expect(mocks.api).toHaveBeenNthCalledWith(
      2,
      "/summaries?limit=25&offset=50&batch_status=reserved",
    );
    expect(screen.getByText("Prepared by: Ada Maker")).toBeVisible();
    expect(screen.getByText("₦125.10")).toBeVisible();
    expect(screen.getByText("Queued — not submitted: 2")).toBeVisible();
    expect(screen.getByRole("link", { name: "Next earnings" })).toHaveAttribute(
      "href",
      expect.stringContaining("credits=2&runs=2"),
    );
    expect(screen.getByRole("link", { name: "Previous runs" })).toHaveAttribute(
      "href",
      expect.stringContaining("credits=1&runs=1"),
    );
  });

  it("bounds invalid query input and shows truthful empty states", async () => {
    mocks.api.mockResolvedValue({ items: [], total: 0 });
    render(
      await PayoutBatchesPage({
        searchParams: Promise.resolve({ credits: "-3", runs: "oops", currency: "NOTMONEY" }),
      }),
    );
    expect(mocks.api).toHaveBeenCalledWith("/eligible?limit=25&offset=0");
    expect(screen.getByText("No payment runs match this page.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Next runs" })).not.toBeInTheDocument();
  });

  it("renders unknown line outcomes without inventing failed or paid finality", async () => {
    mocks.api.mockResolvedValue({ summary, lines: [line], total: 60 });
    render(await BatchDetailPage(detailProps("1")));
    expect(mocks.api).toHaveBeenCalledExactlyOnceWith("/batch/detail?limit=25&offset=25");
    expect(screen.getByText("Provider outcome unknown")).toBeVisible();
    expect(screen.getByText("Named Driver")).toBeVisible();
    expect(screen.queryByText("Verified paid")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verify line" })).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation", { name: "Payment line pages" })).getByRole("link", {
        name: "Next",
      }),
    ).toHaveAttribute("href", expect.stringContaining("line_page=2"));
  });

  it("shows Cardvert as the approver of an automatic batch and offers no approval", async () => {
    const automatic = {
      ...summary,
      approval_mode: "automatic",
      maker_name: "Cardvert (automatic payouts)",
      approved_at: "2026-09-14T10:00:00Z",
    };
    mocks.api
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [automatic], total: 1 });
    render(await PayoutBatchesPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("Approved automatically by Cardvert")).toBeVisible();
    expect(screen.queryByText(/Maker:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Awaiting independent approval/)).not.toBeInTheDocument();
  });

  it("does not offer approve or send on an automatic batch's detail page", async () => {
    mocks.api.mockResolvedValue({
      summary: { ...summary, approval_mode: "automatic", approved_at: "2026-09-14T10:00:00Z" },
      lines: [line],
      total: 1,
    });
    render(await BatchDetailPage(detailProps()));
    expect(screen.getByText(/Approved automatically by/)).toHaveTextContent("Cardvert");
    expect(screen.getByRole("link", { name: "Automatic payouts" })).toHaveAttribute(
      "href",
      "/admin/money?tab=payouts",
    );
    expect(screen.queryByText("Batch actions")).not.toBeInTheDocument();
    expect(screen.queryByText(/Checker:/)).not.toBeInTheDocument();
  });

  it("limits existing-draft selection to its maker", async () => {
    mocks.api
      .mockResolvedValueOnce({ summary: { ...summary, status: "draft" }, lines: [], total: 0 })
      .mockResolvedValueOnce({ items: [], total: 26 });
    render(await BatchDetailPage(detailProps()));
    expect(mocks.api).toHaveBeenLastCalledWith("/eligible?limit=25&offset=0&currency=NGN");
    expect(screen.getByText("Credit selection batch")).toBeVisible();
    expect(screen.getByText("No payments on this page.")).toBeVisible();
  });

  it("does not offer a checker another maker's draft credits", async () => {
    mocks.role.mockResolvedValue({ user: { id: "checker" } });
    mocks.api.mockResolvedValue({ summary: { ...summary, status: "draft" }, lines: [], total: 0 });
    render(await BatchDetailPage(detailProps()));
    expect(mocks.api).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText("Only the person who prepared this draft can reserve it."),
    ).toBeVisible();
  });

  it("shows verified evidence on paid lines and preserves submitted verification action", async () => {
    mocks.api.mockResolvedValue({
      summary: { ...summary, checker_name: "Grace Checker", approved_at: summary.created_at },
      lines: [
        {
          ...line,
          status: "submitted",
          outcome: "submitted",
          reconciled_at: summary.created_at,
          reconciler_name: "Audit Reviewer",
        },
      ],
      total: 1,
    });
    render(await BatchDetailPage(detailProps("bad")));
    expect(screen.getByText("Grace Checker")).toBeVisible();
    expect(screen.getByText("Submitted — awaiting verification")).toBeVisible();
    expect(screen.getByRole("button", { name: "Verify line" })).toBeVisible();
  });

  it("shows one failed-section state when the selected run cannot be read", async () => {
    mocks.api.mockRejectedValueOnce(new Error("offline"));
    render(await BatchDetailPage(detailProps()));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText("Batch actions")).not.toBeInTheDocument();
  });

  it("keeps no history distinct from final failure or payment", async () => {
    mocks.api
      .mockResolvedValueOnce({ id: "batch", lines: [line] })
      .mockResolvedValueOnce({ items: [], total: 0, latest_submission_outcome: null });
    render(
      await LineHistoryPage({
        params: Promise.resolve({ batchId: "batch", lineId: "line" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(
      screen.getByText(
        "No verified final result has been recorded. This does not mean failed or paid.",
      ),
    ).toBeVisible();
  });

  it("pages applied and retained provider evidence without changing its meaning", async () => {
    mocks.api.mockResolvedValueOnce({ id: "batch", lines: [line] }).mockResolvedValueOnce({
      items: [
        {
          id: "1",
          outcome: "succeeded",
          source: "webhook",
          applied: true,
          provider_occurred_at: summary.created_at,
          created_at: summary.created_at,
        },
        {
          id: "2",
          outcome: "failed",
          source: "poll",
          applied: false,
          provider_occurred_at: summary.created_at,
          created_at: summary.created_at,
        },
      ],
      total: 60,
      latest_submission_outcome: "unknown",
    });
    render(
      await LineHistoryPage({
        params: Promise.resolve({ batchId: "batch", lineId: "line" }),
        searchParams: Promise.resolve({
          batch: "batch",
          line: "line",
          history_page: "1",
          day: "2026-09-28",
          runs: "2",
        }),
      }),
    );
    expect(mocks.api).toHaveBeenCalledWith("/lines/line/history?limit=25&offset=25");
    expect(screen.getByText(/Verified paid · Applied to this payment/)).toBeVisible();
    expect(screen.getByText(/Failed · Recorded without changing this payment/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      expect.stringContaining("history_page=2"),
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      expect.stringContaining("day=2026-09-28&runs=2"),
    );
  });
  it.each([
    { id: "other", lines: [line] },
    { id: "batch", lines: [{ ...line, id: "other" }] },
  ])("never reads history without the exact selected parent and line", async (parent) => {
    mocks.api.mockResolvedValue(parent);
    render(
      await LineHistoryPage({
        params: Promise.resolve({ batchId: "batch", lineId: "line" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(mocks.api).toHaveBeenCalledExactlyOnceWith("/batch");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });
});
