"use server";

import { headers } from "next/headers";
import { z } from "zod";
import { createApiClient, createLoginApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { env } from "@/lib/env";

const optionalText = (max: number) =>
  z.preprocess((value) => {
    const text = String(value ?? "").trim();
    return text || undefined;
  }, z.string().max(max).optional());

const applicationSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  full_name: z.string().trim().min(1, "Enter your full name").max(255),
  phone: optionalText(32),
  service_city: z
    .string({ error: "Enter the city you drive in" })
    .trim()
    .min(1, "Enter the city you drive in")
    .max(128, "Use 128 characters or fewer for your city"),
  country_code: optionalText(2).transform((value) => value?.toUpperCase()),
});

const onboardingAccessSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
});

export interface DriverApplicationState {
  error?: string;
  fieldErrors?: Partial<
    Record<"email" | "full_name" | "phone" | "service_city" | "country_code", string>
  >;
  submitted?: boolean;
}

export interface DriverOnboardingAccessState {
  error?: string;
  done?: string;
  email?: string;
}

export async function submitDriverApplicationAction(
  _previous: DriverApplicationState,
  formData: FormData,
): Promise<DriverApplicationState> {
  const parsed = applicationSchema.safeParse({
    email: formData.get("email"),
    full_name: formData.get("full_name"),
    phone: formData.get("phone"),
    service_city: formData.get("service_city"),
    country_code: formData.get("country_code"),
  });
  if (!parsed.success) {
    const fields = parsed.error.flatten().fieldErrors;
    return {
      fieldErrors: {
        email: fields.email?.[0],
        full_name: fields.full_name?.[0],
        phone: fields.phone?.[0],
        service_city: fields.service_city?.[0],
        country_code: fields.country_code?.[0],
      },
    };
  }

  try {
    const { data } = await createApiClient().POST("/api/v1/auth/register-driver", {
      body: parsed.data,
    });
    if (!data)
      return { error: "We couldn't send your application right now. Please try again later." };
    return { submitted: true };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? "We couldn't send your application right now. Please try again later."
          : "We couldn't connect. Check your internet connection and try again.",
    };
  }
}

export async function requestDriverOnboardingAccessAction(
  _previous: DriverOnboardingAccessState,
  formData: FormData,
): Promise<DriverOnboardingAccessState> {
  const parsed = onboardingAccessSchema.safeParse({ email: formData.get("email") });
  if (!parsed.success) {
    return {
      error: parsed.error.flatten().fieldErrors.email?.[0] ?? "Enter a valid email address",
      email: String(formData.get("email") ?? ""),
    };
  }

  try {
    const config = env();
    const clientIp = loginClientIpHeader(
      await headers(),
      config.LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER,
    );
    await createLoginApiClient(clientIp).POST("/api/v1/auth/driver-onboarding-access/request", {
      body: { email: parsed.data.email },
    });
  } catch {
    return {
      error: "We couldn't send a new link right now. Try again in a few minutes.",
      email: parsed.data.email,
    };
  }

  return {
    done: "If your application is still open, we've emailed you a link to continue.",
    email: parsed.data.email,
  };
}
