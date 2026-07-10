import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatDateRange } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { AssignmentActions } from "./assignment-actions";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Jobs" };

type AssignmentStatus = components["schemas"]["CampaignAssignmentStatus"];

const statusMeta: Record<
  AssignmentStatus,
  { label: string; tone: "default" | "amber" | "cyan" | "green" | "coral" }
> = {
  offered: { label: "Offered", tone: "cyan" },
  accepted: { label: "Accepted", tone: "amber" },
  active: { label: "Active", tone: "green" },
  deactivated: { label: "Deactivated", tone: "default" },
  cancelled: { label: "Cancelled", tone: "coral" },
  completed: { label: "Completed", tone: "default" },
};

export default async function DriverAssignmentsPage() {
  const api = createApiClient(await getSessionToken());
  const { data } = await api
    .GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } })
    .catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    });

  const items = data?.items ?? [];

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>

      {items.length === 0 ? (
        <Panel className="p-6 text-center">
          <p className="text-sm font-medium">No jobs yet</p>
          <p className="text-muted mt-1 text-xs">
            Campaign offers appear here once ops assigns your vehicle.
          </p>
        </Panel>
      ) : (
        items.map((a) => (
          <Panel key={a.id} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-base font-medium">{a.campaign?.name ?? "Campaign"}</p>
                <p className="micro text-faint mt-1">
                  {formatDateRange(a.campaign?.start_at, a.campaign?.end_at)}
                </p>
                <p className="micro text-faint mt-0.5">
                  {a.vehicle?.plate_number ?? "—"} · {a.vehicle?.vehicle_type ?? "vehicle"}
                </p>
              </div>
              <StatusChip tone={statusMeta[a.status].tone}>{statusMeta[a.status].label}</StatusChip>
            </div>
            <AssignmentActions assignmentId={a.id} status={a.status} />
          </Panel>
        ))
      )}
    </div>
  );
}
