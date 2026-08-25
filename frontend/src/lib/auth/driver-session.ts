import "server-only";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken, setSessionCookie } from "./session";
import { tokenNeedsRefresh } from "./token";

export type DriverSessionStatus =
  | { status: "valid"; driverId: string }
  | { status: "missing" | "revoked" | "wrong-role" | "unavailable" };

/** Validate backend session/role and rotate only a currently valid driver cookie. */
export async function validateDriverSession(): Promise<DriverSessionStatus> {
  const token = await getSessionToken();
  if (!token) return { status: "missing" };
  try {
    const api = createApiClient(token);
    const { data: me } = await api.GET("/api/v1/me");
    if (!me) return { status: "unavailable" };
    if (me.user.role !== "driver") return { status: "wrong-role" };
    if (tokenNeedsRefresh(token, 30 * 60)) {
      const { data: refreshed } = await api.POST("/api/v1/auth/refresh");
      if (!refreshed) return { status: "unavailable" };
      await setSessionCookie(refreshed.access_token, refreshed.expires_in);
    }
    return { status: "valid", driverId: me.user.id };
  } catch (error) {
    if (error instanceof ApiError && (error.isAuthError || error.isForbidden)) {
      return { status: "revoked" };
    }
    return { status: "unavailable" };
  }
}
