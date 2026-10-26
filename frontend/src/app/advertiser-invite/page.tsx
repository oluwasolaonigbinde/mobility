import type { Metadata } from "next";
import { Panel } from "@/components/ui/panel";
import { InvitePassword } from "./invite-password";

export const metadata: Metadata = { title: "Accept your Cardvert invite", referrer: "no-referrer" };

export default function AdvertiserInvitePage() {
  return (
    <main className="bg-atmosphere flex flex-1 items-center justify-center p-6">
      <div className="animate-rise w-full max-w-sm">
        <p className="micro text-amber mb-3">Your Cardvert login</p>
        <h1 className="font-display text-4xl font-semibold">Accept your invite</h1>
        <p className="text-muted mt-3 text-sm">
          Choose a password, then sign in. Your invite works once, for 24 hours.
        </p>
        <Panel className="mt-8 p-6">
          <InvitePassword />
        </Panel>
      </div>
    </main>
  );
}
