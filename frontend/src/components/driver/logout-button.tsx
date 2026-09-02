"use client";

import { useEffect, useState, useTransition } from "react";
import { signOutAction, type SignOutResult } from "@/lib/auth/actions";

export const DRIVER_SESSION_CHANNEL = "cardvert-driver-session";
const SESSION_TAB_ID = `${Date.now()}-${Math.random()}`;

export function notifyDriverLogout(): void {
  window.dispatchEvent(new Event("cardvert-driver-logout"));
  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(DRIVER_SESSION_CHANNEL);
    channel.postMessage({ type: "logout", sender: SESSION_TAB_ID });
    channel.close();
  }
}

export function handleRemoteSessionLogout(
  navigate: (path: string) => void = (path) => window.location.assign(path),
): void {
  window.dispatchEvent(new Event("cardvert-driver-logout"));
  navigate("/login");
}

export function handleSessionLogoutMessage(
  message: { type?: string; sender?: string },
  currentTabId: string,
  navigate?: (path: string) => void,
): boolean {
  if (message.type !== "logout" || message.sender === currentTabId) return false;
  handleRemoteSessionLogout(navigate);
  return true;
}

export async function runSignOutFlow(
  action: () => Promise<SignOutResult> = signOutAction,
  navigate: (path: string) => void = (path) => window.location.assign(path),
): Promise<string | undefined> {
  try {
    const result = await action();
    if (result.globalRevocationFailed) {
      return "Sign-out on every device could not be confirmed. Please try again.";
    }
    if (result.globalRevocationConfirmed) notifyDriverLogout();
    navigate("/login");
    return undefined;
  } catch {
    return "Sign-out on every device could not be confirmed. Please try again.";
  }
}

export function SessionLogoutButton({
  label,
  className,
  formClassName,
}: {
  label: string;
  className?: string;
  formClassName?: string;
}) {
  const [error, setError] = useState<string>();
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    if (!("BroadcastChannel" in window)) return;
    const channel = new BroadcastChannel(DRIVER_SESSION_CHANNEL);
    channel.onmessage = (event) => {
      handleSessionLogoutMessage(event.data as { type?: string; sender?: string }, SESSION_TAB_ID);
    };
    return () => channel.close();
  }, []);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        setError(undefined);
        startTransition(async () => setError(await runSignOutFlow()));
      }}
      className={formClassName}
    >
      <button type="submit" className={className} disabled={pending}>
        {label}
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </form>
  );
}

export function DriverLogoutButton() {
  return (
    <SessionLogoutButton
      label="Exit"
      className="micro text-faint hover:text-coral transition-colors"
    />
  );
}
