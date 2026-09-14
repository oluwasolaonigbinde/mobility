import Link from "next/link";
import { batchApi } from "../../../batch-api";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";

export default async function LineHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ batchId: string; lineId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { batchId, lineId } = await params;
  const query = await searchParams;
  const page = /^\d+$/.test(query.page ?? "") ? Math.min(Number(query.page), 100000) : 0;
  const history = await batchApi<{
    items: {
      id: string;
      outcome: string;
      source: string;
      applied: boolean;
      provider_occurred_at: string;
      created_at: string;
    }[];
    latest_submission_outcome: string | null;
    total: number;
  }>(`/lines/${lineId}/history?limit=25&offset=${page * 25}`);
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link className="underline" href={`/admin/payouts/batches/${batchId}`}>
        Back to batch
      </Link>
      <PageHeader
        title="Payment line history"
        eyebrow="Verified provider evidence; individual outcomes remain authoritative"
      />
      <p>
        Latest submission observation:{" "}
        {history.latest_submission_outcome ?? "No provider observation recorded"}
      </p>
      {history.items.map((event) => (
        <Panel key={event.id} className="space-y-2 p-4">
          <p>
            {event.outcome} ·{" "}
            {event.applied ? "Applied to this line" : "Retained; did not change this line"}
          </p>
          <p>
            Verified via {event.source} · provider time {formatDateTime(event.provider_occurred_at)}
          </p>
          <p className="text-muted text-sm">Recorded {formatDateTime(event.created_at)}</p>
        </Panel>
      ))}
      {!history.items.length ? (
        <p>No verified final result has been recorded. This does not mean failed or paid.</p>
      ) : null}
      <nav aria-label="History pages" className="flex gap-4">
        {page > 0 ? <Link href={`?page=${page - 1}`}>Previous</Link> : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < history.total ? <Link href={`?page=${page + 1}`}>Next</Link> : null}
      </nav>
    </div>
  );
}
