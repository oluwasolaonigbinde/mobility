import type { components } from "@/lib/api/schema";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Insight = components["schemas"]["HighExposureZoneInsightsRead"];

const stateCopy: Record<Exclude<Insight["state"], "ready">, string> = {
  empty: "No zone ranking is available for this report yet.",
  suppressed: "Zone rankings are not shown because there is too little data to protect privacy.",
  stale: "This zone ranking is out of date. Cardvert needs to issue a new ranking.",
  unavailable: "A zone ranking is unavailable for this report.",
};

export function HighExposureZoneInsights({
  insight,
  surface,
}: {
  insight: Insight;
  surface: "map" | "report" | "admin";
}) {
  const ariaLabel = surface === "map" ? "Zone map ranking" : "Zone ranking";

  return (
    <Panel role="region" aria-label={ariaLabel} className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="micro text-amber">Zone ranking</p>
          <h2 className="mt-1 font-medium">Top zones by estimated ad exposure</h2>
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
                  {surface === "admin" ? (
                    <p className="micro text-faint mt-1 font-mono">{item.zone_id}</p>
                  ) : null}
                </div>
                <div className="text-right">
                  <p className="text-sm">
                    {formatCount(item.modelled_potential_contacts)} estimated ad exposure
                  </p>
                  <p className="micro text-faint mt-1">{formatCount(item.trip_count)} trips</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="micro text-muted mt-4">
            Campaign activity score: {insight.campaign_exposure_score ?? "—"} / 100 · a separate,
            uncalibrated index (named “Exposure score” in downloads)
          </p>
          {insight.provenance ? (
            <details className="micro text-faint mt-2 font-mono break-all">
              <summary className="cursor-pointer font-sans">
                Zone ranking technical reference
              </summary>
              <p className="mt-2">
                {insight.provenance.formula_version} · formula{" "}
                {insight.provenance.formula_fingerprint.slice(0, 12)}… · run{" "}
                {insight.provenance.measurement_run_id}
              </p>
              {surface === "admin" ? (
                <>
                  <p className="mt-1">
                    score {insight.provenance.exposure_score_id} · exposure{" "}
                    {insight.provenance.exposure_formula_version} · formula{" "}
                    {insight.provenance.exposure_formula_fingerprint.slice(0, 12)}… · input{" "}
                    {insight.provenance.exposure_input_fingerprint.slice(0, 12)}…
                  </p>
                  {insight.provenance.source_segments.map((segment) => (
                    <p key={segment.segment_id} className="mt-1">
                      segment {segment.segment_id} · version {segment.segment_version} · snapshot{" "}
                      {segment.segment_snapshot_sha256.slice(0, 12)}… · reissue of{" "}
                      {segment.reissue_of_segment_id ?? "original"}
                    </p>
                  ))}
                </>
              ) : null}
            </details>
          ) : null}
          {insight.uncertainty ? (
            <p className="micro text-faint mt-3">{insight.uncertainty}</p>
          ) : null}
        </>
      ) : (
        <p className="text-muted mt-4 text-sm">{stateCopy[insight.state]}</p>
      )}
      <p className="micro text-faint mt-3">
        Ranks privacy-cleared zones by estimated opportunities to see (named “modelled potential
        contacts” in downloads). The activity score, impressions and attribution are separate
        measures. Rankings are not individual people, measured views or guaranteed outcomes.
      </p>
    </Panel>
  );
}
