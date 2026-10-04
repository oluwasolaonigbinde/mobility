"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { activeMapStyle, basemapMode, DEFAULT_CENTER, DEFAULT_ZOOM } from "@/lib/map/config";
import { geometryBounds, validateZoneGeometry, type ZoneGeometry } from "@/lib/zones/geometry";
import { Panel } from "@/components/ui/panel";

export type GovernedZoneGeometry = {
  rank: number;
  name: string;
  geometry: Record<string, unknown>;
};

const ZONES_SOURCE = "governed-ranked-zones";
export const MAP_READY_TIMEOUT_MS = 3_000;

export function GovernedZoneMap({ zones }: { zones: GovernedZoneGeometry[] }) {
  if (!zones.length || zones.some((zone) => !validateZoneGeometry(zone.geometry).ok)) {
    return (
      <Panel role="status" className="p-5">
        Campaign areas are unavailable.
      </Panel>
    );
  }
  return basemapMode() === "local" ? <AreaMap zones={zones} /> : <ProviderZoneMap zones={zones} />;
}

function AreaMap({ zones }: { zones: GovernedZoneGeometry[] }) {
  const bounds = zones.map((zone) => geometryBounds(zone.geometry as unknown as ZoneGeometry));
  const west = Math.min(...bounds.map((b) => b[0]));
  const south = Math.min(...bounds.map((b) => b[1]));
  const east = Math.max(...bounds.map((b) => b[2]));
  const north = Math.max(...bounds.map((b) => b[3]));
  const longitudeScale = Math.cos((((south + north) / 2) * Math.PI) / 180);
  const scale = Math.min(
    620 / Math.max((east - west) * longitudeScale, 0.00001),
    300 / Math.max(north - south, 0.00001),
  );
  const x = (lon: number) => 360 + (lon - (west + east) / 2) * longitudeScale * scale;
  const y = (lat: number) => 210 - (lat - (south + north) / 2) * scale;
  return (
    <Panel className="overflow-hidden" aria-label="Campaign area map">
      <svg
        viewBox="0 0 720 420"
        className="bg-raised h-auto w-full"
        role="img"
        aria-label="Campaign areas by estimated ad exposure"
      >
        {zones.map((zone, index) => {
          const geometry = zone.geometry as unknown as ZoneGeometry;
          const polygons =
            geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
          const b = bounds[index]!;
          const path = polygons
            .map((polygon) =>
              polygon
                .map(
                  (ring) =>
                    ring.map(([lon, lat], i) => `${i ? "L" : "M"}${x(lon)},${y(lat)}`).join(" ") +
                    " Z",
                )
                .join(" "),
            )
            .join(" ");
          return (
            <g key={zone.rank}>
              <path
                d={path}
                fill="var(--color-amber)"
                fillOpacity="0.24"
                stroke="var(--color-amber)"
                strokeWidth="3"
                fillRule="evenodd"
              >
                <title>{`${zone.rank}. ${zone.name}`}</title>
              </path>
              <text
                x={x((b[0] + b[2]) / 2)}
                y={y((b[1] + b[3]) / 2)}
                textAnchor="middle"
                fill="var(--color-ink)"
                stroke="var(--color-bg)"
                strokeWidth="4"
                paintOrder="stroke"
                fontSize="22"
                fontWeight="600"
              >
                {zone.name}
              </text>
            </g>
          );
        })}
      </svg>
      <ol className="text-muted flex flex-wrap gap-x-5 gap-y-2 p-4 text-sm" aria-label="Map areas">
        {zones.map((zone) => (
          <li key={zone.rank}>
            {zone.rank}. {zone.name}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function ProviderZoneMap({ zones }: { zones: GovernedZoneGeometry[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("Preparing your campaign map…");

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let failed = false;
    const timeout: { id: number | undefined } = { id: undefined };
    let map: MapLibreMap;
    const fail = (reason: string) => {
      if (failed) return;
      failed = true;
      if (timeout.id !== undefined) window.clearTimeout(timeout.id);
      setState("error");
      setMessage(reason);
    };

    try {
      map = new MapLibreMap({
        container: containerRef.current,
        style: activeMapStyle(),
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        attributionControl: { compact: true },
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
        zones.forEach((zone) => {
          const [w, south, e, north] = geometryBounds(zone.geometry as unknown as ZoneGeometry);
          const label = document.createElement("span");
          label.textContent = zone.name;
          label.className = "bg-bg text-ink rounded px-2 py-1 text-xs font-medium";
          new Marker({ element: label }).setLngLat([(w + e) / 2, (south + north) / 2]).addTo(map);
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
        setMessage(`${zones.length} campaign area${zones.length === 1 ? "" : "s"}`);
      } catch {
        fail("The campaign areas could not be drawn. Please try again.");
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
    <Panel className="relative overflow-hidden" aria-label="Campaign area map">
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
        </div>
      )}
    </Panel>
  );
}
