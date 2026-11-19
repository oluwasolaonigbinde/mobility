import "server-only";
import { cookies } from "next/headers";

/** httpOnly cookie holding the server-issued feedback review token (REQ-336). */
export const FEEDBACK_REVIEW_COOKIE = "cardvert_feedback_review";
const MAX_AGE_SECONDS = 12 * 60 * 60;

export async function getReviewToken(): Promise<string | undefined> {
  return (await cookies()).get(FEEDBACK_REVIEW_COOKIE)?.value || undefined;
}

export async function setReviewToken(token: string, expiresAt: string): Promise<void> {
  const remaining = Math.floor((Date.parse(expiresAt) - Date.now()) / 1000);
  const maxAge = Number.isFinite(remaining)
    ? Math.max(0, Math.min(MAX_AGE_SECONDS, remaining))
    : MAX_AGE_SECONDS;
  (await cookies()).set(FEEDBACK_REVIEW_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge,
  });
}

export async function clearReviewToken(): Promise<void> {
  (await cookies()).delete(FEEDBACK_REVIEW_COOKIE);
}
