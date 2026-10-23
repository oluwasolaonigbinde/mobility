import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { PageHeader } from "@/components/ui/page-header";
import { updateCompanyAction } from "./actions";

export const metadata: Metadata = { title: "Company profile" };

export default async function CompanyPage({
  searchParams,
}: {
  searchParams: Promise<{ saved?: string; error?: string }>;
}) {
  const notice = await searchParams;
  await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const { data: company } = await api.GET("/api/v1/advertiser/company");
  if (!company) return null;

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      <PageHeader
        title="Company profile"
        eyebrow="Your company's billing and operations contacts"
      />
      {notice.saved ? <p className="text-green mb-4 text-sm">Company profile saved.</p> : null}
      {notice.error ? <p className="text-coral mb-4 text-sm">{notice.error}</p> : null}
      <p className="text-muted mb-4 text-sm">
        These are contact details only. Campaign update emails go to your sign-in email when email
        is switched on.
      </p>
      <CompanyProfileForm company={company} action={updateCompanyAction} />
    </div>
  );
}
