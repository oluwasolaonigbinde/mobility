"use server";

import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { publicActionError } from "@/lib/api/public-action-error";

const setupSchema = z
  .object({
    token: z.string().trim().min(1).max(512),
    newPassword: z.string().min(12, "Use at least 12 characters"),
    confirmPassword: z.string(),
  })
  .refine((value) => value.newPassword === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match",
  });

export interface DriverAccountSetupState {
  error?: string;
  done?: string;
}

export async function completeDriverAccountSetupAction(
  _previous: DriverAccountSetupState,
  formData: FormData,
): Promise<DriverAccountSetupState> {
  const parsed = setupSchema.safeParse({
    token: formData.get("token"),
    newPassword: formData.get("new_password"),
    confirmPassword: formData.get("confirm_password"),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Check the password fields." };
  }

  try {
    await createApiClient().POST("/api/v1/auth/driver-account-setup/complete", {
      body: { token: parsed.data.token, new_password: parsed.data.newPassword },
    });
  } catch (error) {
    return {
      error: publicActionError(
        error,
        {
          DRIVER_ACCOUNT_SETUP_INVALID: "This setup action is invalid, expired, or already used.",
          PASSWORD_TOO_SHORT: "Use at least 12 characters.",
        },
        "Account setup is temporarily unavailable. Try again later.",
      ),
    };
  }

  return { done: "Account setup completed. Sign in with your new password." };
}
