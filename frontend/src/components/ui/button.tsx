import { type ButtonHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

type Variant = "primary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary:
    "bg-amber text-accent-ink font-medium hover:bg-amber-soft shadow-glow-amber disabled:shadow-none",
  ghost: "border border-edge bg-raised text-ink hover:border-edge-strong",
  danger: "border border-coral/40 bg-coral/10 text-coral hover:bg-coral/15",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return (
    <button
      className={cx(
        "inline-flex h-11 items-center justify-center gap-2 rounded-lg px-5 text-sm transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
