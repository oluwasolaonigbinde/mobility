"use client";

import { useCallback, useRef, useSyncExternalStore, type ReactNode } from "react";
import { DriverDataUnavailable } from "./data-unavailable";

function useFreshNetworkAuthority() {
  const stale = useRef(false);
  const subscribe = useCallback((onChange: () => void) => {
    const markStale = () => {
      stale.current = true;
      onChange();
    };
    window.addEventListener("offline", markStale);
    window.addEventListener("online", onChange);
    if (!navigator.onLine) stale.current = true;
    return () => {
      window.removeEventListener("offline", markStale);
      window.removeEventListener("online", onChange);
    };
  }, []);
  const getSnapshot = useCallback(() => navigator.onLine && !stale.current, []);
  return useSyncExternalStore(subscribe, getSnapshot, () => true);
}

/** Hide server-rendered driver authority as soon as the browser loses the network. */
export function FreshDriverAuthority({
  children,
  title,
  detail,
  retryHref,
}: {
  children: ReactNode;
  title: string;
  detail: string;
  retryHref: string;
}) {
  const hasFreshNetworkAuthority = useFreshNetworkAuthority();

  if (!hasFreshNetworkAuthority) {
    return <DriverDataUnavailable title={title} detail={detail} retryHref={retryHref} />;
  }
  return children;
}
