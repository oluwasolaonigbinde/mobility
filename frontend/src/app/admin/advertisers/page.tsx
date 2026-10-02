import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import { adminStatus } from "@/lib/status/admin";
import { exactCompanyMoney, readCompanyInvoices } from "./company-reads";

export default async function AdvertisersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string }>;
}) {
  const p = await searchParams;
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const api = createApiClient(await getSessionToken());
  const { data } = await api
    .GET("/api/v1/admin/advertiser-organizations", {
      params: { query: { q: p.q, limit: 25, offset } },
    })
    .catch(() => ({ data: undefined }));
  const summaries = new Map<string, Awaited<ReturnType<typeof summary>>>();
  async function summary(id: string) {
    const [company, people] = await Promise.all([
      api
        .GET("/api/v1/admin/advertiser-organizations/{organization_id}/company", {
          params: { path: { organization_id: id } },
        })
        .then(({ data }) => data),
      api
        .GET("/api/v1/admin/advertiser-organizations/{organization_id}/members", {
          params: { path: { organization_id: id }, query: { limit: 1, offset: 0 } },
        })
        .then(({ data }) => data),
    ]);
    if (!company || company.id !== id || !people) throw new Error("Incomplete company section");
    const money = await readCompanyInvoices(api, id);
    return { company, people: people.total, money };
  }
  let failed = false;
  if (data) {
    for (let offset = 0; offset < data.items.length; offset += 1) {
      const company = data.items[offset]!;
      try {
        summaries.set(company.id, await summary(company.id));
      } catch {
        failed = true;
      }
    }
  }
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Advertisers"
        actions={
          <Link className="text-cyan underline" href="/admin/advertisers/new">
            Add company
          </Link>
        }
      />
      <QueueSearch q={p.q} label="Search companies" />
      {!data || failed ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-4 text-sm">{data.total} matching companies</p>
          {!data.items.length ? (
            <p>No matching companies.</p>
          ) : (
            <div className="grid gap-3">
              {data.items.map((c) => {
                const detail = summaries.get(c.id)!;
                return (
                  <Link
                    key={c.id}
                    href={`/admin/advertisers/${c.id}`}
                    className="border-edge hover:bg-raised rounded-xl border p-4"
                  >
                    <h2 className="font-medium">{c.name}</h2>
                    <p className="text-muted text-sm">
                      {detail.company.billing_contact_name ??
                        detail.company.operational_contact_name ??
                        "No contact recorded"}{" "}
                      ·{" "}
                      {detail.company.billing_email ??
                        detail.company.operational_contact_email ??
                        ""}{" "}
                      · {adminStatus(c.status)}
                    </p>
                    <p className="text-muted text-sm">
                      People: {detail.people} · Live campaigns:{" "}
                      {
                        detail.money.campaigns.filter(
                          (campaign) =>
                            campaign.status === "active" || campaign.status === "paused",
                        ).length
                      }
                    </p>
                    <p className="text-sm">
                      Outstanding:{" "}
                      {detail.money.outstanding.length
                        ? detail.money.outstanding
                            .map(({ currency, amount }) => exactCompanyMoney(amount, currency))
                            .join(" · ")
                        : "No issued invoices"}
                    </p>
                  </Link>
                );
              })}
            </div>
          )}
          <Pagination
            total={data.total}
            limit={25}
            offset={offset}
            hrefFor={(o) =>
              `/admin/advertisers?${new URLSearchParams({ q: p.q ?? "", offset: String(o) })}`
            }
          />
        </>
      )}
    </div>
  );
}
