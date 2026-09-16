"use client";

import { useEffect, useRef, useState, type ElementType, type ReactNode } from "react";

/**
 * Fades a block up the first time it enters the viewport.
 *
 * Purely decorative, and it must never be the reason content cannot be read.
 * Three things guarantee that:
 *  - the observer sets `data-visible="true"` once and then stops watching;
 *  - `prefers-reduced-motion: reduce` forces `.terrax-reveal` opaque in marketing.css;
 *  - with JavaScript disabled nothing here runs at all, so the public root page
 *    ships a <noscript> rule that makes every `.terrax-reveal` block opaque.
 *
 * There is deliberately no `IntersectionObserver` feature check: any browser
 * lacking it also lacks the CSS this page is built on, so the branch could only
 * ever be dead code.
 */
export function Reveal({
  as: Tag = "div",
  delay = 0,
  className = "",
  children,
  id,
}: {
  as?: ElementType;
  delay?: number;
  className?: string;
  children: ReactNode;
  /** Section anchor, when the revealed block is itself a navigation target. */
  id?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      data-visible={visible ? "true" : "false"}
      style={{ animationDelay: `${delay}ms` }}
      className={`terrax-reveal ${className}`}
      id={id}
    >
      {children}
    </Tag>
  );
}
