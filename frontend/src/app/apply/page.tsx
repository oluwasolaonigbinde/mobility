import Link from "next/link";
import { ApplicationJourney } from "./application-journey";

export const metadata = { title: "Driver application", referrer: "no-referrer" as const };
export default async function DriverApplicationPage({
  searchParams,
}: {
  searchParams: Promise<{ step?: string }>;
}) {
  const { step } = await searchParams;
  return (
    <main className="bg-atmosphere flex-1 p-6 md:p-10">
      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-4xl font-semibold">Apply to drive</h1>
            <p className="text-muted mt-3 max-w-xl">
              Tell us about yourself and your car. We’ll guide you through the checks.
            </p>
          </div>
          <Link href="/login" className="text-green text-sm underline">
            Already have a driver account? Sign in
          </Link>
        </div>
        <ApplicationJourney requestedStep={step} />
      </div>
    </main>
  );
}
