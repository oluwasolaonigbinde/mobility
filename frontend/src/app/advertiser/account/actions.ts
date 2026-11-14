"use server";

import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { companyProfileUpdate } from "@/lib/advertiser/company-profile";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { companyUpdateErrorCode } from "./errors";

export async function updateCompanyAction(formData: FormData) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/advertiser/company", { body: companyProfileUpdate(formData) });
  } catch (error) {
    unstable_rethrow(error);
    redirect(`/advertiser/account?error=${companyUpdateErrorCode(error)}`);
  }
  revalidatePath("/advertiser/account");
  redirect("/advertiser/account?saved=1");
}
