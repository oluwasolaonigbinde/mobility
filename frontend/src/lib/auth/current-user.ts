import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "./session";
import type { components } from "@/lib/api/schema";

export type MeResponse = components["schemas"]["MeResponse"];
export type Role = components["schemas"]["UserRole"];

/**
 * Fetch the authenticated user's context (/api/v1/me), memoized per request.
 *
 * Returns null when there is no session or the token is rejected — the
 * backend is the authority on token validity, not the frontend.
 */
export const getCurrentUser = cache(async (): Promise<MeResponse | null> => {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    const api = createApiClient(token);
    const { data } = await api.GET("/api/v1/me");
    return data ?? null;
  } catch (error) {
    if (error instanceof ApiError && error.isAuthError) {
      return null;
    }
    throw error;
  }
});

/**
 * Layout/page guard: require a signed-in user with one of the given roles.
 * Redirects are UX only — real enforcement happens in the backend on every
 * proxied call.
 */
export async function requireRole(...roles: Role[]): Promise<MeResponse> {
  const me = await getCurrentUser();
  if (!me) {
    redirect("/login");
  }
  if (!roles.includes(me.user.role)) {
    redirect(roleHome(me.user.role));
  }
  if (me.user.must_change_password) {
    redirect(changePasswordPath(me.user.role));
  }
  return me;
}

export function changePasswordPath(role: Role): string {
  return role === "driver" ? "/driver/change-password" : "/change-password";
}

/** Where each role lands after login. */
export function roleHome(role: Role): string {
  switch (role) {
    case "admin":
      return "/admin";
    case "advertiser":
      return "/advertiser";
    case "driver":
      return "/driver";
  }
}
