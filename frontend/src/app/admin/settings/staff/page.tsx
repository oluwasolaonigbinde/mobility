import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { UserStatusMenu } from "../../users/user-status-menu";
import { QueueSearch, QueueUnavailable } from "../../queue-search";
import { adminStatus } from "@/lib/status/admin";
export default async function StaffPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string }>;
}) {
  const p = await searchParams;
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/users", { params: { query: { role: "admin", q: p.q, limit: 25, offset } } })
    .catch(() => ({ data: undefined }));
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Staff logins"
        eyebrow="Terrax staff"
        actions={
          <Link className="text-cyan underline" href="/admin/settings/staff/new">
            Add staff login
          </Link>
        }
      />
      <QueueSearch q={p.q} label="Search staff" />
      {!data ? (
        <QueueUnavailable />
      ) : (
        <>
          <p className="text-muted mb-4 text-sm">{data.total} matching staff sign-ins</p>
          {!data.items.length ? (
            <p>No matching staff.</p>
          ) : (
            <ul className="grid gap-3">
              {data.items.map((user) => (
                <li
                  className="border-edge flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4"
                  key={user.id}
                >
                  <div>
                    <p className="font-medium">{user.full_name}</p>
                    <p className="text-muted text-sm">
                      {user.email} · {adminStatus(user.status)}
                    </p>
                  </div>
                  <UserStatusMenu
                    userId={user.id}
                    userLabel={user.full_name}
                    status={user.status}
                    role="admin"
                  />
                </li>
              ))}
            </ul>
          )}
          <Pagination
            total={data.total}
            limit={25}
            offset={offset}
            hrefFor={(o) =>
              `/admin/settings/staff?${new URLSearchParams({ q: p.q ?? "", offset: String(o) })}`
            }
          />
        </>
      )}
    </div>
  );
}
