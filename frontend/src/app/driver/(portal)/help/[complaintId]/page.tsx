import type { Metadata } from "next";
import { ComplaintConversationPage } from "@/components/complaints/complainant-pages";

export const metadata: Metadata = { title: "Support conversation" };

export default async function DriverComplaintPage({
  params,
}: {
  params: Promise<{ complaintId: string }>;
}) {
  const { complaintId } = await params;
  return <ComplaintConversationPage party="driver" complaintId={complaintId} />;
}
