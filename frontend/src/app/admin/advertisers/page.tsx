import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import { adminStatus } from "@/lib/status/admin";

export default async function AdvertisersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string }>;
}) {
  const p = await searchParams;
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/advertiser-organizations", {
      params: { query: { q: p.q, limit: 25, offset } },
    })
    .catch(() => ({ data: undefined }));
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Advertisers" />
      <QueueSearch q={p.q} label="Search companies" />
      {!data ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-4 text-sm">{data.total} matching companies</p>
          {!data.items.length ? (
            <p>No matching companies.</p>
          ) : (
            <div className="grid gap-3">
              {data.items.map((c) => (
                <Link
                  key={c.id}
                  href={`/admin/advertisers/${c.id}`}
                  className="border-edge hover:bg-raised rounded-xl border p-4"
                >
                  <h2 className="font-medium">{c.name}</h2>
                  <p className="text-muted text-sm">
                    {c.billing_email ?? "No billing contact recorded"} · {adminStatus(c.status)}
                  </p>
                </Link>
              ))}
            </div>
          )}
          <Pagination
            total={data.total}
            limit={25}
            offset={offset}
            hrefFor={(o) =>
              `/admin/advertisers?${new URLSearchParams({ q: p.q ?? "", offset: String(o) })}`
            }
          />
        </>
      )}
    </div>
  );
}
