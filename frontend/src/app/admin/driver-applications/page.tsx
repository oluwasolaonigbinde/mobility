import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { PersonPayeeDecisionActions } from "./person-payee-decision-actions";

export const metadata: Metadata = { title: "Driver applications" };
const PAGE_SIZE = 25;

export default async function AdminDriverApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/driver-applications", {
    params: { query: { limit: PAGE_SIZE, offset } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Driver applications"
        eyebrow={`${total} pending application${total === 1 ? "" : "s"}`}
      />
      {items.length === 0 ? (
        <EmptyState
          title="No pending driver applications"
          body="New public applications will appear here for operations review."
        />
      ) : (
        <Panel className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1180px] text-sm">
              <thead>
                <tr className="border-edge micro text-muted border-b text-left">
                  <th className="px-5 py-3.5 font-normal">Applicant</th>
                  <th className="px-5 py-3.5 font-normal">Contact</th>
                  <th className="px-5 py-3.5 font-normal">Location</th>
                  <th className="px-5 py-3.5 font-normal">Status</th>
                  <th className="px-5 py-3.5 font-normal">Person &amp; payee</th>
                  <th className="px-5 py-3.5 font-normal">Received</th>
                  <th className="px-5 py-3.5 font-normal">Review</th>
                </tr>
              </thead>
              <tbody>
                {items.map((application) => {
                  const personPayee = application.person_payee;
                  const personPayeeStatus = personPayee?.status ?? "not_submitted";
                  return (
                    <tr
                      key={application.id}
                      className="border-edge/60 border-b align-top last:border-0"
                    >
                      <td className="px-5 py-3.5">
                        <p className="font-medium">{application.full_name}</p>
                        <p className="text-faint mt-1 font-mono text-xs">
                          {application.id.slice(0, 8)}…
                        </p>
                      </td>
                      <td className="px-5 py-3.5">
                        <p>{application.email}</p>
                        <p className="text-muted mt-1">
                          {application.phone ?? "No phone supplied"}
                        </p>
                      </td>
                      <td className="px-5 py-3.5">
                        {application.service_city ?? "—"}
                        {application.country_code ? ` · ${application.country_code}` : ""}
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusChip tone="amber">{application.status}</StatusChip>
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusChip
                          tone={
                            personPayeeStatus === "approved"
                              ? "green"
                              : personPayeeStatus === "pending_review"
                                ? "amber"
                                : "default"
                          }
                        >
                          {personPayeeStatus.replaceAll("_", " ")}
                        </StatusChip>
                        {personPayee?.masked_nin ? (
                          <p className="text-muted mt-1 font-mono text-xs">
                            v{personPayee.version} · {personPayee.masked_nin}
                          </p>
                        ) : null}
                      </td>
                      <td className="text-muted px-5 py-3.5 whitespace-nowrap">
                        {formatDate(application.created_at)}
                      </td>
                      <td className="px-5 py-3.5">
                        {personPayeeStatus === "pending_review" && personPayee?.submission_id ? (
                          <PersonPayeeDecisionActions
                            applicationId={application.id}
                            submissionId={personPayee.submission_id}
                          />
                        ) : (
                          <span className="text-faint text-xs">No pending review</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(value) =>
          value ? `/admin/driver-applications?offset=${value}` : "/admin/driver-applications"
        }
      />
    </div>
  );
}
