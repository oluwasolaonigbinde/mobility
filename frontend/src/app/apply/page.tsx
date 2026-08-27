import type { Metadata } from "next";
import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { DriverApplicationForms } from "./application-forms";

export const metadata: Metadata = { title: "Driver application" };

export default function DriverApplicationPage() {
  return (
    <main className="bg-atmosphere relative flex-1 overflow-hidden p-6 md:p-10">
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden />
      <div className="animate-rise relative mx-auto w-full max-w-5xl">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="micro text-amber mb-3">Cardvert // driver network</p>
            <h1 className="font-display text-4xl font-semibold tracking-tight">Drive the city.</h1>
            <p className="text-muted mt-3 max-w-xl text-sm">
              Applications are reviewed by operations before any account can access the driver
              workspace.
            </p>
          </div>
          <Link href="/login" className="text-muted hover:text-ink text-sm transition-colors">
            Already invited? Sign in →
          </Link>
        </div>
        <Panel className="mb-5 p-5" aria-labelledby="application-journey-title">
          <p className="micro text-cyan">Application journey</p>
          <h2 id="application-journey-title" className="font-display mt-1 text-xl font-semibold">
            Application receipt is not work approval
          </h2>
          <ol className="text-muted mt-4 grid gap-3 text-xs sm:grid-cols-5">
            {[
              "Submit contact details",
              "Use the expiring onboarding code",
              "Submit person/payee evidence",
              "Submit vehicle evidence",
              "Wait for admin review and invitation",
            ].map((step, index) => (
              <li key={step} className="border-edge bg-raised rounded-lg border p-3">
                <span className="text-amber font-mono">{index + 1}</span>
                <span className="mt-1 block leading-5">{step}</span>
              </li>
            ))}
          </ol>
          <p className="text-muted mt-4 text-xs">
            After admin review and invitation, sign in to the driver app. The status reference and
            onboarding code never grant a session, campaign work, or tracking authority.
          </p>
        </Panel>
        <DriverApplicationForms />
        <p className="micro text-faint mt-6">
          No password, work access, assignment, payout or document access is created by these forms.
          Vehicle approval never assigns campaign work automatically.
        </p>
      </div>
    </main>
  );
}
