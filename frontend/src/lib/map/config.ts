/**
 * Map configuration.
 *
 * Style is env-configurable so an approved provider can be supplied without a
 * code change. The default is a local, provider-neutral schematic background
 * with no network source.
 *
 * D44 selects MapTiler: NEXT_PUBLIC_MAP_STYLE_URL is its complete HTTPS style
 * URL with a domain-restricted public key, frozen into the frontend build.
 * Go-live provider/account/licence gates remain in docs/deployment-templates.md.
 */
import { setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import mapLibrePackage from "maplibre-gl/package.json";

// prebuild/predev copy both worker dependencies from this installed version.
// Keep the worker same-origin and independent of the page's current URL.
export const MAP_WORKER_URL = `/maplibre/${mapLibrePackage.version}/maplibre-gl-worker.mjs`;
if (typeof window !== "undefined") setWorkerUrl(MAP_WORKER_URL);

export const LOCAL_SCHEMATIC_STYLE: StyleSpecification = {
  version: 8,
  name: "Cardvert local schematic",
  sources: {},
  layers: [
    {
      id: "local-background",
      type: "background",
      paint: { "background-color": "#f3f7f1" },
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

/** Abuja, Federal Capital Territory — the network's flagship city. */
export const DEFAULT_CENTER: [number, number] = [7.4913, 9.0643];
export const DEFAULT_ZOOM = 11;

export const ZONE_COLORS = {
  target: "#256f1a", // accent
  exclusion: "#b02030", // danger
} as const satisfies Record<string, string>;

/** CSS-var forms for DOM elements (legend chips) — track the active theme. */
export const ZONE_COLOR_VARS = {
  target: "var(--color-amber)",
  exclusion: "var(--color-coral)",
} as const satisfies Record<keyof typeof ZONE_COLORS, string>;

/**
 * Theme-resolved zone colors for the MapLibre canvas (which cannot read CSS
 * variables). Falls back to the static palette during SSR.
 */
export function zoneColors(): Record<keyof typeof ZONE_COLORS, string> & { neutral: string } {
  const fallback = { ...ZONE_COLORS, neutral: "#46543f" };
  if (typeof document === "undefined") return fallback;
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fb: string) => styles.getPropertyValue(name).trim() || fb;
  return {
    target: read("--color-amber", fallback.target),
    exclusion: read("--color-coral", fallback.exclusion),
    neutral: read("--color-muted", fallback.neutral),
  };
}
