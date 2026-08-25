"use client";

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker
        .register("/driver-sw.js", { scope: "/driver", updateViaCache: "none" })
        .then((registration) => {
          window.dispatchEvent(
            new CustomEvent("cardvert-driver-service-worker", {
              detail: { status: "registered", updating: Boolean(registration.installing) },
            }),
          );
          void registration.update();
        })
        .catch(() => {
          window.dispatchEvent(
            new CustomEvent("cardvert-driver-service-worker", {
              detail: { status: "failed", updating: false },
            }),
          );
        });
    }
  }, []);
  return null;
}
