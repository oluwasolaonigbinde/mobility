import Link from "next/link";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import type { components } from "@/lib/api/schema";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState } from "@/components/ui/empty-state";
import {
  followUpAdvertiserComplaintAction,
  followUpDriverComplaintAction,
  raiseAdvertiserComplaintAction,
  raiseDriverComplaintAction,
} from "@/lib/complaints/actions";
import {
  CATEGORY_LABELS,
  COMPLAINANT_STATUS,
  SENDER_LABELS,
  formatWat,
  referenceText,
  type ComplaintParty,
} from "@/lib/complaints/labels";
import { readComplaintApi } from "@/lib/complaints/read";
import { ComplaintMessageForm, RaiseComplaintForm } from "./forms";

type Summary = components["schemas"]["ComplaintSummaryRead"];

const BASE: Record<ComplaintParty, string> = {
  driver: "/driver/help",
  advertiser: "/advertiser/help",
};

function Unavailable({ title, retryHref }: { title: string; retryHref: string }) {
  return (
    <Panel className="p-5" role="alert">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-muted mt-1 text-sm">
        Cardvert couldn&apos;t load this right now.{" "}
        <Link href={retryHref} className="text-amber hover:underline">
          Try again
        </Link>
      </p>
    </Panel>
  );
}

function ComplaintRow({ party, item }: { party: ComplaintParty; item: Summary }) {
  const status = COMPLAINANT_STATUS[item.status];
  return (
    <li>
      <Link
        href={`${BASE[party]}/${item.id}`}
        className="hover:bg-raised/60 flex flex-wrap items-center justify-between gap-2 px-5 py-3.5"
      >
        <span>
          <span className="block text-sm font-medium">{CATEGORY_LABELS[item.category]}</span>
          <span className="text-muted block text-xs">
            {referenceText(item.reference_type, item.reference_label)} · Last message{" "}
            {formatWat(item.last_message_at)}
          </span>
        </span>
        <StatusChip tone={status.tone}>{status.label}</StatusChip>
      </Link>
    </li>
  );
}

/** The complainant's Help page: their complaints and the form to raise one. */
export async function ComplaintHelpPage({ party }: { party: ComplaintParty }) {
  const api = createApiClient(await getSessionToken());
  const [list, options] = await Promise.all([
    readComplaintApi(() =>
      party === "driver"
        ? api.GET("/api/v1/driver/complaints")
        : api.GET("/api/v1/advertiser/complaints"),
    ),
    readComplaintApi(() =>
      party === "driver"
        ? api.GET("/api/v1/driver/complaints/reference-options")
        : api.GET("/api/v1/advertiser/complaints/reference-options"),
    ),
  ]);
  if (list.state === "auth" || options.state === "auth") redirect("/login");

  const waiting = list.state === "ready" ? list.data.items.filter((i) => i.waiting_on_you) : [];

  return (
    <div className="animate-rise mx-auto flex max-w-3xl flex-col gap-5">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Help</h1>
        <p className="text-muted mt-1 text-sm">
          Raise a complaint and Terrax Media Customer Service will reply here. You&apos;ll also get
          a notification when they reply.
        </p>
      </div>

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-5 py-3.5">
          <h2 className="text-base font-semibold">Your complaints</h2>
          {waiting.length > 0 ? (
            <p className="text-amber mt-1 text-xs">
              Terrax Media replied to {waiting.length === 1 ? "one" : waiting.length} of your
              complaints.
            </p>
          ) : null}
        </div>
        {list.state === "ready" ? (
          list.data.items.length === 0 ? (
            <p className="text-muted px-5 py-8 text-center text-sm">
              You haven&apos;t raised any complaints.
            </p>
          ) : (
            <ul className="divide-edge/60 divide-y">
              {list.data.items.map((item) => (
                <ComplaintRow key={item.id} party={party} item={item} />
              ))}
            </ul>
          )
        ) : list.state === "missing" ? (
          <p className="text-muted px-5 py-6 text-sm">
            Complaints open once your {party === "driver" ? "driver profile" : "company account"} is
            set up.
          </p>
        ) : (
          <div className="p-4">
            <Unavailable title="Your complaints couldn't be loaded" retryHref={BASE[party]} />
          </div>
        )}
      </Panel>

      {list.state !== "missing" ? (
        <Panel className="p-5">
          <h2 className="mb-4 text-base font-semibold">Raise a complaint</h2>
          <RaiseComplaintForm
            party={party}
            action={
              party === "driver" ? raiseDriverComplaintAction : raiseAdvertiserComplaintAction
            }
            references={options.state === "ready" ? options.data : null}
          />
        </Panel>
      ) : null}
    </div>
  );
}

/** One complaint's conversation, for the driver or advertiser who owns it. */
export async function ComplaintConversationPage({
  party,
  complaintId,
}: {
  party: ComplaintParty;
  complaintId: string;
}) {
  const api = createApiClient(await getSessionToken());
  const detail = await readComplaintApi(() =>
    party === "driver"
      ? api.GET("/api/v1/driver/complaints/{complaint_id}", {
          params: { path: { complaint_id: complaintId } },
        })
      : api.GET("/api/v1/advertiser/complaints/{complaint_id}", {
          params: { path: { complaint_id: complaintId } },
        }),
  );
  if (detail.state === "auth") redirect("/login");

  const back = (
    <Link href={BASE[party]} className="micro text-amber">
      ← All complaints
    </Link>
  );
  if (detail.state === "missing") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        <EmptyState
          title="Complaint not found"
          body="This complaint doesn't exist or isn't part of your account."
        />
      </div>
    );
  }
  if (detail.state !== "ready") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        <Unavailable
          title="This complaint couldn't be loaded"
          retryHref={`${BASE[party]}/${complaintId}`}
        />
      </div>
    );
  }

  const complaint = detail.data;
  const status = COMPLAINANT_STATUS[complaint.status];
  return (
    <div className="animate-rise mx-auto flex max-w-3xl flex-col gap-4">
      {back}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            {CATEGORY_LABELS[complaint.category]}
          </h1>
          <p className="text-muted mt-1 text-sm">
            {referenceText(complaint.reference_type, complaint.reference_label)} · Raised{" "}
            {formatWat(complaint.created_at)}
          </p>
        </div>
        <StatusChip tone={status.tone}>{status.label}</StatusChip>
      </div>

      <ol className="flex flex-col gap-3" aria-label="Conversation">
        {complaint.messages.map((message, index) => (
          <li key={index}>
            <Panel className={`p-4 ${message.sender === "terrax_media" ? "border-amber/40" : ""}`}>
              <p className="micro text-muted">
                {SENDER_LABELS[message.sender]} · {formatWat(message.sent_at)}
              </p>
              <p className="mt-2 text-sm leading-6 whitespace-pre-line">{message.body}</p>
            </Panel>
          </li>
        ))}
      </ol>

      <Panel className="p-5">
        {complaint.status === "resolved" ? (
          <p className="text-muted mb-3 text-sm">
            Terrax Media marked this as resolved. If you still need help, reply below and it will
            reopen.
          </p>
        ) : null}
        <ComplaintMessageForm
          complaintId={complaint.id}
          action={
            party === "driver" ? followUpDriverComplaintAction : followUpAdvertiserComplaintAction
          }
          label="Add a message"
          placeholder="Add anything Customer Service should know."
          submitLabel="Send message"
        />
      </Panel>
    </div>
  );
}
