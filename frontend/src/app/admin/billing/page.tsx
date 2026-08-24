import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

export const metadata: Metadata = { title: "Commercial billing" };

export default async function AdminBillingPage() {
  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/campaigns", {
    params: { query: { limit: 100 } },
  });
  const campaigns = data?.items ?? [];
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Commercial billing"
        eyebrow="Quotations, invoices, receipts, funding and policy gates"
      />
      <Panel className="overflow-hidden">
        <ul className="divide-edge/60 divide-y">
          {campaigns.map((campaign) => (
            <li key={campaign.id} className="flex items-center justify-between gap-4 px-6 py-4">
              <div>
                <p className="text-sm font-medium">{campaign.name}</p>
                <p className="micro text-muted mt-1">{campaign.organization.name}</p>
              </div>
              <div className="flex items-center gap-3">
                <StatusChip tone="default">{campaign.status}</StatusChip>
                <Link
                  href={`/admin/billing/${campaign.id}`}
                  className="border-edge bg-raised rounded-lg border px-3 py-2 text-sm hover:border-edge-strong"
                >
                  Open billing
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
