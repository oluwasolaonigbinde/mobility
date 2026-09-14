export interface ApplicationStagePresentation {
  label: string;
  detail: string;
  tone: "text-green" | "text-amber" | "text-coral" | "text-muted";
}

const STAGES: Record<string, ApplicationStagePresentation> = {
  not_submitted: {
    label: "Not submitted",
    detail: "Use your expiring onboarding access code to submit this stage.",
    tone: "text-muted",
  },
  pending_review: {
    label: "Under review",
    detail: "Cardvert is reviewing the current submitted revision.",
    tone: "text-amber",
  },
  approved: {
    label: "Approved",
    detail: "This stage is approved. Account setup remains a separate final step.",
    tone: "text-green",
  },
  rejected: {
    label: "Changes needed",
    detail: "Submit a new evidence revision with your onboarding access code.",
    tone: "text-coral",
  },
  expired: {
    label: "Renewal needed",
    detail: "Submit renewed evidence for a new administrator review.",
    tone: "text-coral",
  },
};

export function presentApplicationStage(status: string | undefined): ApplicationStagePresentation {
  return (
    STAGES[status ?? ""] ?? {
      label: "Status unavailable",
      detail: "Cardvert could not interpret this stage. Check again before submitting anything.",
      tone: "text-muted",
    }
  );
}
