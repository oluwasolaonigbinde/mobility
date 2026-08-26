import { Stat } from "@/components/ui/stat";
import { formatCount, formatScore } from "@/lib/format";

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

export function MeasurementHeadlineStats({
  exposureScore,
  modelledPotentialContacts,
  estimatedTripCount,
  modelDiagnostic,
}: {
  exposureScore: ExposureScoreView | null;
  modelledPotentialContacts: string | null;
  estimatedTripCount: number;
  modelDiagnostic: string | null;
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
              {exposureScore.uncertainty}
            </>
          ) : (
            "No immutable exposure score has been issued for this measurement run."
          )
        }
      />
      <Stat
        label="Modelled potential contacts"
        value={formatCount(modelledPotentialContacts)}
        hint={`${formatCount(estimatedTripCount)} estimated trips · ${formatScore(modelDiagnostic)} model diagnostic (not a statistical confidence interval)`}
      />
    </>
  );
}
