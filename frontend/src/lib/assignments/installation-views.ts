// Plain names for the installation photo views in the client's policy
// (front, back, both sides, close-up); other configured codes read as words.
const VIEW_LABELS: Record<string, string> = {
  front: "Front",
  back: "Back",
  left: "Left side",
  right: "Right side",
  close_up: "Close-up of the branding",
};

export function installationViewLabel(view: string): string {
  const known = VIEW_LABELS[view];
  if (known) return known;
  const label = view.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}
