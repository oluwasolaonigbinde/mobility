"use client";

import { useState, useTransition, type ReactNode } from "react";
import {
  smallVatConfirmation,
  vatPercentageToRate,
  VAT_PERCENTAGE_ERROR,
} from "@/lib/billing/vat-percentage";

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
        const percentage = String(data.get("tax_percentage") ?? "");
        if (vatPercentageToRate(percentage) === null) {
          setError(VAT_PERCENTAGE_ERROR);
          return;
        }
        const confirmation = smallVatConfirmation(percentage);
        if (confirmation && !window.confirm(confirmation)) return;
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
