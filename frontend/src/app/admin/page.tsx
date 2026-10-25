import { adminValueFailure } from "@/lib/api/admin-read";
import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { Panel } from "@/components/ui/panel";
import { Pagination } from "@/components/ui/pagination";
import { FilterChips, ViewTabs } from "@/components/ui/tabs";
import { QueueUnavailable } from "./queue-search";
import { departments, readWorkQueue, readQueueSource, sources } from "./work-queue";
export const metadata: Metadata = { title: "Work queue" };
function age(at: string) {
  const hours = Math.max(0, Math.floor((Date.now() - Date.parse(at)) / 3600000));
  return hours < 1
    ? "just now"
    : hours < 24
      ? `${hours} h ago`
      : `${Math.floor(hours / 24)} days ago`;
}
export default async function AdminWorkQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ department?: string; source?: string; offset?: string }>;
}) {
  await requireRole("admin");
  const p = await searchParams;
  const selected = departments.find((d) => d === p.department);
  const source = selected
    ? (sources.find((s) => s.department === selected && s.id === p.source) ??
      sources.find((s) => s.department === selected))
    : undefined;
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const [queue, expanded] = await Promise.all([
    readWorkQueue(),
    source ? readQueueSource(source.id, 25, offset) : undefined,
  ]);
  const cards = await Promise.all(
    (selected ? [selected] : departments).map(async (department) => {
      const list = selected
        ? expanded
        : queue[department]
          ? { items: queue[department], total: queue[department].total ?? 0 }
          : undefined;
      if (!list) return { department, rows: undefined, total: undefined };
      try {
        return {
          department,
          total: list.total,
          rows: await Promise.all(
            list.items.map(async (task) => ({
              ...(await task.describe()),
              key: task.key,
              at: task.at,
              event: task.event,
            })),
          ),
        };
      } catch (error) {
        adminValueFailure(error);
        return { department, rows: undefined, total: undefined };
      }
    }),
  );
  const departmentHref = (department: string) =>
    `/admin?department=${encodeURIComponent(department)}`;
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Work queue</h1>
      <p className="text-muted mt-1 mb-6 text-sm">
        Work for each Terrax Media department. Open an item to deal with it.
      </p>
      <ViewTabs
        label="Departments"
        items={[
          { href: "/admin", label: "All departments", active: !selected },
          ...departments.map((department) => ({
            href: departmentHref(department),
            label: department,
            active: selected === department,
          })),
        ]}
      />
      {selected ? (
        <FilterChips
          label="Work lists"
          items={sources
            .filter((s) => s.department === selected)
            .map((s) => ({
              href: `${departmentHref(selected)}&source=${s.id}`,
              label: s.title,
              active: source?.id === s.id,
            }))}
        />
      ) : null}
      <div className="grid gap-5">
        {cards.map((card) => (
          <Panel key={card.department} className="w-full p-5 md:p-6">
            <section aria-label={card.department}>
              <h2 className="font-display text-xl font-semibold">
                {card.department}
                {selected && source ? ` · ${source.title}` : ""}
              </h2>
              {!card.rows ? (
                <div className="mt-3">
                  <QueueUnavailable />
                </div>
              ) : (
                <>
                  {!card.total ? (
                    <p className="text-muted mt-3 text-sm">Nothing waiting</p>
                  ) : (
                    <ul className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {card.rows.map((row) => (
                        <li key={row.key} className="min-w-0">
                          <Link
                            href={row.href}
                            className="border-edge hover:border-edge-strong hover:bg-raised block h-full rounded-lg border p-3 text-sm transition-colors"
                          >
                            <p className="font-medium">
                              {row.name} — {row.reason}
                            </p>
                            <p className="text-muted mt-1 text-xs">
                              {row.event} {age(row.at)}
                            </p>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                  {selected && source ? (
                    <Pagination
                      total={card.total ?? 0}
                      limit={25}
                      offset={offset}
                      hrefFor={(n) =>
                        `${departmentHref(card.department)}&source=${source.id}&offset=${n}`
                      }
                    />
                  ) : (
                    <Link
                      href={departmentHref(card.department)}
                      className="text-cyan mt-4 inline-block text-sm underline"
                    >
                      See all ({card.total})
                    </Link>
                  )}
                </>
              )}
            </section>
          </Panel>
        ))}
      </div>
    </div>
  );
}
