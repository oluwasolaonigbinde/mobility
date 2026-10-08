import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { readDriverApi } from "@/lib/driver/api-read";
import { activeHeldTripIds, presentLedgerEntry } from "@/lib/driver/earnings-presentation";

export const metadata: Metadata = { title: "Earnings" };

const LEDGER_PAGE_SIZE = 50;

function parseOffset(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw || !/^\d+$/.test(raw)) return 0;
  const offset = Number(raw);
  return Number.isSafeInteger(offset) ? offset : 0;
}

export default async function DriverEarningsPage({
  searchParams,
}: {
  searchParams?: Promise<{ offset?: string | string[] }>;
}) {
  const api = createApiClient(await getSessionToken());
  const offset = parseOffset((await searchParams)?.offset);

  const [summary, ledger, assignments, holds] = await Promise.all([
    readDriverApi(() => api.GET("/api/v1/driver/earnings/summary")),
    readDriverApi(() =>
      api.GET("/api/v1/driver/earnings/ledger", {
        params: { query: { limit: LEDGER_PAGE_SIZE, offset } },
      }),
    ),
    readDriverApi(() =>
      api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } }),
    ),
    readDriverApi(() => api.GET("/api/v1/driver/fraud-holds")),
  ]);

  if ([summary, ledger, assignments, holds].some((source) => source.state === "auth")) {
    redirect("/login");
  }
  if (summary.state !== "ready" || ledger.state !== "ready" || holds.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>
        <DriverDataUnavailable
          title="Earnings and review status are unavailable"
          detail="Cardvert couldn't load your latest earnings, payments or trip reviews, so no balance is shown. Try again shortly."
          retryHref="/driver/earnings"
        />
      </div>
    );
  }

  const totals = summary.data.totals_by_currency;
  const entries = ledger.data.items;
  const ledgerTotal = ledger.data.total;
  const ledgerLimit = ledger.data.limit;
  const ledgerOffset = ledger.data.offset;
  const campaignNames = new Map(
    (assignments.state === "ready" ? assignments.data.items : []).map((item) => [
      item.campaign_id,
      item.campaign?.name ?? "Campaign",
    ]),
  );
  const heldTripIds = activeHeldTripIds(holds.data.items);
  const presentedEntries = entries.map((entry) => ({
    entry,
    presentation: presentLedgerEntry(entry, heldTripIds),
  }));
  const firstEntryNumber = entries.length === 0 ? 0 : ledgerOffset + 1;
  const lastEntryNumber = ledgerOffset + entries.length;
  const isPastEnd = entries.length === 0 && ledgerTotal > 0 && ledgerOffset >= ledgerTotal;
  const lastPageOffset =
    ledgerTotal > 0 ? Math.floor((ledgerTotal - 1) / ledgerLimit) * ledgerLimit : 0;
  const previousOffset = Math.max(0, ledgerOffset - ledgerLimit);
  const nextOffset = ledgerOffset + ledgerLimit;

  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Current earnings hidden while offline"
      detail="Reconnect to see your current earnings, payments and trip reviews."
      retryHref="/driver/earnings"
    >
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Earnings</h1>

        {assignments.state !== "ready" ? (
          <DriverDataUnavailable
            title="Campaign labels unavailable"
            detail="Campaign names couldn't load. Your current amounts and payment statuses are shown below."
            retryHref={`/driver/earnings?offset=${ledgerOffset}`}
          />
        ) : null}

        {totals.map((t) => {
          const values = [
            ["Ready to pay", t.released_available_amount, "text-green"],
            ["Ready to pay before deductions", t.available_amount, "text-green"],
            ["Paid (earnings records)", t.paid_amount, "text-green"],
            ["Owed, taken from your payouts", t.carry_forward_debt_amount, "text-coral"],
            ["Voided", t.voided_amount, "text-faint"],
            ["Lifetime earned", t.lifetime_earned_amount, ""],
          ] as const;
          return (
            <section key={t.currency} aria-label={`${t.currency} earnings`}>
              <p className="micro text-muted mb-2">{t.currency}</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Panel className="p-4">
                  <p className="micro text-faint">Ready to pay</p>
                  <p className="font-display text-green mt-1 text-lg font-semibold">
                    {formatMoney(t.batch_payable_amount, t.currency)}
                  </p>
                </Panel>
                <Panel className="p-4">
                  <p className="micro text-faint">Waiting for review</p>
                  <p
                    className={`font-display mt-1 text-lg font-semibold ${heldTripIds.size > 0 ? "text-amber" : "text-muted"}`}
                  >
                    {heldTripIds.size}{" "}
                    {heldTripIds.size === 1 ? "trip needs review" : "trips need review"}
                  </p>
                  <p className="text-faint mt-1 text-[11px]">
                    Waiting for review {formatMoney(t.pending_amount, t.currency)}
                  </p>
                </Panel>
                <Panel className="p-4">
                  <p className="micro text-faint">Paid</p>
                  <p className="font-display text-green mt-1 text-lg font-semibold">
                    {formatMoney(t.cash_paid_amount, t.currency)}
                  </p>
                </Panel>
              </div>
              <details className="mt-3">
                <summary className="text-muted cursor-pointer text-xs">Balance details</summary>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {values.map(([label, amount, tone]) => (
                    <Panel key={label} className="p-4">
                      <p className="micro text-faint">{label}</p>
                      <p className={`font-display mt-1 text-lg font-semibold ${tone}`}>
                        {formatMoney(amount, t.currency)}
                      </p>
                    </Panel>
                  ))}
                  <Panel className="p-4">
                    <p className="micro text-faint">Earnings records</p>
                    <p className="font-display mt-1 text-lg font-semibold">
                      {t.ledger_entry_count}
                    </p>
                  </Panel>
                </div>
              </details>
            </section>
          );
        })}

        <Panel className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="micro text-muted">Your payments</p>
              <p className="text-muted mt-1 text-xs leading-5">
                Paid means money successfully transferred.
              </p>
            </div>
            <span className="bg-green/10 text-green flex size-10 shrink-0 items-center justify-center rounded-full font-mono">
              ₦
            </span>
          </div>
        </Panel>

        <Panel className="overflow-hidden">
          <div className="border-edge border-b px-5 py-3.5">
            <h2 className="micro text-muted">Earnings and adjustments</h2>
            <p className="text-faint mt-1 text-xs">
              {isPastEnd
                ? `No entries at this position · ${ledgerTotal} total`
                : `Showing ${firstEntryNumber}–${lastEntryNumber} of ${ledgerTotal} entries`}
            </p>
          </div>
          {entries.length === 0 ? (
            isPastEnd ? (
              <div className="px-5 py-10 text-center text-sm">
                <p className="text-muted">There are no earnings records at this position.</p>
                <Link
                  href={`/driver/earnings?offset=${lastPageOffset}`}
                  className="micro text-amber mt-3 inline-block"
                >
                  Return to the last page
                </Link>
              </div>
            ) : (
              <p className="text-muted px-5 py-10 text-center text-sm">
                No entries yet — verified trips and account adjustments appear here.
              </p>
            )
          ) : (
            <ul className="divide-edge/60 divide-y">
              {presentedEntries.map(({ entry: e, presentation }) => {
                const row = (
                  <>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {campaignNames.get(e.campaign_id) ??
                          e.description ??
                          e.entry_type.replace("_", " ")}
                      </p>
                      <p className="micro text-faint mt-0.5">{formatDate(e.occurred_at)}</p>
                      {presentation.typeLabel ? (
                        <p className="micro text-muted mt-1">{presentation.typeLabel}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="font-mono text-sm">
                        {e.entry_type === "reversal" ? "−" : ""}
                        {formatMoneyExact(e.amount, e.currency)}
                      </span>
                      <StatusChip tone={presentation.status.tone}>
                        {presentation.status.label === "Released"
                          ? "Ready to pay"
                          : presentation.status.label === "Held" ||
                              presentation.status.label === "Pending"
                            ? "Waiting for review"
                            : presentation.status.label}
                      </StatusChip>
                    </div>
                  </>
                );
                return (
                  <li key={e.id}>
                    {e.trip_session_id ? (
                      <Link
                        href={`/driver/earnings/trips/${e.trip_session_id}`}
                        className="hover:bg-raised/60 flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 transition-colors"
                      >
                        {row}
                      </Link>
                    ) : (
                      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
                        {row}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {ledgerTotal > ledgerLimit && !isPastEnd ? (
            <nav
              aria-label="Earnings pages"
              className="border-edge flex items-center justify-between border-t px-5 py-3.5"
            >
              {ledgerOffset > 0 ? (
                <Link
                  href={`/driver/earnings?offset=${previousOffset}`}
                  className="micro text-amber"
                >
                  Previous
                </Link>
              ) : (
                <span className="micro text-faint">Previous</span>
              )}
              {nextOffset < ledgerTotal ? (
                <Link href={`/driver/earnings?offset=${nextOffset}`} className="micro text-amber">
                  Next
                </Link>
              ) : (
                <span className="micro text-faint">Next</span>
              )}
            </nav>
          ) : null}
        </Panel>
      </div>
    </FreshDriverAuthority>
  );
}
