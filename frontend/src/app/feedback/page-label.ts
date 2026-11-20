export type FeedbackPortal = "public" | "advertiser" | "driver" | "staff";

const PORTAL_LABELS: Record<FeedbackPortal, string> = {
  public: "Public",
  advertiser: "Advertiser",
  driver: "Driver",
  staff: "Staff",
};

export function portalLabel(portal: string): string {
  return PORTAL_LABELS[portal as FeedbackPortal] ?? "Public";
}

/** A same-site relative path, or null — never an off-site "Open page" link. */
export function safePagePath(path: string): string | null {
  if (
    !path.startsWith("/") ||
    path.startsWith("//") ||
    path.startsWith("/\\") ||
    /[\u0000-\u001f\u007f?#]/.test(path)
  )
    return null;
  return path;
}

/** Card title: the note's first sentence, kept short. */
export function feedbackTitle(message: string): string {
  const text = message.trim().replace(/\s+/g, " ");
  const sentence = text.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? text;
  return sentence.length > 120 ? `${sentence.slice(0, 117).trimEnd()}…` : sentence;
}
