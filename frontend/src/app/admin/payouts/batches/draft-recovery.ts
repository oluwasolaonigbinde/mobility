import { z } from "zod";

const draftSchema = z.object({
  requestId: z.string().uuid(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  ledgerEntryIds: z.array(z.string().uuid()).min(1).max(500),
});
export type DraftRecovery = z.infer<typeof draftSchema>;

export function recoveryKey(actorId: string): string {
  return `cardvert-payout-draft:${actorId}`;
}

export function readDraftRecovery(
  storage: Pick<Storage, "getItem">,
  actorId: string,
): DraftRecovery | null {
  const raw = storage.getItem(recoveryKey(actorId));
  if (!raw) return null;
  const result = draftSchema.safeParse(JSON.parse(raw));
  if (!result.success)
    throw new Error("Saved payout recovery could not be read. Open your drafts before continuing.");
  return result.data;
}

export function retainDraftRecovery(
  storage: Pick<Storage, "getItem" | "setItem">,
  actorId: string,
  currency: string,
  ledgerEntryIds: string[],
): DraftRecovery {
  const existing = readDraftRecovery(storage, actorId);
  if (existing) return existing;
  const draft = draftSchema.parse({
    requestId: crypto.randomUUID(),
    currency,
    ledgerEntryIds: [...ledgerEntryIds].sort(),
  });
  storage.setItem(recoveryKey(actorId), JSON.stringify(draft));
  return draft;
}
