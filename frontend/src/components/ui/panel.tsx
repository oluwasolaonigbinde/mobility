import { type HTMLAttributes } from "react";
import { cx } from "@/lib/cx";

/** Core surface — the prototype's glass panel, minus the gimmicks. */
export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-panel border-edge bg-panel shadow-panel border", className)}
      {...props}
    />
  );
}
