"use client";

import { useActionState, useEffect, useState, useTransition } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { formatMoneyExact } from "@/lib/format";
import {
  batchTransitionAction,
  allocateDebtAction,
  createAndReserveBatchAction,
  maskedDestinationAction,
  pollLineAction,
  previewSelectionAction,
  type BatchActionState,
} from "./actions";
import type { EligiblePayment } from "./operation-types";
import {
  readDraftRecovery,
  recoveryKey,
  retainDraftRecovery,
  type DraftRecovery,
} from "./draft-recovery";

const initialState: BatchActionState = {};

export function AllocateDebtForm({ entry }: { entry: EligiblePayment }) {
  const [state, action, pending] = useActionState(allocateDebtAction, initialState);
  return (
    <form
      action={action}
      className="mt-3 space-y-2"
      onSubmit={(event) => {
        if (
          !window.confirm(
            `Allocate available ${entry.currency} credits to ${entry.driver_name}'s carry-forward debt?`,
          )
        )
          event.preventDefault();
      }}
    >
      <input type="hidden" name="driver_profile_id" value={entry.driver_profile_id} />
      <input type="hidden" name="currency" value={entry.currency} />
      <Button type="submit" disabled={pending} variant="ghost">
        {pending ? "Allocating…" : "Allocate debt"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green text-sm">
          {state.done}
        </p>
      ) : null}
    </form>
  );
}

export function MaskedDestination({ versionId }: { versionId: string }) {
  const [result, setResult] = useState<{ mask?: string; error?: string }>({});
  const [pending, start] = useTransition();
  useEffect(() => {
    if (!result.mask) return;
    const timer = window.setTimeout(() => setResult({}), 30_000);
    const hide = () => {
      if (document.hidden) setResult({});
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [result.mask]);
  return (
    <div className="mt-2 text-sm">
      {result.mask ? (
        <p>
          {result.mask}{" "}
          <button type="button" className="underline" onClick={() => setResult({})}>
            Hide
          </button>
        </p>
      ) : (
        <Button
          variant="ghost"
          disabled={pending}
          type="button"
          onClick={() => {
            if (
              window.confirm(
                "View the masked destination for payout review? This access is audited.",
              )
            ) {
              start(async () => setResult(await maskedDestinationAction(versionId)));
            }
          }}
        >
          {pending ? "Checking…" : "Review masked destination"}
        </Button>
      )}
      {result.error ? (
        <p role="alert" className="text-coral">
          {result.error}
        </p>
      ) : null}
    </div>
  );
}

export function CreateBatchForm({
  entries,
  actorId,
  draftId,
  draftCurrency,
}: {
  entries: EligiblePayment[];
  actorId: string;
  draftId?: string;
  draftCurrency?: string;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [recovery, setRecovery] = useState<DraftRecovery | null>(null);
  const [state, setState] = useState<BatchActionState>({});
  const [preview, setPreview] = useState<{
    currency?: string;
    total_amount?: string;
    error?: string;
  } | null>(null);
  const [pending, start] = useTransition();
  useEffect(() => {
    const refresh = () => {
      try {
        setRecovery(readDraftRecovery(localStorage, actorId));
      } catch {
        setState({
          error:
            "Saved recovery is unavailable. Check your existing drafts before starting a batch.",
        });
      }
    };
    refresh();
    window.addEventListener("storage", refresh);
    return () => window.removeEventListener("storage", refresh);
  }, [actorId]);
  const chosen = entries.filter((entry) => selected.includes(entry.ledger_entry_id));
  const currency = draftCurrency ?? chosen[0]?.currency;
  const execute = () =>
    start(async () => {
      if (!navigator.locks) {
        setState({
          error:
            "Safe multi-tab recovery is unavailable in this browser. Open an existing draft or use a browser with Web Locks.",
        });
        return;
      }
      await navigator.locks.request(recoveryKey(actorId), async () => {
        try {
          let saved = readDraftRecovery(localStorage, actorId);
          if (draftId && saved && saved.requestId !== draftId) {
            setState({ error: "Recover the saved batch before working on a different draft." });
            return;
          }
          if (!saved && draftId) {
            saved = { requestId: draftId, currency: draftCurrency!, ledgerEntryIds: selected };
            localStorage.setItem(recoveryKey(actorId), JSON.stringify(saved));
          }
          saved ??= retainDraftRecovery(localStorage, actorId, currency!, selected);
          setRecovery(saved);
          const data = new FormData();
          data.set("request_id", saved.requestId);
          data.set("currency", saved.currency);
          data.set("ledger_entry_ids", saved.ledgerEntryIds.join(","));
          setState(await createAndReserveBatchAction({}, data));
        } catch {
          setState({
            error:
              "The request could not be confirmed. Keep this page and recover the existing draft before trying again.",
          });
        }
      });
    });
  return (
    <div className="space-y-4">
      <p className="text-muted text-sm">
        Choose whole available credits in one currency. These values are advisory; reservation
        rechecks holds, debt and payment eligibility.
      </p>
      {recovery ? (
        <div className="border-edge rounded-lg border p-4">
          <p>
            A saved {recovery.currency} request contains {recovery.ledgerEntryIds.length} credit(s).
            Retry uses the same draft and selection.
          </p>
          <Link className="underline" href={`/admin/payouts/batches/${recovery.requestId}`}>
            Open saved draft or batch
          </Link>
          {draftId === recovery.requestId ? (
            <Button
              type="button"
              variant="ghost"
              disabled={pending}
              onClick={() =>
                start(async () => {
                  if (!navigator.locks) return;
                  await navigator.locks.request(recoveryKey(actorId), async () => {
                    localStorage.removeItem(recoveryKey(actorId));
                    setRecovery(null);
                    setSelected([]);
                    setPreview(null);
                    setState({});
                  });
                })
              }
            >
              Review a different selection for this draft
            </Button>
          ) : null}
          {state.done ? (
            <Button
              variant="ghost"
              type="button"
              onClick={() => {
                localStorage.removeItem(recoveryKey(actorId));
                setRecovery(null);
                setSelected([]);
                setState({});
              }}
            >
              Finish recovery
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {entries.map((entry) => (
          <article
            key={entry.ledger_entry_id}
            className="border-edge min-w-0 rounded-xl border p-4"
          >
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-1"
                aria-label={`Select ${entry.driver_name} ${entry.amount} ${entry.currency}`}
                disabled={
                  pending ||
                  !!recovery ||
                  !entry.eligible ||
                  (!!currency && currency !== entry.currency)
                }
                checked={selected.includes(entry.ledger_entry_id)}
                onChange={(event) => {
                  setPreview(null);
                  setSelected((values) =>
                    event.target.checked
                      ? [...values, entry.ledger_entry_id]
                      : values.filter((id) => id !== entry.ledger_entry_id),
                  );
                }}
              />
              <span className="min-w-0">
                <strong className="block break-words">{entry.driver_name}</strong>
                <span className="text-muted block break-words">{entry.campaign_name}</span>
                <span className="block font-mono">
                  {formatMoneyExact(entry.amount, entry.currency)}
                </span>
              </span>
            </label>
            <p className="text-muted mt-2 text-sm">
              Payee: {entry.payee_name ?? "Not configured"} ·{" "}
              {entry.destination_verified ? "Destination verified" : "Destination unavailable"}
            </p>
            {entry.debt_deducted !== "0.00" && entry.debt_deducted !== "0" ? (
              <p className="text-sm">
                Debt already deducted: {formatMoneyExact(entry.debt_deducted, entry.currency)}
              </p>
            ) : null}
            {entry.ineligibility_reasons.map((reason) => (
              <p key={reason} className="text-amber text-sm">
                {reason}
              </p>
            ))}
            {entry.carry_forward_debt !== "0.00" && entry.carry_forward_debt !== "0" ? (
              <>
                <p className="text-sm">
                  Outstanding debt: {formatMoneyExact(entry.carry_forward_debt, entry.currency)}
                </p>
                <AllocateDebtForm entry={entry} />
              </>
            ) : null}
            {entry.bank_account_version_id ? (
              <MaskedDestination versionId={entry.bank_account_version_id} />
            ) : null}
          </article>
        ))}
      </div>
      {!entries.length ? (
        <p className="text-muted">No available credits match these filters.</p>
      ) : null}
      {!recovery && chosen.length ? (
        <Button
          type="button"
          variant="ghost"
          disabled={pending}
          onClick={() =>
            start(async () => setPreview(await previewSelectionAction(currency!, selected)))
          }
        >
          Review selected credits
        </Button>
      ) : null}
      {preview?.total_amount ? (
        <p>
          Advisory selected total:{" "}
          <strong>{formatMoneyExact(preview.total_amount, preview.currency)}</strong>. Reservation
          rechecks the selected credits.
        </p>
      ) : null}
      {preview?.error ? (
        <p role="alert" className="text-coral">
          {preview.error}
        </p>
      ) : null}
      <Button
        type="button"
        onClick={execute}
        disabled={pending || (!recovery && (!chosen.length || !preview?.total_amount))}
      >
        {pending
          ? "Confirming reservation…"
          : recovery
            ? "Retry saved reservation"
            : draftId
              ? "Reserve this draft"
              : "Create and reserve selected credits"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green text-sm">
          {state.done}
        </p>
      ) : null}
      {state.batchId ? (
        <Link className="block underline" href={`/admin/payouts/batches/${state.batchId}`}>
          Review this batch
        </Link>
      ) : null}
    </div>
  );
}

export function BatchActions({
  batchId,
  status,
}: {
  batchId: string;
  status: "reserved" | "reconciled" | "failed";
}) {
  const [state, action, pending] = useActionState(batchTransitionAction, initialState);
  return (
    <form
      action={action}
      className="flex flex-wrap gap-2"
      onSubmit={(event) => {
        const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
        if (
          submitter?.value === "void" &&
          !window.confirm("Release this batch's pre-provider reservations?")
        )
          event.preventDefault();
      }}
    >
      <input type="hidden" name="batch_id" value={batchId} />
      {status === "reserved" ? (
        <>
          <Button type="submit" name="intent" value="approve" disabled={pending} variant="ghost">
            Approve as checker
          </Button>
          <Button type="submit" name="intent" value="void" disabled={pending} variant="ghost">
            Void reservation
          </Button>
          <Button type="submit" name="intent" value="submit" disabled={pending}>
            Queue submission
          </Button>
        </>
      ) : (
        <>
          <p className="text-muted w-full text-sm">
            Terminally failed payments require a newer verified bank version with a different bank
            or account number and a separately approved replacement. Ambiguous submissions retain
            their original recovery key.
          </p>
          <Button type="submit" name="intent" value="retry_failed" disabled={pending}>
            Request failed-line replacement
          </Button>
        </>
      )}
      {state.error ? (
        <p role="alert" className="text-coral w-full text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green w-full text-sm">
          {state.done}
        </p>
      ) : null}
      {state.batchId ? (
        <Link className="w-full underline" href={`/admin/payouts/batches/${state.batchId}`}>
          Review replacement batch
        </Link>
      ) : null}
    </form>
  );
}

export function PollLineAction({ lineId }: { lineId: string }) {
  const [state, action, pending] = useActionState(pollLineAction, initialState);
  return (
    <form action={action} className="mt-2">
      <input type="hidden" name="line_id" value={lineId} />
      <Button type="submit" disabled={pending} variant="ghost">
        {pending ? "Verifying…" : "Verify line"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      {state.done ? (
        <p role="status" className="text-green text-sm">
          {state.done}
        </p>
      ) : null}
    </form>
  );
}
