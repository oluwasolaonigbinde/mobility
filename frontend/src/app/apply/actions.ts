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
  service_city: optionalText(128),
  country_code: optionalText(2).transform((value) => value?.toUpperCase()),
});

const statusSchema = z.object({
  reference: z.string().trim().min(1, "Enter your application reference").max(255),
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
  reference?: string;
}

export interface DriverApplicationStatusState {
  error?: string;
  pending?: boolean;
  reference?: string;
  personPayeeStatus?: string;
  vehicleStatus?: string;
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
    if (!data) return { error: "Application service is unavailable right now." };
    return {
      submitted: true,
      reference: data.application_reference ?? undefined,
    };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? "Application service is unavailable right now."
          : "Could not reach the application service.",
    };
  }
}

export async function checkDriverApplicationStatusAction(
  _previous: DriverApplicationStatusState,
  formData: FormData,
): Promise<DriverApplicationStatusState> {
  const parsed = statusSchema.safeParse({ reference: formData.get("reference") });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Enter your reference" };

  try {
    const { data } = await createApiClient().GET(
      "/api/v1/auth/driver-application-status/{reference}",
      { params: { path: { reference: parsed.data.reference } } },
    );
    return data?.status === "pending"
      ? {
          pending: true,
          reference: parsed.data.reference,
          personPayeeStatus: data.person_payee?.status ?? "not_submitted",
          vehicleStatus: data.vehicle?.status ?? "not_submitted",
        }
      : { error: "Application status is unavailable right now." };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? "Application status is unavailable right now."
          : "Could not reach the application service.",
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
      error: "Onboarding access is temporarily unavailable. Try again later.",
      email: parsed.data.email,
    };
  }

  return {
    done: "If the application can continue, a new onboarding code will be sent.",
    email: parsed.data.email,
  };
}
