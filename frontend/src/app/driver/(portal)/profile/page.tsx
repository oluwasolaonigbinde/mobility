import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { ProfileForm } from "./profile-form";

export const metadata: Metadata = { title: "Profile" };

export default async function DriverProfilePage() {
  const api = createApiClient(await getSessionToken());

  const [profile, vehicles, assignments, ledger] = await Promise.all([
    api.GET("/api/v1/driver/profile").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/vehicles", { params: { query: { limit: 20 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api
      .GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) return { data: undefined };
        throw e;
      }),
    api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 50 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
  ]);

  const p = profile.data;
  const vs = vehicles.data?.items ?? [];
  const assignmentItems = assignments.data?.items ?? [];
  const ledgerItems = ledger.data?.items ?? [];

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Profile</h1>

      {!p ? (
        <Panel className="p-6 text-center">
          <p className="text-sm font-medium">No driver profile yet</p>
          <p className="text-muted mt-1 text-xs">
            Ops creates your driver profile during onboarding. Contact your fleet manager.
          </p>
        </Panel>
      ) : (
        <>
          <Panel className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-base font-medium">{p.full_name}</p>
                <p className="micro text-faint mt-0.5">{p.email}</p>
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
                {p.onboarding_status}
              </StatusChip>
            </div>
          </Panel>

          <div className="grid grid-cols-3 gap-3">
            <Panel className="p-3.5 text-center">
              <p className="micro text-faint">Campaigns</p>
              <p className="font-display mt-1 text-2xl font-semibold">{assignmentItems.length}</p>
            </Panel>
            <Panel className="p-3.5 text-center">
              <p className="micro text-faint">Trip payouts</p>
              <p className="font-display mt-1 text-2xl font-semibold">
                {ledgerItems.filter((entry) => entry.trip_session_id).length}
              </p>
            </Panel>
            <Panel className="p-3.5 text-center">
              <p className="micro text-faint">Vehicles</p>
              <p className="font-display mt-1 text-2xl font-semibold">{vs.length}</p>
            </Panel>
          </div>

          <Panel className="p-5">
            <h2 className="micro text-muted">Driver readiness</h2>
            <ul className="mt-4 space-y-3">
              {[
                ["Profile", p.onboarding_status === "active", "Onboarding approved by ops"],
                ["Vehicle", vs.some((vehicle) => vehicle.status === "active"), "Active vehicle"],
                [
                  "Campaign",
                  assignmentItems.some((item) => item.status === "active"),
                  "Ready to track and earn",
                ],
              ].map(([label, ready, detail]) => (
                <li key={String(label)} className="flex items-center gap-3">
                  <span
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs ${
                      ready ? "bg-green/10 text-green" : "bg-amber/10 text-amber"
                    }`}
                  >
                    {ready ? "✓" : "!"}
                  </span>
                  <div>
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-faint text-xs">{detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel className="p-5">
            <h2 className="micro text-muted mb-4">Driver details</h2>
            <ProfileForm
              defaults={{
                license_number: p.license_number ?? "",
                service_city: p.service_city ?? "",
                country_code: p.country_code ?? "",
              }}
            />
          </Panel>

          <Panel className="overflow-hidden">
            <div className="border-edge border-b px-5 py-3.5">
              <h2 className="micro text-muted">My vehicles · {vs.length}</h2>
            </div>
            {vs.length === 0 ? (
              <p className="text-muted px-5 py-8 text-center text-sm">
                No vehicles registered — ops adds vehicles to your profile.
              </p>
            ) : (
              <ul className="divide-edge/60 divide-y">
                {vs.map((v) => (
                  <li key={v.id} className="flex items-center justify-between px-5 py-3.5">
                    <div>
                      <p className="font-mono text-sm">{v.plate_number}</p>
                      <p className="micro text-faint mt-0.5">
                        {[v.year, v.make, v.model, v.color].filter(Boolean).join(" ") ||
                          v.vehicle_type}
                      </p>
                    </div>
                    <StatusChip tone={v.status === "active" ? "green" : "default"}>
                      {v.status}
                    </StatusChip>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
