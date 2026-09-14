"use server";

import { headers } from "next/headers";
import { z } from "zod";
import { createLoginApiClient } from "@/lib/api/client";
import { publicActionError } from "@/lib/api/public-action-error";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { env } from "@/lib/env";

const requestSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
});

export interface PasswordResetRequestState {
  error?: string;
  done?: string;
  email?: string;
}

export async function requestPasswordResetAction(
  _previous: PasswordResetRequestState,
  formData: FormData,
): Promise<PasswordResetRequestState> {
  const parsed = requestSchema.safeParse({ email: formData.get("email") });
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
    await createLoginApiClient(clientIp).POST("/api/v1/auth/password-reset/request", {
      body: { email: parsed.data.email },
    });
  } catch (error) {
    return {
      error: publicActionError(
        error,
        {
          PASSWORD_RESET_RATE_LIMITED: "Too many requests. Wait before trying again.",
          RATE_LIMIT_UNAVAILABLE: "Password recovery is temporarily unavailable. Try again later.",
        },
        "Password recovery is temporarily unavailable. Try again later.",
      ),
      email: parsed.data.email,
    };
  }
  return {
    done: "If the account can be recovered, reset instructions will be sent.",
    email: parsed.data.email,
  };
}
