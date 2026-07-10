import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { DriverProfileForm } from "./driver-profile-form";

export const metadata: Metadata = { title: "Add driver profile" };

export default async function NewDriverProfilePage() {
  const api = createApiClient(await getSessionToken());
  // Candidate users: driver-role accounts (profile creation fails cleanly
  // via the API error if one already exists).
  const { data } = await api.GET("/api/v1/admin/users", {
    params: { query: { role: "driver", limit: 100 } },
  });

  return (
    <div className="animate-rise mx-auto max-w-2xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/drivers" className="hover:text-muted">
          Drivers
        </Link>{" "}
        / <span className="text-muted">Add profile</span>
      </nav>
      <PageHeader
        title="Add driver profile"
        eyebrow="Attach driving credentials to a driver-role user"
      />
      <Panel className="p-6 md:p-8">
        <DriverProfileForm
          users={(data?.items ?? []).map((u) => ({
            id: u.id,
            label: `${u.full_name} — ${u.email}`,
          }))}
        />
      </Panel>
    </div>
  );
}
