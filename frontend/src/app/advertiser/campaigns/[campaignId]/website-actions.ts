"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";

export type WebsiteState = { error?: string; done?: string };
const input = z.object({
  campaignId: z.uuid(),
  creativeId: z.uuid(),
  destination: z.string().trim().min(1).max(2048),
});
export async function saveArtworkWebsite(
  _state: WebsiteState,
  form: FormData,
): Promise<WebsiteState> {
  await requireRole("advertiser");
  const parsed = input.safeParse({
    campaignId: form.get("campaign_id"),
    creativeId: form.get("creative_id"),
    destination: form.get("destination"),
  });
  if (!parsed.success) return { error: "Enter a public https website link." };
  const { campaignId, creativeId, destination } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.PUT(
      "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/website",
      {
        params: { path: { campaign_id: campaignId, creative_id: creativeId } },
        body: { destination },
      },
    );
    if (!data || data.creative_id !== creativeId || !data.short_path)
      return { error: "The saved link couldn't be confirmed. Try again." };
  } catch (error) {
    if (error instanceof ApiError && error.status === 422)
      return { error: "Enter a public https website link without a sign-in or custom port." };
    if (error instanceof ApiError && [401, 403, 404].includes(error.status))
      return { error: "This artwork isn't available to your account. Refresh or sign in again." };
    return { error: "The saved link couldn't be confirmed. Try again." };
  }
  revalidatePath(`/advertiser/campaigns/${campaignId}`);
  return { done: "Website link saved." };
}
