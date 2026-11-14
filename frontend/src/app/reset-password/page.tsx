import type { Metadata } from "next";
import { Panel } from "@/components/ui/panel";
import { ResetPasswordLink } from "./reset-link";

export const metadata: Metadata = { title: "Choose a new password", referrer: "no-referrer" };

export default function ResetPasswordPage() {
  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-sm">
        <p className="micro text-amber mb-3">Account recovery</p>
        <h1 className="font-display text-4xl font-semibold">Choose a new password</h1>
        <Panel className="mt-8 p-6">
          <ResetPasswordLink />
        </Panel>
      </div>
    </main>
  );
}
