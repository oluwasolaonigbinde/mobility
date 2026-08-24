import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getCurrentUser } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { summarizeProjectedDelta } from "@/lib/payouts/corrections";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { cx } from "@/lib/cx";
import type { components } from "@/lib/api/schema";
import { NewOrderForm } from "./new-order-form";
import { OrderActions } from "./order-actions";

export const metadata: Metadata = { title: "Correction orders" };

const PAGE_SIZE = 25;
type OrderStatus = components["schemas"]["PayoutCorrectionOrderStatus"];

const STATUSES: OrderStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "executed",
  "rejected",
  "stale",
];

const statusTone: Record<OrderStatus, "default" | "amber" | "cyan" | "green" | "coral"> = {
  draft: "default",
  pending_approval: "amber",
  approved: "cyan",
  executed: "green",
  rejected: "coral",
  stale: "coral",
};

function href(params: { status?: string; offset?: number }): string {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.offset) qs.set("offset", String(params.offset));
  const s = qs.toString();
  return s ? `/admin/payouts/corrections?${s}` : "/admin/payouts/corrections";
}

export default async function AdminCorrectionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const status = STATUSES.includes(params.status as OrderStatus)
    ? (params.status as OrderStatus)
    : undefined;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const me = await getCurrentUser();
  const api = createApiClient(await getSessionToken());
  const [{ data: campaigns }, { data }] = await Promise.all([
    api.GET("/api/v1/admin/campaigns", { params: { query: { limit: 100 } } }),
    api.GET("/api/v1/admin/payouts/correction-orders", {
      params: { query: { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) } },
    }),
  ]);
  const campaignName = new Map((campaigns?.items ?? []).map((c) => [c.id, c.name]));
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/payouts" className="hover:text-muted">
          Payouts
        </Link>{" "}
        / <span className="text-muted">Corrections</span>
      </nav>
      <PageHeader
        title="Correction orders"
        eyebrow="Retroactive day recomputes — projected, independently approved, executed once"
      />

      <Panel className="mb-6 p-6">
        <h2 className="micro text-muted mb-1">Project a correction</h2>
        <p className="text-faint mb-4 text-xs">
          Pick a campaign and Lagos day to preview what a recompute would change, then create a
          draft order carrying that projection.
        </p>
        <NewOrderForm
          campaigns={(campaigns?.items ?? []).map((c) => ({ id: c.id, name: c.name }))}
        />
      </Panel>

      <div className="mb-4 flex gap-1 overflow-x-auto" role="group" aria-label="Filter by status">
        <Link
          href={href({})}
          className={cx(
            "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
            !status ? "bg-raised text-amber" : "text-muted hover:text-ink",
          )}
        >
          All
        </Link>
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={href({ status: s })}
            className={cx(
              "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
              status === s ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {s.replace(/_/g, " ")}
          </Link>
        ))}
      </div>

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-6 py-4">
          <h2 className="micro text-muted">Orders</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-6 py-3 font-normal">Status</th>
                <th className="px-4 py-3 font-normal">Campaign</th>
                <th className="px-4 py-3 font-normal">Lagos day</th>
                <th className="px-4 py-3 text-right font-normal">Projected delta</th>
                <th className="px-4 py-3 font-normal">Creator</th>
                <th className="px-4 py-3 font-normal">Approver</th>
                <th className="px-6 py-3 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-muted px-6 py-10 text-center">
                    No correction orders{status ? ` in ${status.replace(/_/g, " ")}` : " yet"} —
                    project one above.
                  </td>
                </tr>
              ) : (
                items.map((o) => {
                  const delta = summarizeProjectedDelta(o.projected_delta);
                  return (
                    <tr key={o.id} className="border-edge/60 border-b align-top last:border-0">
                      <td className="px-6 py-3">
                        <StatusChip tone={statusTone[o.status]}>
                          {o.status.replace(/_/g, " ")}
                        </StatusChip>
                      </td>
                      <td className="text-muted max-w-[12rem] truncate px-4 py-3">
                        {campaignName.get(o.campaign_id) ?? `${o.campaign_id.slice(0, 8)}…`}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{formatDate(o.lagos_day)}</td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {delta ? (
                          <>
                            <span
                              className={
                                delta.deltaTotal.startsWith("-") ? "text-coral" : "text-green"
                              }
                            >
                              {formatMoneyExact(delta.deltaTotal, delta.currency)}
                            </span>
                            <span className="text-faint block">
                              {delta.tripCount} trip{delta.tripCount === 1 ? "" : "s"} ·{" "}
                              {delta.adjustmentCount} up · {delta.reversalCount} down
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="text-muted px-4 py-3 font-mono text-xs">
                        {o.created_by_user_id.slice(0, 8)}…
                        {me && o.created_by_user_id === me.user.id ? (
                          <span className="text-amber"> (you)</span>
                        ) : null}
                      </td>
                      <td className="text-muted px-4 py-3 font-mono text-xs">
                        {o.approved_by_user_id ? `${o.approved_by_user_id.slice(0, 8)}…` : "—"}
                      </td>
                      <td className="px-6 py-3">
                        <OrderActions
                          orderId={o.id}
                          status={o.status}
                          isCreator={me !== null && o.created_by_user_id === me.user.id}
                          requiresReleaseAt={(delta?.adjustmentCount ?? 0) > 0}
                        />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => href({ status, offset: o || undefined })}
      />
    </div>
  );
}
