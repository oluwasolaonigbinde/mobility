import type { Metadata } from "next";
import { ComplaintHelpPage } from "@/components/complaints/complainant-pages";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { readDriverApi } from "@/lib/driver/api-read";
import { formatMoney } from "@/lib/format";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Help" };

export default async function DriverHelpPage() {
  const api = createApiClient(await getSessionToken());
  const active = await readDriverApi(() => api.GET("/api/v1/driver/campaign-assignments/active"));
  if (active.state === "auth") redirect("/login");
  const payout =
    active.state === "ready"
      ? (active.data.assignment?.offer_terms?.payout as Record<string, unknown> | undefined)
      : undefined;
  const driverPayText =
    payout?.formula_version === "payout_v4" &&
    Number(payout.daily_rate_naira) > 0 &&
    Number(payout.daily_target_miles) > 0
      ? `Your day rate is ${formatMoney(String(payout.daily_rate_naira))} for ${String(payout.daily_target_miles)} miles inside the campaign area; shorter days earn a proportional share, up to the day rate.`
      : "Your accepted job keeps its agreed pay terms; contact support for help with your calculation.";
  return <ComplaintHelpPage party="driver" driverPayText={driverPayText} />;
}
