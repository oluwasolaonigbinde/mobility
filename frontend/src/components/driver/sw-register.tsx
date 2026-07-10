"use client";

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/driver-sw.js", { scope: "/driver" }).catch(() => {
        // Registration failure degrades to a normal web page — never block the app.
      });
    }
  }, []);
  return null;
}
