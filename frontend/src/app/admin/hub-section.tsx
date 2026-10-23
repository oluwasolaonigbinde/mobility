import Link from "next/link";
import type { ReactNode } from "react";

export function HubSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="border-edge bg-panel scroll-mt-36 rounded-xl border p-4 md:p-6">
      <h2 tabIndex={-1} className="font-display mb-4 text-xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}
export function HubNav({ sections }: { sections: { id: string; title: string }[] }) {
  return (
    <nav
      aria-label="Page sections"
      className="border-edge bg-panel sticky top-32 z-20 mb-5 overflow-x-auto overflow-y-hidden rounded-lg border p-1.5 md:top-14"
    >
      <div className="flex min-w-max gap-1 lg:min-w-0">
        {sections.map((s) => (
          <Link
            key={s.id}
            href={`#${s.id}`}
            data-tab
            className="text-muted hover:bg-raised hover:text-ink flex-1 rounded-md px-4 py-2.5 text-center text-[0.9375rem] font-medium whitespace-nowrap transition-colors"
          >
            {s.title}
          </Link>
        ))}
      </div>
    </nav>
  );
}
export function HubChecklist({
  title,
  items,
}: {
  title: string;
  items: { label: string; state: string; section: string; done?: boolean }[];
}) {
  return (
    <div className="mb-6">
      <h2 className="font-display mb-3 text-xl font-semibold">{title}</h2>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <li key={item.label}>
            <Link
              href={`#${item.section}`}
              className="border-edge hover:bg-raised flex h-full items-start gap-2 rounded-lg border p-3 text-sm"
            >
              <span aria-hidden className={item.done ? "text-green" : "text-amber"}>
                {item.done ? "✓" : "○"}
              </span>
              <span>
                <span className="block font-medium">{item.label}</span>
                <span className="text-muted text-xs">{item.state}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
