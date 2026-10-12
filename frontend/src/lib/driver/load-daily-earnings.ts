import "server-only";
import type { ApiClient } from "@/lib/api/client";
import { readDriverApi } from "./api-read";
import { activeHeldTripIds } from "./earnings-presentation";
import { dailyEarnings } from "./daily-earnings";
import type { components } from "@/lib/api/schema";

export async function loadDailyEarnings(api: ApiClient) {
  const holds = await readDriverApi(() => api.GET("/api/v1/driver/fraud-holds"));
  if (holds.state !== "ready") return holds;
  const entries: components["schemas"]["EarningsLedgerEntryRead"][] = [];
  let total: number | undefined;
  for (let offset = 0; offset < 2000; offset += 100) {
    const page = await readDriverApi(() =>
      api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 100, offset } } }),
    );
    if (page.state !== "ready") return page;
    if (
      !Number.isSafeInteger(page.data.total) ||
      (total !== undefined && page.data.total !== total)
    )
      return { state: "unavailable" as const };
    total = page.data.total;
    entries.push(...page.data.items);
    if (entries.length === total) {
      if (new Set(entries.map((entry) => entry.id)).size !== entries.length)
        return { state: "unavailable" as const };
      const days = dailyEarnings(entries, activeHeldTripIds(holds.data.items));
      return days === null
        ? { state: "unavailable" as const }
        : { state: "ready" as const, data: days };
    }
    if (page.data.items.length !== 100) break;
  }
  return { state: "unavailable" as const };
}
