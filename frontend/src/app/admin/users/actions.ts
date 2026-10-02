"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface AdminActionState {
  error?: string;
}

const createUserSchema = z
  .object({
    email: z.string().trim().toLowerCase().email("Enter a valid email"),
    full_name: z.string().trim().min(1, "Full name is required").max(255),
    phone: z
      .string()
      .trim()
      .max(32)
      .transform((v) => (v === "" ? null : v)),
    role: z.enum(["admin", "advertiser", "driver"]),
    password: z.string().min(12, "Password must be at least 12 characters"),
    current_password: z.string().optional(),
    // Advertiser onboarding optionally creates its company.
    org_name: z
      .string()
      .trim()
      .max(255)
      .transform((v) => (v === "" ? undefined : v))
      .optional(),
    org_currency: z
      .string()
      .trim()
      .toUpperCase()
      .transform((v) => (v === "" ? undefined : v))
      .pipe(z.string().length(3, "Use a 3-letter currency code").optional()),
  })
  .superRefine((data, ctx) => {
    if (data.role === "admin" && !data.current_password) {
      ctx.addIssue({
        code: "custom",
        path: ["current_password"],
        message: "Your current password is required",
      });
    }
    if (data.org_name && data.role !== "advertiser") {
      ctx.addIssue({
        code: "custom",
        path: ["org_name"],
        message: "Companies attach to advertiser logins",
      });
    }
  });

export async function createUserAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const parsed = createUserSchema.safeParse({
    email: formData.get("email"),
    full_name: formData.get("full_name"),
    phone: formData.get("phone") ?? "",
    role: formData.get("role"),
    password: formData.get("password"),
    current_password: formData.get("current_password") ?? undefined,
    org_name: formData.get("org_name") ?? "",
    org_currency: formData.get("org_currency") ?? "",
  });
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return { error: first?.message ?? "Invalid input" };
  }
  const { org_name, org_currency, current_password, ...user } = parsed.data;

  const api = createApiClient(await getSessionToken());
  let userId: string;
  let organizationId: string | undefined;
  try {
    const { data } = await api.POST("/api/v1/admin/users", {
      body: { ...user, status: "active", ...(user.role === "admin" ? { current_password } : {}) },
    });
    if (!data) return { error: "Unexpected empty response creating the user." };
    userId = data.id;
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  if (org_name) {
    try {
      const { data } = await api.POST("/api/v1/admin/advertiser-organizations", {
        body: {
          name: org_name,
          currency: org_currency ?? "NGN",
          owner_user_id: userId,
          status: "active",
        },
      });
      organizationId = data?.organization.id;
    } catch (error) {
      const reason = error instanceof ApiError ? error.message : "server unreachable";
      return {
        error: `Login created, but the company failed: ${reason}.`,
      };
    }
  }

  const destination =
    user.role === "admin"
      ? "/admin/settings/staff"
      : user.role === "advertiser"
        ? organizationId
          ? `/admin/advertisers/${organizationId}`
          : "/admin/advertisers"
        : "/admin/drivers";
  revalidatePath(destination);
  redirect(destination);
}

const userStatusSchema = z.object({
  userId: z.string().uuid(),
  status: z.enum(["active", "invited", "suspended", "disabled"]),
  current_password: z.string().min(1).optional(),
});

export async function updateUserStatusAction(
  input: z.input<typeof userStatusSchema>,
): Promise<AdminActionState> {
  const parsed = userStatusSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid request" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/admin/users/{user_id}", {
      params: { path: { user_id: parsed.data.userId } },
      body: {
        status: parsed.data.status,
        ...(parsed.data.current_password !== undefined
          ? { current_password: parsed.data.current_password }
          : {}),
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/settings/staff");
  return {};
}
