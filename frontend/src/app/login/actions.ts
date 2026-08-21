"use server";

import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { z } from "zod";
import { createLoginApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { setSessionCookie } from "@/lib/auth/session";
import { changePasswordPath, roleHome } from "@/lib/auth/current-user";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { env } from "@/lib/env";
import { demoLoginRoleSchema, type DemoLoginRole } from "./demo-role";

const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export interface LoginState {
  error?: string;
  fieldErrors?: Partial<Record<"email" | "password", string>>;
}

export async function demoLoginAction(
  role: DemoLoginRole,
  _prev: LoginState,
  _formData: FormData,
): Promise<LoginState> {
  void _prev;
  void _formData;
  const parsedRole = demoLoginRoleSchema.safeParse(role);
  if (!parsedRole.success) return { error: "Sign-in is unavailable." };

  const config = env();
  const credentialsByRole = {
    advertiser: {
      email: config.DEMO_LOGIN_ADVERTISER_EMAIL,
      password: config.DEMO_LOGIN_ADVERTISER_PASSWORD,
    },
    driver: {
      email: config.DEMO_LOGIN_DRIVER_EMAIL,
      password: config.DEMO_LOGIN_DRIVER_PASSWORD,
    },
    admin: {
      email: config.DEMO_LOGIN_ADMIN_EMAIL,
      password: config.DEMO_LOGIN_ADMIN_PASSWORD,
    },
  } satisfies Record<DemoLoginRole, { email?: string; password?: string }>;
  const selected = credentialsByRole[parsedRole.data];
  if (!config.DEMO_LOGIN_ENABLED || !selected.email || !selected.password) {
    return { error: "Sign-in is unavailable." };
  }

  const credentials = new FormData();
  credentials.set("email", selected.email);
  credentials.set("password", selected.password);
  return loginAction({}, credentials);
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
    const clientIp = loginClientIpHeader(
      await headers(),
      env().LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER,
    );
    const api = createLoginApiClient(clientIp);
    const { data } = await api.POST("/api/v1/auth/login", { body: parsed.data });
    if (!data) {
      return { error: "Unexpected empty response from the server." };
    }
    await setSessionCookie(data.access_token, data.expires_in);
    home = data.user.must_change_password
      ? changePasswordPath(data.user.role)
      : roleHome(data.user.role);
  } catch (error) {
    if (error instanceof ApiError) {
      // Backend deliberately does not reveal whether the email exists.
      return {
        error:
          error.status === 429
            ? `Too many attempts. Try again in ${String(error.details?.retry_after_seconds ?? "a few")} seconds.`
            : error.status === 401 || error.status === 403
              ? "Invalid email or password, or the account is not active."
              : error.message,
      };
    }
    return { error: "Could not reach the server. Please try again." };
  }
  redirect(home);
}
