import type { ReactNode } from "react";
import { Panel } from "@/components/ui/panel";
import { OMITTED_TOTAL_LABEL } from "./measurement-authority";

type DailyCompleteness = {
  complete: boolean;
  suppressed: boolean;
  in_progress_trip_count: number;
  insufficient_data_trip_count: number;
  excluded_trip_count: number;
};

export function dailyMetricPublishable(completeness: DailyCompleteness): boolean {
  return (
    completeness.complete &&
    !completeness.suppressed &&
    completeness.in_progress_trip_count === 0 &&
    completeness.insufficient_data_trip_count === 0 &&
    completeness.excluded_trip_count === 0
  );
}

export function FrozenDailyMetricChart({
  title,
  description,
  suppressed,
  children,
}: {
  title: string;
  description: string;
  suppressed: boolean;
  children: ReactNode;
}) {
  return (
    <Panel className="p-6">
      <h2 className="micro text-muted mb-1">{title}</h2>
      <p className="text-faint mb-4 text-xs">{description}</p>
      {suppressed ? (
        <p className="text-muted px-2 py-10 text-center text-sm">{OMITTED_TOTAL_LABEL}</p>
      ) : (
        children
      )}
    </Panel>
  );
}
