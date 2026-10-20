import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { readDriverApi } from "./api-read";
import { presentEarningsDay } from "./daily-earnings";

/** One read: the server totals every day and the headline figures (REQ-208). */
export async function loadDailyEarnings(api: ApiClient) {
  const result = await readDriverApi(() => api.GET("/api/v1/driver/earnings/days"));
  if (result.state !== "ready") return result;
  return {
    state: "ready" as const,
    data: { days: result.data.days.map(presentEarningsDay), totals: result.data.totals },
  };
}
