"use client";

import { advertiserInviteLink, useFragmentToken } from "@/lib/auth/invite-link";
import { PasswordResetForm } from "../reset-password/reset-form";

export function InvitePassword() {
  const token = useFragmentToken(advertiserInviteLink);
  if (token === null) return <p role="status">Opening your invite…</p>;
  if (!token)
    return <p role="alert">This invite link is incomplete. Ask Terrax for a new invite.</p>;
  return <PasswordResetForm token={token} invite />;
}
