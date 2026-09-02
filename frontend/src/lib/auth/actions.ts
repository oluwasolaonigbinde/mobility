"use server";

import { env } from "@/lib/env";
import { clearSessionCookie, getSessionToken } from "./session";

export interface SignOutResult {
  globalRevocationConfirmed: boolean;
  globalRevocationFailed: boolean;
}

export async function signOutAction(): Promise<SignOutResult> {
  const token = await getSessionToken();
  let revocationFailure: Error | undefined;
  let globalRevocationConfirmed = false;
  if (token) {
    try {
      const response = await fetch(`${env().API_BASE_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (response.status === 204) {
        globalRevocationConfirmed = true;
      } else if (response.status !== 401 && response.status !== 403) {
        revocationFailure = new Error("Unable to revoke all sessions");
      }
    } catch {
      revocationFailure = new Error("Unable to revoke all sessions");
    }
  }
  if (!revocationFailure) await clearSessionCookie();
  return {
    globalRevocationConfirmed,
    globalRevocationFailed: revocationFailure !== undefined,
  };
}
