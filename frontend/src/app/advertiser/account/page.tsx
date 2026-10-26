import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { CompanyProfileForm } from "@/components/company/company-profile-form";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SessionLogoutButton } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";
import { updateCompanyAction } from "./actions";

export const metadata = { title: "Account" };

export default async function AccountPage({
  searchParams,
}: {
  searchParams?: Promise<{ saved?: string; error?: string }>;
}) {
  const me = await requireRole("advertiser");
  const notice = (await searchParams) ?? {};
  const api = createApiClient(await getSessionToken());
  const company = await loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/company"));
  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <h1 className="font-display text-3xl font-semibold">Your account</h1>
      <Panel className="p-6" id="company">
        <h2 className="font-display text-xl font-semibold">Company details</h2>
        <p className="text-muted mt-2 mb-5 text-sm">
          These are contact details only. Campaign emails go to your sign-in email.
        </p>
        {notice.saved ? (
          <p role="status" className="text-green mb-4">
            Company details saved.
          </p>
        ) : null}
        {notice.error ? (
          <p role="alert" className="text-coral mb-4">
            {notice.error}
          </p>
        ) : null}
        {company.available ? (
          <CompanyProfileForm company={company.data} action={updateCompanyAction} />
        ) : (
          <DataUnavailable
            title="Company details unavailable"
            reason={company.reason}
            retryHref="/advertiser/account"
          />
        )}
      </Panel>
      <Panel className="scroll-mt-24 p-6" id="people">
        <h2 className="font-display text-xl font-semibold">People</h2>
        <p className="mt-4 font-semibold">{me.user.full_name}</p>
        <p className="text-muted mt-1 text-sm break-words">{me.user.email}</p>
        <p className="text-muted mt-2 text-sm">Your sign-in</p>
      </Panel>
      <Panel className="scroll-mt-24 p-6" id="password">
        <h2 className="font-display mb-5 text-xl font-semibold">Change password</h2>
        <ChangePasswordForm />
      </Panel>
      <SessionLogoutButton label="Sign out" className="brand-secondary" />
    </div>
  );
}
