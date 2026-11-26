import type { Metadata } from "next";
import { Panel } from "@/components/ui/panel";
import { DriverAccountSetupLink } from "./setup-link";

export const metadata: Metadata = {
  title: "Set up your driver account",
  referrer: "no-referrer",
};

export default function DriverAccountSetupPage() {
  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-md">
        <h1 className="font-display text-4xl font-semibold">Set up your driver account</h1>
        <p className="text-muted mt-3 text-sm">
          Choose a password to finish setting up your driver account.
        </p>
        <Panel className="mt-8 p-6">
          <DriverAccountSetupLink />
        </Panel>
      </div>
    </main>
  );
}
