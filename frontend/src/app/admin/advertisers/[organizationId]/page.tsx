import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { adminStatus } from "@/lib/status/admin";
import { formatDate, formatDateRange } from "@/lib/format";
import { CATEGORY_LABELS } from "@/lib/complaints/labels";
import { HubNav, HubSection } from "../../hub-section";
import { QueueUnavailable } from "../../queue-search";
import { UserStatusMenu } from "../../users/user-status-menu";
import { updateCompanyAction } from "./company/actions";
import { exactCompanyMoney, readCompanyInvoices } from "../company-reads";

export const metadata: Metadata = { title: "Advertiser" };
const sections = [
  { id: "details", title: "Details" },
  { id: "people", title: "People" },
  { id: "campaigns", title: "Campaigns" },
  { id: "money", title: "Invoices and payments" },
  { id: "complaints", title: "Complaints" },
  { id: "activity", title: "Activity" },
];
export default async function CompanyHub({
  params,
  searchParams,
}: {
  params: Promise<{ organizationId: string }>;
  searchParams: Promise<{
    campaign?: string;
    saved?: string;
    error?: string;
    people_offset?: string;
    complaint_offset?: string;
    activity_offset?: string;
  }>;
}) {
  const { organizationId } = await params;
  const p = await searchParams;
  const offset = (value?: string) =>
    Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
  const api = createApiClient(await getSessionToken());
  const company = await api
    .GET("/api/v1/admin/advertiser-organizations/{organization_id}/company", {
      params: { path: { organization_id: organizationId } },
    })
    .then(({ data }) => data)
    .catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) notFound();
      return undefined;
    });
  if (!company || company.id !== organizationId)
    return (
      <div>
        <PageHeader title="Advertiser" />
        <QueueUnavailable />
      </div>
    );
  const [people, complaints, activity] = await Promise.all([
    api
      .GET("/api/v1/admin/advertiser-organizations/{organization_id}/members", {
        params: {
          path: { organization_id: organizationId },
          query: { limit: 25, offset: offset(p.people_offset) },
        },
      })
      .then(({ data }) => data)
      .catch(() => undefined),
    api
      .GET("/api/v1/admin/complaints", {
        params: {
          query: { organization_id: organizationId, limit: 25, offset: offset(p.complaint_offset) },
        },
      })
      .then(({ data }) => data)
      .catch(() => undefined),
    api
      .GET("/api/v1/admin/audit-events", {
        params: {
          query: { entity_id: organizationId, limit: 25, offset: offset(p.activity_offset) },
        },
      })
      .then(({ data }) => data)
      .catch(() => undefined),
  ]);
  const money = await readCompanyInvoices(api, organizationId).catch(() => undefined);
  const href = (key: string, value: number, section: string) => {
    const query = new URLSearchParams();
    for (const field of ["people_offset", "complaint_offset", "activity_offset"] as const) {
      if (p[field]) query.set(field, p[field]);
    }
    query.set(key, String(value));
    return `/admin/advertisers/${organizationId}?${query}#${section}`;
  };
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={company.name} eyebrow={adminStatus(company.status)} />
      <HubNav sections={sections} />
      {p.saved ? (
        <p role="status" className="text-green mb-4">
          Company profile saved.
        </p>
      ) : null}
      {p.error ? (
        <p role="alert" className="text-coral mb-4">
          {p.error}
        </p>
      ) : null}
      <div className="grid gap-5">
        <HubSection id="details" title="Details">
          <CompanyProfileForm
            company={company}
            action={updateCompanyAction.bind(null, organizationId, p.campaign)}
          />
        </HubSection>
        <HubSection id="people" title="People">
          {!people ? (
            <QueueUnavailable />
          ) : (
            <>
              <p className="text-muted mb-3 text-sm">
                {people.total} company sign-in account{people.total === 1 ? "" : "s"}
              </p>
              {!people.items.length ? (
                <p>No company sign-in account recorded.</p>
              ) : (
                <ul className="grid gap-3">
                  {people.items.map(({ user, membership }) => (
                    <li
                      key={user.id}
                      className="border-edge flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
                    >
                      <div>
                        <p className="font-medium">{user.full_name}</p>
                        <p className="text-muted text-sm">{user.email}</p>
                        <p className="text-muted text-sm">
                          {membership.role === "owner" ? "Company owner" : "Company member"} ·
                          Membership: {adminStatus(membership.status)} · Login:{" "}
                          {adminStatus(user.status)}
                        </p>
                      </div>
                      <UserStatusMenu
                        userId={user.id}
                        userLabel={user.full_name}
                        role={user.role}
                        status={user.status}
                      />
                    </li>
                  ))}
                </ul>
              )}
              <Pagination
                total={people.total}
                limit={25}
                offset={offset(p.people_offset)}
                hrefFor={(o) => href("people_offset", o, "people")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="campaigns" title="Campaigns">
          {!money ? (
            <QueueUnavailable />
          ) : !money.campaigns.length ? (
            <p>No campaigns yet.</p>
          ) : (
            <ul className="grid gap-3">
              {money.campaigns.map((campaign) => (
                <li key={campaign.id}>
                  <Link className="text-cyan underline" href={`/admin/campaigns/${campaign.id}`}>
                    {campaign.name}
                  </Link>
                  <p className="text-muted text-sm">
                    {adminStatus(campaign.status)} ·{" "}
                    {formatDateRange(campaign.start_at, campaign.end_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </HubSection>
        <HubSection id="money" title="Invoices and payments">
          {!money ? (
            <QueueUnavailable />
          ) : (
            <>
              <p className="mb-4 font-medium">
                Outstanding:{" "}
                {money.outstanding.length
                  ? money.outstanding
                      .map(({ currency, amount }) => exactCompanyMoney(amount, currency))
                      .join(" · ")
                  : "No issued invoices"}
              </p>
              {!money.invoices.length ? (
                <p>No invoices yet.</p>
              ) : (
                <ul className="grid gap-3">
                  {money.invoices.map(({ invoice, campaign }) => (
                    <li key={invoice.id} className="border-edge rounded-lg border p-3">
                      <Link
                        className="text-cyan underline"
                        href={`/admin/campaigns/${campaign.id}?drawer=invoice&invoice=${invoice.id}#money`}
                      >
                        {invoice.invoice_number ?? "Draft invoice"} · {campaign.name}
                      </Link>
                      <p className="text-muted text-sm">
                        {adminStatus(invoice.status)} · {adminStatus(invoice.payment_status)} ·{" "}
                        {formatDate(invoice.issued_at ?? invoice.created_at)}
                      </p>
                      <p className="mt-2 text-sm">
                        Amount:{" "}
                        {exactCompanyMoney(invoice.effective_obligation_amount, invoice.currency)}
                        {" · "}Recorded funding:{" "}
                        {exactCompanyMoney(invoice.funded_amount, invoice.currency)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              <h3 className="mt-5 mb-3 font-medium">Refunds and credits</h3>
              {!money.settlements.length ? (
                <p>No refunds or credits recorded.</p>
              ) : (
                <ul className="grid gap-3">
                  {money.settlements.map(({ settlement, campaign }) => (
                    <li key={settlement.id} className="border-edge rounded-lg border p-3">
                      <Link
                        className="text-cyan underline"
                        href={`/admin/campaigns/${campaign.id}#money`}
                      >
                        {campaign.name}
                      </Link>
                      <p className="text-sm">
                        {adminStatus(settlement.disposition, "settlement")} ·{" "}
                        {exactCompanyMoney(settlement.amount, settlement.currency)}
                        {" · "}
                        {formatDate(settlement.recorded_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </HubSection>
        <HubSection id="complaints" title="Complaints">
          {!complaints ? (
            <QueueUnavailable />
          ) : (
            <>
              {!complaints.items.length ? (
                <p>No complaints.</p>
              ) : (
                <ul className="grid gap-3">
                  {complaints.items.map((item) => (
                    <li key={item.id}>
                      <Link
                        className="text-cyan underline"
                        href={`/admin/support?tab=complaints&organization_id=${organizationId}&complaint=${item.id}`}
                      >
                        {item.raised_by_name} · {CATEGORY_LABELS[item.category]}
                      </Link>
                      <p className="text-muted text-sm">
                        {adminStatus(item.status)} · {formatDate(item.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              <Pagination
                total={complaints.total}
                limit={25}
                offset={offset(p.complaint_offset)}
                hrefFor={(o) => href("complaint_offset", o, "complaints")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="activity" title="Activity">
          {!activity ? (
            <QueueUnavailable />
          ) : (
            <>
              {!activity.items.length ? (
                <p>No activity recorded.</p>
              ) : (
                <ul className="grid gap-3">
                  {activity.items.map((event) => (
                    <li key={event.id}>
                      <p>
                        {event.actor_email ?? "System"} · {formatDate(event.created_at)}
                      </p>
                      <details className="text-muted text-sm">
                        <summary>Technical reference</summary>
                        <p>{event.action}</p>
                        <pre className="overflow-auto">
                          {JSON.stringify(event.metadata, null, 2)}
                        </pre>
                      </details>
                    </li>
                  ))}
                </ul>
              )}
              <Pagination
                total={activity.total}
                limit={25}
                offset={offset(p.activity_offset)}
                hrefFor={(o) => href("activity_offset", o, "activity")}
              />
            </>
          )}
        </HubSection>
      </div>
    </div>
  );
}
