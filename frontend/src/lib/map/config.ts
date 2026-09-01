/**
 * Map configuration.
 *
 * Style is env-configurable so an approved provider can be supplied without a
 * code change. The default is a local, provider-neutral schematic background
 * with no network source.
 *
 * ⚠ Go-live: confirm basemap licensing (see docs/archive/fablev1-work.md).
 */
import type { StyleSpecification } from "maplibre-gl";

const LOCAL_SCHEMATIC_STYLE: StyleSpecification = {
  version: 8,
  name: "Cardvert local schematic",
  sources: {},
  layers: [
    {
      id: "local-background",
      type: "background",
      paint: { "background-color": "#151827" },
    },
  ],
};

/**
 * Resolved at map construction. An already-mounted map keeps its style until
 * remount; production provider configuration remains an external release gate.
 */
export function activeMapStyle(): string | StyleSpecification {
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL || LOCAL_SCHEMATIC_STYLE;
}

/** Compatibility for existing campaign-zone editing; the return may be an inline style. */
export function activeMapStyleUrl(): string | StyleSpecification {
  return activeMapStyle();
}

export function basemapMode(): "configured-provider" | "local" {
  return process.env.NEXT_PUBLIC_MAP_STYLE_URL ? "configured-provider" : "local";
}

/**
 * Themes whose ground is dark but not graphite retint the basemap: stock dark
 * tiles are graphite-black, which reintroduces the exact "all black" those
 * themes exist to escape. Data layers (heatmap, zones, markers) are untouched.
 */
const MAP_TINTS: Record<string, { background: string; water: string; land: string }> = {
  "blue-hour": { background: "#1a2450", water: "#101940", land: "#202b5c" },
  "terra-grain": { background: "#123309", water: "#06180d", land: "#173f10" },
};

/** Retints the base layers for the active theme. No-op on other themes. */
export function applyThemeMapTint(map: import("maplibre-gl").Map) {
  if (typeof document === "undefined") return;
  const tint = MAP_TINTS[document.documentElement.dataset.theme ?? ""];
  if (!tint) return;
  let done = false;
  const retint = () => {
    if (done) return;
    const layers = map.getStyle()?.layers;
    if (!layers?.length) return;
    done = true;
    for (const layer of layers) {
      if (layer.type === "background") {
        map.setPaintProperty(layer.id, "background-color", tint.background);
      } else if (layer.type === "fill" && /water|ocean/i.test(layer.id)) {
        map.setPaintProperty(layer.id, "fill-color", tint.water);
      } else if (layer.type === "fill" && /land|park|green/i.test(layer.id)) {
        map.setPaintProperty(layer.id, "fill-color", tint.land);
      }
    }
  };
  if (map.isStyleLoaded()) retint();
  else map.once("load", retint);
}

/** Abuja, Federal Capital Territory — the network's flagship city. */
export const DEFAULT_CENTER: [number, number] = [7.4913, 9.0643];
export const DEFAULT_ZOOM = 11;

export const ZONE_COLORS = {
  target: "#ffa62b", // amber
  bonus: "#34e5d0", // cyan
  exclusion: "#ff5c5c", // coral
} as const satisfies Record<string, string>;

/** CSS-var forms for DOM elements (legend chips) — track the active theme. */
export const ZONE_COLOR_VARS = {
  target: "var(--color-amber)",
  bonus: "var(--color-cyan)",
  exclusion: "var(--color-coral)",
} as const satisfies Record<keyof typeof ZONE_COLORS, string>;

/**
 * Theme-resolved zone colors for the MapLibre canvas (which cannot read CSS
 * variables). Falls back to the static palette during SSR.
 */
export function zoneColors(): Record<keyof typeof ZONE_COLORS, string> & { neutral: string } {
  const fallback = { ...ZONE_COLORS, neutral: "#8a90a0" };
  if (typeof document === "undefined") return fallback;
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fb: string) => styles.getPropertyValue(name).trim() || fb;
  return {
    target: read("--color-amber", fallback.target),
    bonus: read("--color-cyan", fallback.bonus),
    exclusion: read("--color-coral", fallback.exclusion),
    neutral: read("--color-muted", fallback.neutral),
  };
}
