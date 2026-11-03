import type { Metadata } from "next";
import { PhoneCheck } from "./phone-check";

export const metadata: Metadata = { title: "Phone check" };

export default function DriverCapabilityPage() {
  return <PhoneCheck />;
}
