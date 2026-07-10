import type { ReactNode } from "react";
import { Panel } from "./panel";
import { cx } from "@/lib/cx";

/** KPI tile — mono eyebrow, Clash Display numeral, optional signal accent. */
export function Stat({
  label,
  value,
  hint,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "amber" | "cyan" | "green" | "coral";
  className?: string;
}) {
  const toneClass = {
    default: "text-ink",
    amber: "text-amber",
    cyan: "text-cyan",
    green: "text-green",
    coral: "text-coral",
  }[tone];

  return (
    <Panel className={cx("p-5", className)}>
      <p className="micro text-muted">{label}</p>
      <p className={cx("font-display mt-2 text-3xl font-semibold tracking-tight", toneClass)}>
        {value}
      </p>
      {hint ? <p className="text-muted mt-1.5 text-xs">{hint}</p> : null}
    </Panel>
  );
}
