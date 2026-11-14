"use client";

import Link from "next/link";
import { passwordResetLink, useFragmentToken } from "@/lib/auth/invite-link";
import { PasswordResetForm } from "./reset-form";

export function ResetPasswordLink() {
  const token = useFragmentToken(passwordResetLink);
  if (token === null)
    return (
      <p role="status" className="text-muted text-sm">
        Opening your reset link…
      </p>
    );
  if (!token)
    return (
      <div>
        <p role="alert" className="text-coral text-sm">
          This reset link is incomplete. Request a new one.
        </p>
        <Link href="/forgot-password" className="text-amber mt-4 inline-block text-sm">
          Request a new link
        </Link>
      </div>
    );
  return <PasswordResetForm token={token} />;
}
