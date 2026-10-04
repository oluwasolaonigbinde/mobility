import { Panel } from "@/components/ui/panel";
import type { UnavailableReason } from "@/lib/advertiser/page-data";

const details: Record<UnavailableReason, string> = {
  forbidden: "Your account doesn't have access to this.",
  missing: "This information couldn't be found.",
  operational: "This couldn't be loaded right now.",
  protocol: "This couldn't be loaded right now.",
  insufficient: "Results appear after more trips are recorded.",
};

export function DataUnavailable({
  title,
  reason,
  retryHref,
  className,
}: {
  title: string;
  reason: UnavailableReason;
  retryHref: string;
  className?: string;
}) {
  const retryable = reason === "operational" || reason === "protocol";
  const heading = reason === "insufficient" ? "Results" : title;
  return (
    <Panel className={`p-5 ${className ?? ""}`} role="status" aria-label={heading}>
      <h2 className="text-base font-semibold">{heading}</h2>
      <p className="text-muted mt-1 text-sm">
        {details[reason]}
        {retryable ? (
          <>
            {" "}
            <a href={retryHref} className="text-amber hover:underline">
              Try again
            </a>
          </>
        ) : null}
      </p>
    </Panel>
  );
}
