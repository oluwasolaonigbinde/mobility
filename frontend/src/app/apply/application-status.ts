export interface ApplicationStagePresentation {
  label: string;
  detail: string;
  tone: "text-green" | "text-amber" | "text-coral" | "text-muted";
}

const SEND_WITH_CODE = "Send this step with the code from your email, or get a new code below.";

const STAGES: Record<string, ApplicationStagePresentation> = {
  not_submitted: {
    label: "Not sent yet",
    detail: SEND_WITH_CODE,
    tone: "text-muted",
  },
  pending_review: {
    label: "Being checked",
    detail: "We're checking what you sent.",
    tone: "text-amber",
  },
  approved: {
    label: "Approved",
    detail: "This step is approved. Setting up your account is a separate last step.",
    tone: "text-green",
  },
  rejected: {
    label: "Changes needed",
    detail: `Please send this step again. ${SEND_WITH_CODE}`,
    tone: "text-coral",
  },
  expired: {
    label: "Send again",
    detail: `This needs renewing. ${SEND_WITH_CODE}`,
    tone: "text-coral",
  },
};

export function presentApplicationStage(status: string | undefined): ApplicationStagePresentation {
  return (
    STAGES[status ?? ""] ?? {
      label: "Status unavailable",
      detail: "We couldn't read this status. Please check again later.",
      tone: "text-muted",
    }
  );
}
