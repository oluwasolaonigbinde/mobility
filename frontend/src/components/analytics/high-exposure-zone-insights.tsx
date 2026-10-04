import type { components } from "@/lib/api/schema";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Insight = components["schemas"]["HighExposureZoneInsightsRead"];

const stateCopy: Record<Exclude<Insight["state"], "ready">, string> = {
  empty: "No zone ranking is available for this report yet.",
  suppressed: "Zone rankings are not shown because there is too little data to protect privacy.",
  stale: "This zone ranking is out of date. Terrax Media needs to issue a new ranking.",
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
          {
            {
              ready: "Ready",
              empty: "No results yet",
              suppressed: "Not enough data",
              stale: "Needs updating",
              unavailable: "Unavailable",
            }[insight.state]
          }
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
                  <p className="micro text-faint mt-1">
                    {formatCount(item.trip_count)} area visits
                  </p>
                </div>
              </li>
            ))}
          </ol>
          {surface !== "report" ? (
            <p className="micro text-muted mt-4">
              Campaign activity score: {insight.campaign_exposure_score ?? "—"} / 100
            </p>
          ) : null}
          {/* D38(c): run and fingerprint references appear on staff screens only. */}
          {insight.provenance && surface === "admin" ? (
            <details className="micro text-faint mt-2 font-mono break-all">
              <summary className="cursor-pointer font-sans">
                Zone ranking technical reference
              </summary>
              <p className="mt-2">
                {insight.provenance.formula_version} · formula{" "}
                {insight.provenance.formula_fingerprint.slice(0, 12)}… · run{" "}
                {insight.provenance.measurement_run_id}
              </p>
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
            </details>
          ) : null}
          {insight.uncertainty && surface === "admin" ? (
            <p className="micro text-faint mt-3">{insight.uncertainty}</p>
          ) : null}
        </>
      ) : (
        <p className="text-muted mt-4 text-sm">{stateCopy[insight.state]}</p>
      )}
      {surface !== "report" ? (
        <details className="text-muted mt-3 text-sm">
          <summary className="cursor-pointer">How this is calculated</summary>
          <p className="mt-2">
            Areas are ranked by estimated opportunities to see the ad, based on campaign routes and
            traffic. These are not counts of people, measured views or guaranteed results.
          </p>
          <p className="mt-2">
            The activity score combines distance, tracking time and route quality. It is a separate
            measure from estimated ad exposure.
          </p>
          <p className="mt-2">
            A trip is counted in each mapped area section and time window it visits. It can
            contribute more than once to an area’s count.
          </p>
        </details>
      ) : null}
    </Panel>
  );
}
