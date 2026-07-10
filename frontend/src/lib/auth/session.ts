import "server-only";
import { cookies } from "next/headers";
import { env } from "@/lib/env";

/**
 * Session = the backend JWT stored in an httpOnly cookie.
 *
 * The token is never readable by browser JavaScript (XSS-safe) and never
 * stored in localStorage. The backend has no refresh tokens, so the cookie
 * simply expires alongside the JWT and the user is routed back to login.
 */

export async function setSessionCookie(token: string, expiresInSeconds: number): Promise<void> {
  const store = await cookies();
  store.set(env().SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: env().NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: expiresInSeconds,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(env().SESSION_COOKIE_NAME);
}

export async function getSessionToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(env().SESSION_COOKIE_NAME)?.value;
}
