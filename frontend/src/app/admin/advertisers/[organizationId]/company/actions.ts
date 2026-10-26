"use server";

import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
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
    const message =
      error instanceof ApiError ? publicActionError(error) : "Could not update company profile";
    redirect(
      `${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}error=${encodeURIComponent(message)}`,
    );
  }
  revalidatePath(companyPath(organizationId));
  if (campaignId) revalidatePath(`/admin/campaigns/${campaignId}`);
  redirect(`${companyPath(organizationId, campaignId)}${campaignId ? "&" : "?"}saved=1`);
}
