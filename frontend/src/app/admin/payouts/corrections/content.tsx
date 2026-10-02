import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { summarizeProjectedDelta } from "@/lib/payouts/corrections";
import { Pagination } from "@/components/ui/pagination";
import { HubDrawer } from "../../hub-drawer";
import { QueueUnavailable } from "../../queue-search";
import { moneyHref, type MoneyQuery } from "../../money/navigation";
import { NewOrderForm } from "./new-order-form";
import { OrderActions } from "./order-actions";
type Order = components["schemas"]["PayoutCorrectionOrderRead"];
const statuses = [
  "draft",
  "pending_approval",
  "approved",
  "executed",
  "rejected",
  "stale",
] as const;
export default async function Corrections({ query }: { query: MoneyQuery }) {
  const me = await requireRole("admin"),
    api = createApiClient(await getSessionToken());
  const status = statuses.find((value) => value === query.correction_status),
    raw = Number(query.correction_offset ?? 0),
    offset = Number.isFinite(raw) ? Math.max(0, Math.floor(raw)) : 0;
  const { data } = await api
    .GET("/api/v1/admin/payouts/correction-orders", {
      params: { query: { limit: 25, offset, status } },
    })
    .catch(() => ({ data: undefined }));
  let selected: Order | undefined = data?.items.find((order) => order.id === query.correction),
    selectionFailed = false;
  if (query.correction && !selected) {
    const { data: detail } = await api
      .GET("/api/v1/admin/payouts/correction-orders/{order_id}", {
        params: { path: { order_id: query.correction } },
      })
      .catch(() => ({ data: undefined }));
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
          .catch(() => ({ data: undefined }));
        if (campaign?.id === campaignId) names.set(campaignId, campaign.name);
      }),
    );
  }
  const namesFailed = names.size !== ids.length;
  const delta = selected ? summarizeProjectedDelta(selected.projected_delta) : null;
  return (
    <div className="space-y-5">
      <details className="border-edge rounded border p-4">
        <summary>Prepare a pay correction</summary>
        <p className="text-muted my-3 text-sm">
          Choose a campaign and day to preview the change. A different staff member must approve it
          before it can run.
        </p>
        <NewOrderForm />
      </details>
      <nav aria-label="Correction status" className="flex flex-wrap gap-3">
        <Link
          href={moneyHref(query, { correction_status: undefined, correction_offset: undefined })}
        >
          All
        </Link>
        {statuses.map((value) => (
          <Link
            key={value}
            href={moneyHref(query, { correction_status: value, correction_offset: undefined })}
          >
            {adminStatus(value, "correction")}
          </Link>
        ))}
      </nav>
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
                  {delta.tripCount} trips
                </p>
              ) : null}
              <OrderActions
                orderId={selected.id}
                status={selected.status}
                isCreator={selected.created_by_user_id === me.user.id}
                requiresReleaseAt={(delta?.adjustmentCount ?? 0) > 0}
              />
              <details className="mt-4">
                <summary>Recorded calculation details</summary>
                <pre className="max-w-full overflow-auto">
                  {JSON.stringify(selected.projected_delta, null, 2)}
                </pre>
              </details>
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
