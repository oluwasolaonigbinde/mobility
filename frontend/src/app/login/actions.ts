"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { setSessionCookie } from "@/lib/auth/session";
import { roleHome } from "@/lib/auth/current-user";

const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export interface LoginState {
  error?: string;
  fieldErrors?: Partial<Record<"email" | "password", string>>;
}

export async function loginAction(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const parsed = credentialsSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    const flat = parsed.error.flatten().fieldErrors;
    return {
      fieldErrors: {
        email: flat.email?.[0],
        password: flat.password?.[0],
      },
    };
  }

  let home: string;
  try {
    const api = createApiClient();
    const { data } = await api.POST("/api/v1/auth/login", { body: parsed.data });
    if (!data) {
      return { error: "Unexpected empty response from the server." };
    }
    await setSessionCookie(data.access_token, data.expires_in);
    home = roleHome(data.user.role);
  } catch (error) {
    if (error instanceof ApiError) {
      // Backend deliberately does not reveal whether the email exists.
      return {
        error:
          error.status === 401 || error.status === 403
            ? "Invalid email or password, or the account is not active."
            : error.message,
      };
    }
    return { error: "Could not reach the server. Please try again." };
  }
  redirect(home);
}
