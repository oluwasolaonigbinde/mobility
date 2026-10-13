"use client";

import { useEffect, useRef, useState } from "react";
import { BankPicker } from "./bank-picker";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { onboardingResponseJson } from "@/lib/files/onboarding-upload";

type Check = {
  outcome: "resolved" | "unavailable";
  account_name?: string;
  bank_check_receipt: string;
};

export function ApplicationBankDetails({ accessToken }: { accessToken: string }) {
  const [bank, setBank] = useState("");
  const [number, setNumber] = useState("");
  const [check, setCheck] = useState<Check>();
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const [previousAccessToken, setPreviousAccessToken] = useState(accessToken);
  const generation = useRef(0);
  if (previousAccessToken !== accessToken) {
    setPreviousAccessToken(accessToken);
    setCheck(undefined);
    setConfirmed(false);
    setError(undefined);
    setPending(false);
  }
  function invalidate() {
    generation.current += 1;
    setCheck(undefined);
    setConfirmed(false);
    setError(undefined);
    setPending(false);
  }
  useEffect(() => {
    const current = ++generation.current;
    if (!bank || !/^[0-9]{10}$/.test(number) || !accessToken.trim()) return;
    const timer = setTimeout(async () => {
      setPending(true);
      try {
        const response = await fetch("/api/apply/onboarding/account-name", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            application_access_token: accessToken.trim(),
            bank_code: bank,
            account_number: number,
          }),
        });
        const result = await onboardingResponseJson<Check>(response);
        if (generation.current === current) setCheck(result);
      } catch (caught) {
        if (generation.current === current)
          setError(
            caught instanceof Error ? caught.message : "We couldn't check your account. Try again.",
          );
      } finally {
        if (generation.current === current) setPending(false);
      }
    }, 350);
    return () => {
      clearTimeout(timer);
      generation.current += 1;
    };
  }, [bank, number, accessToken, attempt]);
  return (
    <section className="grid gap-4" aria-label="Bank details">
      <BankPicker
        onBank={(code) => {
          invalidate();
          setBank(code);
        }}
      />
      <label className="flex flex-col gap-1.5 text-sm">
        Account number (10 digits)
        <input
          name="account_number"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          value={number}
          onChange={(event) => {
            invalidate();
            setNumber(event.target.value);
          }}
          minLength={10}
          maxLength={10}
          required
          className="border-edge bg-raised text-ink h-11 rounded-lg border px-3"
        />
      </label>
      {pending ? (
        <p role="status" className="text-muted text-sm">
          Checking account name…
        </p>
      ) : null}
      {check?.outcome === "resolved" ? (
        <div className="grid gap-2">
          <p role="status" className="text-sm">
            Account name: {check.account_name}. Is this you?
          </p>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setConfirmed(true)}
            disabled={confirmed}
          >
            {confirmed ? "Confirmed" : "This is me"}
          </Button>
          <input type="hidden" name="account_name" value={check.account_name ?? ""} />
        </div>
      ) : null}
      {check?.outcome === "unavailable" ? (
        <>
          <p className="text-muted text-sm">
            We can&apos;t check the name right now. Enter it as shown on your bank account.
          </p>
          <Field name="account_name" label="Name on bank account" required autoComplete="off" />
        </>
      ) : null}
      {error ? (
        <p role="alert" className="text-coral text-sm">
          {error}{" "}
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              invalidate();
              setAttempt(attempt + 1);
            }}
          >
            Try again
          </Button>
        </p>
      ) : null}
      <input type="hidden" name="bank_check_receipt" value={check?.bank_check_receipt ?? ""} />
      <input type="hidden" name="account_name_confirmed" value={String(confirmed)} />
      <input type="hidden" name="bank_check_outcome" value={check?.outcome ?? ""} />
    </section>
  );
}
