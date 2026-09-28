"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export async function updateCompanyAction(formData: FormData) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/advertiser/company", { body: companyProfileUpdate(formData) });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Could not update company profile";
    redirect(`/advertiser/company?error=${encodeURIComponent(message)}`);
  }
  revalidatePath("/advertiser/company");
  redirect("/advertiser/company?saved=1");
}
