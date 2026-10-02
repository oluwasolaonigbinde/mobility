"use client";
import { useRouter } from "next/navigation";
import { SearchSelect } from "../search-select";
export function CampaignPicker({ section }: { section: string }) {
  const router = useRouter();
  return (
    <SearchSelect
      kind="campaign_any"
      name="campaign"
      label="Campaign"
      onSelect={(id) => router.push(`/admin/campaigns/${id}#${section}`)}
    />
  );
}
