"use server";
import { z } from "zod";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { createAdvertiserFromEnquiry } from "@/lib/api/audit-batch2";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";

export type EnquiryConversionState = { error?: string };
export async function convertEnquiry(
  enquiryId: string,
  _state: EnquiryConversionState,
): Promise<EnquiryConversionState> {
  await requireRole("admin");
  if (!z.uuid().safeParse(enquiryId).success) return { error: "This enquiry couldn’t be found." };
  let organizationId: string;
  try {
    // Let the existing company creation authority choose the owner; email is not proof of ownership.
    const { data } = await createAdvertiserFromEnquiry(
      createApiClient(await getSessionToken()),
      enquiryId,
    );
    if (!data || data.status !== "converted" || !z.uuid().safeParse(data.organization_id).success)
      return {
        error: "We couldn’t confirm the advertiser was created. Try again to check this enquiry.",
      };
    organizationId = data.organization_id;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.code === "ENQUIRY_CONVERSION_CONFLICT")
      return {
        error:
          "This enquiry already has an advertiser with a different owner. Reload the enquiry to check it.",
      };
    if (error instanceof ApiError && [403, 404].includes(error.status))
      return { error: "This enquiry isn’t available." };
    return {
      error: "We couldn’t confirm the advertiser was created. Try again to check this enquiry.",
    };
  }
  revalidatePath("/admin/enquiries");
  revalidatePath(`/admin/enquiries/${enquiryId}`);
  revalidatePath("/admin/advertisers");
  redirect(`/admin/advertisers/${organizationId}`);
}
