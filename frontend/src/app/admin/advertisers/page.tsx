export const metadata = { title: "Advertisers" };
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import { adminStatus } from "@/lib/status/admin";
import { exactCompanyMoney } from "./company-reads";
import { readAdminAdvertiserOrganizations } from "@/lib/api/navigation";

export default async function AdvertisersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string }>;
}) {
  const p = await searchParams;
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const api = createApiClient(await getSessionToken());
  const { data } = await readAdminAdvertiserOrganizations(api, { q: p.q, limit: 25, offset }).catch(
    () => ({ data: undefined }),
  );
  // The list read already carries each company's outstanding invoice money (REQ-208).
  const failed = Boolean(
    data?.items.some(
      (company) =>
        ![company.member_count, company.live_campaign_count].every(
          (count) => Number.isSafeInteger(count) && count >= 0,
        ),
    ),
  );
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Advertisers"
        actions={
          <div className="flex gap-4">
            <Link className="text-cyan underline" href="/admin/enquiries">
              New enquiries
            </Link>
            <Link className="text-cyan underline" href="/admin/advertisers/new">
              Add company
            </Link>
          </div>
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
                return (
                  <Link
                    key={c.id}
                    href={`/admin/advertisers/${c.id}`}
                    className="border-edge hover:bg-raised rounded-xl border p-4"
                  >
                    <h2 className="font-medium">{c.name}</h2>
                    <p className="text-muted text-sm">
                      {c.billing_contact_name ??
                        c.operational_contact_name ??
                        "No contact recorded"}{" "}
                      · {c.billing_email ?? c.operational_contact_email ?? ""} ·{" "}
                      {adminStatus(c.status)}
                    </p>
                    <p className="text-muted text-sm">
                      People: {c.member_count} · Live campaigns: {c.live_campaign_count}
                    </p>
                    <p className="text-sm">
                      Outstanding:{" "}
                      {c.outstanding.length
                        ? c.outstanding
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
