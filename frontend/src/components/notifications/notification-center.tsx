"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
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

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "content-type": "application/json" } });
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
}: {
  notification: NotificationItem;
  onRead: (id: string) => void;
}) {
  return (
    <li className="border-edge border-b py-3 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{notification.title}</p>
          <p className="text-muted mt-1 text-sm">{notification.body}</p>
          <p className="micro text-faint mt-1.5">{formatDateTime(notification.created_at)}</p>
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
  const notifications = useQuery({
    queryKey: listKey,
    queryFn: () => scopedApiJson<NotificationList>("/api/notifications"),
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
  const unread =
    isOnline && !count.isError && !count.isFetching ? (count.data?.unread_count ?? 0) : 0;
  const showNotifications: NotificationList | undefined =
    isOnline && !notifications.isError && !notifications.isFetching
      ? notifications.data
      : undefined;
  const showPreferences: Preferences | undefined =
    isOnline && !preferences.isError && !preferences.isFetching ? preferences.data : undefined;

  return (
    <div className="relative">
      <button
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
          className="border-edge bg-panel absolute top-full right-0 z-50 mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-lg border p-4 shadow-xl"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="font-display text-base font-semibold">Notifications</p>
            <button
              type="button"
              onClick={() => markAllRead.mutate()}
              disabled={!isOnline || unread === 0 || markAllRead.isPending}
              className="micro text-amber disabled:text-faint hover:text-amber/80"
            >
              Mark all read
            </button>
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
          {showNotifications?.items?.length === 0 ? (
            <p className="text-muted py-6 text-sm">You are all caught up.</p>
          ) : null}
          {showNotifications?.items?.length ? (
            <ul className="mt-2 max-h-96 overflow-y-auto">
              {showNotifications.items.map((notification) => (
                <NotificationItemRow
                  key={notification.id}
                  notification={notification}
                  onRead={(id) => markRead.mutate(id)}
                />
              ))}
            </ul>
          ) : null}
          {canManageAdvertiserPreferences ? (
            <div className="border-edge mt-3 border-t pt-3">
              <p className="micro text-faint mb-2">ORGANIZATION DELIVERY PREFERENCES</p>
              <p className="text-muted text-sm">In-app notifications are always on.</p>
              <label className="mt-3 flex items-center justify-between gap-3 text-sm">
                Transactional email
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
