import type { ReactNode } from "react";
import { Panel } from "./panel";

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <Panel className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <p className="font-display text-lg font-semibold">{title}</p>
      {body ? <p className="text-muted max-w-sm text-sm">{body}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </Panel>
  );
}
