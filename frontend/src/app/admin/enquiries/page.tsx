import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { readStaffEnquiries } from "@/lib/api/audit-batch2";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { ViewTabs } from "@/components/ui/tabs";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import { ApiError } from "@/lib/api/errors";
import { redirect } from "next/navigation";

export const metadata = { title: "New enquiries" };
export default async function EnquiriesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; q?: string; offset?: string }>;
}) {
  await requireRole("admin");
  const query = await searchParams;
  const status = query.status === "converted" ? "converted" : "new";
  const q = query.q?.trim().slice(0, 128);
  const offset = Number.isFinite(Number(query.offset))
    ? Math.max(0, Math.floor(Number(query.offset)))
    : 0;
  const href = (next: { status?: string; offset?: number }) =>
    `/admin/enquiries?${new URLSearchParams({ status: next.status ?? status, q: q ?? "", offset: String(next.offset ?? 0) })}`;
  const api = createApiClient(await getSessionToken());
  const result = await readStaffEnquiries(api, { status, q, limit: 25, offset }).catch((error) => {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    return undefined;
  });
  const data = result?.data;
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="New enquiries" eyebrow="People who asked Terrax Media about advertising" />
      <ViewTabs
        label="Enquiry status"
        items={[
          { href: href({ status: "new" }), label: "New", active: status === "new" },
          {
            href: href({ status: "converted" }),
            label: "Advertiser created",
            active: status === "converted",
          },
        ]}
      />
      <QueueSearch q={q} label="Search enquiries">
        <input type="hidden" name="status" value={status} />
      </QueueSearch>
      {!data ? (
        <>
          <QueueUnavailable />
          <Link href={href({ offset })} className="text-green underline">
            Try again
          </Link>
        </>
      ) : (
        <>
          {!data.items.length ? (
            <p className="text-muted py-8">
              {status === "new"
                ? "No new enquiries. Website quote requests will appear here."
                : "No enquiries have been turned into advertisers yet."}
            </p>
          ) : (
            <ul className="grid gap-3">
              {data.items.map((enquiry) => (
                <li key={enquiry.id}>
                  <Link
                    href={`/admin/enquiries/${enquiry.id}`}
                    className="border-edge hover:bg-raised block rounded-xl border p-5"
                  >
                    <h2 className="font-medium">{enquiry.company}</h2>
                    <p className="text-muted mt-1 text-sm">
                      {enquiry.contact_name} · {enquiry.email}
                    </p>
                    <p className="text-muted mt-2 text-xs">
                      {formatDateTime(enquiry.created_at)} · Nigeria time (WAT)
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Pagination
            total={data.total}
            limit={25}
            offset={offset}
            hrefFor={(offset) => href({ offset })}
          />
        </>
      )}
    </div>
  );
}
