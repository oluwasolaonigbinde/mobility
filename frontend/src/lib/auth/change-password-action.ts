"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { roleHome } from "@/lib/auth/current-user";
import { getSessionToken, setSessionCookie } from "@/lib/auth/session";

const schema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password"),
    newPassword: z.string().min(12, "Use at least 12 characters"),
    confirmPassword: z.string().min(1, "Confirm your new password"),
  })
  .refine((value) => value.newPassword === value.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export interface ChangePasswordState {
  error?: string;
  fieldErrors?: Partial<Record<"currentPassword" | "newPassword" | "confirmPassword", string>>;
}

export async function changePasswordAction(
  _previous: ChangePasswordState,
  formData: FormData,
): Promise<ChangePasswordState> {
  const parsed = schema.safeParse({
    currentPassword: formData.get("currentPassword"),
    newPassword: formData.get("newPassword"),
    confirmPassword: formData.get("confirmPassword"),
  });
  if (!parsed.success) {
    const fields = parsed.error.flatten().fieldErrors;
    return {
      fieldErrors: {
        currentPassword: fields.currentPassword?.[0],
        newPassword: fields.newPassword?.[0],
        confirmPassword: fields.confirmPassword?.[0],
      },
    };
  }

  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/auth/change-password", {
      body: {
        current_password: parsed.data.currentPassword,
        new_password: parsed.data.newPassword,
      },
    });
    if (!data) return { error: "Unexpected empty response from the server." };
    await setSessionCookie(data.access_token, data.expires_in);
    redirect(roleHome(data.user.role));
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 429) return { error: "Too many attempts. Please try again shortly." };
      if (error.code === "CURRENT_PASSWORD_INCORRECT") {
        return { fieldErrors: { currentPassword: "Current password is incorrect" } };
      }
      return { error: error.message };
    }
    throw error;
  }
}
