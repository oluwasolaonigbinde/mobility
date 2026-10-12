import type { Metadata } from "next";
import Link from "next/link";
import { Steps } from "@/components/ui/steps";
import { DriverApplicationForms, NewCodePanel } from "./application-forms";
import { PersonPayeeForm } from "./person-payee-form";
import { VehicleForm } from "./vehicle-form";

export const metadata: Metadata = { title: "Driver application" };

const STEPS = [
  { id: "apply", title: "Apply", detail: "Your name and contact details" },
  { id: "details", title: "Your details", detail: "Your ID, bank details and documents" },
  { id: "car", title: "Your car", detail: "Your car and its papers" },
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
            <h1 className="font-display text-4xl font-semibold tracking-tight">
              Start an application
            </h1>
            <p className="text-muted mt-3 max-w-xl">
              Three short steps. We check each one before you start driving.
            </p>
          </div>
          <Link href="/login" className="text-muted hover:text-ink text-sm transition-colors">
            Already invited? Sign in →
          </Link>
        </div>
        <div className="mb-5">
          <Steps
            label="Application steps"
            columns
            items={STEPS.map((item) => ({
              key: item.id,
              title: item.title,
              detail: item.detail,
              href: `/apply?step=${item.id}`,
              current: item.id === step,
            }))}
          />
        </div>
        {step === "apply" ? <DriverApplicationForms /> : null}
        {step === "details" ? <PersonPayeeForm /> : null}
        {step === "car" ? <VehicleForm /> : null}
        {step !== "apply" ? <NewCodePanel /> : null}
        {next ? (
          <p className="mt-5 text-sm">
            <Link href={`/apply?step=${next.id}`} className="text-cyan">
              Next: {next.title} →
            </Link>
          </p>
        ) : null}
      </div>
    </main>
  );
}
