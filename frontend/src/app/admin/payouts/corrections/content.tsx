import { adminReadFailure } from "@/lib/api/admin-read";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { projectedTripRows, summarizeProjectedDelta } from "@/lib/payouts/corrections";
import { Pagination } from "@/components/ui/pagination";
import { FilterChips } from "@/components/ui/tabs";
import { HubDrawer } from "../../hub-drawer";
import { QueueUnavailable } from "../../queue-search";
import { moneyHref, type MoneyQuery } from "../../money/navigation";
import { NewOrderForm } from "./new-order-form";
import { OrderActions } from "./order-actions";
type Order = components["schemas"]["PayoutCorrectionOrderRead"];
const statuses = ["draft", "executed", "stale"] as const;
export default async function Corrections({ query }: { query: MoneyQuery }) {
  await requireRole("admin");
  const api = createApiClient(await getSessionToken());
  const status = statuses.find((value) => value === query.correction_status),
    raw = Number(query.correction_offset ?? 0),
    offset = Number.isFinite(raw) ? Math.max(0, Math.floor(raw)) : 0;
  const { data } = await api
    .GET("/api/v1/admin/payouts/correction-orders", {
      params: { query: { limit: 25, offset, status } },
    })
    .catch(adminReadFailure);
  let selected: Order | undefined = data?.items.find((order) => order.id === query.correction),
    selectionFailed = false;
  if (query.correction && !selected) {
    const { data: detail } = await api
      .GET("/api/v1/admin/payouts/correction-orders/{order_id}", {
        params: { path: { order_id: query.correction } },
      })
      .catch(adminReadFailure);
    if (detail?.id === query.correction) selected = detail;
    else selectionFailed = true;
  }
  const names = new Map<string, string>();
  const ids = [
    ...new Set([
      ...(data?.items ?? []).map((order) => order.campaign_id),
      ...(selected ? [selected.campaign_id] : []),
    ]),
  ];
  for (let index = 0; index < ids.length; index += 4) {
    await Promise.all(
      ids.slice(index, index + 4).map(async (campaignId) => {
        const { data: campaign } = await api
          .GET("/api/v1/admin/campaigns/{campaign_id}", {
            params: { path: { campaign_id: campaignId } },
          })
          .catch(adminReadFailure);
        if (campaign?.id === campaignId) names.set(campaignId, campaign.name);
      }),
    );
  }
  const namesFailed = names.size !== ids.length;
  const delta = selected ? summarizeProjectedDelta(selected.projected_delta) : null;
  return (
    <div className="space-y-5">
      <details className="border-edge rounded border p-4">
        <summary>Correct a driver&apos;s pay</summary>
        <p className="text-muted my-3 text-sm">
          Choose a campaign and day to preview a pay correction.
        </p>
        <NewOrderForm />
      </details>
      <FilterChips
        label="Correction status"
        items={[
          {
            href: moneyHref(query, { correction_status: undefined, correction_offset: undefined }),
            label: "All",
            active: !status,
          },
          ...statuses.map((value) => ({
            href: moneyHref(query, { correction_status: value, correction_offset: undefined }),
            label: adminStatus(value, "correction"),
            active: status === value,
          })),
        ]}
      />
      {!data || namesFailed ? (
        <QueueUnavailable />
      ) : (
        <>
          <ul className="grid gap-3">
            {data.items.map((order) => {
              const summary = summarizeProjectedDelta(order.projected_delta);
              return (
                <li className="border-edge rounded border p-4" key={order.id}>
                  <Link className="underline" href={moneyHref(query, { correction: order.id })}>
                    {names.get(order.campaign_id)} · {formatDate(order.lagos_day)}
                  </Link>
                  <p>
                    {adminStatus(order.status, "correction")}
                    {summary ? ` · ${formatMoneyExact(summary.deltaTotal, summary.currency)}` : ""}
                  </p>
                </li>
              );
            })}
          </ul>
          {!data.items.length ? <p>No matching pay corrections.</p> : null}
          <Pagination
            total={data.total}
            limit={25}
            offset={offset}
            hrefFor={(next) => moneyHref(query, { correction_offset: String(next) })}
          />
        </>
      )}
      {query.correction ? (
        <HubDrawer title="Pay correction" closeHref={moneyHref(query, { correction: undefined })}>
          {selectionFailed || !selected || namesFailed ? (
            <QueueUnavailable />
          ) : (
            <>
              <h3>
                {names.get(selected.campaign_id)} · {formatDate(selected.lagos_day)}
              </h3>
              <p>{adminStatus(selected.status, "correction")}</p>
              <p>{selected.reason}</p>
              {delta ? (
                <p>
                  Expected change: {formatMoneyExact(delta.deltaTotal, delta.currency)} ·{" "}
                  {delta.tripCount} {delta.tripCount === 1 ? "trip" : "trips"}
                </p>
              ) : null}
              <OrderActions
                orderId={selected.id}
                status={selected.status}
                requiresReleaseAt={(delta?.adjustmentCount ?? 0) > 0}
              />
              <ul aria-label="Trip pay changes" className="mt-4 space-y-3">
                {projectedTripRows(selected.projected_delta).map((trip, index) => (
                  <li key={trip.id}>
                    <Link
                      className="underline"
                      href={`/admin/drivers/${trip.driverId}?trip=${trip.id}#trips-and-pay`}
                    >
                      Trip {index + 1}
                    </Link>
                    <p>
                      Current: {formatMoneyExact(trip.previous, trip.currency)} · Correct:{" "}
                      {formatMoneyExact(trip.target, trip.currency)}
                    </p>
                    <p>Change: {formatMoneyExact(trip.change, trip.currency)}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
