import type { Metadata } from "next";
import { CapabilityProbe } from "./capability-probe";
import { PhoneCheck } from "./phone-check";

export const metadata: Metadata = { title: "Phone check" };

// ?view=support is unlinked, not an access boundary: it shows the driver's own
// redacted probe report for a support conversation (D38(b)).
export default async function DriverCapabilityPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const { view } = await searchParams;
  return view === "support" ? <CapabilityProbe /> : <PhoneCheck />;
}
