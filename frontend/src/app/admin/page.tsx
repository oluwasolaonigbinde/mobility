import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { Panel } from "@/components/ui/panel";
import { Pagination } from "@/components/ui/pagination";
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
      } catch {
        return { department, rows: undefined, total: undefined };
      }
    }),
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Work queue</h1>
      <p className="text-muted mt-1 mb-8 text-sm">
        Work for each Terrax Media department. Open an item to deal with it.
      </p>
      {selected ? (
        <>
          <Link href="/admin" className="text-cyan mb-4 inline-block underline">
            All departments
          </Link>
          <nav aria-label="Work lists" className="mb-4 flex flex-wrap gap-3">
            {sources
              .filter((s) => s.department === selected)
              .map((s) => (
                <Link
                  key={s.id}
                  href={`/admin?department=${encodeURIComponent(selected)}&source=${s.id}`}
                  aria-current={source?.id === s.id ? "page" : undefined}
                  className="text-cyan text-sm underline"
                >
                  {s.title}
                </Link>
              ))}
          </nav>
        </>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <Panel key={card.department} className="p-5">
            <section aria-label={card.department}>
              <h2 className="font-medium">
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
                    <ul className="divide-edge/60 mt-3 divide-y">
                      {card.rows.map((row) => (
                        <li key={row.key}>
                          <Link href={row.href} className="hover:text-amber block py-3 text-sm">
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
                        `/admin?department=${encodeURIComponent(card.department)}&source=${source.id}&offset=${n}`
                      }
                    />
                  ) : (
                    <Link
                      href={`/admin?department=${encodeURIComponent(card.department)}`}
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
