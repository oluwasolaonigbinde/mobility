import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { PageHeader } from "@/components/ui/page-header";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { updateCompanyAction } from "./company/actions";
import { QueueUnavailable } from "../../queue-search";

export const metadata: Metadata = { title: "Advertiser company" };

export default async function AdminCompanyPage({
  params,
  searchParams,
}: {
  params: Promise<{ organizationId: string }>;
  searchParams: Promise<{ campaign?: string; saved?: string; error?: string }>;
}) {
  const { organizationId } = await params;
  const notice = await searchParams;
  const api = createApiClient(await getSessionToken());
  let company;
  try {
    ({ data: company } = await api.GET(
      "/api/v1/admin/advertiser-organizations/{organization_id}/company",
      { params: { path: { organization_id: organizationId } } },
    ));
  } catch (error) {
    if (error instanceof ApiError && [403, 404].includes(error.status)) notFound();
    return (
      <div className="mx-auto max-w-5xl">
        <PageHeader title="Advertiser company" />
        <QueueUnavailable />
      </div>
    );
  }
  if (!company || company.id !== organizationId) notFound();

  return (
    <div id="details" className="animate-rise mx-auto max-w-5xl">
      {notice.campaign ? (
        <nav className="micro text-muted mb-4">
          <Link href={`/admin/campaigns/${notice.campaign}#money`}>Campaign money</Link> / Company
        </nav>
      ) : null}
      <PageHeader title={company.name} eyebrow="Advertiser billing and operational contacts" />
      {notice.saved ? <p className="text-green mb-4 text-sm">Company profile saved.</p> : null}
      {notice.error ? <p className="text-coral mb-4 text-sm">{notice.error}</p> : null}
      <CompanyProfileForm
        company={company}
        action={updateCompanyAction.bind(null, organizationId, notice.campaign)}
      />
    </div>
  );
}
