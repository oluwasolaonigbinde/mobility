import Image from "next/image";
import { COMPANY } from "@/lib/marketing/site";

/**
 * The official Terrax Media lockup.
 *
 * Both files are the approved logo artwork from `docs/brand/terrax-media/`,
 * losslessly reduced to a web delivery size and nothing else — not redrawn, not
 * recoloured, not stretched, not rotated, per Brand Guide §2 "Prohibited use".
 *
 *  - `light`  the full-colour lockup, for the terrax-paper and terrax-card grounds.
 *  - `dark`   the approved reversed (white) lockup, for the terrax-ink and terrax-deep grounds.
 *
 * The two source files have slightly different aspect ratios, so each variant
 * carries its own intrinsic size and both are constrained by height only.
 */
const VARIANTS = {
  light: { src: "/brand/terrax/terrax-logo.png", width: 2092, height: 680 },
  dark: { src: "/brand/terrax/terrax-logo-white.png", width: 1544, height: 499 },
} as const;

export function Wordmark({
  variant,
  className = "h-9 w-auto",
  priority = false,
}: {
  variant: keyof typeof VARIANTS;
  className?: string;
  priority?: boolean;
}) {
  const { src, width, height } = VARIANTS[variant];
  return (
    <Image
      src={src}
      alt={COMPANY}
      width={width}
      height={height}
      className={className}
      priority={priority}
    />
  );
}
