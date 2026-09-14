"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { DriverDataUnavailable } from "./data-unavailable";

export function FreshDriverAuthority({
  children,
  refreshKey,
  title,
  detail,
  retryHref,
}: {
  children: ReactNode;
  refreshKey: string;
  title: string;
  detail: string;
  retryHref: string;
}) {
  const router = useRouter();
  const [hasFreshNetworkAuthority, setHasFreshNetworkAuthority] = useState(true);
  const stale = useRef(false);
  const acceptedRefreshKey = useRef(refreshKey);

  useEffect(() => {
    const markStale = () => {
      stale.current = true;
      setHasFreshNetworkAuthority(false);
    };
    const requestFreshAuthority = () => {
      if (stale.current) router.refresh();
    };
    window.addEventListener("offline", markStale);
    window.addEventListener("online", requestFreshAuthority);
    if (!navigator.onLine) markStale();
    return () => {
      window.removeEventListener("offline", markStale);
      window.removeEventListener("online", requestFreshAuthority);
    };
  }, [router]);

  useEffect(() => {
    if (stale.current && navigator.onLine && acceptedRefreshKey.current !== refreshKey) {
      acceptedRefreshKey.current = refreshKey;
      stale.current = false;
      setHasFreshNetworkAuthority(true);
    }
  }, [refreshKey]);

  if (!hasFreshNetworkAuthority) {
    return <DriverDataUnavailable title={title} detail={detail} retryHref={retryHref} />;
  }
  return children;
}
