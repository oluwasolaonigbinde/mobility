import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "../queue-search";
import { OperationForm } from "../operation-form";
export default async function ContactQueue({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; history?: string }>;
}) {
  const p = await searchParams;
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const history = p.history === "true";
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/manual-driver-contact-tasks", {
      params: { query: { limit: 25, offset, history } },
    })
    .catch(() => ({ data: undefined }));
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Driver contact"
        eyebrow={
          history ? "Recorded task history" : "Current authorized work and completed outcomes"
        }
      />
      <p className="text-muted mb-5">
        Operations-run contact requires the verified phone and consent for the exact task purpose. A
        withdrawn or changed consent removes unfinished work from this queue; its history remains
        recorded. No automated message is sent here.
      </p>
      <form className="mb-5">
        <label>
          <input type="checkbox" name="history" value="true" defaultChecked={history} /> Include
          blocked history (read only)
        </label>
        <button className="text-cyan ml-4">Apply</button>
      </form>
      {!data ? (
        <QueueUnavailable />
      ) : !data.items.length ? (
        <p>No contact tasks match this view.</p>
      ) : (
        <div className="grid gap-4">
          {data.items.map((t) => (
            <section key={t.id} className="border-edge rounded-xl border p-4">
              <h2 className="font-medium">
                {t.driver_name ?? "Driver name unavailable"} · {t.masked_phone}
              </h2>
              <p>
                {t.purpose.replaceAll("_", " ")} · {t.status} · {formatDate(t.created_at)}
              </p>
              {t.completed_at ? (
                <p>
                  Outcome: {t.completion_outcome} · {formatDate(t.completed_at)}
                </p>
              ) : history ? (
                <p className="text-muted">
                  Historical record. Return to current work to confirm whether this task is
                  actionable.
                </p>
              ) : (
                <OperationForm id={t.id} contact />
              )}
            </section>
          ))}
        </div>
      )}
      {data ? (
        <Pagination
          total={data.total}
          limit={25}
          offset={offset}
          hrefFor={(o) => `/admin/contact?history=${history}&offset=${o}`}
        />
      ) : null}
    </div>
  );
}
