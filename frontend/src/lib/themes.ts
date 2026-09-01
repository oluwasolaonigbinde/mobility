/**
 * Theme registry — one entry per selectable visual direction.
 *
 * Mechanics: every theme is a set of CSS custom-property overrides scoped to
 * `html[data-theme="<slug>"]` in globals.css. Components never branch on the
 * theme; they wear token classes and the variables re-map underneath them.
 * The default ("night") is the base :root token set and uses no attribute.
 */
export interface ThemeMeta {
  slug: string;
  name: string;
  tagline: string;
  colorScheme: "light" | "dark";
  /** Representative swatches for the switcher UI: [bg, panel, accent, secondary] */
  swatches: [string, string, string, string];
}

export const DEFAULT_THEME = "night";
export const THEME_STORAGE_KEY = "vantage-theme";

export const THEMES: ThemeMeta[] = [
  {
    slug: "night",
    name: "Direction 1",
    tagline: "",
    colorScheme: "dark",
    swatches: ["#0a0b0e", "#121419", "#ffa62b", "#34e5d0"],
  },
  {
    slug: "daylight-ops",
    name: "Direction 2",
    tagline: "",
    colorScheme: "light",
    swatches: ["#f3f5f8", "#ffffff", "#1e50d2", "#0f766e"],
  },
  {
    slug: "ivory-ledger",
    name: "Direction 3",
    tagline: "",
    colorScheme: "light",
    swatches: ["#efe9d8", "#fbf8f0", "#a63d17", "#1e5f5a"],
  },
  {
    slug: "blue-hour",
    name: "Direction 4",
    tagline: "",
    colorScheme: "dark",
    swatches: ["#161f47", "#1d2a58", "#ffb648", "#7ad1ff"],
  },
  {
    slug: "danfo",
    name: "Direction 5",
    tagline: "",
    colorScheme: "light",
    swatches: ["#f5f1e6", "#ffffff", "#f7c400", "#17150f"],
  },
  {
    slug: "hi-vis",
    name: "Direction 6",
    tagline: "",
    colorScheme: "light",
    swatches: ["#e7e5e0", "#f6f5f2", "#e04e00", "#1747d1"],
  },
  {
    slug: "terra-grain",
    name: "Direction 7",
    tagline: "",
    colorScheme: "dark",
    swatches: ["#071e03", "#0e2a09", "#f2c94c", "#c8f6d0"],
  },
  {
    slug: "coverage",
    name: "Direction 8",
    tagline: "",
    colorScheme: "light",
    swatches: ["#eef6ee", "#ffffff", "#256f1a", "#7a5230"],
  },
  {
    slug: "broadside",
    name: "Direction 9",
    tagline: "",
    colorScheme: "light",
    swatches: ["#efeee1", "#e4e2cf", "#9c352f", "#0b1f07"],
  },
];

export function applyTheme(slug: string) {
  const root = document.documentElement;
  if (slug === DEFAULT_THEME) {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = slug;
  }
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, slug);
  } catch {
    /* storage unavailable (private mode) — theme still applies for the session */
  }
}

export function currentTheme(): string {
  return document.documentElement.dataset.theme ?? DEFAULT_THEME;
}

/**
 * Inline boot script for the root layout: applies the persisted theme before
 * first paint so a non-default theme never flashes dark. Must stay ES5-safe
 * and self-contained (it is serialized into the HTML).
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t&&t!==${JSON.stringify(DEFAULT_THEME)})document.documentElement.dataset.theme=t;}catch(e){}})();`;
