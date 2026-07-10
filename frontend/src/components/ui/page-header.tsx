import type { ReactNode } from "react";

export function PageHeader({
  title,
  eyebrow,
  actions,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">{title}</h1>
        {eyebrow ? <p className="micro text-muted mt-1">{eyebrow}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
    </div>
  );
}
