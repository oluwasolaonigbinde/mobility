import type { Metadata } from "next";
import Link from "next/link";
import { cx } from "@/lib/cx";
import { DriverApplicationForms } from "./application-forms";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

export const metadata: Metadata = { title: "Driver application" };

const STEPS = [
  {
    id: "apply",
    title: "Apply",
    detail: "Send your contact details. Cardvert emails you a code for the next step.",
  },
  {
    id: "details",
    title: "Your details",
    detail: "Use the emailed code to send your ID, bank details and documents for review.",
  },
  {
    id: "car",
    title: "Your car",
    detail: "Once your details are approved, send your car's documents for review.",
  },
] as const;

type StepId = (typeof STEPS)[number]["id"];

export default async function DriverApplicationPage({
  searchParams,
}: {
  searchParams: Promise<{ step?: string }>;
}) {
  const requested = (await searchParams).step;
  const step: StepId = STEPS.some((item) => item.id === requested)
    ? (requested as StepId)
    : "apply";
  const index = STEPS.findIndex((item) => item.id === step);
  const next = STEPS[index + 1];
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
        <nav aria-label="Application steps" className="mb-5">
          <ol className="grid gap-3 sm:grid-cols-3">
            {STEPS.map((item, position) => (
              <li key={item.id}>
                <Link
                  href={`/apply?step=${item.id}`}
                  aria-current={item.id === step ? "step" : undefined}
                  className={cx(
                    "border-edge bg-raised block rounded-lg border p-3 text-xs transition-colors",
                    item.id === step ? "border-amber" : "hover:border-ink/30",
                  )}
                >
                  <span className="text-amber font-mono">{position + 1}</span>
                  <span className="text-ink mt-1 block font-medium">{item.title}</span>
                  <span className="text-muted mt-1 block leading-5">{item.detail}</span>
                </Link>
              </li>
            ))}
          </ol>
        </nav>
        {step === "apply" ? <DriverApplicationForms /> : null}
        {step === "details" ? <PersonPayeeForm /> : null}
        {step === "car" ? <VehicleForm /> : null}
        {next ? (
          <p className="mt-5 text-sm">
            <Link href={`/apply?step=${next.id}`} className="text-cyan">
              Next: {next.title} →
            </Link>
          </p>
        ) : null}
        <p className="micro text-faint mt-6">
          No password, work access, assignment, payout or document access is created by these forms.
          Vehicle approval never assigns campaign work automatically. After both reviews pass,
          Terrax Media separately starts account setup; choose your password with that one-use link,
          then sign in.
        </p>
      </div>
    </main>
  );
}
