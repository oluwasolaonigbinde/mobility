export const metadata = { title: "Support" };
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { ComplaintMessageForm, ComplaintUpdateForm } from "@/components/complaints/forms";
import { replyToComplaintAction, updateComplaintAction } from "@/lib/complaints/actions";
import { CATEGORY_LABELS, STAFF_STATUS, formatWat } from "@/lib/complaints/labels";
import { adminStatus } from "@/lib/status/admin";
import { HubDrawer } from "../hub-drawer";
import { QueueUnavailable } from "../queue-search";
import { OperationForm } from "../operation-form";
import { completePages, worklistHref } from "../worklist-reads";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { RecordPhoneVerification } from "../drivers/record-phone-verification";

type Query = {
  tab?: string;
  status?: string;
  offset?: string;
  user_id?: string;
  organization_id?: string;
  driver_profile_id?: string;
  complaint?: string;
  task?: string;
  history?: string;
  mine?: string;
};
export default async function SupportPage({ searchParams }: { searchParams: Promise<Query> }) {
  const p = await searchParams;
  const tab = p.tab === "contact" ? "contact" : "complaints";
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  const href = (changes: Partial<Query>) => worklistHref("/admin/support", { ...p, tab }, changes);
  const closeHref = href({ complaint: undefined, task: undefined });
  const status =
    p.status === "answered" || p.status === "resolved"
      ? p.status
      : p.status === "all"
        ? undefined
        : "open";
  const complaints =
    tab === "complaints"
      ? await api
          .GET("/api/v1/admin/complaints", {
            params: {
              query: {
                limit: 25,
                offset,
                status,
                user_id: p.user_id,
                organization_id: p.organization_id,
                assigned_to_me: p.mine === "true",
              },
            },
          })
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const contact =
    tab === "contact"
      ? await api
          .GET("/api/v1/admin/manual-driver-contact-tasks", {
            params: {
              query: {
                limit: 25,
                offset,
                driver_profile_id: p.driver_profile_id,
                history: p.history === "true",
              },
            },
          })
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const phoneWork =
    tab === "contact"
      ? await api
          .GET("/api/v1/admin/phone-verification-challenges", {
            params: { query: { driver_profile_id: p.driver_profile_id, limit: 25, offset } },
          })
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  let selectedComplaint;
  let complaintMissing = false;
  if (tab === "complaints" && p.complaint) {
    const selection = await api
      .GET("/api/v1/admin/complaints/{complaint_id}", {
        params: { path: { complaint_id: p.complaint } },
      })
      .then(({ data }) => ({ data, missing: false }))
      .catch((error: unknown) => ({
        data: undefined,
        missing: error instanceof ApiError && error.status === 404,
      }));
    selectedComplaint = selection.data;
    complaintMissing = selection.missing;
    if (
      selectedComplaint &&
      (selectedComplaint.id !== p.complaint ||
        (p.user_id && selectedComplaint.raised_by_user_id !== p.user_id) ||
        (p.organization_id && selectedComplaint.advertiser_organization_id !== p.organization_id))
    ) {
      selectedComplaint = undefined;
      complaintMissing = true;
    }
  }
  const staff = selectedComplaint
    ? await completePages((next) =>
        api.GET("/api/v1/admin/users", {
          params: { query: { role: "admin", status: "active", limit: 100, offset: next } },
        }),
      ).catch(() => undefined)
    : undefined;
  let selectedTask: components["schemas"]["ManualContactTaskRead"] | undefined;
  let taskMissing = false;
  if (tab === "contact" && p.task) {
    const all = await completePages((next) =>
      api.GET("/api/v1/admin/manual-driver-contact-tasks", {
        params: {
          query: {
            limit: 100,
            offset: next,
            driver_profile_id: p.driver_profile_id,
            history: p.history === "true",
          },
        },
      }),
    ).catch(() => undefined);
    selectedTask = all?.find((item) => item.id === p.task);
    taskMissing = !!all && !selectedTask;
    if (
      selectedTask &&
      p.driver_profile_id &&
      selectedTask.driver_profile_id !== p.driver_profile_id
    ) {
      selectedTask = undefined;
      taskMissing = true;
    }
  }
  const taskRow = (task: NonNullable<typeof selectedTask>) => (
    <>
      <p className="font-medium">
        {task.driver_name} · {task.masked_phone}
      </p>
      <p className="text-muted text-sm">
        {adminStatus(task.purpose, "contact_purpose")} · {adminStatus(task.status)} ·{" "}
        {formatWat(task.created_at)}
      </p>
      {task.completed_at ? (
        <p>
          Outcome: {adminStatus(task.completion_outcome)} · {formatWat(task.completed_at)}
        </p>
      ) : null}
    </>
  );
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Support" />
      <nav aria-label="Support lists" className="mb-5 flex flex-wrap gap-3">
        <Link
          className="border-edge rounded-lg border p-2"
          href={href({ tab: "complaints", offset: undefined, task: undefined })}
        >
          Complaints
        </Link>
        <Link
          className="border-edge rounded-lg border p-2"
          href={href({ tab: "contact", offset: undefined, complaint: undefined })}
        >
          Driver contact
        </Link>
      </nav>
      {tab === "complaints" ? (
        <>
          <nav aria-label="Complaint status" className="mb-5 flex flex-wrap gap-3">
            {[
              ["open", "Needs a reply"],
              ["answered", "Waiting on them"],
              ["resolved", "Resolved"],
              ["all", "All"],
            ].map(([value, label]) => (
              <Link
                key={value}
                className="text-cyan underline"
                href={href({ status: value, offset: undefined, complaint: undefined })}
              >
                {label}
              </Link>
            ))}
          </nav>
          {!complaints || complaints.items.some((item) => !item.party_name) ? (
            <QueueUnavailable />
          ) : (
            <>
              {!complaints.items.length ? (
                <p>No complaints match these filters.</p>
              ) : (
                <ul className="grid gap-3">
                  {complaints.items.map((item) => (
                    <li key={item.id}>
                      <Link
                        className="border-edge block rounded-xl border p-4"
                        href={href({ complaint: item.id })}
                      >
                        <p className="font-medium">
                          {item.party_name} · {CATEGORY_LABELS[item.category]}
                        </p>
                        <p className="text-muted text-sm">
                          {STAFF_STATUS[item.status].label} · {formatWat(item.last_message_at)}
                        </p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <Pagination
                total={complaints.total}
                limit={25}
                offset={offset}
                hrefFor={(o) => href({ offset: String(o), complaint: undefined })}
              />
            </>
          )}
        </>
      ) : (
        <>
          <p className="text-muted mb-4 text-sm">
            Contact tasks use the driver&apos;s current consent and verified phone. Completed
            outcomes remain recorded.
          </p>
          <section className="mb-6">
            <h2 className="mb-3 font-medium">Phone verification</h2>
            {!phoneWork ? (
              <QueueUnavailable />
            ) : (
              <>
                {!phoneWork.items.length ? (
                  <p>No phone verifications are waiting.</p>
                ) : (
                  phoneWork.items.map((item) => (
                    <div className="border-edge mb-3 rounded-lg border p-4" key={item.id}>
                      <Link
                        className="text-cyan underline"
                        href={`/admin/drivers/${item.driver_profile_id}#phone`}
                      >
                        {item.driver_name ?? "Driver"}
                      </Link>
                      <p className="mt-2 text-sm">{item.masked_phone}</p>
                      <RecordPhoneVerification
                        driverId={item.driver_profile_id}
                        challengeId={item.id}
                      />
                    </div>
                  ))
                )}
                <Pagination
                  total={phoneWork.total}
                  limit={25}
                  offset={offset}
                  hrefFor={(o) => href({ offset: String(o), task: undefined })}
                />
              </>
            )}
          </section>
          <Link
            className="text-cyan mb-4 inline-block underline"
            href={href({
              history: p.history === "true" ? undefined : "true",
              offset: undefined,
              task: undefined,
            })}
          >
            {p.history === "true" ? "Current work" : "Include recorded history"}
          </Link>
          {!contact || contact.items.some((task) => !task.driver_name) ? (
            <QueueUnavailable />
          ) : (
            <>
              {!contact.items.length ? (
                <p>No contact tasks match these filters.</p>
              ) : (
                <ul className="grid gap-3">
                  {contact.items.map((task) => (
                    <li key={task.id}>
                      <Link
                        className="border-edge block rounded-xl border p-4"
                        href={href({ task: task.id })}
                      >
                        {taskRow(task)}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <Pagination
                total={contact.total}
                limit={25}
                offset={offset}
                hrefFor={(o) => href({ offset: String(o), task: undefined })}
              />
            </>
          )}
        </>
      )}
      {tab === "complaints" && p.complaint ? (
        <HubDrawer title="Complaint" closeHref={closeHref}>
          {!selectedComplaint ? (
            complaintMissing ? (
              <p>Complaint not found for these filters.</p>
            ) : (
              <QueueUnavailable />
            )
          ) : (
            <>
              <h3 className="font-medium">
                {selectedComplaint.party_name} · {CATEGORY_LABELS[selectedComplaint.category]}
              </h3>
              <p className="text-muted mb-4 text-sm">
                {STAFF_STATUS[selectedComplaint.status].label}
              </p>
              <ol aria-label="Conversation" className="mb-5 grid gap-3">
                {selectedComplaint.messages.map((message) => (
                  <li key={message.id} className="border-edge rounded-lg border p-3">
                    <p className="text-muted text-sm">
                      {message.author_name} · {formatWat(message.sent_at)}
                    </p>
                    <p className="mt-2 whitespace-pre-line">{message.body}</p>
                  </li>
                ))}
              </ol>
              <ComplaintMessageForm
                complaintId={selectedComplaint.id}
                action={replyToComplaintAction}
                label="Reply as Terrax Media"
                placeholder="Write your reply"
                submitLabel="Send reply"
                allowResolve
              />
              {!staff ? (
                <QueueUnavailable />
              ) : (
                <ComplaintUpdateForm
                  complaintId={selectedComplaint.id}
                  action={updateComplaintAction}
                  staff={staff.map((person) => ({ id: person.id, label: person.full_name }))}
                />
              )}
            </>
          )}
        </HubDrawer>
      ) : null}
      {tab === "contact" && p.task ? (
        <HubDrawer title="Driver contact" closeHref={closeHref}>
          {!selectedTask ? (
            taskMissing ? (
              <p>Contact task not found for these filters.</p>
            ) : (
              <QueueUnavailable />
            )
          ) : !selectedTask.driver_name ? (
            <QueueUnavailable />
          ) : (
            <>
              {taskRow(selectedTask)}
              {!selectedTask.completed_at &&
              p.history !== "true" &&
              selectedTask.status === "open" ? (
                <OperationForm id={selectedTask.id} contact />
              ) : (
                <p className="text-muted mt-4">Recorded history.</p>
              )}
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
