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
      <Stat
        label="Exposure score"
        value={formatExposurePoints(exposureScore?.score ?? null)}
        tone="amber"
        hint={
          exposureScore ? (
            <>
              {exposureScore.formulaVersion} · {formatCount(exposureScore.routeCount)} scored routes
              · {formatCount(exposureScore.missingRouteCount)} missing · formula{" "}
              {exposureScore.formulaFingerprint.slice(0, 12)}… · input{" "}
              {exposureScore.inputFingerprint.slice(0, 12)}…<br />
              Synthetic uncalibrated operational index; not an impression estimate, audience count,
              statistical confidence interval or attribution result.
            </>
          ) : (
            "No immutable exposure score has been issued for this measurement run."
          )
        }
      />
      <Stat
        label="Modelled potential contacts"
        value={
          completeness.suppressed || modelledPotentialContacts === null
            ? OMITTED_TOTAL_LABEL
            : formatCount(modelledPotentialContacts)
        }
        hint={`${formatCount(completeness.coveredTripCount)} of ${formatCount(completeness.denominatorTripCount)} completed trips covered · ${formatCount(completeness.insufficientDataTripCount)} insufficient-data · ${formatCount(completeness.excludedTripCount)} excluded${
          completeness.suppressed
            ? " · total omitted rather than zero-filled"
            : completeness.complete
              ? ""
              : " · period incomplete"
        } · ${formatScore(modelDiagnostic)} model diagnostic (not a statistical confidence interval)`}
      />
    </>
  );
}
