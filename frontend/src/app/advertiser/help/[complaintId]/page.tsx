import type { Metadata } from "next";
import { ComplaintConversationPage } from "@/components/complaints/complainant-pages";
import { readOwnConversation } from "@/lib/complaints/conversation";
import { CATEGORY_LABELS } from "@/lib/complaints/labels";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ complaintId: string }>;
}): Promise<Metadata> {
  const detail = await readOwnConversation("advertiser", (await params).complaintId);
  return {
    title:
      detail.state === "ready" ? CATEGORY_LABELS[detail.data.category] : "Support conversation",
  };
}

export default async function AdvertiserComplaintPage({
  params,
}: {
  params: Promise<{ complaintId: string }>;
}) {
  const { complaintId } = await params;
  return <ComplaintConversationPage party="advertiser" complaintId={complaintId} />;
}
