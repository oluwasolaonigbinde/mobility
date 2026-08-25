import type { Metadata } from "next";
import Link from "next/link";
import { DriverApplicationForms } from "./application-forms";

export const metadata: Metadata = { title: "Driver application" };

export default function DriverApplicationPage() {
  return (
    <main className="bg-atmosphere relative flex-1 overflow-hidden p-6 md:p-10">
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden />
      <div className="animate-rise relative mx-auto w-full max-w-5xl">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="micro text-amber mb-3">Vantage // driver network</p>
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
        <DriverApplicationForms />
        <p className="micro text-faint mt-6">
          No password, work access, assignment, payout, vehicle or document access is created by
          this form.
        </p>
      </div>
    </main>
  );
}
