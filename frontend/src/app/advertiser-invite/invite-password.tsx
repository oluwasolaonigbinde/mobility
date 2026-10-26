"use client";

import { useSyncExternalStore } from "react";
import {
  inviteServerSnapshot,
  inviteTokenSnapshot,
  subscribeInviteLink,
} from "@/lib/auth/invite-link";
import { PasswordResetForm } from "../reset-password/reset-form";

export function InvitePassword() {
  const token = useSyncExternalStore(
    subscribeInviteLink,
    inviteTokenSnapshot,
    inviteServerSnapshot,
  );
  if (token === null) return <p role="status">Opening your invite…</p>;
  if (!token)
    return <p role="alert">This invite link is incomplete. Ask Terrax for a new invite.</p>;
  return <PasswordResetForm token={token} invite />;
}
