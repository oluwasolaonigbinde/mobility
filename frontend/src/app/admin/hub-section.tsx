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
      className="border-edge bg-bg/95 sticky top-32 z-20 mb-5 flex gap-2 overflow-x-auto rounded-lg border p-2 md:top-16"
    >
      {sections.map((s) => (
        <Link
          key={s.id}
          href={`#${s.id}`}
          className="hover:bg-raised micro rounded-lg px-3 py-2 whitespace-nowrap"
        >
          {s.title}
        </Link>
      ))}
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
