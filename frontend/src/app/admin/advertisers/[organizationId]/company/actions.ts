"use server";

import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { companyUpdateErrorCode } from "@/lib/advertiser/company-profile-errors";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";

function companyPath(organizationId: string, campaignId?: string) {
  const query = campaignId ? `?campaign=${encodeURIComponent(campaignId)}` : "";
  return `/admin/advertisers/${organizationId}${query}`;
}

export async function updateCompanyAction(
  organizationId: string,
  campaignId: string | undefined,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/admin/advertiser-organizations/{organization_id}/company", {
      params: { path: { organization_id: organizationId } },
      body: companyProfileUpdate(formData),
    });
  } catch (error) {
    unstable_rethrow(error);
    redirect(
      `${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}error=${companyUpdateErrorCode(error)}`,
    );
  }
  revalidatePath(companyPath(organizationId));
  if (campaignId) revalidatePath(`/admin/campaigns/${campaignId}`);
  redirect(`${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}saved=1`);
}
