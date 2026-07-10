import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { TripTracker } from "./trip-tracker";

export const metadata: Metadata = { title: "Track" };

export default async function DriverTrackPage() {
  const api = createApiClient(await getSessionToken());

  const [active, current] = await Promise.all([
    api.GET("/api/v1/driver/campaign-assignments/active").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/trips/current").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
  ]);

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Trip tracking</h1>
      <TripTracker
        assignment={active.data?.assignment ?? null}
        initialTrip={current.data?.trip ?? null}
      />
    </div>
  );
}
