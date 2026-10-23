"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { activeMapStyle, DEFAULT_CENTER, zoneColors } from "@/lib/map/config";
import { geometryBounds, validateZoneGeometry, type ZoneGeometry } from "@/lib/zones/geometry";
import { AreaGraphic } from "./area-graphic";

type Area = { id: string; name: string; geometry: unknown; zone_type?: string };
export type MapPosition = { longitude: number; latitude: number };

/** Current snapshot only. Prop changes replace the entire map; no trail or marker identity. */
export function CampaignMap({
  areas,
  positions = [],
}: {
  areas: Area[];
  positions?: MapPosition[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    const element = container.current;
    let map: MapLibreMap | undefined;
    let observer: ResizeObserver | undefined;
    let disposed = false;
    try {
      const valid = areas.filter((area) => validateZoneGeometry(area.geometry).ok);
      map = new MapLibreMap({
        container: container.current,
        style: activeMapStyle(),
        center: DEFAULT_CENTER,
        zoom: 11,
        interactive: false,
        attributionControl: {},
      });
      const instance = map;
      map.on("error", () => setFailed(true));
      map.on("load", () => {
        instance.resize();
        const colors = zoneColors();
        instance.addSource("areas", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: valid.map((area) => ({
              type: "Feature",
              properties: { exclusion: area.zone_type === "exclusion" },
              geometry: area.geometry as unknown as ZoneGeometry,
            })),
          },
        });
        instance.addLayer({
          id: "area-fill",
          type: "fill",
          source: "areas",
          paint: {
            "fill-color": ["case", ["get", "exclusion"], colors.exclusion, colors.target],
            "fill-opacity": 0.16,
          },
        });
        instance.addLayer({
          id: "area-line",
          type: "line",
          source: "areas",
          paint: {
            "line-color": ["case", ["get", "exclusion"], colors.exclusion, colors.target],
            "line-width": 2,
          },
        });
        if (valid.some((area) => area.zone_type === "exclusion")) {
          const data = new Uint8Array(8 * 8 * 4);
          for (let y = 0; y < 8; y++)
            for (let x = 0; x < 8; x++) {
              if ((x + y) % 8 < 2) data.set([176, 32, 48, 150], (y * 8 + x) * 4);
            }
          instance.addImage("avoid-hatch", { width: 8, height: 8, data });
          instance.addLayer({
            id: "avoid-hatch",
            type: "fill",
            source: "areas",
            filter: ["==", ["get", "exclusion"], true],
            paint: { "fill-pattern": "avoid-hatch" },
          });
        }
        instance.addSource("driving", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: positions.map((point) => ({
              type: "Feature",
              properties: {},
              geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
            })),
          },
        });
        instance.addLayer({
          id: "anonymous-dots",
          type: "circle",
          source: "driving",
          paint: {
            "circle-radius": 6,
            "circle-color": colors.target,
            "circle-stroke-width": 3,
            "circle-stroke-color": "#ffffff",
          },
        });
        const fit = () => {
          if (disposed) return;
          instance.resize();
          if (!valid.length) return;
          const bounds = valid.map((area) =>
            geometryBounds(area.geometry as unknown as ZoneGeometry),
          );
          instance.fitBounds(
            [
              [Math.min(...bounds.map((b) => b[0])), Math.min(...bounds.map((b) => b[1]))],
              [Math.max(...bounds.map((b) => b[2])), Math.max(...bounds.map((b) => b[3]))],
            ],
            { padding: 24, maxZoom: 14, duration: 0 },
          );
        };
        fit();
        observer = new ResizeObserver(fit);
        observer.observe(element);
        setFailed(false);
      });
    } catch {
      // A real geometry picture remains available when WebGL or the provider fails.
      queueMicrotask(() => {
        if (!disposed) setFailed(true);
      });
    }
    return () => {
      disposed = true;
      observer?.disconnect();
      map?.remove();
    };
  }, [areas, positions]);
  return (
    <div
      className="flex h-full min-h-0 flex-col"
      role="img"
      aria-label={`Campaign map${areas.length ? ` for ${areas.map((area) => area.name).join(", ")}` : ""}${positions.length ? ` with ${positions.length} anonymous driving dots` : ""}`}
    >
      <div className="relative min-h-0 flex-1">
        <div
          ref={container}
          style={{ position: "absolute", inset: 0 }}
          className={failed ? "invisible" : ""}
        />
        {failed ? <AreaGraphic areas={areas} positions={positions} /> : null}
        {!areas.length ? (
          <p className="bg-raised absolute inset-0 grid place-items-center p-5 text-center">
            No campaign areas chosen yet.
          </p>
        ) : null}
      </div>
      {failed ? (
        <p className="bg-white px-3 py-2 text-xs">Map unavailable · campaign areas shown</p>
      ) : null}
      {areas.some((area) => area.zone_type === "exclusion") ? (
        <p className="border-edge shrink-0 border-t bg-white px-3 py-2 text-xs">
          Green: where to drive · Hatched red: avoid
        </p>
      ) : null}
    </div>
  );
}
