import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { adminStatus } from "@/lib/status/admin";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";

const tabs = [
  { id: "applicants", title: "Applicants", status: "pending" },
  { id: "active", title: "Active", status: "active" },
  { id: "suspended", title: "Suspended", status: "suspended" },
  { id: "not-approved", title: "Not approved", status: "rejected" },
] as const;
export default async function DriversPage({
  searchParams,
}: {
  searchParams: Promise<{
    tab?: string;
    q?: string;
    offset?: string;
    source?: string;
    history?: string;
    [key: string]: string | undefined;
  }>;
}) {
  const p = await searchParams;
  if (
    (!p.tab || p.tab === "applicants") &&
    !["applications", "profiles", "cars"].includes(p.source ?? "")
  ) {
    const lists = await Promise.all(
      ["applications", "profiles"].map(async (source) => ({
        source,
        body: await DriversList(
          { searchParams: Promise.resolve({ ...p, source, offset: p[source + "_offset"] }) },
          true,
        ),
      })),
    );
    return (
      <div className="mx-auto max-w-6xl">
        <PageHeader
          title="Drivers"
          actions={
            <Link href="/admin/drivers/new" className="text-cyan underline">
              Add driver
            </Link>
          }
        />
        <nav aria-label="Driver status" className="mb-5 flex gap-2 overflow-x-auto">
          {tabs.map((t) => (
            <Link
              key={t.id}
              href={"/admin/drivers?tab=" + t.id}
              aria-current={t.id === "applicants" ? "page" : undefined}
              className="rounded-lg px-4 py-2 text-sm whitespace-nowrap"
            >
              {t.title}
            </Link>
          ))}
        </nav>
        <div className="space-y-8">
          {lists.map(({ source, body }) => (
            <section
              key={source}
              aria-label={
                source === "applications" ? "New applications" : "Pending driver profiles"
              }
            >
              <h2 className="mb-3 text-lg font-medium">
                {source === "applications" ? "New applications" : "Pending driver profiles"}
              </h2>
              {body}
            </section>
          ))}
        </div>
      </div>
    );
  }
  return DriversList({ searchParams });
}
async function DriversList(
  { searchParams }: { searchParams: Promise<Record<string, string | undefined>> },
  embedded = false,
) {
  const p = await searchParams;
  const tab = tabs.find((t) => t.id === p.tab) ?? tabs[0];
  const source =
    tab.id === "applicants" && p.source !== "profiles"
      ? "applications"
      : p.source === "cars"
        ? "cars"
        : "profiles";
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  const query = { q: p.q, limit: 25, offset };
  const [profiles, applications, cars] = await Promise.all([
    source === "profiles"
      ? api
          .GET("/api/v1/admin/drivers", {
            params: { query: { ...query, onboarding_status: tab.status } },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    source === "applications"
      ? api
          .GET("/api/v1/admin/driver-applications", {
            params: { query: { ...query, history: p.history === "true" } },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    source === "cars"
      ? api.GET("/api/v1/admin/vehicles", { params: { query } }).catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
  ]);
  const rows =
    source === "applications"
      ? applications.data?.items.map((a) => ({
          id: a.id,
          name: a.full_name,
          phone: a.phone,
          city: a.service_city,
          plates: a.vehicle?.plate_number,
          status: adminStatus(a.status, "driver"),
          next:
            a.person_payee?.status !== "approved"
              ? "Review documents and bank details"
              : "Review car",
          href: a.driver_profile_id
            ? "/admin/drivers/" + a.driver_profile_id + "?application=" + a.id
            : "/admin/drivers/applicant/" + a.id,
        }))
      : source === "cars"
        ? cars.data?.items.map((v) => ({
            id: v.id,
            name: v.driver_profile.full_name,
            phone: v.driver_profile.phone,
            city: null,
            plates: v.plate_number,
            status: adminStatus(v.status),
            next: "Check car",
            href: "/admin/drivers/" + v.driver_profile_id + "#cars",
          }))
        : profiles.data?.items.map((d) => ({
            id: d.id,
            name: d.full_name,
            phone: d.phone,
            city: d.service_city,
            plates: undefined,
            status: adminStatus(d.onboarding_status, "driver"),
            next:
              d.onboarding_status === "pending"
                ? "Check bank details and car"
                : "View current work",
            href: "/admin/drivers/" + d.id,
          }));
  const total = applications.data?.total ?? cars.data?.total ?? profiles.data?.total;
  const driverCars =
    source === "profiles" && profiles.data
      ? await Promise.all(
          profiles.data.items.map((d) =>
            api
              .GET("/api/v1/admin/vehicles", {
                params: { query: { driver_profile_id: d.id, limit: 100 } },
              })
              .catch(() => ({ data: undefined })),
          ),
        )
      : [];
  return (
    <div className="mx-auto max-w-6xl">
      {!embedded ? (
        <>
          <PageHeader
            title="Drivers"
            actions={
              <Link
                href="/admin/drivers/new"
                className="bg-amber text-bg rounded-lg px-4 py-3 text-sm"
              >
                Add driver
              </Link>
            }
          />
          <nav aria-label="Driver status" className="mb-5 flex gap-2 overflow-x-auto">
            {tabs.map((t) => (
              <Link
                key={t.id}
                href={"/admin/drivers?tab=" + t.id}
                aria-current={t.id === tab.id ? "page" : undefined}
                className={
                  "rounded-lg px-4 py-2 text-sm whitespace-nowrap " +
                  (t.id === tab.id ? "bg-raised text-amber" : "text-muted")
                }
              >
                {t.title}
              </Link>
            ))}
          </nav>
        </>
      ) : null}
      <QueueSearch
        q={p.q}
        label={source === "cars" ? "Search driver names or car plates" : "Search drivers"}
      >
        <input type="hidden" name="tab" value={tab.id} />
        <input type="hidden" name="source" value={source} />
        {p.history === "true" ? <input type="hidden" name="history" value="true" /> : null}
      </QueueSearch>
      {!embedded && tab.id === "applicants" ? (
        <nav aria-label="Applicant source" className="mb-4 flex gap-4 text-sm">
          <Link
            className="text-cyan underline"
            href="/admin/drivers?tab=applicants&source=applications"
          >
            New applications
          </Link>
          <Link
            className="text-cyan underline"
            href="/admin/drivers?tab=applicants&source=profiles"
          >
            Other pending profiles
          </Link>
        </nav>
      ) : null}
      {source === "cars" ? (
        <p className="text-muted mb-4 text-sm">Cars directory · all recorded car states</p>
      ) : null}
      {!rows || (source === "profiles" && driverCars.some((read) => !read.data)) ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-3 text-sm">
            {total} matching{" "}
            {source === "cars"
              ? "cars"
              : source === "applications"
                ? "applications"
                : "driver profiles"}
          </p>
          {!rows.length ? (
            <p>No matching drivers. Try a different search.</p>
          ) : (
            <div className="grid gap-3">
              {rows.map((row, index) => (
                <Link
                  key={row.id}
                  href={row.href}
                  className="border-edge hover:bg-raised grid gap-2 rounded-xl border p-4 text-sm md:grid-cols-[2fr_1fr_1fr_1.5fr]"
                >
                  <div>
                    <h2 className="font-medium">{row.name}</h2>
                    <p className="text-muted">{row.phone ?? "No phone recorded"}</p>
                  </div>
                  <p>{row.city ?? ""}</p>
                  <p>
                    {row.plates ??
                      (source === "profiles"
                        ? driverCars[index]?.data?.items.map((v) => v.plate_number).join(", ") ||
                          "No cars recorded"
                        : "No car recorded")}
                  </p>
                  <div>
                    <p>{row.status}</p>
                    <p className="text-muted">Next: {row.next}</p>
                  </div>
                </Link>
              ))}
            </div>
          )}
          <Pagination
            total={total ?? 0}
            limit={25}
            offset={offset}
            hrefFor={(n) =>
              "/admin/drivers?" +
              new URLSearchParams(
                embedded
                  ? {
                      ...(Object.fromEntries(
                        Object.entries(p).filter(
                          ([key, value]) =>
                            key !== "source" && key !== "offset" && value !== undefined,
                        ),
                      ) as Record<string, string>),
                      tab: tab.id,
                      [source + "_offset"]: String(n),
                    }
                  : {
                      tab: tab.id,
                      source,
                      q: p.q ?? "",
                      history: p.history ?? "false",
                      offset: String(n),
                    },
              )
            }
          />
        </>
      )}
    </div>
  );
}
