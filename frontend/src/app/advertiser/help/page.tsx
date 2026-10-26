import type { Metadata } from "next";
import { ComplaintHelpPage } from "@/components/complaints/complainant-pages";

export const metadata: Metadata = { title: "Get help" };

export default function AdvertiserHelpPage() {
  return <ComplaintHelpPage party="advertiser" />;
}
