import { cx } from "@/lib/cx";

type Tone = "default" | "amber" | "cyan" | "green" | "coral";

const tones: Record<Tone, string> = {
  default: "border-edge-strong/60 bg-raised text-muted",
  amber: "border-amber/40 bg-amber/10 text-amber",
  cyan: "border-cyan/40 bg-cyan/10 text-cyan",
  green: "border-green/40 bg-green/10 text-green",
  coral: "border-coral/40 bg-coral/10 text-coral",
};

export function StatusChip({
  tone = "default",
  children,
  className,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "micro inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
