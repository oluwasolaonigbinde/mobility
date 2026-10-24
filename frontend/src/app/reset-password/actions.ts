"use server";

import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { publicActionError } from "@/lib/api/public-action-error";

const completeSchema = z
  .object({
    token: z.string().trim().min(1).max(512),
    newPassword: z.string().min(12, "Use at least 12 characters"),
    confirmPassword: z.string(),
  })
  .refine((value) => value.newPassword === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match",
  });

export interface PasswordResetCompleteState {
  error?: string;
  requestNewLink?: boolean;
  done?: string;
}

export async function completePasswordResetAction(
  _previous: PasswordResetCompleteState,
  formData: FormData,
): Promise<PasswordResetCompleteState> {
  return completePasswordAction(formData, false);
}

export async function completeAdvertiserInviteAction(
  _previous: PasswordResetCompleteState,
  formData: FormData,
): Promise<PasswordResetCompleteState> {
  return completePasswordAction(formData, true);
}

async function completePasswordAction(
  formData: FormData,
  invite: boolean,
): Promise<PasswordResetCompleteState> {
  const parsed = completeSchema.safeParse({
    token: formData.get("token"),
    newPassword: formData.get("new_password"),
    confirmPassword: formData.get("confirm_password"),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Check the password fields." };
  }
  try {
    await createApiClient().POST(
      invite ? "/api/v1/auth/advertiser-invite/complete" : "/api/v1/auth/password-reset/complete",
      {
        body: { token: parsed.data.token, new_password: parsed.data.newPassword },
      },
    );
  } catch (error) {
    return {
      ...(!invite && error instanceof ApiError && error.code === "PASSWORD_RESET_INVALID"
        ? { requestNewLink: true }
        : {}),
      error: publicActionError(
        error,
        {
          PASSWORD_RESET_INVALID: "This reset link is invalid, expired, or already used.",
          ADVERTISER_INVITE_INVALID:
            "This invite link is invalid, expired, or already used. Ask Terrax for a new invite.",
          PASSWORD_TOO_SHORT: "Use at least 12 characters.",
        },
        invite
          ? "The invite couldn't be completed. Ask Terrax for a new invite."
          : "The password could not be reset. Request a new link and try again.",
      ),
    };
  }
  return {
    done: invite
      ? "Your login is ready. Sign in with your new password."
      : "Password reset completed. Sign in with your new password.",
  };
}
