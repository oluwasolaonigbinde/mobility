import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount } from "@/lib/format";
import { Stat } from "@/components/ui/stat";

export const metadata: Metadata = { title: "Operations" };

export default async function AdminOperationsPage() {
  await requireRole("admin");
  const api = createApiClient(await getSessionToken());

  const [users, drivers, vehicles, flags] = await Promise.all([
    api.GET("/api/v1/admin/users", { params: { query: { limit: 1 } } }),
    api.GET("/api/v1/admin/drivers", { params: { query: { limit: 1 } } }),
    api.GET("/api/v1/admin/vehicles", { params: { query: { limit: 1 } } }),
    api.GET("/api/v1/admin/fraud-flags", { params: { query: { limit: 1, status: "open" } } }),
  ]);

  const openFlags = flags.data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">
        Fleet &amp; Trust Operations
      </h1>
      <p className="micro text-muted mt-1 mb-8">Network-wide · live</p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Users" value={formatCount(users.data?.total)} />
        <Stat label="Drivers" value={formatCount(drivers.data?.total)} tone="amber" />
        <Stat label="Vehicles" value={formatCount(vehicles.data?.total)} />
        <Stat
          label="Open fraud flags"
          value={formatCount(openFlags)}
          tone={openFlags > 0 ? "coral" : "green"}
        />
      </div>
    </div>
  );
}
