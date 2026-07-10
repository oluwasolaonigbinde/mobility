import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { VehicleStatusMenu } from "./vehicle-status-menu";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Vehicles" };

const PAGE_SIZE = 25;
type VStatus = components["schemas"]["VehicleStatus"];

const tone: Record<VStatus, "green" | "amber" | "coral" | "default"> = {
  active: "green",
  pending: "amber",
  suspended: "coral",
  inactive: "default",
};

export default async function AdminVehiclesPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/vehicles", {
    params: { query: { limit: PAGE_SIZE, offset } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Vehicles"
        eyebrow={`${total} vehicle${total === 1 ? "" : "s"} in the fleet`}
        actions={
          <Link
            href="/admin/vehicles/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + Register vehicle
          </Link>
        }
      />

      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-5 py-3.5 font-normal">Plate</th>
                <th className="px-5 py-3.5 font-normal">Vehicle</th>
                <th className="px-5 py-3.5 font-normal">Type</th>
                <th className="px-5 py-3.5 font-normal">Status</th>
                <th className="px-5 py-3.5 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((v) => (
                <tr key={v.id} className="border-edge/60 border-b last:border-0">
                  <td className="px-5 py-3.5 font-mono text-xs">{v.plate_number}</td>
                  <td className="px-5 py-3.5">
                    {[v.year, v.make, v.model, v.color].filter(Boolean).join(" ") || "—"}
                  </td>
                  <td className="px-5 py-3.5 capitalize">{v.vehicle_type}</td>
                  <td className="px-5 py-3.5">
                    <StatusChip tone={tone[v.status]}>{v.status}</StatusChip>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <VehicleStatusMenu vehicleId={v.id} status={v.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => (o ? `/admin/vehicles?offset=${o}` : "/admin/vehicles")}
      />
    </div>
  );
}
