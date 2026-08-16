import type { Metadata } from "next";
import { CapabilityProbe } from "./capability-probe";

export const metadata: Metadata = { title: "PWA capability probe" };

export default function DriverCapabilityPage() {
  return <CapabilityProbe />;
}
