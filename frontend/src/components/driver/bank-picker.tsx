"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type Bank = { code: string; name: string };

export function BankPicker({
  disabled,
  onBank,
}: {
  disabled?: boolean;
  onBank?: (code: string) => void;
}) {
  const [banks, setBanks] = useState<Bank[]>([]);
  const [query, setQuery] = useState("");
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    fetch("/api/apply/onboarding/banks", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Bank list unavailable");
        return response.json() as Promise<Bank[]>;
      })
      .then((result) => {
        if (current) {
          setBanks(result);
          setError(false);
        }
      })
      .catch(() => {
        if (current) setError(true);
      });
    return () => {
      current = false;
    };
  }, [attempt]);
  const filtered = banks.filter((bank) =>
    `${bank.name} ${bank.name.includes("Guaranty") ? "GTBank" : ""} ${bank.name.includes("United Bank for Africa") ? "UBA" : ""}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  const selected = banks.find((bank) => bank.code === value);
  return (
    <div className="grid gap-2">
      <label className="flex flex-col gap-1.5 text-sm">
        Search banks
        <input
          type="search"
          name="bank_search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={disabled}
          placeholder="Type your bank's name"
          className="border-edge bg-raised text-ink h-11 rounded-lg border px-3"
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        Bank
        <select
          name="bank_code"
          value={value}
          required
          disabled={disabled || !banks.length}
          onChange={(event) => {
            setValue(event.target.value);
            onBank?.(event.target.value);
          }}
          className="border-edge bg-raised text-ink h-11 rounded-lg border px-3"
        >
          <option value="">Choose your bank</option>
          {selected && !filtered.some((bank) => bank.code === value) ? (
            <option value={selected.code}>{selected.name}</option>
          ) : null}
          {filtered.map((bank) => (
            <option key={bank.code} value={bank.code}>
              {bank.name}
            </option>
          ))}
        </select>
      </label>
      {!banks.length && !error ? (
        <p role="status" className="text-muted text-sm">
          Loading banks…
        </p>
      ) : null}
      {banks.length && !filtered.length ? (
        <p role="status" className="text-muted text-sm">
          No banks found. Try another name.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-coral text-sm">
          We couldn&apos;t load banks.{" "}
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setError(false);
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </Button>
        </p>
      ) : null}
    </div>
  );
}
