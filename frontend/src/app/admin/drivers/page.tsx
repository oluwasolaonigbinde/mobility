import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { DriverOnboardingMenu } from "./onboarding-menu";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Drivers" };

const PAGE_SIZE = 25;
type Onboarding = components["schemas"]["DriverOnboardingStatus"];

const tone: Record<Onboarding, "green" | "amber" | "coral" | "default"> = {
  active: "green",
  pending: "amber",
  suspended: "coral",
  rejected: "default",
};

export default async function AdminDriversPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/drivers", {
    params: { query: { limit: PAGE_SIZE, offset } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Drivers"
        eyebrow={`${total} driver profile${total === 1 ? "" : "s"}`}
        actions={
          <Link
            href="/admin/drivers/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + Add driver profile
          </Link>
        }
      />

      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-5 py-3.5 font-normal">Driver</th>
                <th className="px-5 py-3.5 font-normal">Licence</th>
                <th className="px-5 py-3.5 font-normal">City</th>
                <th className="px-5 py-3.5 font-normal">Onboarding</th>
                <th className="px-5 py-3.5 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id} className="border-edge/60 border-b last:border-0">
                  <td className="px-5 py-3.5">
                    <p className="font-medium">{d.full_name}</p>
                    <p className="micro text-faint mt-0.5">{d.email}</p>
                  </td>
                  <td className="px-5 py-3.5 font-mono text-xs">{d.license_number ?? "—"}</td>
                  <td className="px-5 py-3.5">{d.service_city ?? "—"}</td>
                  <td className="px-5 py-3.5">
                    <StatusChip tone={tone[d.onboarding_status]}>{d.onboarding_status}</StatusChip>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <DriverOnboardingMenu driverProfileId={d.id} status={d.onboarding_status} />
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
        hrefFor={(o) => (o ? `/admin/drivers?offset=${o}` : "/admin/drivers")}
      />
    </div>
  );
}
