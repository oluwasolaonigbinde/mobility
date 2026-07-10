import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { VehicleForm } from "./vehicle-form";

export const metadata: Metadata = { title: "Register vehicle" };

export default async function NewVehiclePage() {
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/users", {
    params: { query: { role: "driver", limit: 100 } },
  });

  return (
    <div className="animate-rise mx-auto max-w-2xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/vehicles" className="hover:text-muted">
          Vehicles
        </Link>{" "}
        / <span className="text-muted">Register</span>
      </nav>
      <PageHeader title="Register vehicle" eyebrow="Attach a vehicle to its driver" />
      <Panel className="p-6 md:p-8">
        <VehicleForm
          users={(data?.items ?? []).map((u) => ({
            id: u.id,
            label: `${u.full_name} — ${u.email}`,
          }))}
        />
      </Panel>
    </div>
  );
}
