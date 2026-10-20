import type { Metadata } from "next";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { DriverAccountSetupForm } from "./setup-form";

export const metadata: Metadata = {
  title: "Set up your driver account",
  referrer: "no-referrer",
};

export default async function DriverAccountSetupPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string | string[] }>;
}) {
  const rawToken = (await searchParams).token;
  const token = typeof rawToken === "string" && rawToken.length <= 512 ? rawToken : "";

  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-md">
        <p className="micro text-amber mb-3">Driver account setup</p>
        <h1 className="font-display text-4xl font-semibold">Set up your driver account</h1>
        <p className="text-muted mt-3 text-sm">
          Choose a password to finish setting up your driver account.
        </p>
        <Panel className="mt-8 p-6">
          {token ? (
            <DriverAccountSetupForm token={token} />
          ) : (
            <div>
              <p role="alert" className="text-coral text-sm">
                This link is incomplete. Ask Terrax for a new account setup email.
              </p>
              <Link href="/apply" className="text-amber mt-4 inline-block text-sm">
                Return to application information
              </Link>
            </div>
          )}
        </Panel>
      </div>
    </main>
  );
}
