import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";

export const metadata = { title: "Driver applications" };

export default async function AdminDriverApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; q?: string; history?: string }>;
}) {
  const params = await searchParams;
  const offset = Math.max(0, Math.floor(Number(params.offset) || 0));
  const history = params.history === "true";
  const { data } = await createApiClient(await getSessionToken()).GET(
    "/api/v1/admin/driver-applications",
    {
      params: { query: { limit: 25, offset, q: params.q, history } },
    },
  );
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Driver applications"
        eyebrow={
          data
            ? `${data.total} ${history ? "recorded" : "pending"} applications`
            : "Work list unavailable"
        }
      />
      <QueueSearch q={params.q}>
        <label className="text-muted text-sm">
          <input type="checkbox" name="history" value="true" defaultChecked={history} /> Include
          history
        </label>
      </QueueSearch>
      {!data ? (
        <QueueUnavailable />
      ) : data.items.length === 0 ? (
        <p>No matching applications. Clear the search or include history.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.items.map((a) => (
            <Link
              key={a.id}
              href={`/admin/driver-applications/${a.id}`}
              className="border-edge bg-raised min-w-0 rounded-xl border p-5"
            >
              <h2 className="font-medium">{a.full_name}</h2>
              <p className="text-muted text-sm break-all">
                {a.email} · {a.service_city ?? "City not supplied"}
              </p>
              <p className="mt-3 text-sm">
                {a.status.replaceAll("_", " ")} · Received {formatDate(a.created_at)}
              </p>
              <p className="text-muted text-sm">
                Person &amp; payee: {a.person_payee?.status.replaceAll("_", " ") ?? "Not submitted"}
              </p>
              <p className="text-muted text-sm">
                Vehicle: {a.vehicle?.plate_number ?? "Not supplied"} ·{" "}
                {a.vehicle?.status.replaceAll("_", " ") ?? "Not submitted"}
              </p>
              <span className="text-cyan mt-3 block text-sm">
                Open current evidence and review →
              </span>
            </Link>
          ))}
        </div>
      )}
      {data ? (
        <Pagination
          total={data.total}
          limit={25}
          offset={offset}
          hrefFor={(o) =>
            `/admin/driver-applications?${new URLSearchParams({ q: params.q ?? "", history: String(history), offset: String(o) })}`
          }
        />
      ) : null}
    </div>
  );
}
