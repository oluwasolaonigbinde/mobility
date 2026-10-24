"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";

export type CreateCompanyState = { error?: string };
const company = z.object({
  name: z.string().trim().min(1, "Company name is required").max(255),
  email: z.string().trim().toLowerCase().email("Enter a valid email"),
  currency: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z]{3}$/, "Use a 3-letter currency code")
    .optional(),
});
export async function createCompanyAction(
  _state: CreateCompanyState,
  form: FormData,
): Promise<CreateCompanyState> {
  await requireRole("admin");
  const parsed = company.safeParse({
    name: form.get("name"),
    email: form.get("email"),
    currency: String(form.get("currency") ?? "").trim() || undefined,
  });
  if (!parsed.success)
    return { error: parsed.error.issues[0]?.message ?? "Check the company details." };
  let id: string;
  try {
    const { data } = await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/advertiser-organizations",
      { body: parsed.data },
    );
    if (!data)
      return {
        error: "The company could not be confirmed. Check the company list before trying again.",
      };
    id = data.organization.id;
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? error.message
          : "The company could not be confirmed. Check the company list before trying again.",
    };
  }
  revalidatePath("/admin/advertisers");
  redirect(`/admin/advertisers/${id}#people`);
}
