"use server";

import { headers } from "next/headers";
import { z } from "zod";
import { createLoginApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { env } from "@/lib/env";

const text = (max: number) => z.string().trim().min(1, "Enter this detail").max(max);
const schema = z.object({
  company: text(160),
  contact_name: text(160),
  email: z.string().trim().toLowerCase().email("Enter a valid email address").max(254),
  phone: z.string().trim().max(32),
  brief: text(2000),
});

export type EnquiryField = "company" | "contact_name" | "email" | "phone" | "brief";
export interface CampaignEnquiryState {
  submitted?: boolean;
  error?: string;
  fieldErrors?: Partial<Record<EnquiryField, string>>;
  values?: Partial<Record<EnquiryField, string>>;
}

export async function submitCampaignEnquiry(
  _previous: CampaignEnquiryState,
  formData: FormData,
): Promise<CampaignEnquiryState> {
  const raw = {
    company: formData.get("company"),
    contact_name: formData.get("contact_name"),
    email: formData.get("email"),
    phone: formData.get("phone") ?? "",
    brief: formData.get("brief"),
  };
  // Return only bounded text to preserve the form after failures, never File objects.
  const values = Object.fromEntries(
    Object.entries(raw).map(([key, value]) => [
      key,
      typeof value === "string" ? value.slice(0, key === "brief" ? 2000 : 254) : "",
    ]),
  );
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    const errors = parsed.error.flatten().fieldErrors;
    return {
      values,
      fieldErrors: Object.fromEntries(
        Object.entries(errors).map(([key, messages]) => [key, messages?.[0]]),
      ),
    };
  }
  try {
    const ip = loginClientIpHeader(await headers(), env().LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER);
    const { data } = await createLoginApiClient(ip).POST("/api/v1/campaign-enquiries", {
      body: parsed.data,
    });
    if (data?.status === "submitted") return { submitted: true };
  } catch (error) {
    if (error instanceof ApiError && error.status === 429) {
      return { values, error: "Please wait before sending another enquiry, or email us directly." };
    }
  }
  return {
    values,
    error: "We could not confirm your enquiry was sent. Please try again or email us directly.",
  };
}
