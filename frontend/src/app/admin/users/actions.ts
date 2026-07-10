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
    // Advertiser onboarding: optionally create the organization in the same step
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
    if (data.org_name && data.role !== "advertiser") {
      ctx.addIssue({
        code: "custom",
        path: ["org_name"],
        message: "Organizations attach to advertiser users",
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
    org_name: formData.get("org_name") ?? "",
    org_currency: formData.get("org_currency") ?? "",
  });
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return { error: first?.message ?? "Invalid input" };
  }
  const { org_name, org_currency, ...user } = parsed.data;

  const api = createApiClient(await getSessionToken());
  let userId: string;
  try {
    const { data } = await api.POST("/api/v1/admin/users", {
      body: { ...user, status: "active" },
    });
    if (!data) return { error: "Unexpected empty response creating the user." };
    userId = data.id;
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  if (org_name) {
    try {
      await api.POST("/api/v1/admin/advertiser-organizations", {
        body: {
          name: org_name,
          currency: org_currency ?? "NGN",
          owner_user_id: userId,
          status: "active",
        },
      });
    } catch (error) {
      const reason = error instanceof ApiError ? error.message : "server unreachable";
      return {
        error: `User created, but the organization failed: ${reason}. Create it again from this page.`,
      };
    }
  }

  revalidatePath("/admin/users");
  redirect("/admin/users");
}

const userStatusSchema = z.object({
  userId: z.string().uuid(),
  status: z.enum(["active", "invited", "suspended", "disabled"]),
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
      body: { status: parsed.data.status },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/users");
  return {};
}
