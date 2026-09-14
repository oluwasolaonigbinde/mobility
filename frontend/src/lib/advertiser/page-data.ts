import "server-only";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/errors";

export type UnavailableReason = "gated" | "forbidden" | "missing" | "operational" | "protocol";
export type PageData<T> =
  { available: true; data: T } | { available: false; reason: UnavailableReason };

export async function loadAdvertiserPageData<T>(
  request: () => Promise<{ data?: T }>,
): Promise<PageData<T>> {
  try {
    const { data } = await request();
    return data == null ? { available: false, reason: "protocol" } : { available: true, data };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/login");
      if (error.code === "PRIVACY_LIVE_USE_BLOCKED") return { available: false, reason: "gated" };
      if (error.status === 403) return { available: false, reason: "forbidden" };
      if (error.status === 404) return { available: false, reason: "missing" };
      if (error.status === 429 || error.status >= 500) {
        return { available: false, reason: "operational" };
      }
    }
    if (
      error instanceof TypeError &&
      /^(fetch failed|failed to fetch|NetworkError when attempting to fetch resource\.?)$/i.test(
        error.message,
      )
    ) {
      return { available: false, reason: "operational" };
    }
    throw error;
  }
}
