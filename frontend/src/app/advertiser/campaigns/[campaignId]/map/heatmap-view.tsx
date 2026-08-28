"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  activeMapStyle,
  applyThemeMapTint,
  basemapMode,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
} from "@/lib/map/config";
import { geometryBounds, type ZoneGeometry } from "@/lib/zones/geometry";
import { Panel } from "@/components/ui/panel";

export type GovernedZoneGeometry = {
  rank: number;
  name: string;
  geometry: Record<string, unknown>;
};

const ZONES_SOURCE = "governed-ranked-zones";
export const MAP_READY_TIMEOUT_MS = 3_000;

export function GovernedZoneMap({ zones }: { zones: GovernedZoneGeometry[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("Preparing the governed zone map…");

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let failed = false;
    const timeout: { id: number | undefined } = { id: undefined };
    let map: maplibregl.Map;
    const fail = (reason: string) => {
      if (failed) return;
      failed = true;
      if (timeout.id !== undefined) window.clearTimeout(timeout.id);
      setState("error");
      setMessage(reason);
    };

    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: activeMapStyle(),
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        attributionControl: false,
      });
    } catch {
      fail("The map could not start. No zone geometry is shown.");
      return;
    }

    mapRef.current = map;
    timeout.id = window.setTimeout(
      () => fail("The map did not become ready within 3 seconds. No zone geometry is shown."),
      MAP_READY_TIMEOUT_MS,
    );
    const onError = () => fail("The configured map style failed. No zone geometry is shown.");
    map.on("error", onError);
    map.once("load", () => {
      if (failed) return;
      try {
        applyThemeMapTint(map);
        const data = {
          type: "FeatureCollection" as const,
          features: zones.map((zone) => ({
            type: "Feature" as const,
            geometry: zone.geometry as unknown as ZoneGeometry,
            properties: { rank: zone.rank, name: zone.name },
          })),
        };
        map.addSource(ZONES_SOURCE, { type: "geojson", data });
        map.addLayer({
          id: `${ZONES_SOURCE}-fill`,
          type: "fill",
          source: ZONES_SOURCE,
          paint: {
            "fill-color": "#ffa62b",
            "fill-opacity": 0.22,
            "fill-outline-color": "#ffd68c",
          },
        });
        map.addLayer({
          id: `${ZONES_SOURCE}-line`,
          type: "line",
          source: ZONES_SOURCE,
          paint: { "line-color": "#ffa62b", "line-width": 3 },
        });
        const bounds = zones
          .map((zone) => geometryBounds(zone.geometry as unknown as ZoneGeometry))
          .reduce(([w1, s1, e1, n1], [w2, s2, e2, n2]) => [
            Math.min(w1, w2),
            Math.min(s1, s2),
            Math.max(e1, e2),
            Math.max(n1, n2),
          ]);
        map.fitBounds(bounds as [number, number, number, number], {
          padding: 70,
          duration: 0,
        });
        if (timeout.id !== undefined) window.clearTimeout(timeout.id);
        setState("ready");
        setMessage(
          `${zones.length} disclosure-cleared ranked zone${zones.length === 1 ? "" : "s"}`,
        );
      } catch {
        fail("The governed zone geometry could not be rendered. No zone geometry is shown.");
      }
    });

    return () => {
      if (timeout.id !== undefined) window.clearTimeout(timeout.id);
      map.off("error", onError);
      map.remove();
      mapRef.current = null;
    };
  }, [zones]);

  return (
    <Panel className="relative overflow-hidden" aria-label="Governed campaign zone map">
      <div
        ref={containerRef}
        className={state === "error" ? "hidden" : "h-[540px] w-full"}
        data-testid="governed-zone-map"
      />
      {state === "error" ? (
        <div role="alert" className="border-coral/40 bg-coral/10 m-5 rounded-lg border p-5">
          <p className="font-medium">Map unavailable</p>
          <p className="text-muted mt-2 text-sm">{message}</p>
        </div>
      ) : (
        <div
          role="status"
          className="micro bg-bg/90 absolute bottom-3 left-3 z-10 rounded-lg px-3 py-2 backdrop-blur"
        >
          <p className={state === "ready" ? "text-ink" : "text-muted"}>{message}</p>
          <p className="text-faint mt-1">
            {basemapMode() === "local"
              ? "Local schematic background · no production basemap configured"
              : "Configured basemap · production licence remains an external release gate"}
          </p>
        </div>
      )}
    </Panel>
  );
}
