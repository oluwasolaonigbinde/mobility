import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ComplaintMessageForm, ComplaintUpdateForm } from "@/components/complaints/forms";
import { replyToComplaintAction, updateComplaintAction } from "@/lib/complaints/actions";
import { CATEGORY_LABELS, STAFF_STATUS, formatWat, referenceText } from "@/lib/complaints/labels";
import { readComplaintApi } from "@/lib/complaints/read";

export const metadata: Metadata = { title: "Complaint" };

export default async function StaffComplaintPage({
  params,
}: {
  params: Promise<{ complaintId: string }>;
}) {
  const { complaintId } = await params;
  const api = createApiClient(await getSessionToken());
  const [detail, staff] = await Promise.all([
    readComplaintApi(() =>
      api.GET("/api/v1/admin/complaints/{complaint_id}", {
        params: { path: { complaint_id: complaintId } },
      }),
    ),
    readComplaintApi(() =>
      api.GET("/api/v1/admin/users", {
        params: { query: { role: "admin", status: "active", limit: 100 } },
      }),
    ),
  ]);

  const back = (
    <Link href="/admin/complaints" className="micro text-amber">
      ← Customer Service inbox
    </Link>
  );
  if (detail.state === "missing") {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {back}
        <EmptyState title="Complaint not found" body="It may have been opened with a wrong link." />
      </div>
    );
  }
  if (detail.state !== "ready") {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {back}
        <Panel className="p-5" role="alert">
          <h2 className="text-base font-semibold">This complaint couldn&apos;t be loaded</h2>
          <p className="text-muted mt-1 text-sm">
            <Link href={`/admin/complaints/${complaintId}`} className="text-amber hover:underline">
              Try again
            </Link>
          </p>
        </Panel>
      </div>
    );
  }

  const complaint = detail.data;
  const chip = STAFF_STATUS[complaint.status];
  const staffOptions =
    staff.state === "ready"
      ? staff.data.items.map((person) => ({ id: person.id, label: person.full_name }))
      : null;

  return (
    <div className="animate-rise mx-auto flex max-w-4xl flex-col gap-4">
      {back}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            {complaint.party_name}
          </h1>
          <p className="text-muted mt-1 text-sm">
            {complaint.party === "driver" ? "Driver" : "Advertiser"} · raised by{" "}
            {complaint.raised_by_name} on {formatWat(complaint.created_at)}
          </p>
        </div>
        <StatusChip tone={chip.tone}>{chip.label}</StatusChip>
      </div>

      <Panel className="grid gap-3 p-5 text-sm sm:grid-cols-3">
        <div>
          <p className="micro text-muted">About</p>
          <p className="mt-1">{CATEGORY_LABELS[complaint.category]}</p>
        </div>
        <div>
          <p className="micro text-muted">Record</p>
          <p className="mt-1">
            {referenceText(complaint.reference_type, complaint.reference_label)}
          </p>
        </div>
        <div>
          <p className="micro text-muted">Assigned to</p>
          <p className="mt-1">{complaint.assigned_to_name ?? "Nobody"}</p>
        </div>
      </Panel>

      <ol className="flex flex-col gap-3" aria-label="Conversation">
        {complaint.messages.map((message) => (
          <li key={message.id}>
            <Panel className={`p-4 ${message.author_side === "staff" ? "border-amber/40" : ""}`}>
              <p className="micro text-muted">
                {message.author_name}
                {message.author_side === "staff" ? " (Terrax Media)" : ""} ·{" "}
                {formatWat(message.sent_at)}
              </p>
              <p className="mt-2 text-sm leading-6 whitespace-pre-line">{message.body}</p>
            </Panel>
          </li>
        ))}
      </ol>

      <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
        <Panel className="p-5">
          <ComplaintMessageForm
            complaintId={complaint.id}
            action={replyToComplaintAction}
            label="Reply as Terrax Media"
            placeholder="Give a clear answer or the next step. The complainant sees this as Terrax Media."
            submitLabel="Send reply"
            allowResolve
          />
        </Panel>
        <Panel className="p-5">
          <ComplaintUpdateForm
            complaintId={complaint.id}
            action={updateComplaintAction}
            staff={staffOptions}
          />
        </Panel>
      </div>
    </div>
  );
}
