"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { components } from "@/lib/api/schema";
import { MAP_STYLE_URL, DEFAULT_CENTER, DEFAULT_ZOOM, ZONE_COLORS } from "@/lib/map/config";
import { geometryBounds, type ZoneGeometry } from "@/lib/zones/geometry";
import { fetchHeatmapAction } from "./actions";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cx } from "@/lib/cx";

type Zone = components["schemas"]["CampaignZoneRead"];
type Heatmap = components["schemas"]["HeatmapFeatureCollection"];
type Metric = components["schemas"]["HeatmapMetric"];

const METRICS: Array<{ value: Metric; label: string; hint: string }> = [
  { value: "estimated_impressions", label: "Impressions", hint: "Estimated exposure per cell" },
  { value: "ping_count", label: "GPS pings", hint: "Raw verified positions" },
  { value: "trip_count", label: "Trips", hint: "Distinct trips through the cell" },
  { value: "distance_m", label: "Distance", hint: "Metres driven in the cell" },
];

/**
 * Sequential single-hue ramp (dataviz method): amber, monotonic lightness,
 * low cells recede via alpha, hot cells lift toward light. Values are
 * normalized to the current response's max weight; the legend shows the
 * real min→max so the ramp is honest per view.
 */
const RAMP: Array<[number, string]> = [
  [0.0, "rgba(255,166,43,0.10)"],
  [0.25, "rgba(255,166,43,0.30)"],
  [0.5, "rgba(255,166,43,0.55)"],
  [0.75, "rgba(255,178,72,0.75)"],
  [1.0, "rgba(255,214,140,0.92)"],
];

const HEAT_SOURCE = "heatmap-cells";
const ZONES_SOURCE = "zones-overlay";

function compact(n: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function HeatmapView({ campaignId, zones }: { campaignId: string; zones: Zone[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [metric, setMetric] = useState<Metric>("estimated_impressions");
  const [showZones, setShowZones] = useState(true);
  const [meta, setMeta] = useState<Heatmap["metadata"] | null>(null);
  const [range, setRange] = useState<{ min: number; max: number } | null>(null);
  const [cellCount, setCellCount] = useState<number | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [loading, startTransition] = useTransition();

  // --- map boot ------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    map.on("load", () => setMapReady(true));
    return () => {
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- zones overlay ---------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = {
      type: "FeatureCollection" as const,
      features: zones.map((z) => ({
        type: "Feature" as const,
        properties: { zone_type: z.zone_type },
        geometry: z.geometry as unknown as ZoneGeometry,
      })),
    };
    if (!map.getSource(ZONES_SOURCE)) {
      map.addSource(ZONES_SOURCE, { type: "geojson", data });
      map.addLayer({
        id: `${ZONES_SOURCE}-line`,
        type: "line",
        source: ZONES_SOURCE,
        paint: {
          "line-color": [
            "match",
            ["get", "zone_type"],
            "target",
            ZONE_COLORS.target,
            "bonus",
            ZONE_COLORS.bonus,
            "exclusion",
            ZONE_COLORS.exclusion,
            "#8a90a0",
          ],
          "line-width": 1.5,
          "line-dasharray": [2, 2],
        },
      });
    }
    map.setLayoutProperty(`${ZONES_SOURCE}-line`, "visibility", showZones ? "visible" : "none");
  }, [zones, mapReady, showZones]);

  // Fit to zones once (they mark the campaign's home turf)
  const fittedRef = useRef(false);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || fittedRef.current || zones.length === 0) return;
    fittedRef.current = true;
    const b = zones
      .map((z) => geometryBounds(z.geometry as unknown as ZoneGeometry))
      .reduce(([w1, s1, e1, n1], [w2, s2, e2, n2]) => [
        Math.min(w1, w2),
        Math.min(s1, s2),
        Math.max(e1, e2),
        Math.max(n1, n2),
      ]);
    map.fitBounds(b as [number, number, number, number], { padding: 80, duration: 0 });
  }, [zones, mapReady]);

  // --- heatmap load ----------------------------------------------------------
  const zonesBbox = useCallback((): string | null => {
    if (zones.length === 0) return null;
    const [w, s, e, n] = zones
      .map((z) => geometryBounds(z.geometry as unknown as ZoneGeometry))
      .reduce(([w1, s1, e1, n1], [w2, s2, e2, n2]) => [
        Math.min(w1, w2),
        Math.min(s1, s2),
        Math.max(e1, e2),
        Math.max(n1, n2),
      ]);
    // pad ~10% so edge cells aren't clipped
    const pw = (e - w) * 0.1;
    const ph = (n - s) * 0.1;
    return [w - pw, s - ph, e + pw, n + ph].map((v) => v.toFixed(5)).join(",");
  }, [zones]);

  const scan = useCallback(
    (bboxOverride?: string) => {
      const map = mapRef.current;
      if (!map) return;
      const b = map.getBounds();
      const bbox =
        bboxOverride ??
        [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((n) => n.toFixed(5)).join(",");
      setError(undefined);
      startTransition(async () => {
        const result = await fetchHeatmapAction({ campaignId, bbox, metric });
        if (result.error || !result.data) {
          setError(result.error ?? "No data returned");
          return;
        }
        const fc = result.data;
        const weights = fc.features.map((f) => Number(f.properties.weight));
        const max = weights.length ? Math.max(...weights) : 0;
        const min = weights.length ? Math.min(...weights) : 0;
        setMeta(fc.metadata);
        setRange(weights.length ? { min, max } : null);
        setCellCount(fc.features.length);

        const normalized = {
          type: "FeatureCollection" as const,
          features: fc.features.map((f) => ({
            ...f,
            properties: { ...f.properties, norm: max > 0 ? Number(f.properties.weight) / max : 0 },
          })),
        };
        const src = map.getSource(HEAT_SOURCE) as maplibregl.GeoJSONSource | undefined;
        if (src) {
          src.setData(normalized as never);
        } else {
          map.addSource(HEAT_SOURCE, { type: "geojson", data: normalized as never });
          map.addLayer(
            {
              id: `${HEAT_SOURCE}-fill`,
              type: "fill",
              source: HEAT_SOURCE,
              paint: {
                "fill-color": [
                  "interpolate",
                  ["linear"],
                  ["get", "norm"],
                  ...RAMP.flatMap(([stop, color]) => [stop, color] as const),
                ] as never,
                "fill-outline-color": "rgba(255,166,43,0.15)",
              },
            },
            map.getLayer(`${ZONES_SOURCE}-line`) ? `${ZONES_SOURCE}-line` : undefined,
          );
          // per-cell hover tooltip — the relief for low-contrast cool cells
          map.on("mousemove", `${HEAT_SOURCE}-fill`, (e) => {
            const f = e.features?.[0];
            if (!f) return;
            map.getCanvas().style.cursor = "crosshair";
            const p = f.properties as Record<string, string | number>;
            popupRef.current?.remove();
            popupRef.current = new maplibregl.Popup({
              closeButton: false,
              closeOnClick: false,
              className: "heatmap-popup",
            })
              .setLngLat(e.lngLat)
              .setHTML(
                `<div style="font-family:var(--font-mono);font-size:11px;line-height:1.7">` +
                  `<strong>${compact(Number(p.weight))}</strong> ${METRICS.find((m) => m.value === metric)?.label.toLowerCase()}<br/>` +
                  `${p.ping_count} pings · ${p.trip_count} trips · ${compact(Number(p.distance_m))} m` +
                  `</div>`,
              )
              .addTo(map);
          });
          map.on("mouseleave", `${HEAT_SOURCE}-fill`, () => {
            map.getCanvas().style.cursor = "";
            popupRef.current?.remove();
          });
        }
      });
    },
    [campaignId, metric],
  );

  // Initial + metric-change scan. The first scan targets the campaign's
  // zone bounds directly — deterministic regardless of camera/fit timing
  // (a headless race we hit in e2e). Manual rescans use the viewport.
  useEffect(() => {
    if (mapReady) scan(zonesBbox() ?? undefined);
  }, [mapReady, metric, scan, zonesBbox]);

  return (
    <div className="flex flex-col gap-4">
      {/* Controls — one row above the chart per the interaction spec */}
      <div className="flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Heatmap metric" className="flex gap-1">
          {METRICS.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={metric === m.value}
              title={m.hint}
              onClick={() => setMetric(m.value)}
              className={cx(
                "micro rounded-lg px-3 py-2 transition-colors",
                metric === m.value ? "bg-raised text-amber" : "text-muted hover:text-ink",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <label className="micro text-muted flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={showZones}
              onChange={(e) => setShowZones(e.target.checked)}
              className="accent-amber"
            />
            Zones
          </label>
          <Button
            type="button"
            onClick={() => scan()}
            disabled={loading}
            className="!h-9 !px-4 !text-xs"
          >
            {loading ? "Scanning…" : "⌖ Scan this view"}
          </Button>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {error}
        </p>
      ) : null}

      <Panel className="relative overflow-hidden">
        <div ref={containerRef} className="h-[540px] w-full" data-testid="heatmap-map" />
        {/* Legend: honest min→max for the current view */}
        <div className="micro bg-bg/85 absolute bottom-3 left-3 z-10 flex items-center gap-2 rounded-lg px-3 py-2 backdrop-blur">
          {range ? (
            <>
              <span className="text-faint">{compact(range.min)}</span>
              <span
                className="inline-block h-2.5 w-24 rounded-sm"
                style={{
                  background: `linear-gradient(90deg, ${RAMP.map(([s, c]) => `${c} ${s * 100}%`).join(", ")})`,
                }}
                aria-hidden
              />
              <span className="text-ink">{compact(range.max)}</span>
              <span className="text-faint">
                · {cellCount} cells · {meta?.resolution_m}m grid
              </span>
            </>
          ) : (
            <span className="text-faint">
              {loading ? "Scanning…" : "No movement data in this view — pan/zoom and rescan"}
            </span>
          )}
        </div>
      </Panel>
    </div>
  );
}
