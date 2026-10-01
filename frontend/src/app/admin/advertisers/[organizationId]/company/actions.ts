"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

function companyPath(organizationId: string, campaignId?: string) {
  const query = campaignId ? `?campaign=${encodeURIComponent(campaignId)}` : "";
  return `/admin/advertisers/${organizationId}/company${query}`;
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
    const message = error instanceof ApiError ? error.message : "Could not update company profile";
    redirect(
      `${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}error=${encodeURIComponent(message)}`,
    );
  }
  revalidatePath(companyPath(organizationId));
  if (campaignId) revalidatePath(`/admin/billing/${campaignId}`);
  redirect(`${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}saved=1`);
}
