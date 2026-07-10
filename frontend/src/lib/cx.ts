/** Minimal className combiner — no dependency needed at this scale. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
