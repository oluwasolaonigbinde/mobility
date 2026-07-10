import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { AssignmentForm } from "./assignment-form";

export const metadata: Metadata = { title: "Offer assignment" };

export default async function NewAssignmentPage() {
  const api = createApiClient(await getSessionToken());
  const [{ data: campaigns }, { data: drivers }, { data: vehicles }] = await Promise.all([
    api.GET("/api/v1/admin/campaigns", { params: { query: { limit: 100 } } }),
    api.GET("/api/v1/admin/drivers", { params: { query: { limit: 100 } } }),
    api.GET("/api/v1/admin/vehicles", { params: { query: { limit: 100 } } }),
  ]);

  return (
    <div className="animate-rise mx-auto max-w-2xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/assignments" className="hover:text-muted">
          Assignments
        </Link>{" "}
        / <span className="text-muted">Offer</span>
      </nav>
      <PageHeader
        title="Offer assignment"
        eyebrow="Pair a campaign with a driver's vehicle — they accept in the driver app"
      />
      <Panel className="p-6 md:p-8">
        <AssignmentForm
          campaigns={(campaigns?.items ?? []).map((c) => ({
            id: c.id,
            label: `${c.name} (${c.status})`,
          }))}
          drivers={(drivers?.items ?? []).map((d) => ({
            id: d.id,
            label: `${d.full_name} — ${d.service_city ?? "no city"}`,
            driverProfileId: d.id,
          }))}
          vehicles={(vehicles?.items ?? []).map((v) => ({
            id: v.id,
            label: `${v.plate_number} — ${[v.make, v.model].filter(Boolean).join(" ") || v.vehicle_type}`,
            driverProfileId: v.driver_profile_id,
          }))}
        />
      </Panel>
    </div>
  );
}
