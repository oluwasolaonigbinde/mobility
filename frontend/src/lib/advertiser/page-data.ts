import "server-only";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/errors";
import { completePages, IncompletePagesError } from "@/lib/complete-pages";

export type UnavailableReason =
  "forbidden" | "missing" | "operational" | "protocol" | "insufficient";
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
      if (error.status === 403) return { available: false, reason: "forbidden" };
      if (error.status === 404) return { available: false, reason: "missing" };
      if (error.status === 409 && error.code === "DISCLOSURE_SUPPRESSED") {
        return { available: false, reason: "insufficient" };
      }
      if (error.status === 409 && error.code === "CAMPAIGN_REPORT_PENDING")
        return { available: false, reason: "operational" };
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

/** Every page of an advertiser list, or why it is unavailable; each row must pass `belongs`. */
export async function loadAllAdvertiserPages<T extends { id: string }>(
  read: (offset: number) => Promise<{ data?: { items: T[]; total: number } }>,
  belongs: (item: T) => boolean = () => true,
): Promise<PageData<T[]>> {
  try {
    const items = await completePages(async (offset) => {
      const page = await loadAdvertiserPageData(() => read(offset));
      if (!page.available) throw new IncompletePagesError(page.reason);
      return { data: page.data };
    });
    return items.every(belongs)
      ? { available: true, data: items }
      : { available: false, reason: "protocol" };
  } catch (error) {
    if (error instanceof IncompletePagesError) return { available: false, reason: error.reason };
    throw error;
  }
}
