import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Pagination } from "@/components/ui/pagination";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { ViewTabs } from "@/components/ui/tabs";
import { createFeedbackReviewApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { formatDateTime } from "@/lib/format";
import { setFeedbackStatusAction } from "./actions";
import { feedbackTitle, portalLabel, safePagePath } from "./page-label";
import { getReviewToken } from "./review-cookie";
import { UnlockForm } from "./unlock-form";

export const metadata: Metadata = { title: "Feedback", robots: { index: false, follow: false } };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 10;
type FeedbackItem = components["schemas"]["FeedbackItemRead"];
type FeedbackList = components["schemas"]["FeedbackList"];
type Status = "opened" | "resolved";
type Load =
  | { kind: "list"; data: FeedbackList }
  | { kind: "gate"; expired?: boolean }
  | { kind: "off" }
  | { kind: "error" };

async function load(status: Status, offset: number): Promise<Load> {
  const token = await getReviewToken();
  try {
    // Without a token this still asks the API, so a switched-off site says so up front.
    const { data } = await createFeedbackReviewApiClient(token ?? "").GET(
      "/api/v1/feedback/review",
      {
        params: { query: { status, limit: PAGE_SIZE, offset } },
      },
    );
    return data ? { kind: "list", data } : { kind: "error" };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) return { kind: "off" };
      if (error.status === 401) return { kind: "gate", expired: Boolean(token) };
    }
    return { kind: "error" };
  }
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="bg-raised flex flex-1 justify-center px-4 py-8 sm:py-12">
      <div className="w-full max-w-3xl">{children}</div>
    </main>
  );
}

export default async function FeedbackPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string | string[]; page?: string | string[] }>;
}) {
  const query = await searchParams;
  const status: Status = query.status === "resolved" ? "resolved" : "opened";
  const page = Math.max(1, Math.floor(Number(query.page)) || 1);
  const result = await load(status, (page - 1) * PAGE_SIZE);

  if (result.kind === "off" || result.kind === "gate") {
    return (
      <Shell>
        <div className="mx-auto max-w-sm">
          <h1 className="font-display text-3xl font-semibold tracking-tight">Feedback access</h1>
          {result.kind === "off" ? (
            <p className="text-muted mt-3 text-sm">
              Feedback isn&apos;t switched on for this site.
            </p>
          ) : (
            <>
              <p className="text-muted mt-3 mb-6 text-sm">
                {result.expired
                  ? "Your access has ended. Enter the password again."
                  : "Enter the project feedback password to view feedback."}
              </p>
              <Panel className="p-6">
                <UnlockForm />
              </Panel>
            </>
          )}
        </div>
      </Shell>
    );
  }

  if (result.kind === "error") {
    return (
      <Shell>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Feedback</h1>
        <Panel className="mt-6 p-6">
          <p role="alert" className="text-sm">
            Feedback can&apos;t be loaded right now. Refresh the page to try again.
          </p>
        </Panel>
      </Shell>
    );
  }

  const { data } = result;
  const hrefFor = (nextStatus: Status, nextPage = 1) =>
    `/feedback?status=${nextStatus}${nextPage > 1 ? `&page=${nextPage}` : ""}`;
  return (
    <Shell>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight">Feedback</h1>
        <a
          href="/api/feedback/export"
          className="border-edge text-ink hover:border-edge-strong inline-flex h-10 items-center rounded-lg border bg-white px-4 text-sm"
        >
          Export CSV
        </a>
      </div>
      <ViewTabs
        label="Feedback status"
        items={[
          {
            href: hrefFor("opened"),
            label: "Opened",
            active: status === "opened",
            count: data.counts.opened,
          },
          {
            href: hrefFor("resolved"),
            label: "Resolved",
            active: status === "resolved",
            count: data.counts.resolved,
          },
        ]}
      />
      {data.items.length === 0 ? (
        <Panel className="p-6">
          <p className="text-muted text-sm">
            {status === "opened" ? "No open feedback." : "No resolved feedback yet."}
          </p>
        </Panel>
      ) : (
        <ul className="grid gap-4">
          {data.items.map((item) => (
            <li key={item.id}>
              <FeedbackCard item={item} />
            </li>
          ))}
        </ul>
      )}
      <Pagination
        total={data.total}
        limit={PAGE_SIZE}
        offset={data.offset}
        hrefFor={(offset) => hrefFor(status, Math.floor(offset / PAGE_SIZE) + 1)}
      />
    </Shell>
  );
}

function FeedbackCard({ item }: { item: FeedbackItem }) {
  const path = safePagePath(item.page_path);
  const resolved = item.status === "resolved";
  const pinned = item.pin_x !== null && item.pin_y !== null;
  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="min-w-0 font-semibold break-words">{feedbackTitle(item.message)}</h2>
        <StatusChip tone={resolved ? "green" : "amber"}>
          {resolved ? "Resolved" : "Opened"}
        </StatusChip>
      </div>
      <p className="text-muted mt-1 text-sm break-words">
        {item.name} · {formatDateTime(item.created_at)} · {portalLabel(item.portal)}{" "}
        {path ? (
          <Link href={path} className="text-amber underline">
            {path}
          </Link>
        ) : (
          <span>{item.page_path}</span>
        )}
      </p>
      <p className="mt-3 text-sm break-words whitespace-pre-wrap">{item.message}</p>
      {item.has_screenshot ? (
        <div className="border-edge relative mt-4 overflow-hidden rounded-lg border">
          {/* eslint-disable-next-line @next/next/no-img-element -- private, token-checked image */}
          <img
            src={`/api/feedback/${item.id}/screenshot`}
            alt={`Screenshot of ${path ?? "the page"}`}
            width={item.screenshot_width ?? undefined}
            height={item.screenshot_height ?? undefined}
            loading="lazy"
            className="block h-auto w-full"
          />
          {pinned ? (
            <span
              aria-hidden="true"
              className="bg-coral absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
              style={{ left: `${Number(item.pin_x) * 100}%`, top: `${Number(item.pin_y) * 100}%` }}
            />
          ) : null}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        {path ? (
          <Link
            href={path}
            target="_blank"
            rel="noreferrer"
            className="border-edge text-ink hover:border-edge-strong inline-flex h-10 items-center rounded-lg border px-4 text-sm"
          >
            Open page
          </Link>
        ) : null}
        <form action={setFeedbackStatusAction}>
          <input type="hidden" name="id" value={item.id} />
          <input type="hidden" name="status" value={resolved ? "opened" : "resolved"} />
          <Button type="submit" variant={resolved ? "ghost" : "primary"} className="h-10 px-4">
            {resolved ? "Reopen" : "Mark resolved"}
          </Button>
        </form>
      </div>
    </Panel>
  );
}
