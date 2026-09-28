import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { PageHeader } from "@/components/ui/page-header";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { updateCompanyAction } from "./actions";

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
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!company) notFound();

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      {notice.campaign ? (
        <nav className="micro text-muted mb-4">
          <Link href={`/admin/billing/${notice.campaign}`}>Campaign billing</Link> / Company
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
