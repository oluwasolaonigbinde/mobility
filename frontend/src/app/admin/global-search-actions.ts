"use server";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";

export type SearchHit = { name: string; detail?: string; href: string };
export type SearchGroup = { name: string; items: SearchHit[]; unavailable?: boolean };
export async function searchAdmin(q: string): Promise<SearchGroup[]> {
  await requireRole("admin");
  q = q.trim();
  if (q.length < 2 || q.length > 120) return [];
  const api = createApiClient(await getSessionToken());
  const query = { q, limit: 5, offset: 0 };
  const reads = await Promise.allSettled([
    api.GET("/api/v1/admin/drivers", { params: { query } }),
    api.GET("/api/v1/admin/vehicles", { params: { query } }),
    api.GET("/api/v1/admin/campaigns", { params: { query } }),
    api.GET("/api/v1/admin/advertiser-organizations", { params: { query } }),
    api.GET("/api/v1/admin/users", { params: { query: { ...query, role: "admin" } } }),
    api.GET("/api/v1/admin/driver-applications", { params: { query } }),
  ]);
  const [drivers, cars, campaigns, companies, staff, applicants] = reads;
  const unavailable = (read: PromiseSettledResult<{ data?: unknown }>) =>
    read.status === "rejected" || !read.value.data;
  const driverHits: SearchHit[] =
    drivers.status === "fulfilled"
      ? (drivers.value.data?.items ?? []).map((d) => ({
          name: d.full_name,
          detail: d.phone ?? d.email,
          href: `/admin/drivers/${d.id}`,
        }))
      : [];
  if (applicants.status === "fulfilled") {
    for (const a of applicants.value.data?.items ?? []) {
      const href = a.driver_profile_id
        ? `/admin/drivers/${a.driver_profile_id}`
        : `/admin/drivers/applicant/${a.id}`;
      if (!driverHits.some((d) => d.href === href))
        driverHits.push({ name: a.full_name, detail: a.phone ?? a.email, href });
    }
  }
  return [
    {
      name: "Drivers",
      items: driverHits.slice(0, 5),
      unavailable: unavailable(drivers) || unavailable(applicants),
    },
    {
      name: "Cars",
      items:
        cars.status === "fulfilled"
          ? (cars.value.data?.items ?? []).map((v) => ({
              name: v.plate_number,
              detail: [v.make, v.model].filter(Boolean).join(" "),
              href: `/admin/drivers/${v.driver_profile_id}#cars`,
            }))
          : [],
      unavailable: unavailable(cars),
    },
    {
      name: "Campaigns",
      items:
        campaigns.status === "fulfilled"
          ? (campaigns.value.data?.items ?? []).map((c) => ({
              name: c.name,
              detail: c.organization.name,
              href: `/admin/campaigns/${c.id}`,
            }))
          : [],
      unavailable: unavailable(campaigns),
    },
    {
      name: "Companies",
      items:
        companies.status === "fulfilled"
          ? (companies.value.data?.items ?? []).map((c) => ({
              name: c.name,
              detail: c.billing_email ?? undefined,
              href: `/admin/advertisers/${c.id}`,
            }))
          : [],
      unavailable: unavailable(companies),
    },
    {
      name: "Staff",
      items:
        staff.status === "fulfilled"
          ? (staff.value.data?.items ?? []).map((s) => ({
              name: s.full_name,
              detail: s.email,
              href: `/admin/settings/staff?q=${encodeURIComponent(s.email)}`,
            }))
          : [],
      unavailable: unavailable(staff),
    },
  ];
}
