/**
 * Map configuration.
 *
 * Style is env-configurable so the tile provider can be swapped without a
 * code change (MapTiler/Mapbox key, self-hosted OpenFreeMap, …).
 * Default: Carto dark-matter — fits the Vantage dark theme; attribution
 * is rendered by MapLibre from the style's metadata.
 *
 * ⚠ Go-live: confirm basemap licensing (see docs/archive/fablev1-work.md).
 */
export const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ??
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const MAP_STYLE_URL_LIGHT =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL_LIGHT ??
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

/**
 * Basemap for the active theme: light themes (detected via the theme's
 * `color-scheme`) get Carto positron, dark themes keep dark-matter.
 * Resolved at map construction — an already-mounted map keeps its basemap
 * until remount, which is fine for the demo flow (flip theme, navigate).
 */
export function activeMapStyleUrl(): string {
  if (process.env.NEXT_PUBLIC_MAP_STYLE_URL) return MAP_STYLE_URL;
  if (typeof document !== "undefined") {
    const scheme = getComputedStyle(document.documentElement).colorScheme;
    if (scheme.includes("light")) return MAP_STYLE_URL_LIGHT;
  }
  return MAP_STYLE_URL;
}

/**
 * Blue Hour ships a navy-tinted basemap: stock dark tiles are graphite-black,
 * which reintroduces the exact "all black" the theme exists to escape — so on
 * style load we retint the base layers toward the theme's indigo ramp. Data
 * layers (heatmap, zones, markers) are untouched. No-op on other themes.
 */
export function applyThemeMapTint(map: import("maplibre-gl").Map) {
  if (typeof document === "undefined") return;
  if (document.documentElement.dataset.theme !== "blue-hour") return;
  let done = false;
  const retint = () => {
    if (done) return;
    const layers = map.getStyle()?.layers;
    if (!layers?.length) return;
    done = true;
    for (const layer of layers) {
      if (layer.type === "background") {
        map.setPaintProperty(layer.id, "background-color", "#1a2450");
      } else if (layer.type === "fill" && /water|ocean/i.test(layer.id)) {
        map.setPaintProperty(layer.id, "fill-color", "#101940");
      } else if (layer.type === "fill" && /land|park|green/i.test(layer.id)) {
        map.setPaintProperty(layer.id, "fill-color", "#202b5c");
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
