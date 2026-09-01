import { type InputHTMLAttributes, useId } from "react";
import { cx } from "@/lib/cx";

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

/** Labeled input with the Cardvert mono-label treatment and a11y wiring. */
export function Field({ label, error, className, ...props }: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="micro text-muted">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cx(
          "bg-raised text-ink placeholder:text-faint h-11 rounded-lg border px-3.5 text-sm",
          "focus:border-amber transition-colors focus:outline-none",
          error ? "border-coral/60" : "border-edge",
          className,
        )}
        {...props}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
