"use server";

import { getCurrentUser } from "@/lib/auth/current-user";

/** Name to prefill in the feedback panel: the signed-in user's name, or blank. */
export async function feedbackNamePrefill(): Promise<string> {
  try {
    const me = await getCurrentUser();
    return me?.user.full_name.trim().slice(0, 120) ?? "";
  } catch {
    return "";
  }
}
