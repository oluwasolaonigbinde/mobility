"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { components } from "@/lib/api/schema";
import { formatDateTime } from "@/lib/format";

type NotificationList = components["schemas"]["NotificationFeedListRead"];
type NotificationItem = components["schemas"]["NotificationFeedItemRead"];
type UnreadCount = components["schemas"]["NotificationUnreadCountRead"];
type Preferences = components["schemas"]["AdvertiserNotificationPreferenceRead"];

class NotificationRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "NotificationRequestError";
  }
}

const PAGE_SIZE = 20;

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  // Only a request with a JSON body declares one; the BFF boundary refuses a media
  // type on bodyless commands such as mark-read.
  const response = await fetch(path, {
    ...init,
    ...(init?.body !== undefined ? { headers: { "content-type": "application/json" } } : {}),
  });
  const body = (await response.json()) as T | { error?: { message?: string } };
  if (!response.ok) {
    throw new NotificationRequestError(
      response.status,
      typeof body === "object" && body !== null && "error" in body
        ? (body.error?.message ?? "Notification request failed")
        : "Notification request failed",
    );
  }
  return body as T;
}

function mutationErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function useDocumentVisible() {
  return useSyncExternalStore(
    (onChange) => {
      document.addEventListener("visibilitychange", onChange);
      return () => document.removeEventListener("visibilitychange", onChange);
    },
    () => document.visibilityState === "visible",
    () => true,
  );
}

function useNetworkOnline() {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener("online", onChange);
      window.addEventListener("offline", onChange);
      return () => {
        window.removeEventListener("online", onChange);
        window.removeEventListener("offline", onChange);
      };
    },
    () => navigator.onLine,
    () => true,
  );
}

function NotificationItemRow({
  notification,
  onRead,
  onOpen,
}: {
  notification: NotificationItem;
  onRead: (id: string) => void;
  onOpen: () => void;
}) {
  return (
    <li className="border-edge border-b py-3 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{notification.title}</p>
          <p className="text-muted mt-1 text-sm">{notification.body}</p>
          {notification.action_url ? (
            <Link
              href={notification.action_url}
              onClick={onOpen}
              aria-label={`Open ${notification.campaign_name ?? "campaign"}`}
              className="micro text-amber mt-2 inline-block underline underline-offset-2"
            >
              Open
            </Link>
          ) : null}
          <p className="text-faint mt-1.5 text-xs">{formatDateTime(notification.created_at)}</p>
        </div>
        {notification.read_at ? null : (
          <button
            type="button"
            onClick={() => onRead(notification.id)}
            className="micro text-amber hover:text-amber/80 shrink-0"
          >
            Mark read
          </button>
        )}
      </div>
    </li>
  );
}

export function NotificationCenter({
  canManageAdvertiserPreferences = false,
  sessionScope = "anonymous",
}: {
  canManageAdvertiserPreferences?: boolean;
  sessionScope?: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const isVisible = useDocumentVisible();
  const isOnline = useNetworkOnline();
  const countKey = ["notifications", sessionScope, "unread-count"] as const;
  const listKey = ["notifications", sessionScope, "list"] as const;
  const preferenceKey = ["notifications", sessionScope, "preferences"] as const;
  const scopeKey = useMemo(() => ["notifications", sessionScope] as const, [sessionScope]);
  async function scopedApiJson<T>(path: string, init?: RequestInit): Promise<T> {
    try {
      return await apiJson<T>(path, init);
    } catch (error) {
      if (error instanceof NotificationRequestError && [401, 403].includes(error.status)) {
        router.replace("/login");
        router.refresh();
        queryClient.removeQueries({ queryKey: scopeKey });
      }
      throw error;
    }
  }
  const count = useQuery({
    queryKey: countKey,
    queryFn: () => scopedApiJson<UnreadCount>("/api/notifications/unread-count"),
    enabled: isVisible && isOnline,
    refetchInterval: isVisible && isOnline ? 45_000 : false,
    refetchIntervalInBackground: false,
    retry: (failureCount, error) =>
      !(error instanceof NotificationRequestError && [401, 403].includes(error.status)) &&
      failureCount < 1,
  });
  const notifications = useInfiniteQuery({
    queryKey: listKey,
    queryFn: ({ pageParam }) =>
      scopedApiJson<NotificationList>(`/api/notifications?limit=${PAGE_SIZE}&offset=${pageParam}`),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + last.items.length;
      return last.items.length > 0 && next < last.total ? next : undefined;
    },
    enabled: open && isOnline,
    retry: (failureCount, error) =>
      !(error instanceof NotificationRequestError && [401, 403].includes(error.status)) &&
      failureCount < 1,
  });
  const preferences = useQuery({
    queryKey: preferenceKey,
    queryFn: () => scopedApiJson<Preferences>("/api/advertiser/notification-preferences"),
    enabled: open && canManageAdvertiserPreferences && isOnline,
    retry: (failureCount, error) =>
      !(error instanceof NotificationRequestError && [401, 403].includes(error.status)) &&
      failureCount < 1,
  });
  const invalidateNotifications = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: countKey }),
      queryClient.invalidateQueries({ queryKey: listKey }),
    ]);
  const markRead = useMutation({
    mutationFn: (id: string) =>
      scopedApiJson<NotificationItem>(`/api/notifications/${id}/read`, { method: "POST" }),
    onSuccess: invalidateNotifications,
  });
  const markAllRead = useMutation({
    mutationFn: () => scopedApiJson<UnreadCount>("/api/notifications/read-all", { method: "POST" }),
    onSuccess: invalidateNotifications,
  });
  const updatePreferences = useMutation({
    mutationFn: (transactional_email_enabled: boolean) =>
      scopedApiJson<Preferences>("/api/advertiser/notification-preferences", {
        method: "PATCH",
        body: JSON.stringify({ transactional_email_enabled }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: preferenceKey }),
  });
  useEffect(() => {
    if (isOnline) return;
    void queryClient.cancelQueries({ queryKey: scopeKey });
    queryClient.removeQueries({ queryKey: scopeKey });
  }, [isOnline, queryClient, scopeKey]);
  useEffect(
    () => () => {
      queryClient.removeQueries({ queryKey: scopeKey });
    },
    [queryClient, scopeKey],
  );
  // Cached data stays visible during a background refetch so the badge and list
  // do not flicker on every poll; errors and offline still hide it (and offline
  // purges the cache above).
  const unread = isOnline && !count.isError ? (count.data?.unread_count ?? 0) : 0;
  const loadedPages = isOnline && !notifications.isError ? notifications.data?.pages : undefined;
  // Newer notices can shift offsets between pages; show each notice once.
  const shownItems = loadedPages
    ? [
        ...new Map(
          loadedPages
            .flatMap((page) => page.items)
            .filter((item) => !item.read_at)
            .map((item) => [item.id, item]),
        ).values(),
      ]
    : undefined;
  const totalNotifications = loadedPages?.at(-1)?.total ?? 0;
  const showPreferences: Preferences | undefined =
    isOnline && !preferences.isError ? preferences.data : undefined;

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="notification-centre"
        className="micro text-muted hover:text-fg relative rounded px-2 py-1 transition-colors"
      >
        Notifications
        {unread > 0 ? (
          <span className="bg-amber text-bg ml-1.5 inline-flex min-w-4 justify-center rounded-full px-1 text-[10px] font-bold">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <section
          id="notification-centre"
          aria-label="Notifications"
          className="border-edge bg-panel fixed top-14 right-4 z-50 w-[min(24rem,calc(100vw-2rem))] rounded-lg border p-4 font-sans tracking-normal normal-case shadow-xl sm:absolute sm:top-full sm:right-0 sm:mt-2"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="micro text-base font-semibold">Notifications</p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => markAllRead.mutate()}
                disabled={!isOnline || unread === 0 || markAllRead.isPending}
                className="micro text-amber disabled:text-faint hover:text-amber/80"
              >
                Mark all read
              </button>
              <button
                type="button"
                aria-label="Close notification panel"
                onClick={() => {
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className="text-muted hover:text-fg flex size-8 shrink-0 items-center justify-center rounded text-xl"
              >
                <span aria-hidden="true">×</span>
              </button>
            </div>
          </div>
          {markRead.isError ? (
            <div
              role="alert"
              aria-live="polite"
              className="border-coral/40 bg-coral/10 text-coral mt-3 flex items-center justify-between gap-3 rounded border px-3 py-2 text-sm"
            >
              <span>
                {mutationErrorMessage(markRead.error, "Could not mark the notification as read.")}
              </span>
              <button
                type="button"
                disabled={!isOnline}
                className="shrink-0 underline underline-offset-2"
                onClick={() => {
                  if (markRead.variables) markRead.mutate(markRead.variables);
                }}
              >
                Retry
              </button>
            </div>
          ) : null}
          {markAllRead.isError ? (
            <div
              role="alert"
              aria-live="polite"
              className="border-coral/40 bg-coral/10 text-coral mt-3 flex items-center justify-between gap-3 rounded border px-3 py-2 text-sm"
            >
              <span>
                {mutationErrorMessage(markAllRead.error, "Could not mark notifications as read.")}
              </span>
              <button
                type="button"
                disabled={!isOnline}
                className="shrink-0 underline underline-offset-2"
                onClick={() => markAllRead.mutate()}
              >
                Retry
              </button>
            </div>
          ) : null}
          {notifications.isLoading ? (
            <p className="text-muted py-6 text-sm">Loading notifications…</p>
          ) : null}
          {notifications.isError ? (
            <p className="text-coral py-6 text-sm">Could not load notifications.</p>
          ) : null}
          {!isOnline ? (
            <p role="alert" className="text-amber py-6 text-sm">
              Reconnect to load current notifications. Saved notification data is not shown as
              current while offline.
            </p>
          ) : null}
          {shownItems?.length === 0 ? (
            <p className="text-muted py-6 text-sm">You are all caught up.</p>
          ) : null}
          {shownItems?.length ? (
            <>
              <ul className="mt-2 max-h-96 overflow-y-auto">
                {shownItems.map((notification) => (
                  <NotificationItemRow
                    key={notification.id}
                    notification={notification}
                    onRead={(id) => markRead.mutate(id)}
                    onOpen={() => setOpen(false)}
                  />
                ))}
              </ul>
              <div className="border-edge mt-2 flex items-center justify-between gap-3 border-t pt-2">
                <p className="micro text-faint">
                  Showing {shownItems.length} of {totalNotifications}
                  {notifications.hasNextPage ? " · Mark all read includes older ones" : ""}
                </p>
                {notifications.hasNextPage ? (
                  <button
                    type="button"
                    onClick={() => void notifications.fetchNextPage()}
                    disabled={!isOnline || notifications.isFetchingNextPage}
                    className="micro text-amber disabled:text-faint hover:text-amber/80 shrink-0"
                  >
                    {notifications.isFetchingNextPage ? "Loading…" : "Show older"}
                  </button>
                ) : null}
              </div>
            </>
          ) : null}
          {canManageAdvertiserPreferences ? (
            <div className="border-edge mt-3 border-t pt-3">
              <p className="micro text-faint mb-2">Company notification settings</p>
              <p className="text-muted text-sm">Updates always appear here.</p>
              <label className="mt-3 flex items-center justify-between gap-3 text-sm">
                Also send updates by email
                <input
                  type="checkbox"
                  checked={showPreferences?.transactional_email_enabled ?? false}
                  disabled={
                    !isOnline ||
                    preferences.isFetching ||
                    preferences.isError ||
                    updatePreferences.isPending
                  }
                  aria-describedby={
                    updatePreferences.isError ? "notification-preference-error" : undefined
                  }
                  onChange={(event) => updatePreferences.mutate(event.target.checked)}
                />
              </label>
              <p className="text-muted mt-2 text-sm">
                Account and campaign updates. Applies to your whole company.
              </p>
              {updatePreferences.isError ? (
                <div
                  id="notification-preference-error"
                  role="alert"
                  aria-live="polite"
                  className="border-coral/40 bg-coral/10 text-coral mt-2 flex items-center justify-between gap-3 rounded border px-3 py-2 text-sm"
                >
                  <span>
                    {mutationErrorMessage(
                      updatePreferences.error,
                      "Could not save email preferences.",
                    )}
                  </span>
                  <button
                    type="button"
                    disabled={!isOnline}
                    className="shrink-0 underline underline-offset-2"
                    onClick={() => {
                      if (typeof updatePreferences.variables === "boolean") {
                        updatePreferences.mutate(updatePreferences.variables);
                      }
                    }}
                  >
                    Retry
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
