import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { RuleForm } from "./rule-form";
import { cx } from "@/lib/cx";

export const metadata: Metadata = { title: "Payout rules" };

export default async function PayoutRulesPage({
  searchParams,
}: {
  searchParams: Promise<{ campaign?: string }>;
}) {
  const params = await searchParams;
  const api = createApiClient(await getSessionToken());

  const { data: campaigns } = await api.GET("/api/v1/admin/campaigns", {
    params: { query: { limit: 100 } },
  });
  const items = campaigns?.items ?? [];
  const selectedId =
    params.campaign && items.some((c) => c.id === params.campaign) ? params.campaign : items[0]?.id;

  const rules = selectedId
    ? (
        await api.GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules", {
          params: { path: { campaign_id: selectedId }, query: { limit: 10 } },
        })
      ).data
    : undefined;

  // One active rule governs a campaign; edit it if present, else create.
  const activeRule = rules?.items.find((r) => r.status === "active");

  return (
    <div className="animate-rise mx-auto max-w-4xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/payouts" className="hover:text-muted">
          Payouts
        </Link>{" "}
        / <span className="text-muted">Rules</span>
      </nav>
      <PageHeader
        title="Payout rules"
        eyebrow="How drivers earn on each campaign — rates, zone bonuses, caps and fraud multipliers"
      />

      {/* Campaign picker */}
      <div className="mb-5 flex gap-1 overflow-x-auto" role="group" aria-label="Campaign">
        {items.map((c) => (
          <Link
            key={c.id}
            href={`/admin/payouts/rules?campaign=${c.id}`}
            className={cx(
              "micro rounded-lg px-3 py-2 whitespace-nowrap transition-colors",
              c.id === selectedId ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {c.name}
          </Link>
        ))}
      </div>

      {!selectedId ? (
        <Panel className="p-10 text-center">
          <p className="text-muted text-sm">No campaigns yet.</p>
        </Panel>
      ) : (
        <Panel className="p-6 md:p-8">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="micro text-muted">
              {activeRule ? "Active rule" : "No rule yet — platform defaults apply"}
            </h2>
            {activeRule ? <StatusChip tone="green">active</StatusChip> : null}
          </div>
          <RuleForm campaignId={selectedId} rule={activeRule ?? null} />
        </Panel>
      )}
    </div>
  );
}
