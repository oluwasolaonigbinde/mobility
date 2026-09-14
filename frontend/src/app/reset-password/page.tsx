import type { Metadata } from "next";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { PasswordResetForm } from "./reset-form";

export const metadata: Metadata = { title: "Choose a new password", referrer: "no-referrer" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string | string[] }>;
}) {
  const rawToken = (await searchParams).token;
  const token = typeof rawToken === "string" && rawToken.length <= 512 ? rawToken : "";
  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-sm">
        <p className="micro text-amber mb-3">Account recovery</p>
        <h1 className="font-display text-4xl font-semibold">Choose a new password</h1>
        <Panel className="mt-8 p-6">
          {token ? (
            <PasswordResetForm token={token} />
          ) : (
            <div>
              <p role="alert" className="text-coral text-sm">
                This reset link is incomplete. Request a new one.
              </p>
              <Link href="/forgot-password" className="text-amber mt-4 inline-block text-sm">
                Request a new link
              </Link>
            </div>
          )}
        </Panel>
      </div>
    </main>
  );
}
