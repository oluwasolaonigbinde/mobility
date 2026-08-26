import type { components } from "@/lib/api/schema";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Insight = components["schemas"]["HighExposureZoneInsightsRead"];

const stateCopy: Record<Exclude<Insight["state"], "ready">, string> = {
  empty: "No issued zone aggregate is available for this measurement run.",
  suppressed: "Zone rankings are withheld by the disclosure floor.",
  stale: "The issued zone authority is stale. A new governed aggregate is required.",
  unavailable: "The measurement run cannot produce a governed zone ranking.",
};

export function HighExposureZoneInsights({
  insight,
  surface,
}: {
  insight: Insight;
  surface: "map" | "report" | "admin";
}) {
  const ariaLabel =
    surface === "map" ? "High-exposure zone map ranking" : "High-exposure zone ranking";

  return (
    <Panel role="region" aria-label={ariaLabel} className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="micro text-amber">Governed zone insight</p>
          <h2 className="mt-1 font-medium">High-exposure zones</h2>
        </div>
        <StatusChip
          tone={
            insight.state === "ready"
              ? "green"
              : insight.state === "suppressed"
                ? "amber"
                : insight.state === "stale"
                  ? "coral"
                  : "default"
          }
        >
          {insight.state}
        </StatusChip>
      </div>

      {insight.state === "ready" ? (
        <>
          <ol className="border-edge mt-4 divide-y border-y">
            {insight.items.map((item) => (
              <li key={item.zone_id} className="flex flex-wrap justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium">
                    #{item.rank} {item.zone_name}
                  </p>
                  <p className="micro text-faint mt-1 font-mono">{item.zone_id}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm">
                    {formatCount(item.modelled_potential_contacts)} modelled potential contacts
                  </p>
                  <p className="micro text-faint mt-1">
                    {formatCount(item.trip_count)} governed trips
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <p className="micro text-muted mt-4">
            Campaign exposure score: {insight.campaign_exposure_score ?? "—"} / 100 · separate
            uncalibrated operational index
          </p>
          {insight.provenance ? (
            <p className="micro text-faint mt-2 font-mono">
              {insight.provenance.formula_version} · formula{" "}
              {insight.provenance.formula_fingerprint.slice(0, 12)}… · run{" "}
              {insight.provenance.measurement_run_id}
            </p>
          ) : null}
          {insight.uncertainty ? (
            <p className="micro text-faint mt-3">{insight.uncertainty}</p>
          ) : null}
        </>
      ) : (
        <p className="text-muted mt-4 text-sm">{stateCopy[insight.state]}</p>
      )}
      <p className="micro text-faint mt-3">{insight.disclaimer}</p>
    </Panel>
  );
}
