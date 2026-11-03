"use client";

import { useState, useTransition, type ReactNode } from "react";

export function QuotationForm({
  action,
  children,
}: {
  action: (data: FormData) => Promise<{ error: string } | never>;
  children: ReactNode;
}) {
  const [error, setError] = useState<string>();
  const [pending, start] = useTransition();
  return (
    <form
      className="mt-4 grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        start(async () => {
          setError(undefined);
          const result = await action(data);
          setError(result.error);
        });
      }}
    >
      <fieldset disabled={pending} className="contents">
        {children}
      </fieldset>
      {error ? (
        <p role="alert" className="text-coral text-sm">
          {error}
        </p>
      ) : null}
    </form>
  );
}
