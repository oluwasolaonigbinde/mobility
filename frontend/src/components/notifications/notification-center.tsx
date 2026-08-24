"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useSyncExternalStore } from "react";
import type { components } from "@/lib/api/schema";
import { formatDateTime } from "@/lib/format";

type NotificationList = components["schemas"]["NotificationFeedListRead"];
type NotificationItem = components["schemas"]["NotificationFeedItemRead"];
type UnreadCount = components["schemas"]["NotificationUnreadCountRead"];
type Preferences = components["schemas"]["AdvertiserNotificationPreferenceRead"];

const countKey = ["notifications", "unread-count"] as const;
const listKey = ["notifications", "list"] as const;
const preferenceKey = ["notifications", "preferences"] as const;

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "content-type": "application/json" } });
  const body = (await response.json()) as T | { error?: { message?: string } };
  if (!response.ok) {
    throw new Error(
      typeof body === "object" && body !== null && "error" in body
        ? (body.error?.message ?? "Notification request failed")
        : "Notification request failed",
    );
  }
  return body as T;
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
}: {
  canManageAdvertiserPreferences?: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const isVisible = useDocumentVisible();
  const count = useQuery({
    queryKey: countKey,
    queryFn: () => apiJson<UnreadCount>("/api/notifications/unread-count"),
    enabled: isVisible,
    refetchInterval: isVisible ? 45_000 : false,
    refetchIntervalInBackground: false,
  });
  const notifications = useQuery({
    queryKey: listKey,
    queryFn: () => apiJson<NotificationList>("/api/notifications"),
    enabled: open,
  });
  const preferences = useQuery({
    queryKey: preferenceKey,
    queryFn: () => apiJson<Preferences>("/api/advertiser/notification-preferences"),
    enabled: open && canManageAdvertiserPreferences,
  });
  const invalidateNotifications = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: countKey }),
      queryClient.invalidateQueries({ queryKey: listKey }),
    ]);
  const markRead = useMutation({
    mutationFn: (id: string) =>
      apiJson<NotificationItem>(`/api/notifications/${id}/read`, { method: "POST" }),
    onSuccess: invalidateNotifications,
  });
  const markAllRead = useMutation({
    mutationFn: () => apiJson<UnreadCount>("/api/notifications/read-all", { method: "POST" }),
    onSuccess: invalidateNotifications,
  });
  const updatePreferences = useMutation({
    mutationFn: (transactional_email_enabled: boolean) =>
      apiJson<Preferences>("/api/advertiser/notification-preferences", {
        method: "PATCH",
        body: JSON.stringify({ transactional_email_enabled }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: preferenceKey }),
  });
  const unread = count.data?.unread_count ?? 0;

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
              disabled={unread === 0 || markAllRead.isPending}
              className="micro text-amber disabled:text-faint hover:text-amber/80"
            >
              Mark all read
            </button>
          </div>
          {notifications.isLoading ? (
            <p className="text-muted py-6 text-sm">Loading notifications…</p>
          ) : null}
          {notifications.isError ? (
            <p className="text-coral py-6 text-sm">Could not load notifications.</p>
          ) : null}
          {notifications.data?.items.length === 0 ? (
            <p className="text-muted py-6 text-sm">You are all caught up.</p>
          ) : null}
          {notifications.data?.items.length ? (
            <ul className="mt-2 max-h-96 overflow-y-auto">
              {notifications.data.items.map((notification) => (
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
                  checked={preferences.data?.transactional_email_enabled ?? true}
                  disabled={preferences.isLoading || updatePreferences.isPending}
                  onChange={(event) => updatePreferences.mutate(event.target.checked)}
                />
              </label>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
