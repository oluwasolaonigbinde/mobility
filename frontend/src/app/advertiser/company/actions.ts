"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export async function updateCompanyAction(formData: FormData) {
  const optional = (name: string) => String(formData.get(name) ?? "").trim() || null;
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/advertiser/company", {
      body: {
        name: String(formData.get("name") ?? "").trim(),
        billing_email: optional("billing_email"),
        billing_contact_name: optional("billing_contact_name"),
        billing_contact_phone: optional("billing_contact_phone"),
        operational_contact_name: optional("operational_contact_name"),
        operational_contact_email: optional("operational_contact_email"),
        operational_contact_phone: optional("operational_contact_phone"),
        address_line_1: optional("address_line_1"),
        address_line_2: optional("address_line_2"),
        address_city: optional("address_city"),
        address_region: optional("address_region"),
        address_postal_code: optional("address_postal_code"),
        address_country_code: optional("address_country_code"),
        industry: optional("industry"),
      },
    });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Could not update company profile";
    redirect(`/advertiser/company?error=${encodeURIComponent(message)}`);
  }
  revalidatePath("/advertiser/company");
  redirect("/advertiser/company?saved=1");
}
