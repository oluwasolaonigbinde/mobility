import { Stat } from "@/components/ui/stat";
import { formatCount, formatScore } from "@/lib/format";
import { OMITTED_TOTAL_LABEL } from "./measurement-authority";

export type ExposureScoreView = {
  formulaVersion: string;
  formulaFingerprint: string;
  inputFingerprint: string;
  status: "scored" | "insufficient_data";
  score: string | null;
  routeCount: number;
  missingRouteCount: number;
  uncertainty: string;
};

function formatExposurePoints(value: string | null): string {
  if (value === null) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toFixed(2)} / 100` : "—";
}

export type CompletenessView = {
  coveredTripCount: number;
  denominatorTripCount: number;
  insufficientDataTripCount: number;
  excludedTripCount: number;
  complete: boolean;
  suppressed: boolean;
};

export function MeasurementHeadlineStats({
  exposureScore,
  modelledPotentialContacts,
  modelDiagnostic,
  completeness,
}: {
  exposureScore: ExposureScoreView | null;
  modelledPotentialContacts: string | null;
  modelDiagnostic: string | null;
  completeness: CompletenessView;
}) {
  return (
    <>
      <div>
        <Stat
          label="Campaign activity score"
          value={formatExposurePoints(exposureScore?.score ?? null)}
          tone="amber"
          hint={
            exposureScore ? (
              <>
                0–100 index of distance, tracking time and GPS evidence quality (
                {formatCount(exposureScore.routeCount)} routes scored,{" "}
                {formatCount(exposureScore.missingRouteCount)} missing). Not yet calibrated or
                approved as a live measurement method; not an impression estimate, audience count,
                statistical confidence interval or attribution result.
              </>
            ) : (
              "No activity score has been issued for this report."
            )
          }
        />
        {exposureScore ? (
          <details className="text-faint mt-2 text-xs">
            <summary className="cursor-pointer">Activity score technical reference</summary>
            <p className="mt-2 break-all">
              Named “Exposure score” in downloads · {exposureScore.formulaVersion} · formula{" "}
              {exposureScore.formulaFingerprint} · input {exposureScore.inputFingerprint}
            </p>
          </details>
        ) : null}
      </div>
      <div>
        <Stat
          label="Estimated ad exposure"
          value={
            completeness.suppressed || modelledPotentialContacts === null
              ? OMITTED_TOTAL_LABEL
              : formatCount(modelledPotentialContacts)
          }
          hint={`Estimated opportunities to see the ad, based on routes and traffic. This is not a count of people or measured views. ${formatCount(completeness.coveredTripCount)} of ${formatCount(completeness.denominatorTripCount)} completed trips included · ${formatCount(completeness.insufficientDataTripCount)} with too little data · ${formatCount(completeness.excludedTripCount)} excluded${
            completeness.suppressed
              ? " · total not shown rather than counted as zero"
              : completeness.complete
                ? ""
                : " · period incomplete"
          }`}
        />
        <details className="text-faint mt-2 text-xs">
          <summary className="cursor-pointer">Exposure estimate technical reference</summary>
          <p className="mt-2">
            Named “Modelled potential contacts” in downloads · estimate quality factor{" "}
            {formatScore(modelDiagnostic)} (not a statistical confidence level)
          </p>
        </details>
      </div>
    </>
  );
}
