import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { Panel } from "@/components/ui/panel";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "./queue-search";
import { departments, readWorkQueue } from "./work-queue";
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
  searchParams: Promise<{ department?: string; offset?: string }>;
}) {
  await requireRole("admin");
  const p = await searchParams;
  const selected = departments.find((department) => department === p.department);
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const queue = await readWorkQueue();
  const cards = [];
  for (const department of selected ? [selected] : departments) {
    const all = queue[department];
    if (!all) {
      cards.push({ department });
      continue;
    }
    const visible = all.slice(selected ? offset : 0, selected ? offset + 25 : 5);
    try {
      const rows = [];
      for (let i = 0; i < visible.length; i += 4)
        rows.push(
          ...(await Promise.all(
            visible.slice(i, i + 4).map(async (task) => ({
              ...(await task.describe()),
              key: task.key,
              at: task.at,
              event: task.event,
            })),
          )),
        );
      cards.push({ department, rows, total: all.length });
    } catch {
      cards.push({ department });
    }
  }
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Work queue</h1>
      <p className="text-muted mt-1 mb-8 text-sm">
        Work for each Terrax Media department. Open an item to deal with it.
      </p>
      {selected ? (
        <Link href="/admin" className="text-cyan mb-4 inline-block underline">
          All departments
        </Link>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <Panel key={card.department} className="p-5">
            <section aria-label={card.department}>
              <h2 className="font-medium">{card.department}</h2>
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
                  {selected ? (
                    <Pagination
                      total={card.total ?? 0}
                      limit={25}
                      offset={offset}
                      hrefFor={(next) =>
                        `/admin?department=${encodeURIComponent(card.department)}&offset=${next}`
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
