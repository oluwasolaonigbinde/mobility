"use client";

import Link from "next/link";
import { driverAccountSetupLink, useFragmentToken } from "@/lib/auth/invite-link";
import { DriverAccountSetupForm } from "./setup-form";

export function DriverAccountSetupLink() {
  const token = useFragmentToken(driverAccountSetupLink);
  if (token === null)
    return (
      <p role="status" className="text-muted text-sm">
        Opening your setup link…
      </p>
    );
  if (!token)
    return (
      <div>
        <p role="alert" className="text-coral text-sm">
          This link is incomplete. Ask Terrax for a new account setup email.
        </p>
        <Link href="/apply" className="text-amber mt-4 inline-block text-sm">
          Return to application information
        </Link>
      </div>
    );
  return <DriverAccountSetupForm token={token} />;
}
