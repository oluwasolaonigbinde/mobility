import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { ProfileForm } from "./profile-form";
import { DocumentRenewals } from "./document-renewals";
import { PhoneVerification } from "./phone-verification";
import { DriverLogoutButton } from "@/components/driver/logout-button";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { readDriverApi } from "@/lib/driver/api-read";
import { formatMoney } from "@/lib/format";

export const metadata: Metadata = { title: "Profile" };

const accountLabel: Record<string, string> = {
  active: "Active",
  pending: "Being reviewed",
  suspended: "Suspended",
  rejected: "Not approved",
};

const vehicleLabel: Record<string, string> = {
  active: "Approved",
  pending: "Being reviewed",
  inactive: "Not in use",
  suspended: "Suspended",
};

export default async function DriverProfilePage() {
  const api = createApiClient(await getSessionToken());

  // The summary tiles read server totals; limited pages are never counted.
  const [profile, vehicles, assignments, ledger, earnings] = await Promise.all([
    readDriverApi(() => api.GET("/api/v1/driver/profile"), { notFoundIsMissing: true }),
    readDriverApi(() => api.GET("/api/v1/driver/vehicles", { params: { query: { limit: 20 } } })),
    readDriverApi(() =>
      api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 1 } } }),
    ),
    readDriverApi(() =>
      api.GET("/api/v1/driver/earnings/ledger", {
        params: { query: { entry_type: "trip_payout", limit: 1 } },
      }),
    ),
    readDriverApi(() => api.GET("/api/v1/driver/earnings/summary")),
  ]);

  if (
    [profile, vehicles, assignments, ledger, earnings].some((source) => source.state === "auth")
  ) {
    redirect("/login");
  }
  if (profile.state === "unavailable" || vehicles.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Profile</h1>
        <DriverDataUnavailable
          title="Current profile is unavailable"
          detail="Cardvert couldn't verify your current profile and vehicle ownership, so profile changes are unavailable. Try again shortly."
          retryHref="/driver/profile"
        />
        <DriverLogoutButton />
      </div>
    );
  }

  const p = profile.state === "ready" ? profile.data : undefined;
  const vs = vehicles.data.items;
  const campaignCount = assignments.state === "ready" ? assignments.data.total : null;
  const tripPayoutCount = ledger.state === "ready" ? ledger.data.total : null;
  const lifetime = earnings.state === "ready" ? (earnings.data.totals_by_currency ?? []) : [];

  return (
    <>
      <FreshDriverAuthority
        refreshKey={crypto.randomUUID()}
        title="Current profile hidden while offline"
        detail="Reconnect to verify your profile, vehicle ownership and work status. Profile changes are hidden until a fresh read succeeds."
        retryHref="/driver/profile"
      >
        <div className="animate-rise flex flex-col gap-4">
          <h1 className="font-display text-2xl font-semibold tracking-tight">Profile</h1>

          {campaignCount === null || tripPayoutCount === null ? (
            <DriverDataUnavailable
              title="Profile history unavailable"
              detail="Cardvert couldn't load optional campaign or trip counts. Your current profile and vehicle status remain available."
              retryHref="/driver/profile"
            />
          ) : null}

          {!p ? (
            <Panel className="p-6 text-center">
              <p className="text-sm font-medium">No driver profile yet</p>
              <p className="text-muted mt-1 text-xs">Your application is still being reviewed.</p>
            </Panel>
          ) : (
            <>
              <Panel className="p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-base font-medium">{p.full_name}</p>
                    <p className="text-muted mt-0.5 text-sm">{p.email}</p>
                  </div>
                  <StatusChip
                    tone={
                      p.onboarding_status === "active"
                        ? "green"
                        : p.onboarding_status === "pending"
                          ? "amber"
                          : "coral"
                    }
                  >
                    {accountLabel[p.onboarding_status] ?? "Unknown"}
                  </StatusChip>
                </div>
              </Panel>

              <h2 className="font-display -mb-1 text-lg font-semibold">Your history</h2>
              <div className="grid grid-cols-3 gap-3">
                <Panel className="p-3.5 text-center">
                  <p className="micro text-faint">Jobs</p>
                  <p className="font-display mt-1 text-2xl font-semibold">{campaignCount ?? "—"}</p>
                </Panel>
                <Panel className="p-3.5 text-center">
                  <p className="micro text-faint">Paid trips</p>
                  <p className="font-display mt-1 text-2xl font-semibold">
                    {tripPayoutCount ?? "—"}
                  </p>
                </Panel>
                <Panel className="p-3.5 text-center">
                  <p className="micro text-faint">Cars</p>
                  <p className="font-display mt-1 text-2xl font-semibold">{vehicles.data.total}</p>
                </Panel>
              </div>
              {lifetime.map((t) => (
                <p key={t.currency} className="text-muted -mt-1 text-sm">
                  Earned in total: {formatMoney(t.lifetime_earned_amount, t.currency)}
                </p>
              ))}

              <Panel className="p-5">
                <h2 className="font-display mb-4 text-lg font-semibold">Your details</h2>
                <Link
                  href="/driver/change-password"
                  className="text-green mb-4 inline-block text-sm underline"
                >
                  Change password
                </Link>
                <ProfileForm
                  defaults={{
                    license_number: p.license_number ?? "",
                    service_city: p.service_city ?? "",
                    country_code: p.country_code ?? "",
                  }}
                />
              </Panel>

              <DocumentRenewals driverId={p.user_id} />
              <PhoneVerification savedPhone={p.phone ?? ""} />

              <Panel className="overflow-hidden">
                <div className="border-edge border-b px-5 py-3.5">
                  <h2 className="font-display text-lg font-semibold">
                    Your cars
                    {vehicles.data.total > vs.length
                      ? ` · showing ${vs.length} of ${vehicles.data.total}`
                      : ""}
                  </h2>
                </div>
                {vs.length === 0 ? (
                  <p className="text-muted px-5 py-8 text-center text-sm">
                    No cars yet. Terrax Media adds your car once it is approved.
                  </p>
                ) : (
                  <ul className="divide-edge/60 divide-y">
                    {vs.map((v) => (
                      <li key={v.id} className="flex items-center justify-between px-5 py-3.5">
                        <div>
                          <p className="text-sm">{v.plate_number}</p>
                          <p className="text-muted mt-0.5 text-sm">
                            {[v.year, v.make, v.model, v.color].filter(Boolean).join(" ") ||
                              v.vehicle_type}
                          </p>
                        </div>
                        <StatusChip tone={v.status === "active" ? "green" : "default"}>
                          {vehicleLabel[v.status] ?? "Unknown"}
                        </StatusChip>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}
        </div>
      </FreshDriverAuthority>
      <div className="mt-4">
        <DriverLogoutButton />
      </div>
    </>
  );
}
