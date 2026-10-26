"use server";

import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export async function updateCompanyAction(formData: FormData) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/advertiser/company", { body: companyProfileUpdate(formData) });
  } catch (error) {
    unstable_rethrow(error);
    const message =
      error instanceof ApiError ? publicActionError(error) : "Could not update company profile";
    redirect(`/advertiser/account?error=${encodeURIComponent(message)}`);
  }
  revalidatePath("/advertiser/account");
  redirect("/advertiser/account?saved=1");
}
