import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { UserStatusMenu } from "./user-status-menu";
import { cx } from "@/lib/cx";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Users" };

const PAGE_SIZE = 25;
type Role = components["schemas"]["UserRole"];
type UserStatus = components["schemas"]["UserStatus"];

const ROLES: Role[] = ["admin", "advertiser", "driver"];
const statusTone: Record<UserStatus, "green" | "cyan" | "amber" | "coral"> = {
  active: "green",
  invited: "cyan",
  suspended: "amber",
  disabled: "coral",
};

function href(params: { role?: string; offset?: number }): string {
  const qs = new URLSearchParams();
  if (params.role) qs.set("role", params.role);
  if (params.offset) qs.set("offset", String(params.offset));
  const s = qs.toString();
  return s ? `/admin/users?${s}` : "/admin/users";
}

export default async function AdminUsersPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const role = ROLES.includes(params.role as Role) ? (params.role as Role) : undefined;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/users", {
    params: { query: { limit: PAGE_SIZE, offset, ...(role ? { role } : {}) } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Users"
        eyebrow={`${total} account${total === 1 ? "" : "s"} across the network`}
        actions={
          <Link
            href="/admin/users/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + Create user
          </Link>
        }
      />

      <div className="mb-4 flex gap-1" role="group" aria-label="Filter by role">
        <Link
          href={href({})}
          className={cx(
            "micro rounded-lg px-3 py-2 transition-colors",
            !role ? "bg-raised text-amber" : "text-muted hover:text-ink",
          )}
        >
          All
        </Link>
        {ROLES.map((r) => (
          <Link
            key={r}
            href={href({ role: r })}
            className={cx(
              "micro rounded-lg px-3 py-2 capitalize transition-colors",
              role === r ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {r}
          </Link>
        ))}
      </div>

      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-5 py-3.5 font-normal">User</th>
                <th className="px-5 py-3.5 font-normal">Role</th>
                <th className="px-5 py-3.5 font-normal">Status</th>
                <th className="px-5 py-3.5 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id} className="border-edge/60 border-b last:border-0">
                  <td className="px-5 py-3.5">
                    <p className="font-medium">{u.full_name}</p>
                    <p className="micro text-faint mt-0.5">{u.email}</p>
                  </td>
                  <td className="px-5 py-3.5 capitalize">{u.role}</td>
                  <td className="px-5 py-3.5">
                    <StatusChip tone={statusTone[u.status]}>{u.status}</StatusChip>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <UserStatusMenu userId={u.id} status={u.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => href({ role, offset: o })}
      />
    </div>
  );
}
