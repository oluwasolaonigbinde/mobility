import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDuration, formatMoney } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { ProcessTripForm } from "./process-trip-form";

export const metadata: Metadata = { title: "Payouts" };

const PAGE_SIZE = 25;

export default async function AdminPayoutsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/payout-calculations", {
    params: { query: { limit: PAGE_SIZE, offset } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Payouts"
        eyebrow={`${total} calculation${total === 1 ? "" : "s"} — every payout traces to an analyzed, fraud-screened trip`}
      />

      {/* Process a trip: analytics → impressions → payout */}
      <Panel className="mb-6 p-6">
        <h2 className="micro text-muted mb-1">Process a trip</h2>
        <p className="text-faint mb-4 text-xs">
          Runs the full pipeline: route analytics → impression estimate → payout calculation +
          ledger entry. Idempotent — safe to re-run.
        </p>
        <ProcessTripForm />
      </Panel>

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-6 py-4">
          <h2 className="micro text-muted">Calculations</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-6 py-3 font-normal">Trip</th>
                <th className="px-4 py-3 font-normal">Formula</th>
                <th className="px-4 py-3 text-right font-normal">Gross</th>
                <th className="px-4 py-3 text-right font-normal">Paid time</th>
                <th className="px-4 py-3 text-right font-normal">Quality ×</th>
                <th className="px-4 py-3 text-right font-normal">Fraud ×</th>
                <th className="px-4 py-3 text-right font-normal">Final</th>
                <th className="px-4 py-3 font-normal">Ledger</th>
                <th className="px-6 py-3 font-normal">Calculated</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-muted px-6 py-10 text-center">
                    No payout calculations yet — process a trip above.
                  </td>
                </tr>
              ) : (
                items.map((c) => (
                  <tr
                    key={c.id}
                    className="border-edge/60 border-b font-mono text-xs last:border-0"
                  >
                    <td className="text-muted px-6 py-3">{c.trip_session_id.slice(0, 8)}…</td>
                    <td className="text-muted px-4 py-3">
                      {c.formula_version === "payout_v2" ? "hourly v2" : c.formula_version}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatMoney(c.gross_payout, c.currency)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatDuration(c.payable_seconds)}
                    </td>
                    <td className="px-4 py-3 text-right">{c.quality_multiplier ?? "—"}</td>
                    <td className="px-4 py-3 text-right">{c.fraud_multiplier ?? "—"}</td>
                    <td className="text-green px-4 py-3 text-right font-medium">
                      {formatMoney(c.final_payout, c.currency)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip
                        tone={
                          c.ledger_entry?.status === "available"
                            ? "green"
                            : c.ledger_entry?.status === "pending"
                              ? "amber"
                              : "default"
                        }
                      >
                        {c.ledger_entry?.status ?? "none"}
                      </StatusChip>
                    </td>
                    <td className="text-muted px-6 py-3">{formatDate(c.calculated_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => (o ? `/admin/payouts?offset=${o}` : "/admin/payouts")}
      />

      <p className="micro text-faint mt-6">
        Earning terms are set per campaign —{" "}
        <Link href="/admin/payouts/rules" className="text-amber hover:underline">
          edit payout rules →
        </Link>
      </p>
    </div>
  );
}
