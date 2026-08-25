"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import type { components } from "@/lib/api/schema";
import {
  activeMapStyleUrl,
  applyThemeMapTint,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
  ZONE_COLOR_VARS,
  zoneColors,
} from "@/lib/map/config";
import { geometryBounds, type ZoneGeometry } from "@/lib/zones/geometry";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { StatusChip } from "@/components/ui/status-chip";
import { createZoneAction, updateZoneAction, deleteZoneAction } from "./actions";
import { cx } from "@/lib/cx";

type Zone = components["schemas"]["CampaignZoneRead"];
type ZoneType = components["schemas"]["CampaignZoneType"];

const ZONE_TYPE_META: Record<
  ZoneType,
  { label: string; tone: "amber" | "cyan" | "coral"; hint: string }
> = {
  target: { label: "Target", tone: "amber", hint: "Pay premium driver time here" },
  bonus: { label: "Bonus", tone: "cyan", hint: "Extra driver incentive" },
  exclusion: { label: "Exclusion", tone: "coral", hint: "Never count modelled contacts here" },
};

const SOURCE_ID = "campaign-zones";

function zonesToFeatureCollection(zones: Zone[]) {
  return {
    type: "FeatureCollection" as const,
    features: zones.map((z) => ({
      type: "Feature" as const,
      properties: { id: z.id, zone_type: z.zone_type, name: z.name },
      geometry: z.geometry as unknown as ZoneGeometry,
    })),
  };
}

export function ZonesEditor({ campaignId, zones }: { campaignId: string; zones: Zone[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [pendingGeometry, setPendingGeometry] = useState<ZoneGeometry | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [saving, startTransition] = useTransition();

  // --- map lifecycle -------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: activeMapStyleUrl(),
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    applyThemeMapTint(map);
    mapRef.current = map;

    // Terra Draw needs the style fully loaded before it can attach layers.
    map.on("load", () => {
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [new TerraDrawPolygonMode()],
      });
      draw.start();
      draw.setMode("static");
      drawRef.current = draw;

      draw.on("finish", (id) => {
        const snapshot = draw.getSnapshot();
        const feature = snapshot.find((f) => f.id === id);
        if (feature && feature.geometry.type === "Polygon") {
          setPendingGeometry(feature.geometry as ZoneGeometry);
          setDrawing(false);
          draw.setMode("static");
        }
      });

      setMapReady(true);
    });

    return () => {
      drawRef.current?.stop();
      drawRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- render zones as colored fills --------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const data = zonesToFeatureCollection(zones);
    const existing = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(data);
      return;
    }

    const zc = zoneColors();
    map.addSource(SOURCE_ID, { type: "geojson", data });
    map.addLayer({
      id: `${SOURCE_ID}-fill`,
      type: "fill",
      source: SOURCE_ID,
      paint: {
        "fill-color": [
          "match",
          ["get", "zone_type"],
          "target",
          zc.target,
          "bonus",
          zc.bonus,
          "exclusion",
          zc.exclusion,
          zc.neutral,
        ],
        "fill-opacity": 0.22,
      },
    });
    map.addLayer({
      id: `${SOURCE_ID}-line`,
      type: "line",
      source: SOURCE_ID,
      paint: {
        "line-color": [
          "match",
          ["get", "zone_type"],
          "target",
          zc.target,
          "bonus",
          zc.bonus,
          "exclusion",
          zc.exclusion,
          zc.neutral,
        ],
        "line-width": 1.5,
      },
    });
    map.on("click", `${SOURCE_ID}-fill`, (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) setSelectedId(id);
    });
    map.on("mouseenter", `${SOURCE_ID}-fill`, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", `${SOURCE_ID}-fill`, () => (map.getCanvas().style.cursor = ""));
  }, [zones, mapReady]);

  // Fit to existing zones once on load
  const fittedRef = useRef(false);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || fittedRef.current || zones.length === 0) return;
    fittedRef.current = true;
    const bounds = zones
      .map((z) => geometryBounds(z.geometry as unknown as ZoneGeometry))
      .reduce(([w1, s1, e1, n1], [w2, s2, e2, n2]) => [
        Math.min(w1, w2),
        Math.min(s1, s2),
        Math.max(e1, e2),
        Math.max(n1, n2),
      ]);
    map.fitBounds(bounds as [number, number, number, number], { padding: 60, duration: 0 });
  }, [zones, mapReady]);

  // --- interactions --------------------------------------------------------
  function startDrawing() {
    setError(undefined);
    setPendingGeometry(null);
    setDrawing(true);
    drawRef.current?.setMode("polygon");
  }

  function cancelDrawing() {
    setDrawing(false);
    setPendingGeometry(null);
    drawRef.current?.setMode("static");
    drawRef.current?.clear();
  }

  const zoomToZone = useCallback((zone: Zone) => {
    const map = mapRef.current;
    if (!map) return;
    map.fitBounds(geometryBounds(zone.geometry as unknown as ZoneGeometry), {
      padding: 80,
      duration: 500,
    });
  }, []);

  function saveNewZone(formData: FormData) {
    if (!pendingGeometry) return;
    const name = String(formData.get("name") ?? "").trim();
    const zoneType = String(formData.get("zone_type") ?? "target") as ZoneType;
    setError(undefined);
    startTransition(async () => {
      const result = await createZoneAction({
        campaignId,
        name,
        zoneType,
        geometry: pendingGeometry,
      });
      if (result.error) {
        setError(result.error);
      } else {
        setPendingGeometry(null);
        drawRef.current?.clear();
      }
    });
  }

  function saveZoneEdit(zone: Zone, formData: FormData) {
    const name = String(formData.get("name") ?? "").trim();
    const zoneType = String(formData.get("zone_type") ?? zone.zone_type) as ZoneType;
    setError(undefined);
    startTransition(async () => {
      const result = await updateZoneAction({ campaignId, zoneId: zone.id, name, zoneType });
      if (result.error) setError(result.error);
      else setEditingId(null);
    });
  }

  function removeZone(zone: Zone) {
    if (!window.confirm(`Delete zone "${zone.name}"? This cannot be undone.`)) return;
    setError(undefined);
    startTransition(async () => {
      const result = await deleteZoneAction({ campaignId, zoneId: zone.id });
      if (result.error) setError(result.error);
    });
  }

  const typeFields = (defaults?: Zone) => (
    <div className="flex gap-2" role="radiogroup" aria-label="Zone type">
      {(Object.keys(ZONE_TYPE_META) as ZoneType[]).map((t) => (
        <label
          key={t}
          className="border-edge bg-raised hover:border-edge-strong has-checked:border-amber/60 has-checked:bg-amber/10 flex-1 cursor-pointer rounded-lg border p-2.5 transition-colors"
        >
          <input
            type="radio"
            name="zone_type"
            value={t}
            defaultChecked={(defaults?.zone_type ?? "target") === t}
            className="sr-only"
          />
          <span className="block text-xs font-medium">{ZONE_TYPE_META[t].label}</span>
          <span className="micro text-faint mt-0.5 block">{ZONE_TYPE_META[t].hint}</span>
        </label>
      ))}
    </div>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {/* Map */}
      <Panel className="relative overflow-hidden lg:col-span-2">
        <div ref={containerRef} className="h-[520px] w-full" data-testid="zones-map" />
        <div className="absolute top-3 left-3 z-10 flex gap-2">
          {!drawing && !pendingGeometry ? (
            <Button type="button" onClick={startDrawing} className="!h-9 !px-4 !text-xs">
              ✏ Draw zone
            </Button>
          ) : drawing ? (
            <>
              <span className="micro bg-bg/85 text-amber rounded-lg px-3 py-2 backdrop-blur">
                Click to add points · click the first point to close
              </span>
              <Button
                type="button"
                variant="ghost"
                onClick={cancelDrawing}
                className="!h-9 !px-3 !text-xs"
              >
                Cancel
              </Button>
            </>
          ) : null}
        </div>
        {/* Legend */}
        <div className="micro bg-bg/85 absolute bottom-3 left-3 z-10 flex gap-3 rounded-lg px-3 py-2 backdrop-blur">
          {(Object.keys(ZONE_TYPE_META) as ZoneType[]).map((t) => (
            <span key={t} className="flex items-center gap-1.5">
              <span
                className="inline-block size-2.5 rounded-sm"
                style={{ background: ZONE_COLOR_VARS[t] }}
                aria-hidden
              />
              {ZONE_TYPE_META[t].label}
            </span>
          ))}
        </div>
      </Panel>

      {/* Side panel */}
      <div className="flex flex-col gap-4">
        {pendingGeometry ? (
          <Panel className="border-amber/40 p-5">
            <h2 className="micro text-amber mb-3">New zone</h2>
            <form action={saveNewZone} className="flex flex-col gap-3">
              <input
                name="name"
                required
                placeholder="Zone name, e.g. Wuse II core"
                className="border-edge bg-raised text-ink placeholder:text-faint focus:border-amber h-10 rounded-lg border px-3 text-sm focus:outline-none"
              />
              {typeFields()}
              <div className="flex gap-2">
                <Button type="submit" disabled={saving} className="!h-10 flex-1 !text-xs">
                  {saving ? "Saving…" : "Save zone"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={cancelDrawing}
                  className="!h-10 !text-xs"
                >
                  Discard
                </Button>
              </div>
            </form>
          </Panel>
        ) : null}

        {error ? (
          <p
            role="alert"
            className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
          >
            {error}
          </p>
        ) : null}

        <Panel className="overflow-hidden">
          <div className="border-edge border-b px-5 py-3.5">
            <h2 className="micro text-muted">Zones · {zones.length}</h2>
          </div>
          {zones.length === 0 ? (
            <p className="text-muted px-5 py-8 text-center text-sm">
              No zones yet. Draw your first target zone on the map.
            </p>
          ) : (
            <ul className="divide-edge/60 max-h-[440px] divide-y overflow-y-auto">
              {zones.map((zone) => (
                <li
                  key={zone.id}
                  className={cx("px-5 py-3.5", selectedId === zone.id && "bg-raised/60")}
                >
                  {editingId === zone.id ? (
                    <form action={(fd) => saveZoneEdit(zone, fd)} className="flex flex-col gap-2.5">
                      <input
                        name="name"
                        defaultValue={zone.name}
                        required
                        className="border-edge bg-raised text-ink focus:border-amber h-9 rounded-lg border px-3 text-sm focus:outline-none"
                      />
                      {typeFields(zone)}
                      <div className="flex gap-2">
                        <Button type="submit" disabled={saving} className="!h-8 flex-1 !text-xs">
                          Save
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setEditingId(null)}
                          className="!h-8 !text-xs"
                        >
                          Cancel
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(zone.id);
                          zoomToZone(zone);
                        }}
                        className="min-w-0 text-left"
                      >
                        <span className="block truncate text-sm font-medium">{zone.name}</span>
                        <span className="micro text-faint mt-0.5 block">
                          {formatCount(Number(zone.area_sq_m) / 1e6)} km²
                        </span>
                      </button>
                      <div className="flex shrink-0 items-center gap-2">
                        <StatusChip tone={ZONE_TYPE_META[zone.zone_type].tone}>
                          {ZONE_TYPE_META[zone.zone_type].label}
                        </StatusChip>
                        <button
                          type="button"
                          onClick={() => setEditingId(zone.id)}
                          className="micro text-muted hover:text-ink"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => removeZone(zone)}
                          className="micro text-muted hover:text-coral"
                          aria-label={`Delete ${zone.name}`}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
