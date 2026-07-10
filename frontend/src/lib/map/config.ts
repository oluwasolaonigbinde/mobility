/**
 * Map configuration.
 *
 * Style is env-configurable so the tile provider can be swapped without a
 * code change (MapTiler/Mapbox key, self-hosted OpenFreeMap, …).
 * Default: Carto dark-matter — fits the Vantage dark theme; attribution
 * is rendered by MapLibre from the style's metadata.
 *
 * ⚠ Go-live: confirm basemap licensing (see fablev1-work.md).
 */
export const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ??
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

/** Abuja, Federal Capital Territory — the network's flagship city. */
export const DEFAULT_CENTER: [number, number] = [7.4913, 9.0643];
export const DEFAULT_ZOOM = 11;

export const ZONE_COLORS = {
  target: "#ffa62b", // amber
  bonus: "#34e5d0", // cyan
  exclusion: "#ff5c5c", // coral
} as const satisfies Record<string, string>;
